"""
Inspection Telemetry Service — bridge between phyphox/bearing analysis and health scoring.

Three responsibilities:
  1. Score vibration/condition data into a 0–100 inspection score
  2. Persist inspection records to asset_evidence
  3. Provide the latest score + age for the health rating calculator's additive modifier

ISO 10816 Class III thresholds (SA 50Hz context):
  Zone A (< 2.8 mm/s)  → good
  Zone B (2.8–7.1)     → acceptable
  Zone C/D (> 7.1)     → action required
"""

import logging
from datetime import datetime
from uuid import UUID

logger = logging.getLogger(__name__)


def _rms_ms2_to_velocity(rms_ms2: float, dominant_freq_hz: float | None, default_shaft_rpm: float = 1500.0) -> float:
    """Convert RMS acceleration (m/s²) to vibration velocity (mm/s).

    Uses dominant frequency or default shaft speed to convert.
    velocity_mm_s = (rms_ms2 * 1000) / (2 * pi * freq)
    """
    freq = dominant_freq_hz or (default_shaft_rpm / 60.0)
    if freq <= 0:
        return 0.0
    return (rms_ms2 * 1000.0) / (2 * 3.14159 * freq)


class InspectionTelemetryService:
    @staticmethod
    def score_from_phyphox(parsed_output: dict, analyzer_result: dict) -> float:
        """Convert phyphox + bearing analyzer output to a 0–100 inspection score.

        Args:
            parsed_output: Dict from PhyphoxParser.parse_export()
            analyzer_result: Dict from BearingAnalyzer.analyze()

        Returns:
            Float score clamped to [0, 100]
        """
        score = 100.0
        defect_detected = analyzer_result.get("defect_detected", False)
        defect_type = analyzer_result.get("defect_type")
        confidence = analyzer_result.get("confidence", 0.0)
        mechanical_fault = analyzer_result.get("mechanical_fault")
        rms_total = parsed_output.get("rms_total_ms2") or parsed_output.get("rms")
        peak_freqs = parsed_output.get("peak_frequencies_hz", [])
        dominant_freq = peak_freqs[0] if peak_freqs else None

        # Velocity from RMS
        velocity = _rms_ms2_to_velocity(rms_total or 0.0, dominant_freq)

        # Hard cap: ISO 10816 Zone C/D
        if velocity > 7.1:
            return 25.0

        # No defect path
        if not defect_detected and not mechanical_fault:
            if velocity < 2.8:
                return round(90.0 + (1.0 - velocity / 2.8) * 10.0, 1)  # 90–100
            else:
                return round(85.0 - (velocity - 2.8) / (7.1 - 2.8) * 15.0, 1)  # 70–85

        # Mechanical fault (imbalance / misalignment / looseness)
        if mechanical_fault:
            if confidence < 0.5:
                score = 65.0
            elif confidence < 0.8:
                score = 50.0
            else:
                score = 40.0

        # Bearing defect — takes lower score if also mechanical fault
        if defect_detected:
            if defect_type in ("outer_race", "inner_race"):
                if confidence < 0.6:
                    score = min(score, 45.0)
                else:
                    score = min(score, 30.0)
            elif defect_type in ("ball", "cage"):
                score = min(score, 35.0)
            else:
                score = min(score, 40.0)

        return round(max(0.0, min(100.0, score)), 1)

    @staticmethod
    def score_from_manual(noise_db: float | None, condition_rating: int, notes: str | None = None) -> float:
        """Score from manual technician entry.

        Args:
            noise_db: Optional dB reading
            condition_rating: 1–5 (1=critical, 5=excellent)
            notes: Optional human notes (stored but not scored)

        Returns:
            Float score clamped to [0, 100]
        """
        if condition_rating < 1 or condition_rating > 5:
            raise ValueError(f"condition_rating must be 1-5, got {condition_rating}")

        base = {1: 20.0, 2: 40.0, 3: 65.0, 4: 82.0, 5: 95.0}[condition_rating]
        modifier = 0.0

        if noise_db is not None:
            if noise_db > 95:
                modifier = -10.0
            elif noise_db >= 85:
                modifier = -5.0
            elif noise_db < 70:
                modifier = 5.0

        return round(max(0.0, min(100.0, base + modifier)), 1)

    @staticmethod
    def calculate_inspection_modifier(inspection_score: float | None, age_days: int | None) -> float:
        """Pure function: compute additive modifier from inspection score and age.

        Rules:
          - None or stale (>90 days) → 0.0 (no effect)
          - 60–90 days → 50% decay
          - Fresh → full modifier based on score band
        """
        if inspection_score is None or age_days is None:
            return 0.0
        if age_days > 90:
            return 0.0

        if inspection_score >= 85:
            modifier = 5.0
        elif inspection_score >= 70:
            modifier = 2.0
        elif inspection_score >= 55:
            modifier = 0.0
        elif inspection_score >= 40:
            modifier = -5.0
        elif inspection_score >= 25:
            modifier = -10.0
        else:
            modifier = -15.0

        if age_days > 60:
            modifier *= 0.5

        return modifier

    async def record_inspection(
        self,
        equipment_id: str,
        site_id: str,
        inspection_score: float,
        inspection_type: str,
        raw_payload: dict,
        normalized_payload: dict,
        inspected_by_user_id: str | None = None,
    ) -> str | None:
        """Persist inspection result to asset_evidence.

        Non-blocking — exceptions are logged, never raised.

        Returns:
            Evidence UUID string, or None on failure
        """
        try:
            from datetime import datetime
            from uuid import UUID

            from app.database.repositories.asset_evidence_repository import AssetEvidenceRepository
            from app.database.repositories.equipment_repository import EquipmentRepository
            from app.models.asset_evidence import (
                ArtifactType,
                CreateAssetEvidenceInput,
                EvidenceClass,
                ProvenanceType,
                SourceType,
            )

            eq_repo = EquipmentRepository()
            eq = eq_repo.get_by_code(equipment_id)
            if not eq:
                logger.warning(f"Inspection recording failed: equipment {equipment_id} not found")
                return None

            eq_uuid = UUID(eq["id"]) if isinstance(eq["id"], str) else eq["id"]
            site_uuid = UUID(site_id) if isinstance(site_id, str) and len(site_id) == 36 else None
            if site_uuid is None:
                site_resp = eq_repo.client.table("sites").select("id").eq("code", site_id).limit(1).execute()
                site_uuid = UUID(site_resp.data[0]["id"]) if site_resp.data else None
            if site_uuid is None:
                logger.warning(f"Inspection recording failed: site {site_id} not resolved")
                return None

            provenance = (
                ProvenanceType.USER_UPLOAD if inspection_type == "phyphox_upload" else ProvenanceType.MANUAL_ENTRY
            )

            payload = CreateAssetEvidenceInput(
                site_id=site_uuid,
                equipment_id=eq_uuid,
                source_type=SourceType.INSPECTION,
                artifact_type=ArtifactType.STRUCTURED_DATA,
                evidence_class=EvidenceClass.CONDITION_ASSESSMENT,
                event_timestamp=datetime.utcnow(),
                raw_payload=raw_payload,
                normalized_payload=normalized_payload,
                confidence_score=0.85 if inspection_type == "phyphox_upload" else 0.75,
                assessment_relevance=True,
                provenance_type=provenance,
                provenance_uri=f"inspection:{inspected_by_user_id or 'unknown'}:{inspection_type}",
                uploader_user_id=UUID(inspected_by_user_id)
                if inspected_by_user_id and len(inspected_by_user_id) == 36
                else None,
            )

            repo = AssetEvidenceRepository()
            evidence = await repo.create(payload)
            logger.info(
                f"Inspection evidence {evidence.evidence_id} recorded for {equipment_id} (score={inspection_score})"
            )
            return str(evidence.evidence_id)

        except Exception as e:
            logger.warning(f"Failed to record inspection for {equipment_id}: {e}")
            return None

    async def get_latest_inspection_score(self, equipment_id: str) -> tuple[float | None, int | None]:
        """Get the most recent inspection score and its age in days.

        Returns:
            (inspection_score, age_days) or (None, None) if no data or error.
        """
        try:
            from app.database.repositories.equipment_repository import EquipmentRepository

            eq_repo = EquipmentRepository()
            eq = eq_repo.get_by_code(equipment_id)
            if not eq:
                return None, None

            eq_uuid = eq["id"]
            if isinstance(eq_uuid, str) and len(eq_uuid) == 36:
                eq_uuid = UUID(eq_uuid)

            client = eq_repo.client
            if not client:
                return None, None

            result = (
                client.table("asset_evidence")
                .select("normalized_payload, event_timestamp")
                .eq("equipment_id", str(eq_uuid))
                .eq("evidence_class", "condition_assessment")
                .eq("source_type", "inspection")
                .order("event_timestamp", desc=True)
                .limit(1)
                .execute()
            )

            if not result.data:
                return None, None

            row = result.data[0]
            normalized = row.get("normalized_payload", {})
            if not isinstance(normalized, dict):
                return None, None

            insp_score = normalized.get("inspection_score")
            if insp_score is None:
                return None, None

            ts = row.get("event_timestamp")
            if ts:
                age = (datetime.utcnow() - datetime.fromisoformat(ts.replace("Z", "+00:00"))).days
            else:
                age = None

            return float(insp_score), age

        except Exception as e:
            logger.debug(f"Failed to get latest inspection score for {equipment_id}: {e}")
            return None, None

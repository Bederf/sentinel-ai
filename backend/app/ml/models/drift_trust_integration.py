"""Drift Verdict → Trust Delta Mapping

Maps drift detection verdicts to trust confidence penalties and generates findings
for operator visibility. Integration point between Phase 240 drift detection and
Phase 238 readiness orchestrator.

Phase 240 M2.3: Drift→Trust Causality
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger("sentinel.drift_trust_integration")


@dataclass
class DriftFinding:
    """Single equipment drift finding for readiness response."""

    equipment_id: str
    equipment_type: str
    drift_verdict: str
    drift_score: float | None = None
    severity: str = "low"  # low, medium, high


def drift_verdict_to_penalty(verdict: str) -> float:
    """Map drift verdict to trust penalty.

    Maps Phase 240 drift verdicts to trust confidence penalties per the
    trust formula: trust_confidence = base_trust × (1.0 - drift_penalty)

    Args:
        verdict: One of 'UNEVALUABLE', 'FEATURE_MISMATCH', 'DRIFT_DETECTED',
                 'NO_DRIFT_DETECTED', or 'INSUFFICIENT_DATA'

    Returns:
        Penalty value (0.0 to 0.5):
        - UNEVALUABLE: -0.5 (data quality uncertain, cannot trust)
        - FEATURE_MISMATCH: -0.3 (schema mismatch, baseline invalid)
        - DRIFT_DETECTED: -0.2 (model degrading)
        - NO_DRIFT_DETECTED: +0.05 (confidence boost)
        - INSUFFICIENT_DATA: -0.5 (fail-closed, cannot evaluate)
    """
    verdict_lower = (verdict or "").upper().strip()

    penalty_map = {
        "UNEVALUABLE": -0.5,
        "FEATURE_MISMATCH": -0.3,
        "DRIFT_DETECTED": -0.2,
        "NO_DRIFT_DETECTED": 0.05,
        "INSUFFICIENT_DATA": -0.5,
    }

    return penalty_map.get(verdict_lower, -0.5)  # Default: fail-closed


def compute_drift_penalty_for_site(site_id: str, equipment_verdicts: dict[str, str]) -> float:
    """Compute max drift penalty across all equipment at a site.

    Takes the worst (most negative) penalty across all equipment verdicts,
    ensuring that one drifting unit can lower the entire site's trust.

    Args:
        site_id: Site identifier (for logging)
        equipment_verdicts: Dict mapping equipment_type → verdict string
                           (e.g., {"chiller": "DRIFT_DETECTED", "ahu": "NO_DRIFT_DETECTED"})

    Returns:
        Maximum penalty (most negative), representing the site's worst-case drift.
    """
    if not equipment_verdicts:
        return 0.0  # No equipment evaluated = no drift penalty

    penalties = [drift_verdict_to_penalty(verdict) for verdict in equipment_verdicts.values()]
    max_penalty = max(penalties) if penalties else 0.0

    logger.debug(
        "[DRIFT→TRUST] Site %s: equipment_verdicts=%s, penalties=%s, max_penalty=%s",
        site_id,
        equipment_verdicts,
        penalties,
        max_penalty,
    )

    return max_penalty


def compute_trust_confidence(base_trust: float, drift_penalty: float) -> float:
    """Compute trust confidence using the Phase 240 formula.

    trust_confidence = base_trust × (1.0 - drift_penalty)

    Where:
    - base_trust = gates_passed / total_gates (from readiness evaluation)
    - drift_penalty = max(equipment_penalties) (from compute_drift_penalty_for_site)

    Args:
        base_trust: Base trust from gate evaluation (0.0 to 1.0)
        drift_penalty: Drift penalty from equipment verdicts (negative values)

    Returns:
        Trust confidence score (0.0 to 1.0)
    """
    # Ensure drift_penalty doesn't make formula negative
    # If drift_penalty is -0.5, then (1.0 - (-0.5)) = 1.5, so we can exceed 1.0
    # If drift_penalty is 0.05 (boost), then (1.0 - 0.05) = 0.95
    # Clamp final result to [0.0, 1.0]
    confidence = base_trust * (1.0 - drift_penalty)
    clamped = max(0.0, min(1.0, confidence))

    logger.debug(
        "[DRIFT→TRUST] trust_confidence: base_trust=%s, drift_penalty=%s, confidence=%s, clamped=%s",
        base_trust,
        drift_penalty,
        confidence,
        clamped,
    )

    return round(clamped, 4)


def create_findings_from_drift(
    site_id: str,
    equipment_verdicts: dict[str, tuple[str, str | None]],  # equipment_type → (verdict, equipment_id)
) -> list[dict]:
    """Generate operator-visible findings from drift verdicts.

    Creates findings for UNEVALUABLE and DRIFT_DETECTED verdicts, enabling
    operators to understand why trust changed.

    Args:
        site_id: Site identifier
        equipment_verdicts: Dict mapping equipment_type → (verdict, equipment_id)
                           e.g., {"chiller": ("DRIFT_DETECTED", "S002-CHILLER-B1-001")}

    Returns:
        List of finding dicts with keys: finding_type, equipment_type, equipment_id,
        severity, operator_review_required, reason
    """
    findings: list[dict] = []

    for equipment_type, (verdict, equipment_id) in equipment_verdicts.items():
        if verdict == "UNEVALUABLE":
            findings.append(
                {
                    "finding_type": "data_quality_uncertain",
                    "equipment_type": equipment_type,
                    "equipment_id": equipment_id or f"unknown_{equipment_type}",
                    "severity": "medium",
                    "operator_review_required": True,
                    "reason": "Drift evaluation data quality uncertain; operator review recommended",
                }
            )
        elif verdict == "FEATURE_MISMATCH":
            findings.append(
                {
                    "finding_type": "baseline_schema_mismatch",
                    "equipment_type": equipment_type,
                    "equipment_id": equipment_id or f"unknown_{equipment_type}",
                    "severity": "medium",
                    "operator_review_required": True,
                    "reason": "Feature schema mismatch; baseline model features changed",
                }
            )
        elif verdict == "DRIFT_DETECTED":
            findings.append(
                {
                    "finding_type": "model_degradation",
                    "equipment_type": equipment_type,
                    "equipment_id": equipment_id or f"unknown_{equipment_type}",
                    "severity": "high",
                    "operator_review_required": True,
                    "reason": "Model drift detected; model performance degrading",
                }
            )

    logger.info("[DRIFT→TRUST] Generated %d findings for site %s", len(findings), site_id)
    return findings


def extract_equipment_verdicts_from_db(
    site_id: str,
    equipment_types: list[str] | None = None,
) -> dict[str, tuple[str, str | None]]:
    """Query drift_detection_log for latest verdicts per equipment.

    Fetches the most recent drift verdict for each equipment type at a site,
    enabling gate evaluation and finding creation.

    Args:
        site_id: Site identifier
        equipment_types: Optional list of equipment types to query. If None,
                        queries all types: chiller, ahu, fcu, vav, generator, ups, pump

    Returns:
        Dict mapping equipment_type → (verdict, equipment_id)
        e.g., {"chiller": ("DRIFT_DETECTED", "S002-CHILLER-B1-001")}
    """
    if equipment_types is None:
        equipment_types = ["chiller", "ahu", "fcu", "vav", "generator", "ups", "pump"]

    verdicts: dict[str, tuple[str, str | None]] = {}

    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        if not client:
            logger.warning("[DRIFT→TRUST] Supabase client unavailable for site %s", site_id)
            return verdicts
    except Exception as e:
        logger.error("[DRIFT→TRUST] Failed to load Supabase client: %s", e)
        return verdicts

    for eq_type in equipment_types:
        try:
            # Query latest verdict per equipment type
            result = (
                client.table("drift_detection_log")
                .select("verdict, equipment_id")
                .eq("site_id", site_id)
                .eq("equipment_type", eq_type)
                .order("recorded_at", desc=True)
                .limit(1)
                .execute()
            )

            if result.data:
                row = result.data[0]
                verdict = row.get("verdict", "UNEVALUABLE")
                equipment_id = row.get("equipment_id")
                verdicts[eq_type] = (verdict, equipment_id)
                logger.debug(
                    "[DRIFT→TRUST] Site %s, %s: verdict=%s, equipment_id=%s",
                    site_id,
                    eq_type,
                    verdict,
                    equipment_id,
                )
            else:
                # No verdict found = cannot evaluate = UNEVALUABLE
                verdicts[eq_type] = ("UNEVALUABLE", None)
                logger.debug("[DRIFT→TRUST] Site %s, %s: no verdict found (UNEVALUABLE)", site_id, eq_type)

        except Exception as e:
            logger.warning("[DRIFT→TRUST] Failed to fetch verdict for %s/%s: %s", site_id, eq_type, e)
            verdicts[eq_type] = ("UNEVALUABLE", None)

    return verdicts

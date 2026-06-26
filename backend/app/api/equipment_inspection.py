"""API endpoints for equipment inspection telemetry.

POST /api/equipment/{equipment_id}/inspection/upload — phyphox file upload
POST /api/equipment/{equipment_id}/inspection/manual — manual technician entry
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.middleware.auth_middleware import require_auth
from app.models.auth import AuthContext, AuthLevel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/equipment", tags=["inspection"])


@router.post("/{equipment_id}/inspection/manual")
async def submit_manual_inspection(
    equipment_id: str,
    condition_rating: int = Form(..., ge=1, le=5, description="Equipment condition 1-5 (1=critical, 5=excellent)"),
    noise_db: float | None = Form(None, description="Optional noise reading in dB"),
    notes: str | None = Form(None, description="Technician notes"),
    auth: AuthContext = Depends(require_auth(AuthLevel.OPERATOR)),
) -> dict:
    """Submit a manual inspection observation for equipment.

    Args:
        equipment_id: Equipment code (e.g. S002-AHU-B1-001)
        condition_rating: 1-5 rating (1=critical, 5=excellent)
        noise_db: Optional decibel reading
        notes: Optional technician notes
    """
    try:
        from app.database.repositories.equipment_repository import EquipmentRepository
        from app.services.inspection_telemetry_service import InspectionTelemetryService

        # Verify equipment exists
        eq_repo = EquipmentRepository()
        eq = eq_repo.get_by_code(equipment_id)
        if not eq:
            raise HTTPException(status_code=404, detail=f"Equipment {equipment_id} not found")

        site_id = eq.get("site_id", "site-002")
        insp_svc = InspectionTelemetryService()

        score = insp_svc.score_from_manual(noise_db, condition_rating, notes)
        normalized = {
            "inspection_score": score,
            "inspection_type": "manual_entry",
            "condition_rating": condition_rating,
            "noise_db": noise_db,
            "inspected_at": datetime.utcnow().isoformat() + "Z",
        }
        raw = {"notes": notes, "condition_rating": condition_rating, "noise_db": noise_db}
        user_id = str(auth.user_id) if auth.user_id else None

        evidence_id = await insp_svc.record_inspection(
            equipment_id=equipment_id,
            site_id=site_id,
            inspection_score=score,
            inspection_type="manual_entry",
            raw_payload=raw,
            normalized_payload=normalized,
            inspected_by_user_id=user_id,
        )

        return {
            "equipment_id": equipment_id,
            "inspection_score": score,
            "condition_rating": condition_rating,
            "evidence_id": evidence_id,
            "message": "Inspection recorded",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Manual inspection failed for {equipment_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to record inspection")


@router.post("/{equipment_id}/inspection/upload")
async def upload_inspection_file(
    equipment_id: str,
    file: UploadFile = File(..., description="Phyphox CSV or JSON export"),
    auth: AuthContext = Depends(require_auth(AuthLevel.OPERATOR)),
) -> dict:
    """Upload a phyphox vibration export for analysis.

    Accepts CSV or JSON exports from the phyphox app.
    Runs bearing analysis and returns the computed inspection score.
    """
    try:
        from app.database.repositories.equipment_repository import EquipmentRepository
        from app.services.bearing_analyzer import BearingAnalyzer
        from app.services.inspection_telemetry_service import InspectionTelemetryService
        from app.services.phyphox_parser import PhyphoxParser

        # Verify equipment
        eq_repo = EquipmentRepository()
        eq = eq_repo.get_by_code(equipment_id)
        if not eq:
            raise HTTPException(status_code=404, detail=f"Equipment {equipment_id} not found")

        equipment_type = (eq.get("type") or "").lower()
        site_id = eq.get("site_id", "site-002")

        # Parse file
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="Empty file")

        parser = PhyphoxParser()
        try:
            parsed = parser.parse_export(data, file.filename or "export.csv")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"File parse error: {e}")

        # Run bearing analysis
        analyzer = BearingAnalyzer()
        result = analyzer.analyze(parsed, equipment_type=equipment_type)

        # Score
        insp_svc = InspectionTelemetryService()
        score = insp_svc.score_from_phyphox(parsed, result)

        normalized = {
            "inspection_score": score,
            "inspection_type": "phyphox_upload",
            "rms_total_ms2": parsed.get("rms_total_ms2") or parsed.get("rms"),
            "dominant_freq_hz": (parsed.get("peak_frequencies_hz") or [None])[0],
            "spectrum_shape": parsed.get("spectrum_shape"),
            "defect_detected": result.get("defect_detected"),
            "defect_type": result.get("defect_type"),
            "confidence": result.get("confidence"),
            "mechanical_fault": result.get("mechanical_fault"),
            "inspected_at": datetime.utcnow().isoformat() + "Z",
        }
        user_id = str(auth.user_id) if auth.user_id else None

        evidence_id = await insp_svc.record_inspection(
            equipment_id=equipment_id,
            site_id=site_id,
            inspection_score=score,
            inspection_type="phyphox_upload",
            raw_payload=parsed,
            normalized_payload=normalized,
            inspected_by_user_id=user_id,
        )

        return {
            "equipment_id": equipment_id,
            "inspection_score": score,
            "bearing_defect_detected": result.get("defect_detected", False),
            "bearing_defect_type": result.get("defect_type"),
            "mechanical_fault_type": result.get("mechanical_fault"),
            "confidence": result.get("confidence", 0.0),
            "evidence_id": evidence_id,
            "message": "Inspection recorded",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Inspection upload failed for {equipment_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to process inspection file")

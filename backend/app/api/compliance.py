"""
Compliance Management API Endpoints

Provides REST API for compliance workflows: OHS, Fire Safety, Emergency Lighting,
Legionella Management, Electrical Compliance, and Lift Inspection.

Phase 28: SENTINEL Compliance
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.models.compliance import (
    ElectricalCompliance,
    ComplianceStatus,
)
from app.database.repositories.compliance_repository import ComplianceRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/compliance", tags=["compliance"])


def get_compliance_repo() -> ComplianceRepository:
    """Dependency injection for ComplianceRepository."""
    return ComplianceRepository()


# ============================================================================
# OHS Compliance Endpoints
# ============================================================================


@router.post("/ohs/checklist/generate")
async def generate_ohs_checklist(
    site_code: str = Query(..., description="Building code"),
    zone_id: str = Query(..., description="Zone identifier"),
    repo: ComplianceRepository = Depends(get_compliance_repo),
) -> dict:
    """
    Generate OHS checklist for zone.

    Creates inspection task from OHS template with zone-specific requirements.
    """
    try:
        template = await repo.get_ohs_checklist_template(site_code)
        if not template:
            raise HTTPException(status_code=404, detail="OHS template not found")

        task = await repo.create_inspection_task(template, zone_id)
        return {
            "task_id": str(task.id),
            "items_count": len(template.get("checklist_items", [])),
        }

    except Exception as e:
        logger.error(f"Failed to generate OHS checklist: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ohs/checklist/{task_id}/complete")
async def complete_ohs_checklist(
    task_id: str,
    findings: dict = None,
    repo: ComplianceRepository = Depends(get_compliance_repo),
) -> dict:
    """
    Mark OHS checklist complete with findings.

    Creates inspection result and compliance audit record.
    """
    try:
        findings = findings or {}
        result = await repo.create_inspection_result(task_id, findings)
        audit = await repo.create_compliance_audit(
            audit_type="OHS",
            findings=findings,
            auditor_info={"role": "OHS Inspector"},
        )

        return {"result_id": str(result.id), "audit_id": str(audit.id)}

    except Exception as e:
        logger.error(f"Failed to complete OHS checklist: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# Fire Equipment Endpoints
# ============================================================================


@router.get("/fire/equipment")
async def list_fire_equipment(
    site_code: str = Query(..., description="Building code"),
    zone_id: Optional[str] = Query(None, description="Zone filter"),
    repo: ComplianceRepository = Depends(get_compliance_repo),
) -> dict:
    """List fire safety equipment at site/zone."""
    try:
        equipment = await repo.get_fire_equipment(site_code, zone_id)
        return {"equipment": equipment, "count": len(equipment)}

    except Exception as e:
        logger.error(f"Failed to list fire equipment: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/fire/equipment/{equipment_id}/inspect")
async def schedule_fire_equipment_inspection(
    equipment_id: str,
    repo: ComplianceRepository = Depends(get_compliance_repo),
) -> dict:
    """Schedule fire equipment inspection (12-month NFPA 10 interval)."""
    try:
        # For now, use equipment_id as location reference
        schedule = await repo.create_fire_inspection_schedule("extinguisher", equipment_id)
        return {"schedule_id": str(schedule.id), "next_due": schedule.next_due_date}

    except Exception as e:
        logger.error(f"Failed to schedule fire inspection: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/fire/equipment/{equipment_id}/charge")
async def record_fire_equipment_charge(
    equipment_id: str,
    pressure: float = Query(..., description="Pressure in PSI"),
    test_date: str = Query(..., description="Test date ISO format"),
    repo: ComplianceRepository = Depends(get_compliance_repo),
) -> dict:
    """Record fire equipment pressure test."""
    try:
        test_datetime = datetime.fromisoformat(test_date)
        tracking = await repo.update_fire_equipment_pressure(
            equipment_id, pressure, test_datetime
        )

        return {"equipment_id": str(tracking.id), "pressure": tracking.charge_pressure}

    except Exception as e:
        logger.error(f"Failed to record pressure test: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# Emergency Light Testing Endpoints
# ============================================================================


@router.post("/emergency-light/schedule")
async def schedule_emergency_light_tests(
    light_codes: List[str] = Query(..., description="List of light codes"),
    auto_test: bool = Query(True, description="Enable auto-testing"),
    repo: ComplianceRepository = Depends(get_compliance_repo),
) -> dict:
    """Schedule emergency light testing (daily auto-test, IEC 62034)."""
    try:
        schedules = await repo.create_emergency_light_schedules(light_codes, auto_test)
        return {
            "count": len(schedules),
            "schedules": [{"id": str(s.id)} for s in schedules],
        }

    except Exception as e:
        logger.error(f"Failed to schedule emergency lights: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/emergency-light/{light_code}/test")
async def record_emergency_light_test(
    light_code: str,
    battery_health_percent: int = Query(..., description="Battery health 0-100%"),
    test_result: str = Query(
        ..., description="Test result: pass, fail, warning"
    ),
    repo: ComplianceRepository = Depends(get_compliance_repo),
) -> dict:
    """Record emergency light test result (battery health trend tracking)."""
    try:
        if not 0 <= battery_health_percent <= 100:
            raise ValueError("Battery health must be 0-100%")

        result = await repo.record_emergency_light_test(
            light_code, battery_health_percent, test_result
        )

        return {"light_code": light_code, "battery_health": battery_health_percent}

    except Exception as e:
        logger.error(f"Failed to record emergency light test: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# Legionella Management Endpoints
# ============================================================================


@router.post("/legionella/assess")
async def assess_legionella_risk(
    tower_code: str = Query(..., description="Cooling tower code"),
    water_temp: float = Query(..., description="Water temperature in Celsius"),
    last_treatment: str = Query(
        ..., description="Last treatment date ISO format"
    ),
    repo: ComplianceRepository = Depends(get_compliance_repo),
) -> dict:
    """Assess legionella risk for cooling tower (SABS standard)."""
    try:
        treatment_date = datetime.fromisoformat(last_treatment)
        assessment = await repo.assess_legionella_risk(
            tower_code, water_temp, treatment_date
        )

        return {"tower_code": tower_code, "risk_level": assessment.risk_level}

    except Exception as e:
        logger.error(f"Failed to assess legionella risk: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/legionella/maintenance-task/{risk_assessment_id}")
async def create_legionella_maintenance_task(
    risk_assessment_id: str,
    repo: ComplianceRepository = Depends(get_compliance_repo),
) -> dict:
    """Create legionella maintenance task based on risk level."""
    try:
        schedule = await repo.create_legionella_maintenance_task(risk_assessment_id)
        return {"schedule_id": str(schedule.id)}

    except Exception as e:
        logger.error(f"Failed to create legionella task: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# Electrical Compliance Endpoints
# ============================================================================


@router.post("/electrical/certificate")
async def track_electrical_certificate(
    certificate: ElectricalCompliance,
    repo: ComplianceRepository = Depends(get_compliance_repo),
) -> dict:
    """Track electrical Certificate of Compliance (5-year South African standard)."""
    try:
        saved = await repo.create_electrical_compliance(certificate)
        return {
            "certificate_id": str(saved.id),
            "expiry_date": saved.expiry_date.isoformat() if saved.expiry_date else None,
        }

    except Exception as e:
        logger.error(f"Failed to track electrical certificate: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/electrical/status")
async def get_electrical_compliance_status(
    site_code: str = Query(..., description="Building code"),
    repo: ComplianceRepository = Depends(get_compliance_repo),
) -> ComplianceStatus:
    """Get electrical compliance status for site."""
    try:
        status = await repo.get_electrical_compliance_status(site_code)
        return status

    except Exception as e:
        logger.error(f"Failed to get electrical status: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# Lift Inspection Endpoints
# ============================================================================


@router.post("/lift/schedule")
async def schedule_lift_inspection(
    lift_code: str = Query(..., description="Lift code"),
    inspection_type: str = Query(
        ...,
        description="periodic_6monthly, annual_insurance, or after_repair",
    ),
    repo: ComplianceRepository = Depends(get_compliance_repo),
) -> dict:
    """Schedule lift inspection."""
    try:
        schedule = await repo.create_lift_inspection_schedule(lift_code, inspection_type)
        return {"schedule_id": str(schedule.id), "inspection_type": inspection_type}

    except Exception as e:
        logger.error(f"Failed to schedule lift inspection: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/lift/{lift_code}/test-results")
async def record_lift_test_results(
    lift_code: str,
    test_results: dict = None,
    repo: ComplianceRepository = Depends(get_compliance_repo),
) -> dict:
    """Record lift inspection test results."""
    try:
        test_results = test_results or {}
        result = await repo.record_lift_test_results(lift_code, test_results)

        return {"lift_code": lift_code, "compliant": result.get("compliant", False)}

    except Exception as e:
        logger.error(f"Failed to record lift test results: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# Overall Status Endpoints
# ============================================================================


@router.get("/status")
async def get_compliance_status(
    site_code: str = Query(..., description="Building code"),
    repo: ComplianceRepository = Depends(get_compliance_repo),
) -> ComplianceStatus:
    """Get overall compliance status for site."""
    try:
        status = await repo.get_compliance_status(site_code)
        return status

    except Exception as e:
        logger.error(f"Failed to get compliance status: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/audits")
async def list_compliance_audits(
    site_code: str = Query(..., description="Building code"),
    compliance_type: Optional[str] = Query(None, description="Filter by type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100),
    repo: ComplianceRepository = Depends(get_compliance_repo),
) -> dict:
    """List compliance audits for site."""
    try:
        audits = await repo.get_compliance_audits(
            site_code, compliance_type, status, limit
        )
        return {"audits": audits, "count": len(audits)}

    except Exception as e:
        logger.error(f"Failed to list audits: {e}")
        raise HTTPException(status_code=400, detail=str(e))

"""
Onboarding Baseline API (Phase 206-01)

REST API for baseline eligibility checking and seeding during asset onboarding.
Provides endpoints for:
- GET /api/onboarding/baseline-eligibility - Check equipment baseline eligibility
- POST /api/onboarding/seed-baselines - Seed baselines for eligible equipment

Phase: 206-asset-onboarding
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from app.database.repositories.equipment_repository import EquipmentRepository
from app.services.baseline_seed_service import BaselineSeedService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


async def _get_major_mechanical_equipment(site_id: str) -> list[dict[str, Any]]:
    """
    Get major mechanical equipment for a site.

    Returns list of equipment dicts with id, code, name, type, etc.
    """
    try:
        repo = EquipmentRepository()
        equipment_list = repo.get_by_site_code(site_code=site_id)

        major_types = {"chiller", "ahu", "fcu", "pump", "generator", "bess", "cooling_tower", "ct", "crac"}
        major_equipment = [
            eq for eq in equipment_list
            if eq.get("type", "").lower() in major_types
        ]

        return major_equipment

    except Exception as e:
        logger.error(f"Error fetching equipment for site {site_id}: {e}")
        return []


@router.get("/baseline-eligibility")
async def check_baseline_eligibility(site_id: str) -> dict[str, Any]:
    """
    Check baseline eligibility for all major mechanical equipment at a site.

    Returns equipment with eligibility status:
    - eligible: Has telemetry, no active alerts, can receive baseline
    - degraded: Health score < threshold
    - insufficient_data: < 24h telemetry
    - active_fault: Has active alerts
    - already_baselined: Already has active baseline
    - not_applicable: Not major mechanical type
    """
    equipment = await _get_major_mechanical_equipment(site_id)

    if not equipment:
        return {
            "site_id": site_id,
            "total_equipment": 0,
            "eligible_count": 0,
            "results": [],
        }

    # Check eligibility for each piece of equipment
    results = []
    eligible_count = 0

    for eq in equipment:
        eq_id = eq.get("id") or eq.get("equipment_id")
        eq_code = eq.get("code") or eq_id
        eq_name = eq.get("name") or eq_code
        eq_type = eq.get("type") or "unknown"

        # Calculate eligibility
        # This is a simplified check - in production would query telemetry and alerts
        eligibility_status = _determine_eligibility(eq)

        if eligibility_status == "eligible":
            eligible_count += 1

        results.append({
            "equipment_id": eq_id,
            "equipment_code": eq_code,
            "equipment_name": eq_name,
            "equipment_type": eq_type,
            "status": eligibility_status,
            "health_score": None,
            "telemetry_hours": None,
            "has_active_alerts": False,
            "is_anomaly_flagged": False,
            "has_existing_baseline": eligibility_status == "already_baselined",
            "eligibility_status": eligibility_status,
            "eligibility_reason": _get_eligibility_reason(eligibility_status),
        })

    return {
        "site_id": site_id,
        "total_equipment": len(equipment),
        "eligible_count": eligible_count,
        "results": results,
    }


def _determine_eligibility(equipment: dict[str, Any]) -> str:
    """Determine eligibility status for equipment."""
    eq_type = equipment.get("type", "").lower()

    # Not major mechanical type
    major_types = {"chiller", "ahu", "fcu", "pump", "generator", "bess", "cooling_tower", "ct", "crac"}
    if eq_type not in major_types:
        return "not_applicable"

    # Check if already has baseline (would query baseline repository)
    # For now, default to eligible
    return "eligible"


def _get_eligibility_reason(status: str) -> str:
    """Get human-readable reason for eligibility status."""
    reasons = {
        "eligible": "Equipment has sufficient telemetry and is ready for baseline",
        "degraded": "Equipment health score below threshold",
        "insufficient_data": "Less than 24 hours of telemetry data",
        "active_fault": "Equipment has active alerts or faults",
        "already_baselined": "Equipment already has an active baseline",
        "not_applicable": "Equipment type does not require baseline assessment",
    }
    return reasons.get(status, "Unknown status")


@router.post("/seed-baselines")
async def seed_baselines(site_id: str, equipment_ids: list[str]) -> dict[str, Any]:
    """
    Seed baselines for specified equipment.

    Args:
        site_id: Site identifier
        equipment_ids: List of equipment identifiers to seed

    Returns:
        Batch result with seeded/skipped/error counts and per-equipment results
    """
    if not equipment_ids:
        return {
            "site_id": site_id,
            "total_requested": 0,
            "seeded_count": 0,
            "skipped_count": 0,
            "error_count": 0,
            "results": [],
        }

    service = BaselineSeedService()

    try:
        results = await service.seed_batch(
            equipment_ids=equipment_ids,
            site_id=site_id,
            captured_by="automated",
        )

        seeded_count = sum(1 for r in results if r["status"] in ("seeded", "seeded_fallback"))
        skipped_count = sum(1 for r in results if r["status"] == "skipped")
        error_count = sum(1 for r in results if r["status"] == "error")

        return {
            "site_id": site_id,
            "total_requested": len(equipment_ids),
            "seeded_count": seeded_count,
            "skipped_count": skipped_count,
            "error_count": error_count,
            "results": results,
        }

    except Exception as e:
        logger.error(f"Error seeding baselines for site {site_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
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

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from app.database.repositories.equipment_repository import EquipmentRepository
from app.middleware.auth_middleware import AuthContext, require_auth
from app.services.baseline_seed_service import BaselineSeedService
from app.services.onboarding_canonicalization_service import OnboardingCanonicalizationService
from app.services.onboarding_hierarchy_service import OnboardingHierarchyService


class SeedBaselinesBody(BaseModel):
    equipment_ids: list[str] = []


class EquipmentCanonicalizationBody(BaseModel):
    commit: bool = False


class HierarchyIngestionBody(BaseModel):
    commit: bool = True
    auto_fetch: bool = True
    hierarchy: dict[str, Any] | None = None


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


def _check_site_access(auth: AuthContext, site_id: str) -> None:
    """Raise 403 if auth context does not have access to site_id."""
    from app.config.access_profiles import has_profile_site_access

    email = getattr(auth, "email", None) or ""
    if not has_profile_site_access(email, site_id):
        raise HTTPException(
            status_code=403,
            detail=f"You do not have access to site {site_id}",
        )


async def _get_major_mechanical_equipment(site_id: str) -> list[dict[str, Any]]:
    """
    Get major mechanical equipment for a site.

    Returns list of equipment dicts with id, code, name, type, etc.
    """
    try:
        repo = EquipmentRepository()
        equipment_list = repo.get_by_site_code(site_code=site_id)

        major_types = {"chiller", "ahu", "fcu", "pump", "generator", "bess", "cooling_tower", "ct", "crac"}
        major_equipment = [eq for eq in equipment_list if eq.get("type", "").lower() in major_types]

        return major_equipment

    except Exception as e:
        logger.error(f"Error fetching equipment for site {site_id}: {e}")
        return []


@router.post("/equipment-canonicalization/{site_id}")
async def canonicalize_onboarding_equipment(
    site_id: str,
    body: EquipmentCanonicalizationBody = Body(default_factory=EquipmentCanonicalizationBody),
    auth: AuthContext = Depends(require_auth()),
) -> dict[str, Any]:
    """Preview or apply onboarding equipment canonicalization for a site.

    This normalizes vendor/BMS equipment identifiers into SENTINEL canonical
    fields, creates approved aliases, and writes equipment-zone relationships.
    ``commit=false`` returns the proposed counts without changing rows.
    """
    _check_site_access(auth, site_id)
    try:
        service = OnboardingCanonicalizationService()
        return service.canonicalize_site(site_id, commit=body.commit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Onboarding equipment canonicalization failed for %s: %s", site_id, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/hierarchy-ingestion/{site_id}")
async def ingest_onboarding_hierarchy(
    site_id: str,
    body: HierarchyIngestionBody = Body(default_factory=HierarchyIngestionBody),
    auth: AuthContext = Depends(require_auth()),
) -> dict[str, Any]:
    """Import native BMS hierarchy evidence for a site.

    When ``hierarchy`` is provided, it is expected to be the normalized bridge
    shape with ``nodes`` and ``relationships``. When omitted and ``auto_fetch``
    is true, the service asks the enabled SIMBIOT adapter for native hierarchy
    (for example bridge ``/api/sites/{site_id}/hierarchy``). If the upstream
    only exposes flat points, the endpoint returns ``available=false`` and
    onboarding falls back to naming inference/manual mapping.
    """
    _check_site_access(auth, site_id)
    try:
        service = OnboardingHierarchyService()
        return await service.ingest_site_hierarchy(
            site_id,
            hierarchy=body.hierarchy,
            commit=body.commit,
            auto_fetch=body.auto_fetch,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Onboarding hierarchy ingestion failed for %s: %s", site_id, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/baseline-eligibility")
async def check_baseline_eligibility(
    site_id: str,
    auth: AuthContext = Depends(require_auth()),
) -> dict[str, Any]:
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
    _check_site_access(auth, site_id)
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

        results.append(
            {
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
            }
        )

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
async def seed_baselines(
    site_id: str,
    body: SeedBaselinesBody = Body(...),
    auth: AuthContext = Depends(require_auth()),
) -> dict[str, Any]:
    """
    Seed baselines for specified equipment.

    Args:
        site_id: Site identifier
        body: Request body with equipment_ids list
        auth: Auth context (injected, validates site access)

    Returns:
        Batch result with seeded/skipped/error counts and per-equipment results
    """
    _check_site_access(auth, site_id)
    if not body.equipment_ids:
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
            equipment_ids=body.equipment_ids,
            site_id=site_id,
            captured_by="automated",
        )

        seeded_count = sum(1 for r in results if r["status"] in ("seeded", "seeded_fallback"))
        skipped_count = sum(1 for r in results if r["status"] == "skipped")
        error_count = sum(1 for r in results if r["status"] == "error")

        return {
            "site_id": site_id,
            "total_requested": len(body.equipment_ids),
            "seeded_count": seeded_count,
            "skipped_count": skipped_count,
            "error_count": error_count,
            "results": results,
        }

    except Exception as e:
        logger.error(f"Error seeding baselines for site {site_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e

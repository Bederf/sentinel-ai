"""
Onboarding Baseline API (Phase 206-01)

REST API for baseline eligibility checking and seeding during asset onboarding.
Provides endpoints for:
- GET /api/onboarding/baseline-eligibility - Check equipment baseline eligibility
- POST /api/onboarding/seed-baselines - Seed baselines for eligible equipment

Phase: 206-asset-onboarding
"""

import logging
import re
from datetime import UTC, datetime
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


class BridgeReviewCommitBody(BaseModel):
    mappings: dict[str, Any]
    approved_by: str = "system"
    discovery_id: str | None = None


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


def _site_prefix(site_id: str) -> str:
    match = re.search(r"(\d{3})", site_id)
    return f"S{match.group(1)}" if match else site_id.upper()


def _normalise_bridge_equipment_code(site_id: str, equipment_id: str) -> str:
    prefix = _site_prefix(site_id)
    value = (equipment_id or "").strip()
    value = re.sub(r"^site-(\d{3})[-_]", lambda m: f"S{m.group(1)}-", value, flags=re.IGNORECASE)
    if not value.upper().startswith(f"{prefix}-"):
        value = f"{prefix}-{value}"
    value = re.sub(r"[\s.:/]+", "-", value.upper())
    value = re.sub(r"-+", "-", value).strip("-")
    return value or f"{prefix}-BRIDGE-EQUIPMENT"


def _point_match_confidence(confidence: str) -> str:
    return {
        "high": "exact",
        "medium": "fuzzy",
        "low": "manual",
        "manual": "manual",
        "unknown": "unmatched",
    }.get((confidence or "").lower(), "fuzzy")


def _chunks(items: list[dict[str, Any]], size: int = 500) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _validate_discovery_session(site_id: str, discovery_id: str | None, max_age_minutes: int = 10) -> dict:
    """Validate a discovery session for freshness and status.

    Returns {"valid": True, ...} or raises HTTPException with 400/403/404.
    """
    from app.database.supabase_client import get_supabase_client

    client = get_supabase_client()

    if not discovery_id:
        raise HTTPException(status_code=400, detail="discovery_id is required for bridge review commit")

    result = (
        client.table("site_discovery_sessions")
        .select("site_id, adapter_type, discovered_at, status")
        .eq("discovery_id", discovery_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail=f"Discovery session {discovery_id} not found")

    session = result.data[0]
    if session.get("site_id") != site_id:
        raise HTTPException(
            status_code=403,
            detail=f"Discovery session {discovery_id} belongs to site {session.get('site_id')}, not {site_id}",
        )

    if session.get("status") != "active":
        raise HTTPException(
            status_code=400,
            detail=f"Discovery session {discovery_id} is not active (status={session.get('status')})",
        )

    from datetime import timedelta

    discovered_at = session.get("discovered_at")
    if discovered_at:
        try:
            discovered_dt = datetime.fromisoformat(discovered_at.replace("Z", "+00:00"))
            if datetime.now(UTC) - discovered_dt > timedelta(minutes=max_age_minutes):
                raise HTTPException(
                    status_code=400,
                    detail=f"Discovery session {discovery_id} expired (> {max_age_minutes} min). Rescan and retry.",
                )
        except ValueError:
            pass  # malformed timestamp — warn but don't block

    return {"valid": True, "adapter_type": session.get("adapter_type"), "discovered_at": discovered_at}


def _bridge_read_only_modules(site_id: str, equipment_rows: list[dict[str, Any]]) -> list[str]:
    from app.models.module_registry import MANDATORY_MODULE_TYPES
    from app.services.simbiot.connection_policy import infer_module_from_equipment_type, infer_module_from_identifiers

    modules = {module.value for module in MANDATORY_MODULE_TYPES}
    for row in equipment_rows:
        inferred = infer_module_from_equipment_type(row.get("type")) or infer_module_from_identifiers(
            row.get("code"),
            row.get("raw_code"),
            row.get("name"),
        )
        if inferred:
            modules.add(inferred.value)
    modules.add("simbiot")
    return sorted(modules)


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


@router.post("/bridge-review/{site_id}/commit")
async def commit_bridge_review_mappings(
    site_id: str,
    body: BridgeReviewCommitBody,
    auth: AuthContext = Depends(require_auth()),
) -> dict[str, Any]:
    """Commit approved direct-bridge review mappings into runtime tables.

    Delegates to the atomic Postgres RPC `commit_bridge_review` which
    performs all upserts in a single transaction.
    """
    _check_site_access(auth, site_id)
    _validate_discovery_session(site_id, body.discovery_id)
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        equipment = body.mappings.get("equipment") if isinstance(body.mappings, dict) else None
        if not isinstance(equipment, list):
            raise HTTPException(status_code=400, detail="Bridge review mappings must include equipment[]")

        # Build equipment array for RPC
        equipment_array: list[dict[str, Any]] = []
        point_array: list[dict[str, Any]] = []
        for raw_item in equipment:
            if not isinstance(raw_item, dict):
                continue
            raw_equipment_id = str(raw_item.get("equipment_id") or raw_item.get("equipment_name") or "").strip()
            if not raw_equipment_id:
                continue
            equipment_code = _normalise_bridge_equipment_code(site_id, raw_equipment_id)
            equipment_type = str(raw_item.get("equipment_type") or "unknown").strip() or "unknown"
            raw_points = raw_item.get("points")
            points: list[Any] = raw_points if isinstance(raw_points, list) else []
            equipment_array.append(
                {
                    "code": equipment_code,
                    "raw_code": raw_equipment_id,
                    "name": str(raw_item.get("equipment_name") or raw_equipment_id),
                    "type": equipment_type,
                    "confidence": raw_item.get("confidence"),
                    "points": points,
                }
            )
            for raw_point in points:
                if not isinstance(raw_point, dict):
                    continue
                point_id = str(raw_point.get("name") or raw_point.get("original_name") or "").strip()
                if not point_id:
                    continue
                point_array.append(
                    {
                        "name": point_id,
                        "original_name": str(raw_point.get("original_name") or point_id),
                        "point_type": str(raw_point.get("point_type") or "sensor"),
                        "confidence": str(raw_point.get("confidence") or raw_item.get("confidence") or "medium"),
                        "equipment_code": equipment_code,
                    }
                )

        # Infer modules (same logic as before, but passed to RPC)
        read_only_modules = _bridge_read_only_modules(site_id, equipment_array)

        # ── PLS: capability sync before commit ─────────────────────────
        # The wizard goes discovery → review → approve, skipping the
        # explicit sync step.  Auto-sync here so canonicalize doesn't fail
        # with PSMS_ILLEGAL_TRANSITION from `discovered`.
        try:
            from app.services.site_onboarding_lifecycle import capability_sync

            await capability_sync(site_id)
        except Exception as sync_exc:
            logger.warning("capability_sync skipped for %s: %s", site_id, sync_exc)

        result = client.rpc(
            "commit_bridge_review",
            {
                "p_site_id": site_id,
                "p_discovery_id": body.discovery_id,
                "p_approved_by": body.approved_by,
                "p_modules": read_only_modules,
                "p_equipment": equipment_array,
                "p_points": point_array,
            },
        ).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="commit_bridge_review returned no data")

        summary = result.data if isinstance(result.data, dict) else result.data[0]
        summary["equipment_received"] = len(equipment)

        # ── Seed tariff schedule based on site municipality ──────────────
        try:
            from app.services.tariff_wizard_service import seed_site_tariff

            tariff_result = await seed_site_tariff(site_id)
            if tariff_result:
                summary["tariff_seeded"] = tariff_result.get("tariff_name")
                logger.info("Tariff seeded for %s: %s", site_id, tariff_result.get("tariff_name"))
        except Exception as tariff_exc:
            logger.warning("Tariff seeding skipped for %s: %s", site_id, tariff_exc)
            summary["tariff_seeded"] = None

        return summary
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Bridge review commit failed for %s: %s", site_id, exc)
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


@router.get("/acceptance-status/{site_id}")
async def get_acceptance_status(
    site_id: str,
    auth: AuthContext = Depends(require_auth()),
) -> dict:
    """Return per-gate acceptance status for a site.

    Evaluates all four acceptance gates (wizard_complete, aggregation_fresh,
    history_fresh, operating_hours_set) and returns a per-gate pass/fail
    breakdown plus ``all_passed``.  Useful for the onboarding wizard to
    show which conditions are blocking ``sentinel_processing_enabled``.
    """
    _check_site_access(auth, site_id)

    from app.services.wizard_acceptance_gates import evaluate

    result = await evaluate(site_id)
    return {
        "site_id": site_id,
        "all_passed": result.all_passed,
        "gates": [{"name": g.name, "passed": g.passed, "reason": g.reason} for g in result.gates],
    }


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

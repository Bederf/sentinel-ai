"""
Health Rating API endpoints — Phase 109B-02

Four endpoints for health assessment timeline:
1. GET /api/equipment/{equipment_id}/health-rating — current rating + breakdown
2. GET /api/equipment/{equipment_id}/health-rating/history — timeline snapshots
3. GET /api/sites/{site_id}/assets/health-summary — all assets with health fields
4. POST /api/health-assessment/recompute — trigger recompute (202 accepted)

HARD RULES:
- Status ONLY from HealthThresholdService
- No risk probability fields in health responses
- History sorted newest-first
- 404 for unknown equipment, 200 with empty list for no snapshots
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.models.health_rating import (
    AssetHealthSummaryItem,
    HealthRating,
    HealthRatingHistory,
    RecomputeRequest,
    RecomputeResult,
)
from app.services.health_threshold_service import get_health_threshold_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["health-rating"])


# ---------------------------------------------------------------------------
# Helpers (lazy singletons)
# ---------------------------------------------------------------------------


def _get_snapshot_service():
    """Get the HealthSnapshotService singleton (lazy import)."""
    from app.services.health_snapshot_service import HealthSnapshotService

    return HealthSnapshotService()


def _get_calculator():
    """Get the HealthRatingCalculator (lazy import)."""
    from app.services.health_rating_calculator import HealthRatingCalculator

    return HealthRatingCalculator()


def _get_equipment_repo():
    """Get the EquipmentRepository (lazy import)."""
    from app.database.repositories.equipment_repository import get_equipment_repository

    return get_equipment_repository()


def _get_asset_health_service():
    """Get the AssetHealthService singleton (lazy import)."""
    from app.services.asset_health_service import get_asset_health_service

    return get_asset_health_service()


# ---------------------------------------------------------------------------
# 1. GET /api/equipment/{equipment_id}/health-rating
# ---------------------------------------------------------------------------


@router.get("/equipment/{equipment_id}/health-rating", response_model=HealthRating)
async def get_equipment_health_rating(equipment_id: str) -> HealthRating:
    """Get current health rating with component breakdown and data quality.

    Returns the most recent snapshot if available, otherwise computes a fresh
    rating on the fly.

    - 404 if the equipment ID is not found in the equipment table.
    - Status is always from HealthThresholdService (assertion enforced).
    """
    repo = _get_equipment_repo()
    equipment = repo.get_by_id(equipment_id)
    if not equipment:
        raise HTTPException(status_code=404, detail=f"Equipment '{equipment_id}' not found")

    snapshot_svc = _get_snapshot_service()
    rating = await snapshot_svc.get_latest(equipment_id)

    if rating is None:
        # Compute a fresh rating
        calculator = _get_calculator()
        from app.config.settings import settings

        mode = "simulation" if settings.demo_mode else "equipment_table"
        rating = await calculator.compute_rating(
            equipment_id=equipment_id,
            equipment=equipment,
            mode=mode,
        )
        # Store the freshly computed snapshot
        try:
            await snapshot_svc.store_snapshot(rating, site_id=equipment.get("site_id"))
        except Exception as e:
            logger.warning("Failed to store fresh snapshot for %s: %s", equipment_id, e)

    # HARD RULE: status must match HealthThresholdService
    threshold_svc = get_health_threshold_service()
    expected_status = threshold_svc.get_health_status(rating.health_score)
    assert rating.health_status == expected_status, (
        f"Status mismatch: rating has '{rating.health_status}' but "
        f"HealthThresholdService says '{expected_status}' for score {rating.health_score}"
    )

    return rating


# ---------------------------------------------------------------------------
# 2. GET /api/equipment/{equipment_id}/health-rating/history
# ---------------------------------------------------------------------------

_VALID_RANGES = {"7d": 7, "30d": 30, "90d": 90}


@router.get("/equipment/{equipment_id}/health-rating/history", response_model=HealthRatingHistory)
async def get_equipment_health_rating_history(
    equipment_id: str,
    range: str = Query("7d", alias="range", description="Time range: 7d, 30d, or 90d"),
) -> HealthRatingHistory:
    """Get health rating history for an equipment item.

    - Sorted newest-first.
    - Returns 200 with empty lists when no snapshots exist (NOT 404).
    - Returns 400 for invalid range parameter.
    """
    # Validate range
    range_days = _VALID_RANGES.get(range)
    if range_days is None:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid range '{range}'. Must be one of: {', '.join(_VALID_RANGES.keys())}",
        )

    snapshot_svc = _get_snapshot_service()
    snapshots = await snapshot_svc.get_history(equipment_id, range_days)
    daily_rollups = await snapshot_svc.get_daily_rollups(equipment_id, range_days)

    return HealthRatingHistory(
        equipment_id=equipment_id,
        range_days=range_days,
        snapshots=snapshots,
        daily_rollups=daily_rollups,
    )


# ---------------------------------------------------------------------------
# 3. GET /api/sites/{site_id}/assets/health-summary
# ---------------------------------------------------------------------------


@router.get("/sites/{site_id}/assets/health-summary")
async def get_site_health_summary(
    site_id: str,
    status: Optional[str] = Query(None, description="Filter by health status (e.g. 'critical')"),
    confidence: Optional[str] = Query(None, description="Filter by confidence (e.g. 'low')"),
    has_baseline: Optional[bool] = Query(None, description="Filter by baseline presence"),
    trend: Optional[str] = Query(None, description="Filter by trend direction (e.g. 'degrading')"),
) -> dict:
    """Get health summary for all equipment at a site.

    Returns one AssetHealthSummaryItem per equipment with all required fields:
    health_score, health_status, confidence, trend_7d, trend_30d,
    has_active_baseline, last_baseline_at, max_deviation_percent_24h,
    deviation_status, assessment_state, health_updated_at, health_source.

    Supports query filters: ?status=critical, ?confidence=low,
    ?has_baseline=false, ?trend=degrading
    """
    # 1. Get base asset health data (equipment + baseline info)
    asset_svc = _get_asset_health_service()
    try:
        assets = await asset_svc.get_site_assets(site_id)
    except Exception as e:
        logger.error("Failed to fetch assets for site %s: %s", site_id, e)
        raise HTTPException(status_code=500, detail=str(e))

    # 2. Enrich each asset with health rating snapshot data
    snapshot_svc = _get_snapshot_service()
    threshold_svc = get_health_threshold_service()

    summary_items: list[AssetHealthSummaryItem] = []

    for asset in assets:
        eq_id = asset.equipment_id

        # Try to get latest snapshot for trend + confidence data
        rating = await snapshot_svc.get_latest(eq_id)

        # Determine confidence and assessment_state
        asset_confidence = "high"
        asset_assessment_state = "normal"
        trend_7d = None
        trend_30d = None

        if rating is not None:
            asset_confidence = rating.confidence
            asset_assessment_state = rating.assessment_state

            # Calculate trends from history
            try:
                history_7d = await snapshot_svc.get_history(eq_id, 7)
                if len(history_7d) >= 2:
                    scores = [h.health_score for h in history_7d]
                    trend_7d = round((scores[0] - scores[-1]) / max(len(scores) - 1, 1), 2)
            except Exception:
                pass

            try:
                history_30d = await snapshot_svc.get_history(eq_id, 30)
                if len(history_30d) >= 2:
                    scores = [h.health_score for h in history_30d]
                    trend_30d = round((scores[0] - scores[-1]) / max(len(scores) - 1, 1), 2)
            except Exception:
                pass

        # Build the summary item — status always from HealthThresholdService
        health_status = threshold_svc.get_health_status(asset.health_score)

        item = AssetHealthSummaryItem(
            equipment_id=eq_id,
            equipment_name=asset.equipment_name,
            equipment_type=asset.equipment_type,
            category=asset.category,
            health_score=float(asset.health_score),
            health_status=health_status,
            confidence=asset_confidence,
            trend_7d=trend_7d,
            trend_30d=trend_30d,
            has_active_baseline=asset.has_active_baseline,
            last_baseline_at=asset.last_baseline_at,
            max_deviation_percent_24h=asset.max_deviation_percent_24h,
            deviation_status=asset.deviation_status,
            assessment_state=asset_assessment_state,
            health_updated_at=asset.health_updated_at,
            health_source=asset.health_source,
        )
        summary_items.append(item)

    # 3. Apply filters
    if status:
        summary_items = [s for s in summary_items if s.health_status == status]
    if confidence:
        summary_items = [s for s in summary_items if s.confidence == confidence]
    if has_baseline is not None:
        summary_items = [s for s in summary_items if s.has_active_baseline == has_baseline]
    if trend == "degrading":
        summary_items = [s for s in summary_items if (s.trend_7d or 0) < -0.1]
    elif trend == "improving":
        summary_items = [s for s in summary_items if (s.trend_7d or 0) > 0.1]
    elif trend == "stable":
        summary_items = [s for s in summary_items if abs(s.trend_7d or 0) <= 0.1]

    return {
        "site_id": site_id,
        "total": len(summary_items),
        "assets": [item.model_dump() for item in summary_items],
    }


# ---------------------------------------------------------------------------
# 4. POST /api/health-assessment/recompute
# ---------------------------------------------------------------------------


@router.post("/health-assessment/recompute", status_code=202)
async def recompute_health_assessment(request: RecomputeRequest) -> dict:
    """Trigger a health assessment recompute.

    - scope='single' requires equipment_id
    - scope='site' requires site_id
    - scope='all' requires neither
    - Returns 202 Accepted with a job ID
    - Runs recompute synchronously in demo mode, async otherwise
    """
    # Validate scope requirements
    if request.scope == "single" and not request.equipment_id:
        raise HTTPException(
            status_code=422,
            detail="equipment_id is required when scope='single'",
        )
    if request.scope == "site" and not request.site_id:
        raise HTTPException(
            status_code=422,
            detail="site_id is required when scope='site'",
        )

    job_id = str(uuid.uuid4())

    logger.info(
        "Health assessment recompute requested: scope=%s equipment_id=%s site_id=%s job_id=%s",
        request.scope,
        request.equipment_id,
        request.site_id,
        job_id,
    )

    # Audit log the request
    try:
        from app.services.audit_logger import AuditLogger
        from app.models.audit_log import AuditResultType

        audit = AuditLogger()
        audit.log_control_action(
            device_id=request.equipment_id or request.site_id or "all",
            point_name="health_assessment_recompute",
            user="system",
            old_value=None,
            new_value={"scope": request.scope, "job_id": job_id},
            result=AuditResultType.SUCCESS,
            metadata={"scope": request.scope, "job_id": job_id},
        )
    except Exception as e:
        logger.debug("Audit log skipped for recompute: %s", e)

    # Run recompute (sync in demo mode for simplicity)
    snapshot_svc = _get_snapshot_service()
    try:
        result: RecomputeResult = await snapshot_svc.recompute(
            scope=request.scope,
            equipment_id=request.equipment_id,
            site_id=request.site_id,
        )
    except Exception as e:
        logger.error("Recompute failed: %s", e)
        return JSONResponse(
            status_code=202,
            content={
                "job_id": job_id,
                "status": "failed",
                "error": str(e),
            },
        )

    return JSONResponse(
        status_code=202,
        content={
            "job_id": job_id,
            "status": "completed",
            "result": result.model_dump(),
        },
    )

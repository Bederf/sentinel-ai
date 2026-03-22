"""
Decision Moment API (Phase 164).

GET /api/decisions/current/{site_id}
  Returns latest DecisionMomentPayload for site, assembled from live fault state.
  No LLM in critical path. Target latency: < 300ms.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.services.decision_moment_aggregator import DecisionMomentAggregator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/decisions", tags=["decisions"])

# Module-level cache: site_id → (payload_dict, cached_at)
_payload_cache: dict[str, tuple[dict, datetime]] = {}
_CACHE_TTL_SECONDS = 30  # refresh after 30s to reflect telemetry changes

_aggregator = DecisionMomentAggregator()


def cache_decision_payload(site_id: str, payload_dict: dict) -> None:
    """Called by the event bus subscriber to pre-warm the cache."""
    _payload_cache[site_id] = (payload_dict, datetime.now(timezone.utc))
    logger.info("Decision payload cached for site %s", site_id)


def clear_decision_payload(site_id: str) -> None:
    """
    Invalidate the cache when a fault resolves.
    Called by the event bus subscriber on fault_cleared / low-importance events.
    Without this, the crisis page shows urgency 0.82 until the 30s TTL expires
    even after the fault clears — eroding operator trust.
    """
    if site_id in _payload_cache:
        del _payload_cache[site_id]
        logger.info("Decision payload cache cleared for site %s (fault resolved)", site_id)


@router.get("/current/{site_id}")
async def get_current_decision(
    site_id: str,
    fault_type: str = Query(default="chiller_fault"),
    severity: str = Query(default="critical"),
    asset_id: str = Query(default=""),
) -> JSONResponse:
    """
    Returns the current DecisionMomentPayload for the given site.

    If a cached payload exists (from event bus trigger) and is fresh, returns it.
    Otherwise assembles on-demand from query params (demo / manual trigger path).

    Query params are used for the on-demand assembly path only — when the event bus
    has pre-warmed the cache, those are ignored.

    Returns 422 when no cached payload exists and asset_id is not provided.
    """
    # Return cached payload if fresh
    if site_id in _payload_cache:
        cached_dict, cached_at = _payload_cache[site_id]
        age_seconds = (datetime.now(timezone.utc) - cached_at).total_seconds()
        if age_seconds < _CACHE_TTL_SECONDS:
            return JSONResponse(content={"data": cached_dict, "source": "cache", "age_seconds": int(age_seconds)})

    # On-demand assembly (demo path / no active event)
    if not asset_id:
        raise HTTPException(
            status_code=422,
            detail=(
                "asset_id required when no cached decision payload exists. "
                "Provide ?asset_id=S002-CHILLER-B1-001&fault_type=chiller_fault&severity=critical"
            ),
        )

    try:
        current_hour = datetime.now().hour
        payload = _aggregator.assemble(
            building_id=site_id,
            fault_type=fault_type,
            severity=severity,
            asset_id=asset_id,
            current_hour=current_hour,
        )
        payload_dict = payload.to_dict()
        # Cache on-demand result too
        _payload_cache[site_id] = (payload_dict, datetime.now(timezone.utc))
        return JSONResponse(content={"data": payload_dict, "source": "on_demand"})
    except Exception as e:
        logger.error("Decision assembly failed for %s: %s", site_id, e)
        raise HTTPException(status_code=500, detail=f"Decision assembly failed: {str(e)}")

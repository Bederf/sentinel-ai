"""PARASITE Decisions API - Visibility into Autonomous Actions.

Endpoints for querying PARASITE decision history and system health.

Handles:
- GET /api/parasite/decisions - List recent decisions
- GET /api/parasite/decisions/{decision_id} - Get single decision with full context
- GET /api/parasite/stats - Aggregated decision statistics
- GET /api/parasite/routing-config - Current routing configuration
- GET /api/parasite/health - PARASITE system health
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Depends, Query, Path

from app.middleware.auth_middleware import require_auth, require_operator
from app.models.auth import AuthContext
from app.database.repositories.parasite_decision_repository import ParasiteDecisionRepository
from app.services.tier_routing_engine import get_tier_routing_engine
from app.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/parasite",
    tags=["parasite"]
)


@router.get(
    "/decisions",
    response_model=Dict[str, Any],
    summary="List recent PARASITE decisions"
)
async def list_decisions(
    site_id: Optional[str] = Query(None, description="Filter by site ID"),
    tier: Optional[str] = Query(None, description="Filter by tier (tier1/tier2/tier3)"),
    limit: int = Query(50, ge=1, le=200, description="Number of decisions to return"),
    auth: AuthContext = Depends(require_auth)
) -> Dict[str, Any]:
    """List recent PARASITE decisions with optional filtering.

    Args:
        site_id: Optional site ID filter
        tier: Optional tier filter (tier1/tier2/tier3)
        limit: Number of decisions to return (max 200)
        auth: Authentication context

    Returns:
        Dict with decisions list, total count, and applied filters
    """
    try:
        parasite_repo = ParasiteDecisionRepository()

        # Get decisions from repository (with filters if provided)
        all_decisions = await parasite_repo.get_recent_decisions(limit=min(limit, 200))

        # Apply filters if provided
        filtered_decisions = all_decisions

        if site_id:
            filtered_decisions = [
                d for d in filtered_decisions
                if d.get("site_id") == site_id
            ]

        if tier:
            filtered_decisions = [
                d for d in filtered_decisions
                if d.get("tier") == tier
            ]

        # Build response
        return {
            "decisions": filtered_decisions[:limit],
            "total": len(filtered_decisions),
            "filters_applied": {
                "site_id": site_id,
                "tier": tier,
                "limit": limit
            }
        }

    except Exception as e:
        logger.error(f"Error listing decisions: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving decisions: {str(e)}"
        )


@router.get(
    "/decisions/{decision_id}",
    response_model=Dict[str, Any],
    summary="Get single decision with full context"
)
async def get_decision(
    decision_id: str = Path(..., description="ID of decision to retrieve"),
    auth: AuthContext = Depends(require_auth)
) -> Dict[str, Any]:
    """Get a single PARASITE decision with complete context.

    Args:
        decision_id: UUID of the decision
        auth: Authentication context

    Returns:
        Full decision record including contributing factors, outcome, COV result
    """
    try:
        parasite_repo = ParasiteDecisionRepository()

        decision = await parasite_repo.get_decision_by_id(decision_id)

        if not decision:
            raise HTTPException(
                status_code=404,
                detail=f"Decision {decision_id} not found"
            )

        return decision

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving decision {decision_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving decision: {str(e)}"
        )


@router.get(
    "/stats",
    response_model=Dict[str, Any],
    summary="Aggregated decision statistics"
)
async def get_stats(
    site_id: str = Query(..., description="Site ID (required)"),
    auth: AuthContext = Depends(require_auth)
) -> Dict[str, Any]:
    """Get aggregated PARASITE decision statistics for a site.

    Args:
        site_id: Site ID (required)
        auth: Authentication context

    Returns:
        Dict with total_decisions, by_tier breakdown, rollback_rate, COV success rate, outcome match rate
    """
    try:
        parasite_repo = ParasiteDecisionRepository()

        # Get all decisions for this site (last 30 days)
        thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()
        decisions = await parasite_repo.get_decisions_by_site(
            site_id=site_id,
            since=thirty_days_ago
        )

        # Calculate statistics
        total = len(decisions)
        by_tier = {
            "tier1": len([d for d in decisions if d.get("tier") == "tier1"]),
            "tier2": len([d for d in decisions if d.get("tier") == "tier2"]),
            "tier3": len([d for d in decisions if d.get("tier") == "tier3"])
        }

        # Count rollbacks
        rolled_back = len([d for d in decisions if d.get("rolled_back") is True])
        rollback_rate = rolled_back / total if total > 0 else 0.0

        # Count COV successes
        cov_verified = len([d for d in decisions if d.get("cov_verified") is True])
        cov_success_rate = cov_verified / total if total > 0 else 0.0

        # Count outcome matches (where outcome_matched=true)
        outcome_matched = len([d for d in decisions if d.get("outcome_matched") is True])
        outcome_match_rate = outcome_matched / total if total > 0 else 0.0

        return {
            "total_decisions": total,
            "by_tier": by_tier,
            "rollback_rate": round(rollback_rate, 3),
            "cov_success_rate": round(cov_success_rate, 3),
            "outcome_match_rate": round(outcome_match_rate, 3),
            "period": "last_30_days"
        }

    except Exception as e:
        logger.error(f"Error calculating stats for {site_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error calculating statistics: {str(e)}"
        )


@router.get(
    "/routing-config",
    response_model=Dict[str, Any],
    summary="Current routing configuration"
)
async def get_routing_config(
    auth: AuthContext = Depends(require_operator)
) -> Dict[str, Any]:
    """Get current PARASITE routing configuration.

    Requires OPERATOR role.

    Args:
        auth: Authentication context (operator level)

    Returns:
        Dict with parasite enabled status, tier thresholds, rate limits, COV timeouts
    """
    try:
        routing_engine = get_tier_routing_engine()

        return {
            "parasite_enabled": settings.parasite_enabled,
            "tier3_enabled": settings.parasite_tier3_enabled,
            "thresholds": {
                "tier2": settings.parasite_tier2_threshold,
                "tier3": settings.parasite_tier3_threshold
            },
            "rate_limit": getattr(settings, "parasite_rate_limit_per_hour", 10),
            "cov_timeout": settings.parasite_cov_verification_timeout_seconds,
            "auto_rollback_enabled": settings.parasite_auto_rollback_enabled,
            "outcome_measurement_window_seconds": getattr(settings, "parasite_outcome_measurement_window", 600)
        }

    except Exception as e:
        logger.error(f"Error retrieving routing config: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving configuration: {str(e)}"
        )


@router.get(
    "/health",
    response_model=Dict[str, Any],
    summary="PARASITE system health"
)
async def get_health(
    auth: AuthContext = Depends(require_auth)
) -> Dict[str, Any]:
    """Get PARASITE system health status.

    Args:
        auth: Authentication context

    Returns:
        Dict with status, pending_measurements count, auto_executions this hour, last decision timestamp
    """
    try:
        parasite_repo = ParasiteDecisionRepository()

        # Determine overall status
        if not settings.parasite_enabled:
            status = "disabled"
        else:
            status = "active"

        # Count pending outcome measurements
        pending_measurements = await parasite_repo.count_pending_measurements()

        # Count auto-executions in last hour
        one_hour_ago = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        recent_executions = await parasite_repo.get_decisions_since(one_hour_ago)
        auto_executions_this_hour = len([
            d for d in recent_executions
            if d.get("decision_type") in ["tier3_auto_execute", "auto_rollback"]
        ])

        # Get last decision timestamp
        all_recent = await parasite_repo.get_recent_decisions(limit=1)
        last_decision_at = all_recent[0].get("created_at") if all_recent else None

        return {
            "status": status,
            "pending_measurements": pending_measurements,
            "auto_executions_this_hour": auto_executions_this_hour,
            "last_decision_at": last_decision_at,
            "tier3_enabled": settings.parasite_tier3_enabled,
            "auto_rollback_enabled": settings.parasite_auto_rollback_enabled
        }

    except Exception as e:
        logger.error(f"Error retrieving health status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving health status: {str(e)}"
        )

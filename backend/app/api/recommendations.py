"""Recommendation management API endpoints.

Provides endpoints for managing recommendations through the control tier workflow:
- GET pending recommendations (approval queue)
- POST approve recommendation
- POST reject recommendation
- GET recommendation details
"""

import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.database.repositories.site_repository import SiteRepository
from app.middleware.auth_middleware import require_auth, require_site_access
from app.middleware.rate_limiter import limiter
from app.models.auth import AuthContext, AuthLevel
from app.services.recommendation_service import get_recommendation_service
from app.utils.ai_provenance import attach_ai_provenance, get_ml_provenance

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recommendations", tags=["Recommendations"])


class ApproveRequest(BaseModel):
    """Request body for approving a recommendation."""

    reason: str | None = None


class RejectRequest(BaseModel):
    """Request body for rejecting a recommendation."""

    reason: str


class CreateRecommendationRequest(BaseModel):
    """Request body for creating a recommendation."""

    site_id: str
    action_type: str
    target_equipment: str
    action: dict[str, Any]
    reason: str
    expected_impact: dict[str, Any] | None = None
    confidence: str = "medium"
    profile: str = ""
    multi_objective_score: float = 0.0


@limiter.limit("20/minute")
@router.get("/{site_id}")
async def get_pending_recommendations(
    request: Request,
    site_id: str,
    limit: int = Query(10, ge=1, le=100),
    auth: AuthContext = Depends(require_site_access("site_id")),
):
    """Get pending recommendations for a site (Tier 2 approval queue).

    Returns recommendations awaiting operator approval, newest first.

    Args:
        site_id: Building identifier
        limit: Maximum number to return (default: 10)

    Returns:
        JSON response with pending recommendations
    """
    try:
        # Shadow phase suppresses the queue from operator view — Supabase is authoritative.
        repo = SiteRepository()
        site = repo.get_by_id(site_id)
        if site and site.get("onboarding_phase") == "shadow":
            return attach_ai_provenance(
                {
                    "site_id": site_id,
                    "recommendations": [],
                    "count": 0,
                    "suppressed": True,
                    "mode": "shadow",
                },
                get_ml_provenance("recommendation-engine-v1"),
            )

        service = get_recommendation_service()
        recs = await service.get_pending_recommendations(site_id, limit)

        return attach_ai_provenance(
            {
                "site_id": site_id,
                "recommendations": [r.to_dict() for r in recs],
                "count": len(recs),
            },
            get_ml_provenance("recommendation-engine-v1"),
        )

    except Exception as e:
        logger.error(f"Error fetching pending recommendations for {site_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching recommendations: {e}")


@limiter.limit("20/minute")
@router.post("/history/{site_id}")
async def get_recommendation_history(
    request: Request,
    site_id: str,
    filters: dict[str, Any] = Body(default={"status": None, "risk_level": None}),
    limit: int = Query(200, ge=1, le=2000),
    auth: AuthContext = Depends(require_site_access("site_id")),
):
    """Get historical recommendations for a site with optional filters.

    Returns all non-pending recommendations (executed, rejected, auto_executed, failed),
    newest first.

    Args:
        site_id: Building identifier
        filters: Optional filter dict with status and/or riskLevel keys
        limit: Maximum number to return (default: 50, max: 500)

    Returns:
        JSON response with historical recommendations
    """
    try:
        # Shadow phase suppresses history from operator view — Supabase is authoritative.
        repo = SiteRepository()
        site = repo.get_by_id(site_id)
        if site and site.get("onboarding_phase") == "shadow":
            return attach_ai_provenance(
                {
                    "site_id": site_id,
                    "recommendations": [],
                    "count": 0,
                    "filters": {
                        "status": None,
                        "risk_level": None,
                    },
                    "suppressed": True,
                    "mode": "shadow",
                },
                get_ml_provenance("recommendation-engine-v1"),
            )

        service = get_recommendation_service()

        # Extract filters from request body
        status_filter = filters.get("status") if filters else None
        risk_level_filter = filters.get("riskLevel") or filters.get("risk_level")

        recs = await service.get_history(
            site_id,
            status_filter=status_filter,
            risk_level_filter=risk_level_filter,
            limit=limit,
        )

        aggregates = await service.get_history_aggregates(site_id)

        return attach_ai_provenance(
            {
                "site_id": site_id,
                "recommendations": [r.to_dict() for r in recs],
                "count": len(recs),
                "aggregates": aggregates,
                "filters": {
                    "status": status_filter,
                    "risk_level": risk_level_filter,
                },
            },
            get_ml_provenance("recommendation-engine-v1"),
        )

    except Exception as e:
        logger.error(f"Error fetching recommendation history for {site_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching recommendation history: {e}")


@limiter.limit("15/minute")
@router.post("")
async def create_recommendation(
    req: Request,
    request: CreateRecommendationRequest,
    auth: AuthContext = Depends(require_auth(AuthLevel.OPERATOR)),
):
    """Create a new recommendation.

    The recommendation will be auto-executed or placed in approval queue
    based on control tier and risk level.

    Args:
        request: Recommendation data

    Returns:
        JSON response with created recommendation
    """
    try:
        service = get_recommendation_service()
        rec = await service.create_recommendation(request.dict())

        return attach_ai_provenance(
            {
                "success": True,
                "recommendation": rec.to_dict(),
                "status": rec.status.value,
                "requires_approval": rec.requires_approval,
            },
            get_ml_provenance("recommendation-engine-v1"),
        )

    except ValueError as e:
        logger.error(f"Validation error creating recommendation: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating recommendation: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating recommendation: {e}")


@router.get("/detail/{rec_id}")
async def get_recommendation(rec_id: str):
    """Get recommendation details.

    Args:
        rec_id: Recommendation ID

    Returns:
        JSON response with recommendation details
    """
    try:
        from app.database.repositories import get_recommendation_repository

        repo = get_recommendation_repository()
        rec = await repo.get(rec_id)

        if not rec:
            raise HTTPException(status_code=404, detail=f"Recommendation {rec_id} not found")

        return attach_ai_provenance(
            {
                "success": True,
                "recommendation": rec.to_dict(),
                "status": rec.status.value,
            },
            get_ml_provenance("recommendation-engine-v1"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching recommendation {rec_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{rec_id}/approve")
async def approve_recommendation(
    rec_id: str,
    request: Request,
    body: ApproveRequest,
    auth: AuthContext = Depends(require_auth(AuthLevel.OPERATOR)),
):
    """Approve recommendation (Tier 2).

    Changes status to APPROVED and executes the recommendation.

    Args:
        rec_id: Recommendation ID
        request: HTTP request (for user_id extraction)
        body: Approval data

    Returns:
        JSON response with approved recommendation
    """
    try:
        # Phase 109: Quality gate pre-check at the API boundary
        try:
            from app.config.settings import settings
            from app.services.quality_gate_evaluator import QualityGateEvaluator
            from app.services.quality_gate_policy import GateStatus

            mode = settings.resolved_ingestion_mode.value

            if mode == "shadow_live":
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "SHADOW_MODE_NO_EXEC",
                        "message": "Cannot approve recommendations in shadow_live mode",
                    },
                )

            if mode == "live_control":
                evaluator = QualityGateEvaluator()
                # Try to get site_id from the recommendation
                try:
                    from app.database.repositories import get_recommendation_repository

                    repo = get_recommendation_repository()
                    rec_obj = await repo.get(rec_id)
                    site_id = rec_obj.site_id if rec_obj else "unknown"
                except Exception:
                    site_id = "unknown"

                metrics = await evaluator.collect_metrics(site_id)
                gate_result = evaluator.evaluate(mode, metrics, site_id=site_id)

                if gate_result.overall == GateStatus.FAIL:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "error": "QUALITY_GATE_BLOCK",
                            "failed_rules": gate_result.failed_rules,
                            "reason_codes": [rc.value for rc in gate_result.reason_codes],
                            "message": "Quality gate failed — execution blocked",
                        },
                    )

        except HTTPException:
            raise
        except Exception as gate_err:
            logger.debug(f"Quality gate pre-check skipped in recommendations.approve: {gate_err}")

        user_id = request.headers.get("X-User-Id", "operator")
        service = get_recommendation_service()

        rec = await service.approve_recommendation(
            rec_id=rec_id,
            user_id=user_id,
            reason=body.reason,
        )

        return attach_ai_provenance(
            {
                "success": True,
                "recommendation": rec.to_dict(),
                "status": rec.status.value,
                "message": f"Recommendation approved and executed by {user_id}",
            },
            get_ml_provenance("recommendation-engine-v1"),
        )

    except ValueError as e:
        logger.error(f"Validation error approving recommendation {rec_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving recommendation {rec_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{rec_id}/reject")
async def reject_recommendation(
    rec_id: str,
    request: Request,
    body: RejectRequest,
    auth: AuthContext = Depends(require_auth(AuthLevel.OPERATOR)),
):
    """Reject recommendation (Tier 2).

    Changes status to REJECTED and logs feedback for learning.

    Args:
        rec_id: Recommendation ID
        request: HTTP request (for user_id extraction)
        body: Rejection data with reason

    Returns:
        JSON response with rejected recommendation
    """
    try:
        user_id = request.headers.get("X-User-Id", "operator")
        service = get_recommendation_service()

        rec = await service.reject_recommendation(
            rec_id=rec_id,
            user_id=user_id,
            reason=body.reason,
        )

        return attach_ai_provenance(
            {
                "success": True,
                "recommendation": rec.to_dict(),
                "status": rec.status.value,
                "message": f"Recommendation rejected by {user_id}",
            },
            get_ml_provenance("recommendation-engine-v1"),
        )

    except ValueError as e:
        logger.error(f"Validation error rejecting recommendation {rec_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting recommendation {rec_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ProcessPendingRequest(BaseModel):
    """Request body for triggering recommendation processing."""

    channel: str = "system"
    trigger: str = "manual"


@limiter.limit("10/minute")
@router.post("/{site_id}/process-pending")
async def trigger_recommendation_processing(
    request: Request,
    site_id: str,
    body: ProcessPendingRequest = ProcessPendingRequest(),
    auth: AuthContext = Depends(require_site_access("site_id")),
):
    """Trigger the recommendation agent to process pending recommendations.

    Invokes the LangGraph recommendation agent to validate, assess impact,
    route through tier engine, and execute or request approval for
    pending recommendations.

    Args:
        site_id: Building identifier (e.g., "S002")
        body: Optional channel and trigger configuration

    Returns:
        JSON response with processing result
    """
    try:
        from langchain_core.messages import HumanMessage

        from app.agents import get_recommendation_graph

        agent = get_recommendation_graph()
        thread_id = f"rec_api_{site_id}"
        config = {"configurable": {"thread_id": thread_id}}

        result = await agent.ainvoke(
            {
                "messages": [HumanMessage(content="process")],
                "site_id": site_id,
                "channel": body.channel,
                "trigger": body.trigger,
            },
            config=config,
        )

        return attach_ai_provenance(
            {
                "success": True,
                "site_id": site_id,
                "response": result.get("response", ""),
                "tier": result.get("tier"),
                "recommendation_id": result.get("recommendation_id"),
                "needs_input": result.get("needs_input", False),
                "processing_complete": result.get("processing_complete", False),
            },
            get_ml_provenance("recommendation-agent-v1"),
        )

    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="LangGraph not available. Install langgraph to use the recommendation agent.",
        )
    except Exception as e:
        logger.error(f"Error processing recommendations for {site_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing recommendations: {e}")

"""Recommendation management API endpoints.

Provides endpoints for managing recommendations through the control tier workflow:
- GET pending recommendations (approval queue)
- POST approve recommendation
- POST reject recommendation
- GET recommendation details
"""

import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, Request, HTTPException, Query, Body
from pydantic import BaseModel

from app.middleware.rate_limiter import limiter
from app.services.recommendation_service import get_recommendation_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recommendations", tags=["Recommendations"])


class ApproveRequest(BaseModel):
    """Request body for approving a recommendation."""

    reason: Optional[str] = None


class RejectRequest(BaseModel):
    """Request body for rejecting a recommendation."""

    reason: str


class CreateRecommendationRequest(BaseModel):
    """Request body for creating a recommendation."""

    site_id: str
    action_type: str
    target_equipment: str
    action: Dict[str, Any]
    reason: str
    expected_impact: Optional[Dict[str, Any]] = None
    confidence: str = "medium"
    profile: str = ""
    multi_objective_score: float = 0.0


@limiter.limit("20/minute")
@router.get("/{site_id}")
async def get_pending_recommendations(
    request: Request, site_id: str, limit: int = Query(10, ge=1, le=100)
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
        service = get_recommendation_service()
        recs = await service.get_pending_recommendations(site_id, limit)

        return {
            "site_id": site_id,
            "recommendations": [r.to_dict() for r in recs],
            "count": len(recs),
        }

    except Exception as e:
        logger.error(f"Error fetching pending recommendations for {site_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching recommendations: {e}"
        )


@limiter.limit("20/minute")
@router.post("/history/{site_id}")
async def get_recommendation_history(
    request: Request,
    site_id: str,
    filters: Dict[str, Any] = Body(default={"status": None, "risk_level": None}),
    limit: int = Query(50, ge=1, le=500),
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

        return {
            "site_id": site_id,
            "recommendations": [r.to_dict() for r in recs],
            "count": len(recs),
            "filters": {
                "status": status_filter,
                "risk_level": risk_level_filter,
            },
        }

    except Exception as e:
        logger.error(f"Error fetching recommendation history for {site_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching recommendation history: {e}"
        )


@limiter.limit("15/minute")
@router.post("")
async def create_recommendation(req: Request, request: CreateRecommendationRequest):
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

        return {
            "success": True,
            "recommendation": rec.to_dict(),
            "status": rec.status.value,
            "requires_approval": rec.requires_approval,
        }

    except ValueError as e:
        logger.error(f"Validation error creating recommendation: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating recommendation: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error creating recommendation: {e}"
        )


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
            raise HTTPException(
                status_code=404,
                detail=f"Recommendation {rec_id} not found"
            )
        
        return {
            "success": True,
            "recommendation": rec.to_dict(),
            "status": rec.status.value,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching recommendation {rec_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
        user_id = request.headers.get("X-User-Id", "operator")
        service = get_recommendation_service()

        rec = await service.approve_recommendation(
            rec_id=rec_id,
            user_id=user_id,
            reason=body.reason,
        )

        return {
            "success": True,
            "recommendation": rec.to_dict(),
            "status": rec.status.value,
            "message": f"Recommendation approved and executed by {user_id}",
        }

    except ValueError as e:
        logger.error(f"Validation error approving recommendation {rec_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving recommendation {rec_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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

        return {
            "success": True,
            "recommendation": rec.to_dict(),
            "status": rec.status.value,
            "message": f"Recommendation rejected by {user_id}",
        }

    except ValueError as e:
        logger.error(f"Validation error rejecting recommendation {rec_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting recommendation {rec_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting recommendation {rec_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

"""Recommendation management API endpoints.

Provides endpoints for managing recommendations through the control tier workflow:
- GET pending recommendations (approval queue)
- POST approve recommendation
- POST reject recommendation
- GET recommendation details
"""

import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel

from app.services.recommendation_service import get_recommendation_service
from app.models.recommendation import Recommendation, RecommendationStatus

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


@router.get("/{site_id}")
async def get_pending_recommendations(
    site_id: str, limit: int = Query(10, ge=1, le=100)
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


@router.post("")
async def create_recommendation(request: CreateRecommendationRequest):
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
        service = get_recommendation_service()
        # Note: In full implementation, would fetch from repository
        # For now, return 404 (repository method not yet integrated)
        raise HTTPException(
            status_code=501,
            detail="Requires repository integration (Phase 72.5)"
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

        # Note: In full implementation, would fetch and update via repository
        # For now, return 501 (not yet implemented)
        raise HTTPException(
            status_code=501,
            detail="Requires repository integration (Phase 72.5)"
        )

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

        # Note: In full implementation, would fetch and update via repository
        # For now, return 501 (not yet implemented)
        raise HTTPException(
            status_code=501,
            detail="Requires repository integration (Phase 72.5)"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting recommendation {rec_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

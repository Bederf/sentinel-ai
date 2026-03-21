"""API endpoints for review queue management.

Phase 162: Semantic Control Foundation — Plan 05.
Human-in-the-loop review interface for semantic classification decisions.
Facility managers review, approve, reject, and override semantic classifications.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.middleware.auth_middleware import require_auth
from app.models.auth import AuthContext
from app.models.review_queue import ReviewQueueEntry, ReviewQueueStats

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/review-queue", tags=["review_queue"])

# Module-level singleton (lazy-initialised to avoid import-time I/O)
_review_service = None


def _get_review_service():
    global _review_service
    if _review_service is None:
        from app.services.review_queue_service import ReviewQueueService

        _review_service = ReviewQueueService()
    return _review_service


# ------------------------------------------------------------------
# Request / response models
# ------------------------------------------------------------------


class ApproveRequest(BaseModel):
    """Request body for approval action."""

    review_notes: str = ""


class RejectRequest(BaseModel):
    """Request body for rejection action."""

    reason: str
    review_notes: str = ""


class OverrideRequest(BaseModel):
    """Request body for override action."""

    correct_tags: list[str]
    justification: str


class BulkApproveRequest(BaseModel):
    """Request body for bulk approval."""

    entry_ids: list[str]


class DecisionResponse(BaseModel):
    """Result of a review decision."""

    entry_id: str
    success: bool
    message: str


class BulkDecisionResponse(BaseModel):
    """Result of a bulk review decision."""

    approved_count: int
    message: str


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.get("/pending", response_model=list[ReviewQueueEntry])
async def get_pending_reviews(
    site_id: str = Query(..., description="Site ID to filter by"),
    safety_class: Optional[str] = Query(None, description="Filter by safety class (LOW/MEDIUM/HIGH)"),
    equipment_id: Optional[str] = Query(None, description="Filter by equipment ID"),
    confidence_threshold: Optional[float] = Query(None, description="Max confidence score filter"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results to return"),
) -> list[ReviewQueueEntry]:
    """Get pending reviews with optional filtering, sorted by priority (lowest first)."""
    from app.database.repositories.review_queue_repository import ReviewQueueRepository

    repo = ReviewQueueRepository()
    return await repo.get_pending_reviews(
        site_id=site_id,
        safety_class=safety_class,
        equipment_id=equipment_id,
        confidence_threshold=confidence_threshold,
        limit=limit,
    )


@router.get("/stats", response_model=ReviewQueueStats)
async def get_queue_stats(
    site_id: str = Query(..., description="Site ID to get stats for"),
) -> ReviewQueueStats:
    """Get review queue statistics including pending count, safety class distribution, and avg age."""
    from app.database.repositories.review_queue_repository import ReviewQueueRepository

    repo = ReviewQueueRepository()
    return await repo.get_review_stats(site_id=site_id)


@router.post("/{entry_id}/approve", response_model=DecisionResponse)
async def approve_review(
    entry_id: str,
    body: ApproveRequest,
    auth: AuthContext = Depends(require_auth),
) -> DecisionResponse:
    """Approve a classification and enable it for control use."""
    service = _get_review_service()
    success = await service.approve_classification(
        entry_id=entry_id,
        reviewed_by=auth.user_id,
        notes=body.review_notes,
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Review queue entry {entry_id} not found")
    return DecisionResponse(
        entry_id=entry_id,
        success=True,
        message="Classification approved for control use.",
    )


@router.post("/{entry_id}/reject", response_model=DecisionResponse)
async def reject_review(
    entry_id: str,
    body: RejectRequest,
    auth: AuthContext = Depends(require_auth),
) -> DecisionResponse:
    """Reject a classification — it will not be used for control decisions."""
    service = _get_review_service()
    success = await service.reject_classification(
        entry_id=entry_id,
        reviewed_by=auth.user_id,
        reason=body.reason,
        notes=body.review_notes,
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Review queue entry {entry_id} not found")
    return DecisionResponse(
        entry_id=entry_id,
        success=True,
        message="Classification rejected and excluded from control decisions.",
    )


@router.post("/{entry_id}/override", response_model=DecisionResponse)
async def override_review(
    entry_id: str,
    body: OverrideRequest,
    auth: AuthContext = Depends(require_auth),
) -> DecisionResponse:
    """Override classification with manually corrected tags."""
    if not body.correct_tags:
        raise HTTPException(status_code=422, detail="correct_tags must not be empty")
    if not body.justification.strip():
        raise HTTPException(status_code=422, detail="justification is required for override")

    service = _get_review_service()
    success = await service.override_classification(
        entry_id=entry_id,
        reviewed_by=auth.user_id,
        correct_tags=body.correct_tags,
        justification=body.justification,
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Review queue entry {entry_id} not found")
    return DecisionResponse(
        entry_id=entry_id,
        success=True,
        message="Classification overridden with corrected tags.",
    )


@router.post("/bulk-approve", response_model=BulkDecisionResponse)
async def bulk_approve(
    body: BulkApproveRequest,
    auth: AuthContext = Depends(require_auth),
) -> BulkDecisionResponse:
    """Bulk approve multiple classifications (typically high-confidence, low-safety entries)."""
    if not body.entry_ids:
        raise HTTPException(status_code=422, detail="entry_ids must not be empty")

    from app.database.repositories.review_queue_repository import ReviewQueueRepository

    repo = ReviewQueueRepository()
    count = await repo.bulk_decision(
        entry_ids=body.entry_ids,
        decision_type="approve",
        reviewed_by=auth.user_id,
        review_notes="Bulk approved",
    )
    return BulkDecisionResponse(
        approved_count=count,
        message=f"Bulk approved {count} classifications.",
    )


@router.get("/{entry_id}/history")
async def get_review_history(entry_id: str) -> list[dict]:
    """Get the full review decision history for a classification entry."""
    from app.database.repositories.review_queue_repository import ReviewQueueRepository

    repo = ReviewQueueRepository()
    decisions = await repo.get_review_history(entry_id=entry_id)
    return [d.model_dump(mode="json") for d in decisions]

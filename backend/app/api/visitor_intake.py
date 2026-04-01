"""Visitor Intake API — receives calendar invite data from n8n IMAP workflow.

POST /api/visits/internal
  Called by n8n workflow when a calendar invite is received in the info@ inbox.
  Creates a Visit, generates token + PIN + QR, sends confirmation email to visitor.

Auth: X-Sentry-API-Key (matches SENTRY_BOT_API_KEY env var)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from app.api.visit_service import VisitService
from app.middleware.auth_middleware import require_auth
from app.models.auth import AuthContext, AuthLevel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/visits", tags=["visitor_intake"])


class VisitIntakeRequest(BaseModel):
    """Payload from n8n IMAP workflow — calendar invite details.

    The n8n workflow parses the ICS attachment / iTip reply from the info@ inbox
    and extracts the relevant fields for visit creation.
    """

    visitor_email: EmailStr = Field(description="External visitor's email address")
    host_email: EmailStr = Field(description="Organizer/host's email address")
    host_name: str | None = Field(default=None, description="Organizer/host's name")
    host_mobile: str | None = Field(default=None, description="Organizer/host's mobile number")
    building_id: str = Field(description="Site ID e.g. site-001")
    meeting_start: str = Field(description="ISO8601 datetime string")
    meeting_end: str = Field(description="ISO8601 datetime string")
    meeting_subject: str | None = Field(default=None, description="Meeting subject/title")
    external_event_id: str | None = Field(
        default=None, description="Unique ID from n8n workflow — used for idempotency to prevent duplicate visits"
    )


class VisitIntakeResponse(BaseModel):
    """Response after successful visit creation."""

    success: bool
    visit_id: str
    token: str
    pin: str
    visitor_email: str
    host_email: str
    building_id: str
    meeting_subject: str | None
    message: str


@router.post("/internal", response_model=VisitIntakeResponse)
async def create_visit_from_intake(
    request: VisitIntakeRequest,
    _auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
) -> VisitIntakeResponse:
    """Create a visit from n8n IMAP intake pipeline.

    Idempotent via external_event_id — if a visit with this external_event_id
    already exists, returns the existing visit instead of creating a duplicate.
    """
    from datetime import datetime

    # Parse datetime strings
    try:
        meeting_start = datetime.fromisoformat(request.meeting_start.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid meeting_start format: {request.meeting_start}"
        )
    try:
        meeting_end = datetime.fromisoformat(request.meeting_end.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid meeting_end format: {request.meeting_end}"
        )

    service = VisitService()

    # Idempotency: skip if external_event_id already exists
    if request.external_event_id:
        from app.database.repositories.visit_repository import VisitRepository

        repo = VisitRepository()
        existing = repo.get_visit_by_external_event_id(request.external_event_id)
        if existing is not None:
            logger.info(
                "[VisitorIntake] Visit for external_event_id=%s already exists — returning existing",
                request.external_event_id,
            )
            return VisitIntakeResponse(
                success=True,
                visit_id=str(existing.id),
                token=str(existing.token),
                pin=existing.pin,
                visitor_email=existing.visitor_email,
                host_email=existing.host_email,
                building_id=existing.building_id,
                meeting_subject=existing.meeting_subject,
                message="Visit already exists for this event",
            )

    # Create visit
    try:
        visit = service.create_visit(
            visitor_email=request.visitor_email,
            host_email=request.host_email,
            building_id=request.building_id,
            meeting_start=meeting_start,
            meeting_end=meeting_end,
            host_name=request.host_name,
            host_mobile=request.host_mobile,
        )
    except Exception as exc:
        logger.error("[VisitorIntake] Failed to create visit: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create visit: {exc}"
        ) from exc

    # Update with external_event_id and meeting_subject if provided
    from app.database.repositories.visit_repository import VisitRepository

    repo = VisitRepository()
    updates: dict = {}
    if request.external_event_id:
        updates["external_event_id"] = request.external_event_id
    if request.meeting_subject:
        updates["meeting_subject"] = request.meeting_subject
    if updates:
        repo.update_visit(visit.id, updates)

    # Reload to get updated meeting_subject
    visit = repo.get_visit_by_id(visit.id) or visit

    logger.info(
        "[VisitorIntake] Created visit %s for %s (event=%s)", visit.id, request.visitor_email, request.external_event_id
    )

    return VisitIntakeResponse(
        success=True,
        visit_id=str(visit.id),
        token=str(visit.token),
        pin=visit.pin,
        visitor_email=visit.visitor_email,
        host_email=visit.host_email,
        building_id=visit.building_id,
        meeting_subject=visit.meeting_subject,
        message="Visit created — confirmation email will be sent to visitor",
    )

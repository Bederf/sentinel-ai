"""Visitor Intake API — creates visitor check-in records and sends QR confirmations.

POST /api/visits/internal
  Receives calendar invite data (from n8n, webhook, or direct trigger).
  Creates a Visit, generates token + PIN + QR code.
  Sends confirmation email directly via backend (info@sentinel-ai.co.za).

Auth: X-Sentry-API-Key (matches SENTRY_BOT_API_KEY env var)
"""

from __future__ import annotations

import base64
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field

from app.api.visit_service import VisitService
from app.middleware.auth_middleware import require_auth
from app.models.auth import AuthContext, AuthLevel
from app.models.visit import VisitStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/visits", tags=["visitor_intake"])


class VisitIntakeRequest(BaseModel):
    """Payload for visitor intake — calendar invite details.

    Can come from n8n, Google Calendar webhook, webhook, or direct API call.
    Contains parsed calendar event data + visitor details.
    """

    visitor_email: EmailStr = Field(description="External visitor's email address")
    visitor_name: str | None = Field(default=None, description="Visitor's display name")
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
    qr_code: str | None
    visitor_email: str
    host_email: str
    host_name: str | None
    building_id: str
    meeting_subject: str | None
    meeting_start: str | None
    meeting_end: str | None
    message: str
    email_already_sent: bool = False
    email_already_sent: bool = False  # True when idempotency matched — n8n should skip email


@router.post("/internal", response_model=VisitIntakeResponse)
async def create_visit_from_intake(
    request: VisitIntakeRequest,
    _auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
) -> VisitIntakeResponse:
    """Create a visit from calendar invite data and send confirmation email.

    Idempotent via external_event_id — if a visit with this external_event_id
    already exists, returns the existing visit instead of creating a duplicate.
    Email is sent directly by backend; no n8n involvement.
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
                qr_code=existing.qr_code,
                visitor_email=existing.visitor_email,
                host_email=existing.host_email,
                host_name=existing.host_name,
                building_id=existing.building_id,
                meeting_subject=existing.meeting_subject,
                meeting_start=existing.meeting_start.isoformat() if existing.meeting_start else None,
                meeting_end=existing.meeting_end.isoformat() if existing.meeting_end else None,
                message="Visit already exists for this event",
                email_already_sent=True,
            )

    # Create visit with PENDING status — awaiting visitor acceptance.
    try:
        visit = service.create_visit(
            visitor_email=request.visitor_email,
            host_email=request.host_email,
            building_id=request.building_id,
            meeting_start=meeting_start,
            meeting_end=meeting_end,
            host_name=request.host_name,
            host_mobile=request.host_mobile,
            visitor_name=request.visitor_name,
            status=VisitStatus.PENDING,
        )
    except Exception as exc:
        logger.error("[VisitorIntake] Failed to create visit: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create visit: {exc}"
        ) from exc

    # Update with meeting_subject and any additional info
    from app.database.repositories.visit_repository import VisitRepository

    repo = VisitRepository()
    updates: dict = {}
    if request.external_event_id:
        updates["external_event_id"] = request.external_event_id
    if request.meeting_subject:
        updates["meeting_subject"] = request.meeting_subject
    if request.visitor_name:
        updates["visitor_name"] = request.visitor_name
    if updates:
        repo.update_visit(visit.id, updates)

    # Reload to get updated fields
    visit = repo.get_visit_by_id(visit.id) or visit

    logger.info(
        "[VisitorIntake] Created visit %s for %s — awaiting acceptance", visit.id, request.visitor_email
    )

    return VisitIntakeResponse(
        success=True,
        visit_id=str(visit.id),
        token=str(visit.token),
        pin=visit.pin,
        qr_code=visit.qr_code,
        visitor_email=visit.visitor_email,
        host_email=visit.host_email,
        host_name=request.host_name or visit.host_name,
        building_id=visit.building_id,
        meeting_subject=visit.meeting_subject,
        meeting_start=meeting_start.isoformat(),
        meeting_end=meeting_end.isoformat(),
        message="Visit created. Waiting for visitor acceptance.",
        email_already_sent=False,
    )


@router.get("/qr/{token}", include_in_schema=True)
async def get_visit_qr(token: str) -> Response:
    """Serve the QR code PNG for a visit token.

    No auth required — token is the secret. Used in visitor confirmation emails
    so email clients can display the QR image via a real URL.
    """
    from uuid import UUID

    from app.database.repositories.visit_repository import VisitRepository

    try:
        uid = UUID(token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token format")

    repo = VisitRepository()
    visit = repo.get_visit_by_token(uid)
    if visit is None or not visit.qr_code:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found")

    png_bytes = base64.b64decode(visit.qr_code)
    return Response(content=png_bytes, media_type="image/png")


class RSVPRequest(BaseModel):
    """Visitor RSVP response to a calendar invite."""

    external_event_id: str = Field(description="Google Calendar UID — links to the pending visit")
    response: str = Field(description="'accepted' or 'declined'")
    visitor_email: EmailStr = Field(description="Visitor email (must match the pending visit)")


class RSVPResponse(BaseModel):
    """Response after RSVP processing."""

    success: bool
    visit_id: str | None
    status: str | None
    qr_code: str | None
    message: str


@router.post("/rsvp", response_model=RSVPResponse)
async def handle_rsvp(
    request: RSVPRequest,
    _auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
) -> RSVPResponse:
    """Handle visitor RSVP (accept/decline) to a calendar invite.

    When a visitor accepts:
      - Updates visit status to CREATED
      - Returns QR code data for n8n to send the confirmation email

    When a visitor declines:
      - Updates visit status to CANCELLED
      - No QR code returned

    Idempotent: if visit is already in final state, returns current state.
    """
    from app.database.repositories.visit_repository import VisitRepository

    repo = VisitRepository()

    # Find the pending visit by external_event_id
    visit = repo.get_visit_by_external_event_id(request.external_event_id)

    if visit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No pending visit found for external_event_id={request.external_event_id}",
        )

    # Verify visitor email matches
    if visit.visitor_email.lower() != request.visitor_email.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Visitor email does not match the pending visit",
        )

    response = request.response.lower()

    if response == "accepted":
        if visit.status in (
            VisitStatus.CREATED,
            VisitStatus.ARRIVED,
            VisitStatus.REGISTERED,
            VisitStatus.APPROVED,
            VisitStatus.ACTIVE,
        ):
            # Already accepted — return current state (idempotent)
            return RSVPResponse(
                success=True,
                visit_id=str(visit.id),
                status=visit.status.value if hasattr(visit.status, "value") else visit.status,
                qr_code=visit.qr_code,
                message="Visit already accepted",
            )

        # Update to CREATED and send QR email
        updated = repo.update_visit(visit.id, {"status": VisitStatus.CREATED})
        logger.info("[RSVP] Visit %s ACCEPTED by %s", visit.id, request.visitor_email)
        try:
            from app.services.visitor_email_service import VisitorEmailService

            email_svc = VisitorEmailService()
            email_svc.send_visitor_confirmation(updated)
        except Exception as exc:
            logger.error("[RSVP] Failed to send QR email for %s: %s", updated.id, exc)
        return RSVPResponse(
            success=True,
            visit_id=str(updated.id),
            status=updated.status.value if hasattr(updated.status, "value") else updated.status,
            qr_code=updated.qr_code,
            message="Visit accepted — confirmation email will be sent",
        )

    elif response == "declined":
        if visit.status == VisitStatus.CANCELLED:
            return RSVPResponse(
                success=True,
                visit_id=str(visit.id),
                status=visit.status.value if hasattr(visit.status, "value") else visit.status,
                qr_code=None,
                message="Visit already declined",
            )

        updated = repo.update_visit(visit.id, {"status": VisitStatus.CANCELLED})
        logger.info("[RSVP] Visit %s DECLINED by %s", visit.id, request.visitor_email)
        return RSVPResponse(
            success=True,
            visit_id=str(updated.id),
            status=updated.status.value if hasattr(updated.status, "value") else updated.status,
            qr_code=None,
            message="Visit declined",
        )

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid response '{request.response}' — must be 'accepted' or 'declined'",
        )


@router.post("/confirm/{token}")
async def confirm_visitor(token: str):
    """Confirm a visitor by token and send QR code — called by concierge when visitor accepts."""
    from uuid import UUID
    from app.database.repositories.visit_repository import VisitRepository

    try:
        visit_uuid = UUID(token)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid token format")

    repo = VisitRepository()
    visit = repo.get_visit_by_token(visit_uuid)

    if not visit:
        raise HTTPException(status_code=404, detail="Visit not found")

    if visit.status != VisitStatus.PENDING:
        return {
            "success": True,
            "message": f"Visit already in status {visit.status}",
            "qr_code": visit.qr_code,
        }

    updated = repo.update_visit(visit.id, {"status": VisitStatus.CREATED})
    email_sent = False
    try:
        from app.services.visitor_email_service import VisitorEmailService
        email_svc = VisitorEmailService()
        email_sent = email_svc.send_visitor_confirmation(updated)
    except Exception as exc:
        logger.error("[Confirm] Failed to send QR email for %s: %s", updated.id, exc)

    return {
        "success": True,
        "visit_id": str(updated.id),
        "pin": updated.pin,
        "qr_code": updated.qr_code,
        "email_sent": email_sent,
        "message": "QR emailed to visitor" if email_sent else "Visit confirmed but email failed — QR below",
    }

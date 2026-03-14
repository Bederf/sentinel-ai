"""REST API endpoints for Space Intelligence (Rev 1.4).

POST /api/space/occupancy-event       — ingest mmWave presence event
GET  /api/space/ghost-findings        — list ghost booking findings
GET  /api/space/rightsizing-findings   — list right-sizing findings
POST /api/space/findings/{id}/dismiss  — dismiss a finding
POST /api/space/findings/{id}/concierge-confirm — legacy empty confirmation
POST /api/space/findings/{id}/inspection-outcome — occupied/empty inspection outcome
GET  /api/space/focus-sessions         — list focus room sessions
GET  /api/space/focus-analytics        — focus room usage analytics
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.core.site_resolver import require_any_site

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/space", tags=["space-intelligence"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class OccupancyEventRequest(BaseModel):
    """Incoming mmWave presence event.

    The ``count`` field is silently ignored if present — LD2410C does not
    provide reliable headcount.
    """

    room_code: str = Field(..., description="Room identifier, e.g. FA1-1Q2-MR4")
    sensor_id: str = Field(..., description="Sensor identifier, e.g. LD2410C-FA1-1Q2-MR4")
    occupied: bool = Field(..., description="True = presence detected")
    source: str = Field(default="mmwave_ld2410c", description="Sensor source type")
    room_type: str = Field(default="meeting", description="Room type: meeting or focus")
    timestamp: datetime | None = Field(default=None, description="Event timestamp (ISO 8601)")
    site_id: str | None = Field(default=None, description="Site code (overrides header)")
    # Radar telemetry (optional — from LD2410C extended payload)
    moving: bool | None = Field(default=None, description="Moving target detected")
    stationary: bool | None = Field(default=None, description="Stationary target detected")
    distance_m: float | None = Field(default=None, description="Distance to target (metres)")
    moving_gate: int | None = Field(default=None, description="Moving target gate (0-8)")
    static_gate: int | None = Field(default=None, description="Static target gate (0-8)")

    class Config:
        extra = "ignore"  # Silently ignore unknown fields like 'count'


class DismissRequest(BaseModel):
    dismissed_by: str = Field(..., description="Who dismissed the finding")


class ConciergeConfirmRequest(BaseModel):
    """Legacy concierge confirmation payload."""

    confirmed_by: str = Field(..., description="Concierge name or ID")
    cost_centre: str = Field(default="", description="Unused legacy field")
    charge_amount: float = Field(default=0.0, description="Unused legacy field")


class InspectionOutcomeRequest(BaseModel):
    confirmed_by: str = Field(..., description="Concierge name or channel identifier")
    occupied: bool = Field(..., description="True if the room is occupied, false if empty")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/occupancy-event")
async def ingest_occupancy_event(
    request: Request,  # noqa: ARG001
    body: OccupancyEventRequest,
    site_id: str = Depends(require_any_site),
) -> dict[str, Any]:
    """Ingest an mmWave presence event and trigger ghost/right-sizing checks.

    If ``count`` is present in the payload, it is silently ignored.
    """
    from app.services.space_event_service import process_occupancy_event

    resolved_site = body.site_id or site_id
    return await process_occupancy_event(
        site_id=resolved_site,
        room_code=body.room_code,
        sensor_id=body.sensor_id,
        occupied=body.occupied,
        source=body.source,
        room_type=body.room_type,
        timestamp=body.timestamp or datetime.utcnow(),
        moving=body.moving,
        stationary=body.stationary,
        distance_m=body.distance_m,
        moving_gate=body.moving_gate,
        static_gate=body.static_gate,
    )


@router.get("/ghost-findings")
async def list_ghost_findings(
    site_id: str = Depends(require_any_site),
    status: str | None = Query(None, description="Filter by status: open, verified_occupied, released, dismissed"),
) -> dict[str, Any]:
    """List ghost booking findings for a site."""
    from app.services.occupancy_store import get_ghost_findings

    findings = get_ghost_findings(site_id, status=status)
    return {
        "findings": [
            {
                "id": f.id,
                "room_code": f.room_code,
                "room_name": f.room_name,
                "booking_id": f.booking_id,
                "organiser_email": f.organiser_email,
                "organiser_name": f.organiser_name,
                "booking_start": f.booking_start.isoformat(),
                "booking_end": f.booking_end.isoformat(),
                "grace_period_minutes": f.grace_period_minutes,
                "detected_at": f.detected_at.isoformat(),
                "status": f.status,
                "notification_sent": f.notification_sent,
                "email_notified_at": f.email_notified_at.isoformat() if f.email_notified_at else None,
                "whatsapp_notified_at": f.whatsapp_notified_at.isoformat() if f.whatsapp_notified_at else None,
                "whatsapp_message_id": f.whatsapp_message_id,
                "response_text": f.response_text,
            }
            for f in findings
        ],
        "count": len(findings),
    }


@router.get("/rightsizing-findings")
async def list_rightsizing_findings(
    site_id: str = Depends(require_any_site),
    status: str | None = Query(None, description="Filter by status: open, acknowledged, dismissed"),
) -> dict[str, Any]:
    """List right-sizing findings for a site."""
    from app.services.occupancy_store import get_rightsizing_findings

    findings = get_rightsizing_findings(site_id, status=status)
    return {
        "findings": [
            {
                "id": f.id,
                "room_code": f.room_code,
                "room_name": f.room_name,
                "room_capacity": f.room_capacity,
                "booking_id": f.booking_id,
                "organiser_email": f.organiser_email,
                "organiser_name": f.organiser_name,
                "booking_start": f.booking_start.isoformat(),
                "booking_end": f.booking_end.isoformat(),
                "booking_duration_minutes": f.booking_duration_minutes,
                "occupied_minutes": f.occupied_minutes,
                "consecutive_vacancy_minutes": f.consecutive_vacancy_minutes,
                "pattern_type": f.pattern_type,
                "detected_at": f.detected_at.isoformat(),
                "status": f.status,
                "notification_sent": f.notification_sent,
            }
            for f in findings
        ],
        "count": len(findings),
    }


@router.post("/findings/{finding_id}/dismiss")
async def dismiss_finding(
    finding_id: str,
    body: DismissRequest,  # noqa: ARG001
) -> dict[str, Any]:
    """Dismiss a ghost or right-sizing finding."""
    from app.services.occupancy_store import (
        update_ghost_finding_status,
        update_rightsizing_finding_status,
    )

    # Try ghost first, then right-sizing
    result = update_ghost_finding_status(finding_id, "dismissed")
    if result:
        return {"success": True, "finding_id": finding_id, "type": "ghost", "status": "dismissed"}

    result = update_rightsizing_finding_status(finding_id, "dismissed")
    if result:
        return {"success": True, "finding_id": finding_id, "type": "rightsizing", "status": "dismissed"}

    raise HTTPException(status_code=404, detail="Finding not found")


@router.post("/findings/{finding_id}/concierge-confirm")
async def concierge_confirm_empty(
    finding_id: str,
    body: ConciergeConfirmRequest,
) -> dict[str, Any]:
    """Legacy endpoint: concierge confirms the room is empty."""
    from app.services.ghost_booking_detector import concierge_confirm_empty as confirm_fn
    from app.services.occupancy_store import get_ghost_finding_by_id

    finding = get_ghost_finding_by_id(finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Ghost finding not found")

    if finding.status not in ("open", "pending_inspection"):
        raise HTTPException(
            status_code=409,
            detail=f"Finding already resolved: status={finding.status}. "
            f"Cannot confirm — room may have been reoccupied.",
        )

    result = confirm_fn(
        finding_id=finding_id,
        confirmed_by=body.confirmed_by,
        cost_centre=body.cost_centre,
        charge_amount=body.charge_amount,
    )

    if not result:
        raise HTTPException(status_code=500, detail="Failed to update finding")

    return {
        "success": True,
        "finding_id": finding_id,
        "status": "confirmed_empty",
        "room_code": result.room_code,
        "room_name": result.room_name,
        "confirmed_by": body.confirmed_by,
        "organiser_email": result.organiser_email,
        "organiser_name": result.organiser_name,
        "message": f"Room {result.room_name} confirmed empty.",
    }


@router.post("/findings/{finding_id}/inspection-outcome")
async def submit_inspection_outcome(
    finding_id: str,
    body: InspectionOutcomeRequest,
) -> dict[str, Any]:
    """Store an occupied/empty ghost-room inspection outcome."""
    from app.services.ghost_booking_detector import concierge_confirm_empty, concierge_confirm_occupied
    from app.services.occupancy_store import get_ghost_finding_by_id

    finding = get_ghost_finding_by_id(finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Ghost finding not found")

    if finding.status not in ("open", "pending_inspection"):
        raise HTTPException(status_code=409, detail=f"Finding already resolved: status={finding.status}")

    if body.occupied:
        result = concierge_confirm_occupied(finding_id, body.confirmed_by)
        message = f"Room {finding.room_code} confirmed occupied."
        status = "verified_occupied"
    else:
        result = concierge_confirm_empty(finding_id, body.confirmed_by)
        message = f"Room {finding.room_code} confirmed empty."
        status = "confirmed_empty"

    if not result:
        raise HTTPException(status_code=500, detail="Failed to update finding")

    return {
        "success": True,
        "finding_id": finding_id,
        "status": status,
        "message": message,
    }


@router.get("/focus-sessions")
async def list_focus_sessions(
    site_id: str = Depends(require_any_site),
    room_code: str | None = Query(None, description="Filter by room code"),
    extended_only: bool = Query(False, description="Only show extended-use sessions"),
) -> dict[str, Any]:
    """List focus room sessions for a site."""
    from app.services import occupancy_store

    if room_code:
        sessions = occupancy_store.get_sessions_for_room(room_code)
        if extended_only:
            sessions = [s for s in sessions if s.extended_use]
    else:
        sessions = occupancy_store.get_sessions_for_site(site_id, extended_only=extended_only)

    return {
        "sessions": [
            {
                "session_id": s.session_id,
                "room_code": s.room_code,
                "room_type": s.room_type,
                "sensor_id": s.sensor_id,
                "start_time": s.start_time.isoformat(),
                "end_time": s.end_time.isoformat() if s.end_time else None,
                "duration_seconds": s.duration_seconds,
                "duration_minutes": round(s.duration_seconds / 60, 1),
                "extended_use": s.extended_use,
                "is_active": s.is_active,
            }
            for s in sessions
        ],
        "count": len(sessions),
    }


@router.get("/focus-analytics")
async def focus_room_analytics(
    site_id: str = Depends(require_any_site),
) -> dict[str, Any]:
    """Get focus room usage analytics for a site."""
    from app.services.focus_room_session_service import get_focus_room_analytics

    return get_focus_room_analytics(site_id)

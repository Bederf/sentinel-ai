"""Event Intelligence API Routes.

Provides endpoints for querying operational events detected by the
EventIntelligenceService. Events are classified telemetry conditions
(temperature deviation, energy spikes, sensor failures, etc.) that
sit between raw telemetry and the reasoning layer.

Phase 145: Operational Event Intelligence.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.middleware.auth_middleware import get_current_auth
from app.models.auth import AuthContext
from app.services.event_intelligence_service import get_event_intelligence_service

logger = logging.getLogger("sentinel.event_intelligence.api")

router = APIRouter(prefix="/api/events", tags=["event-intelligence"])


@router.get("/active")
async def get_active_events(
    site_id: str | None = Query(None, description="Filter by site ID"),
    equipment_id: str | None = Query(None, description="Filter by equipment code"),
    auth: AuthContext | None = Depends(get_current_auth),
) -> dict:
    """Get all currently active (unresolved) operational events.

    Active events represent ongoing conditions that have not yet cleared.
    They include duration tracking and trend analysis.
    """
    service = get_event_intelligence_service()
    events = await service.get_active_events(site_id=site_id, equipment_id=equipment_id)
    return {
        "status": "ok",
        "count": len(events),
        "events": [e.to_dict() for e in events],
    }


@router.get("/active/{site_id}")
async def get_active_events_for_site(
    site_id: str,
    auth: AuthContext | None = Depends(get_current_auth),
) -> dict:
    """Get active operational events for a specific site.

    Returns all unresolved conditions detected for equipment at this site.
    """
    service = get_event_intelligence_service()
    events = await service.get_active_events(site_id=site_id)
    return {
        "status": "ok",
        "site_id": site_id,
        "count": len(events),
        "events": [e.to_dict() for e in events],
    }


@router.get("/summary/{site_id}")
async def get_event_summary(
    site_id: str,
    auth: AuthContext | None = Depends(get_current_auth),
) -> dict:
    """Get event summary for a site — counts by type and severity.

    Useful for dashboard widgets showing operational health at a glance.
    """
    service = get_event_intelligence_service()
    summary = await service.get_event_summary(site_id)
    return {"status": "ok", **summary}


@router.get("/history")
async def get_event_history(
    site_id: str | None = Query(None, description="Filter by site ID"),
    equipment_id: str | None = Query(None, description="Filter by equipment code"),
    event_type: str | None = Query(None, description="Filter by event type"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    auth: AuthContext | None = Depends(get_current_auth),
) -> dict:
    """Query event history with optional filters.

    Returns events from the rolling buffer (most recent first, max 10k).
    """
    service = get_event_intelligence_service()
    events = await service.get_event_history(
        site_id=site_id,
        equipment_id=equipment_id,
        event_type=event_type,
        limit=limit,
    )
    return {
        "status": "ok",
        "count": len(events),
        "events": events,
    }


@router.get("/{event_id}")
async def get_event_detail(
    event_id: str,
    auth: AuthContext | None = Depends(get_current_auth),
) -> dict:
    """Get details for a specific operational event by ID.

    Searches active conditions first, then the history buffer.
    """
    service = get_event_intelligence_service()
    event = await service.get_event_by_id(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
    return {"status": "ok", "event": event}

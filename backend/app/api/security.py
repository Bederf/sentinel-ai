"""Security module API endpoints.

Provides access control monitoring, CCTV camera status, alarm zone management,
badge event tracking, per-zone occupancy, and cross-module recommendations
for HVAC and lighting adjustments based on occupancy levels.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional
import logging

from app.services.security_service import get_security_service
from app.services.security_occupancy_service import get_security_occupancy_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/security", tags=["security"])


# --- Request/Response models ---

class BadgeEventRequest(BaseModel):
    """Request to log a badge event."""
    door_id: str = Field(..., description="Door ID where event occurred")
    zone_id: str = Field(..., description="Zone ID for the door")
    badge_id: str = Field(..., description="Badge ID used")
    person_name: str = Field("", description="Name of badge holder")
    direction: str = Field("entry", description="Direction: entry or exit")
    granted: bool = Field(True, description="Whether access was granted")
    reason: str = Field("", description="Reason for grant/deny")


class ArmAlarmRequest(BaseModel):
    """Request to arm an alarm zone."""
    arm_type: str = Field("full", description="Arm type: full, perimeter, or night")


# --- System status ---

@router.get("/status")
async def get_security_status():
    """Get overall security system status.

    Returns door count, camera count, alarm zone status,
    occupancy total, and active alerts.
    """
    svc = get_security_service()
    status = svc.get_system_status()
    return {
        "total_doors": status.total_doors,
        "doors_secure": status.doors_secure,
        "cameras_online": status.cameras_online,
        "cameras_total": status.cameras_total,
        "alarm_zones_armed": status.alarm_zones_armed,
        "alarm_zones_total": status.alarm_zones_total,
        "active_alerts": status.active_alerts,
        "occupancy_total": status.occupancy_total,
    }


# --- Access zones ---

@router.get("/zones")
async def get_access_zones():
    """Get all access zones with access levels and doors."""
    svc = get_security_service()
    zones = svc.get_access_zones()
    return {
        "zones": [z.model_dump() for z in zones],
        "count": len(zones),
    }


# --- Doors ---

@router.get("/doors")
async def get_all_doors():
    """Get all door status."""
    svc = get_security_service()
    doors = svc.get_doors()
    return {
        "doors": [d.model_dump(mode="json") for d in doors],
        "count": len(doors),
        "secure": sum(1 for d in doors if d.status.value in ("locked", "closed")),
    }


@router.get("/doors/{door_id}")
async def get_door_detail(door_id: str):
    """Get single door status."""
    svc = get_security_service()
    door = svc.get_door_status(door_id)
    if not door:
        raise HTTPException(status_code=404, detail=f"Door {door_id} not found")
    return door.model_dump(mode="json")


# --- Badge events ---

@router.get("/events")
async def get_badge_events(
    zone_id: Optional[str] = Query(None, description="Filter by zone ID"),
    since: Optional[str] = Query(None, description="Filter events since ISO timestamp"),
    limit: int = Query(50, ge=1, le=200, description="Max events to return"),
):
    """Get badge events with optional filtering."""
    svc = get_security_service()
    events = svc.get_recent_badge_events(zone_id=zone_id, limit=limit)
    return {
        "events": [e.model_dump(mode="json") for e in events],
        "count": len(events),
    }


@router.get("/events/denied")
async def get_denied_events():
    """Get denied access events."""
    svc = get_security_service()
    events = svc.get_denied_access_events()
    return {
        "events": [e.model_dump(mode="json") for e in events],
        "count": len(events),
    }


@router.get("/events/after-hours")
async def get_after_hours_events():
    """Get after-hours access events (outside 06:00-20:00)."""
    svc = get_security_service()
    events = svc.get_after_hours_events()
    return {
        "events": [e.model_dump(mode="json") for e in events],
        "count": len(events),
    }


@router.post("/events")
async def log_badge_event(request: BadgeEventRequest):
    """Log a new badge event (demo/test)."""
    svc = get_security_service()
    event_data = {
        "door_id": request.door_id,
        "zone_id": request.zone_id,
        "badge_id": request.badge_id,
        "person_name": request.person_name,
        "direction": request.direction,
        "granted": request.granted,
        "reason": request.reason,
    }
    result = svc.process_badge_event(event_data)
    return result


# --- Cameras ---

@router.get("/cameras")
async def get_all_cameras():
    """Get all cameras with status."""
    svc = get_security_service()
    cameras = svc.get_cameras()
    return {
        "cameras": [c.model_dump(mode="json") for c in cameras],
        "count": len(cameras),
        "online": sum(1 for c in cameras if c.status.value == "online"),
    }


@router.get("/cameras/{camera_id}")
async def get_camera_detail(camera_id: str):
    """Get single camera status."""
    svc = get_security_service()
    camera = svc.get_camera_status(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")
    return camera.model_dump(mode="json")


# --- Alarm zones ---

@router.get("/alarm-zones")
async def get_alarm_zones():
    """Get all alarm zones with status."""
    svc = get_security_service()
    zones = svc.get_alarm_zones()
    return {
        "alarm_zones": [az.model_dump() for az in zones],
        "count": len(zones),
        "armed": sum(1 for az in zones if az.status.value == "armed"),
    }


@router.post("/alarm-zones/{zone_id}/arm")
async def arm_alarm_zone(zone_id: str, request: ArmAlarmRequest):
    """Arm an alarm zone."""
    if request.arm_type not in ("full", "perimeter", "night"):
        raise HTTPException(status_code=400, detail="arm_type must be full, perimeter, or night")
    svc = get_security_service()
    result = svc.arm_alarm_zone(zone_id, request.arm_type)
    return result


@router.post("/alarm-zones/{zone_id}/disarm")
async def disarm_alarm_zone(zone_id: str):
    """Disarm an alarm zone."""
    svc = get_security_service()
    result = svc.disarm_alarm_zone(zone_id)
    return result


@router.post("/alarm-zones/{zone_id}/trigger")
async def trigger_alarm_zone(zone_id: str):
    """Trigger an alarm zone (demo)."""
    svc = get_security_service()
    result = svc.trigger_alarm(zone_id)
    return result


# --- Occupancy ---

@router.get("/occupancy")
async def get_building_occupancy():
    """Get building-wide occupancy from badge data."""
    occ_svc = get_security_occupancy_service()
    result = occ_svc.get_building_occupancy()
    return result


@router.get("/occupancy/recommendations")
async def get_occupancy_recommendations():
    """Get cross-module recommendations based on occupancy.

    Returns HVAC setpoint relaxation and lighting dimming
    suggestions for empty or low-occupancy zones.
    """
    occ_svc = get_security_occupancy_service()
    result = occ_svc.get_all_recommendations()
    return result


@router.get("/occupancy/{zone_id}")
async def get_zone_occupancy(zone_id: str):
    """Get occupancy for a specific zone."""
    occ_svc = get_security_occupancy_service()
    occ = occ_svc.get_zone_occupancy(zone_id)
    return occ.model_dump(mode="json")

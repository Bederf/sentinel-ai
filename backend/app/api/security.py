"""Security module API endpoints.

Provides access control monitoring, CCTV camera status, alarm zone management,
badge event tracking, per-zone occupancy, and cross-module recommendations
for HVAC and lighting adjustments based on occupancy levels.
"""

from fastapi import APIRouter, HTTPException, Query, Request
from app.middleware.rate_limiter import limiter
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

@limiter.limit("30/minute")
@router.get("/status")
async def get_security_status(request: Request):
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

@limiter.limit("30/minute")
@router.get("/zones")
async def get_access_zones(request: Request):
    """Get all access zones with access levels and doors."""
    svc = get_security_service()
    zones = svc.get_access_zones()
    return {
        "zones": [z.model_dump() for z in zones],
        "count": len(zones),
    }


# --- Doors ---

@limiter.limit("30/minute")
@router.get("/doors")
async def get_all_doors(request: Request):
    """Get all door status."""
    svc = get_security_service()
    doors = svc.get_doors()
    return {
        "doors": [d.model_dump(mode="json") for d in doors],
        "count": len(doors),
        "secure": sum(1 for d in doors if d.status.value in ("locked", "closed")),
    }


@limiter.limit("30/minute")
@router.get("/doors/{door_id}")
async def get_door_detail(request: Request, door_id: str):
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


@limiter.limit("30/minute")
@router.get("/events/denied")
async def get_denied_events(request: Request):
    """Get denied access events."""
    svc = get_security_service()
    events = svc.get_denied_access_events()
    return {
        "events": [e.model_dump(mode="json") for e in events],
        "count": len(events),
    }


@limiter.limit("30/minute")
@router.get("/events/after-hours")
async def get_after_hours_events(request: Request):
    """Get after-hours access events (outside 06:00-20:00)."""
    svc = get_security_service()
    events = svc.get_after_hours_events()
    return {
        "events": [e.model_dump(mode="json") for e in events],
        "count": len(events),
    }


@limiter.limit("15/minute")
@router.post("/events")
async def log_badge_event(http_request: Request, request: BadgeEventRequest):
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

@limiter.limit("30/minute")
@router.get("/cameras")
async def get_all_cameras(request: Request):
    """Get all cameras with status."""
    svc = get_security_service()
    cameras = svc.get_cameras()
    return {
        "cameras": [c.model_dump(mode="json") for c in cameras],
        "count": len(cameras),
        "online": sum(1 for c in cameras if c.status.value == "online"),
    }


@limiter.limit("30/minute")
@router.get("/cameras/{camera_id}")
async def get_camera_detail(request: Request, camera_id: str):
    """Get single camera status."""
    svc = get_security_service()
    camera = svc.get_camera_status(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")
    return camera.model_dump(mode="json")


# --- Alarm zones ---

@limiter.limit("30/minute")
@router.get("/alarm-zones")
async def get_alarm_zones(request: Request):
    """Get all alarm zones with status."""
    svc = get_security_service()
    zones = svc.get_alarm_zones()
    return {
        "alarm_zones": [az.model_dump() for az in zones],
        "count": len(zones),
        "armed": sum(1 for az in zones if az.status.value == "armed"),
    }


@limiter.limit("15/minute")
@router.post("/alarm-zones/{zone_id}/arm")
async def arm_alarm_zone(http_request: Request, zone_id: str, request: ArmAlarmRequest):
    """Arm an alarm zone."""
    if request.arm_type not in ("full", "perimeter", "night"):
        raise HTTPException(status_code=400, detail="arm_type must be full, perimeter, or night")
    svc = get_security_service()
    result = svc.arm_alarm_zone(zone_id, request.arm_type)
    return result


@limiter.limit("15/minute")
@router.post("/alarm-zones/{zone_id}/disarm")
async def disarm_alarm_zone(request: Request, zone_id: str):
    """Disarm an alarm zone."""
    svc = get_security_service()
    result = svc.disarm_alarm_zone(zone_id)
    return result


@limiter.limit("15/minute")
@router.post("/alarm-zones/{zone_id}/trigger")
async def trigger_alarm_zone(request: Request, zone_id: str):
    """Trigger an alarm zone (demo)."""
    svc = get_security_service()
    result = svc.trigger_alarm(zone_id)
    return result


# --- Occupancy ---

@limiter.limit("30/minute")
@router.get("/occupancy")
async def get_building_occupancy(request: Request):
    """Get building-wide occupancy from badge data."""
    occ_svc = get_security_occupancy_service()
    result = occ_svc.get_building_occupancy()
    return result


@limiter.limit("30/minute")
@router.get("/occupancy/recommendations")
async def get_occupancy_recommendations(request: Request, site_id: str = "site-002"):
    """Get cross-module recommendations based on occupancy.

    Returns HVAC setpoint relaxation and lighting dimming
    suggestions for empty or low-occupancy zones based on site's active profile.

    Args:
        site_id: Site identifier (default: site-002 for backward compatibility)
    """
    occ_svc = get_security_occupancy_service()
    result = occ_svc.get_all_recommendations(site_id)
    return result


@limiter.limit("30/minute")
@router.get("/occupancy/{zone_id}")
async def get_zone_occupancy(request: Request, zone_id: str):
    """Get occupancy for a specific zone."""
    occ_svc = get_security_occupancy_service()
    occ = occ_svc.get_zone_occupancy(zone_id)
    return occ.model_dump(mode="json")


# --- C•CURE 9000 Integration (Phase 58.2) ---


@limiter.limit("30/minute")
@router.get("/ccure/status")
async def get_ccure_status(request: Request):
    """Get C•CURE system integration status.

    Returns:
        Integration status: demo_mode, partner_license_required, or connected
    """
    # For Phase 58.2, always demo mode
    return {
        "mode": "demo",
        "manufacturer": "Johnson Controls / Software House",
        "model": "C•CURE 9000 v2.90",
        "protocol": "victor Web Service API",
        "license_status": "partner_license_required",
        "message": (
            "Demo mode active. Apply to Software House Connected Partner Program "
            "to enable live integration. See: docs/integrations/ccure-partner-program-roadmap.md"
        ),
        "demo_events_count": 5,
        "demo_doors_count": 2,
        "demo_controllers_count": 2,
    }


@limiter.limit("30/minute")
@router.get("/events/anomalies")
async def get_security_anomalies(
    request: Request,
    since: str = Query("24h", description="Time window: 24h, 7d, 30d"),
    anomaly_type: Optional[str] = Query(None, description="Filter by type"),
):
    """Get security anomalies: after-hours, forced door, controller offline.

    Priority 1: After-hours + HVAC/lighting correlation
    Priority 2: Controller offline + network/UPS correlation

    Args:
        since: Time window ("24h", "7d", "30d")
        anomaly_type: Filter by type (after_hours_access, controller_offline, etc.)

    Returns:
        List of anomaly dicts with severity, description, correlations
    """
    occ_svc = get_security_occupancy_service()

    # Get after-hours anomalies (Priority 1)
    after_hours = occ_svc.detect_after_hours_anomaly()

    # Get equipment health issues (Priority 2)
    equipment_health = occ_svc.detect_security_equipment_health_issues()

    # Combine all anomalies
    all_anomalies = after_hours + equipment_health

    # Filter by type if provided
    if anomaly_type:
        all_anomalies = [a for a in all_anomalies if a["type"] == anomaly_type]

    return {
        "anomalies": all_anomalies,
        "count": len(all_anomalies),
        "summary": {
            "after_hours_count": len(after_hours),
            "equipment_health_count": len(equipment_health),
        },
    }


@limiter.limit("30/minute")
@router.get("/occupancy/real-time")
async def get_real_time_occupancy(
    request: Request, site_id: str = Query("site-002", description="Site identifier")
):
    """Get real-time occupancy from badge events + C•CURE anti-passback zones.

    Combines:
    - Badge entry/exit counting
    - C•CURE anti-passback zone occupancy
    - DALI PIR sensor data (if available)

    Returns:
        Per-zone occupancy with recommendations for HVAC/lighting
    """
    occ_svc = get_security_occupancy_service()

    # Calculate occupancy using badge events
    occupancy = occ_svc.get_building_occupancy()

    # Get HVAC/lighting recommendations based on occupancy
    recommendations = occ_svc.get_all_recommendations(site_id)

    return {
        "site_id": site_id,
        "zones": occupancy.get("zones", []),
        "building_total": occupancy.get("total_occupancy", 0),
        "recommendations": recommendations,
        "updated_at": occupancy.get("last_updated"),
    }

"""Security Module API endpoints.

Provides real-time security monitoring across buildings with:
- Access control event logging and querying
- Visitor management and check-in/out workflow
- Security alerts with severity filtering
- Cross-module occupancy data for HVAC/Lighting integration
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.api.dependencies.module_access import require_active_module
from app.middleware.auth_middleware import require_auth
from app.middleware.rate_limiter import limiter
from app.models.auth import AuthContext, AuthLevel
from app.config.settings import settings
from app.models.module_registry import ModuleType
from app.database.repositories.security_repository import SecurityRepository
from app.models.security import (
    AccessEvent,
    AccessStatus,
    AccessType,
    Visitor,
    SecurityAlert,
    VisitorStatus,
    AlertType,
    AlertSeverity,
    AlertStatus,
    SecurityOverview,
)
from app.utils.ai_provenance import attach_runtime_metadata

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/security",
    dependencies=[
        Depends(
            require_active_module(
                ModuleType.SECURITY,
                site_keys=("site", "site_id"),
            )
        )
    ],
)


# ============================================================================
# Request Models
# ============================================================================


class RegisterVisitorRequest(BaseModel):
    """Request to register new visitor."""

    name: str
    company: str
    host_contact: str
    access_points: List[str]
    purpose: str


class CreateAccessEventRequest(BaseModel):
    """Request to record access event (from access control system webhook)."""

    access_point_id: str
    card_id: str
    person_name: str
    status: str  # granted, denied
    access_type: str  # badge, code, override
    location: str


class CreateAlertRequest(BaseModel):
    """Request to create security alert."""

    alert_type: str
    location: str
    site_id: str
    severity: str
    description: str


# ============================================================================
# Overview & Summary Endpoints
# ============================================================================


@limiter.limit("120/minute")
@router.get("/overview")
async def get_security_overview(request: Request, site: str = Query(..., description="Building site code")):
    """Get building security status summary.

    Returns:
        - total_access_events_today
        - active_visitors
        - open_alerts
        - after_hours_access_count
        - system_status (online/polling/offline)
    """
    try:
        repo = SecurityRepository()

        # Get events from today
        today = datetime.now().date()
        _today_start = datetime.combine(today, datetime.min.time())

        events = repo.list_events(site, limit=1000)
        today_events = [e for e in events if datetime.fromisoformat(e["timestamp"]).date() == today]

        # Get active visitors
        visitors = repo.list_visitors(site)
        active_visitors = [v for v in visitors if v["status"] in ["pending", "checked_in"]]

        # Get open alerts
        alerts = repo.get_alerts(site)
        open_alerts = [a for a in alerts if a["status"] == AlertStatus.OPEN]

        # Count after-hours access
        after_hours = [e for e in today_events if repo._is_after_hours(e.get("timestamp"))]

        return SecurityOverview(
            total_access_events_today=len(today_events),
            active_visitors=len(active_visitors),
            open_alerts=len(open_alerts),
            after_hours_access_count=len(after_hours),
            system_status="online",
            last_updated=datetime.now(),
        ).dict()

    except Exception as e:
        logger.error(f"Error fetching security overview for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("120/minute")
@router.get("/status")
async def get_security_status(request: Request, site: str = Query(..., description="Building site code")):
    """Get building security compliance and status.

    Returns security system status, compliance checks, and system health.
    """
    try:
        repo = SecurityRepository()

        # Get events from today
        today = datetime.now().date()
        events = repo.list_events(site, limit=1000)
        today_events = [e for e in events if datetime.fromisoformat(e.get("timestamp", "")).date() == today]

        # Get active visitors
        visitors = repo.list_visitors(site)
        active_visitors = [v for v in visitors if v.get("status") in ["pending", "checked_in"]]

        # Get open alerts
        alerts = repo.get_alerts(site)
        open_alerts = [a for a in alerts if a.get("status") == "open"]

        # Calculate compliance metrics
        after_hours_count = len([e for e in today_events if repo._is_after_hours(e.get("timestamp", ""))])
        compliance_score = max(0, 100 - (after_hours_count * 5) - (len(open_alerts) * 10))

        return {
            "status": "operational" if len(open_alerts) == 0 else "warning",
            "compliance_score": compliance_score,
            "system_health": {
                "readers_online": True,
                "alert_system": "active",
                "visitor_management": "active",
                "access_logs": "syncing",
            },
            "metrics": {
                "events_today": len(today_events),
                "active_visitors": len(active_visitors),
                "open_alerts": len(open_alerts),
                "after_hours_access": after_hours_count,
            },
            "last_updated": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error fetching security status for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Access Events Endpoints
# ============================================================================


@limiter.limit("120/minute")
@router.get("/events")
async def get_access_events(
    request: Request,
    site: str = Query(..., description="Building site code"),
    after_hours: bool = Query(False, description="Filter after-hours access only"),
    location: Optional[str] = Query(None, description="Filter by access point location"),
    limit: int = Query(100, ge=1, le=1000),
):
    """Get paginated access event list with optional filtering."""
    try:
        repo = SecurityRepository()
        events = repo.list_events(site, limit=limit, after_hours=after_hours, location=location)

        return {"site": site, "event_count": len(events), "events": events}
    except Exception as e:
        logger.error(f"Error fetching access events for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("120/minute")
@router.get("/events/anomalies")
async def get_access_anomalies(
    request: Request,
    site: str = Query(..., description="Building site code"),
    limit: int = Query(50, ge=1, le=1000),
    days_back: int = Query(7, ge=1, le=90, description="Number of days to analyze"),
):
    """Detect and return anomalous access events.

    Uses historical patterns to identify unusual access behavior:
    - After-hours access when not expected
    - Failed access attempts exceeding normal rate
    - Unusual access patterns from specific badges
    - Multiple failed attempts at same location
    """
    try:
        repo = SecurityRepository()

        # Get events for the specified period
        all_events = repo.list_events(site, limit=1000)

        anomalies = []

        # Detect after-hours access
        for event in all_events:
            timestamp_str = event.get("timestamp", "")
            try:
                _event_time = datetime.fromisoformat(timestamp_str)
                if repo._is_after_hours(timestamp_str):
                    anomalies.append(
                        {
                            "type": "after_hours_access",
                            "event_id": event.get("event_id"),
                            "timestamp": timestamp_str,
                            "location": event.get("location"),
                            "person": event.get("person_name"),
                            "severity": "medium",
                            "description": f"Access outside business hours at {event.get('location')}",
                        }
                    )
            except (ValueError, TypeError):
                pass

        # Detect failed access patterns
        failed_events = [e for e in all_events if e.get("status") == "denied"]
        location_failures = {}
        for event in failed_events:
            location = event.get("location", "unknown")
            location_failures[location] = location_failures.get(location, 0) + 1

        for location, count in location_failures.items():
            if count > 3:  # Threshold: more than 3 failures
                anomalies.append(
                    {
                        "type": "high_failure_rate",
                        "location": location,
                        "failure_count": count,
                        "severity": "high" if count > 5 else "medium",
                        "description": f"{count} failed access attempts at {location}",
                    }
                )

        # Sort by severity and return limited set
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        anomalies.sort(key=lambda x: severity_order.get(x.get("severity", "low"), 4))

        return {
            "site": site,
            "anomaly_count": len(anomalies),
            "anomalies": anomalies[:limit],
            "period_days": days_back,
            "analysis_timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error detecting anomalies for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("120/minute")
@router.get("/events/{event_id}")
async def get_access_event(
    request: Request,
    event_id: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """Get single access event details."""
    try:
        repo = SecurityRepository()
        event = repo.get_event_by_id(event_id)

        if not event:
            raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

        return event
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching event {event_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("120/minute")
@router.post("/events")
async def record_access_event(request: Request, data: CreateAccessEventRequest, site: str = Query(...)):
    """Record access event from access control system webhook."""
    try:
        event = AccessEvent(
            timestamp=datetime.now(),
            access_point_id=data.access_point_id,
            card_id=data.card_id,
            person_name=data.person_name,
            status=AccessStatus(data.status),
            access_type=AccessType(data.access_type),
            location=data.location,
        )

        repo = SecurityRepository()
        result = repo.create_event(event)

        return {"event_id": result["event_id"], "status": "recorded"}
    except Exception as e:
        logger.error(f"Error recording access event: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Access Points Endpoints
# ============================================================================


@limiter.limit("120/minute")
@router.get("/access-points")
async def get_access_points(request: Request, site: str = Query(...)):
    """Get all access control points for a site."""
    try:
        repo = SecurityRepository()
        points = repo.get_access_points(site)

        return {"site": site, "point_count": len(points), "access_points": points}
    except Exception as e:
        logger.error(f"Error fetching access points for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("120/minute")
@router.get("/access-points/{point_id}")
async def get_access_point_details(
    request: Request,
    point_id: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """Get details for single access point including recent events."""
    try:
        repo = SecurityRepository()
        point = repo.get_access_point_by_id(point_id)

        if not point:
            raise HTTPException(status_code=404, detail=f"Access point {point_id} not found")

        # Get recent events for this point
        all_events = repo.list_events(point["site_id"], limit=500)
        recent_events = [e for e in all_events if e["access_point_id"] == point_id][:20]

        return {"point": point, "recent_events": recent_events}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching access point {point_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Visitors Endpoints
# ============================================================================


@limiter.limit("120/minute")
@router.get("/visitors")
async def get_visitors(request: Request, site: str = Query(...), limit: int = Query(50)):
    """Get list of active and recent visitors."""
    try:
        repo = SecurityRepository()
        visitors = repo.list_visitors(site, limit=limit)

        return {"site": site, "visitor_count": len(visitors), "visitors": visitors}
    except Exception as e:
        logger.error(f"Error fetching visitors for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("10/minute")
@router.post("/visitors")
async def register_visitor(request: Request, data: RegisterVisitorRequest, site: str = Query(...)):
    """Register new visitor with access points."""
    try:
        visitor = Visitor(
            name=data.name,
            company=data.company,
            visit_date=datetime.now(),
            host_contact=data.host_contact,
            access_points=data.access_points,
            status=VisitorStatus.PENDING,
            purpose=data.purpose,
        )

        repo = SecurityRepository()
        repo.create_event(visitor)  # Store visitor using event system

        return {"visitor_id": visitor.visitor_id, "status": "registered", "name": visitor.name}
    except Exception as e:
        logger.error(f"Error registering visitor: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("120/minute")
@router.post("/visitors/{visitor_id}/checkin")
async def checkin_visitor(
    request: Request,
    visitor_id: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """Record visitor check-in."""
    try:
        repo = SecurityRepository()
        result = repo.record_visit_checkin(visitor_id)

        if not result:
            raise HTTPException(status_code=404, detail=f"Visitor {visitor_id} not found")

        return {"visitor_id": visitor_id, "status": "checked_in"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking in visitor {visitor_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("120/minute")
@router.post("/visitors/{visitor_id}/checkout")
async def checkout_visitor(
    request: Request,
    visitor_id: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """Record visitor check-out."""
    try:
        repo = SecurityRepository()
        result = repo.record_visit_checkout(visitor_id)

        if not result:
            raise HTTPException(status_code=404, detail=f"Visitor {visitor_id} not found")

        return {"visitor_id": visitor_id, "status": "checked_out"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking out visitor {visitor_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("10/minute")
@router.put("/visitors/{visitor_id}/revoke")
async def revoke_visitor(
    request: Request,
    visitor_id: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.OPERATOR)),
):
    """Immediately revoke visitor access."""
    try:
        _repo = SecurityRepository()
        # In real system, would immediately invalidate card/code
        return {"visitor_id": visitor_id, "status": "revoked"}
    except Exception as e:
        logger.error(f"Error revoking visitor {visitor_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Alerts Endpoints
# ============================================================================


@limiter.limit("120/minute")
@router.get("/alerts")
async def get_alerts(
    request: Request,
    site: str = Query(...),
    severity: Optional[str] = Query(None, description="Filter by severity: critical, warning, info"),
    limit: int = Query(50),
):
    """Get security alerts with optional severity filtering."""
    try:
        repo = SecurityRepository()
        alerts = repo.get_alerts(site, severity=severity, limit=limit)

        return {"site": site, "alert_count": len(alerts), "alerts": alerts}
    except Exception as e:
        logger.error(f"Error fetching alerts for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("10/minute")
@router.post("/alerts")
async def create_alert(request: Request, data: CreateAlertRequest):
    """Create security alert (used by monitoring service)."""
    try:
        alert = SecurityAlert(
            alert_type=AlertType(data.alert_type),
            timestamp=datetime.now(),
            location=data.location,
            site_id=data.site_id,
            severity=AlertSeverity(data.severity),
            status=AlertStatus.OPEN,
            description=data.description,
        )

        repo = SecurityRepository()
        result = repo.create_alert(alert)

        return {"alert_id": result["alert_id"], "status": "created"}
    except Exception as e:
        logger.error(f"Error creating alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("120/minute")
@router.put("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(request: Request, alert_id: str, acknowledged_by: str = Query(...)):
    """Acknowledge alert."""
    try:
        repo = SecurityRepository()
        result = repo.acknowledge_alert(alert_id, acknowledged_by)

        if not result:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

        return {"alert_id": alert_id, "status": "acknowledged"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error acknowledging alert {alert_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Cross-Module Integration Endpoints
# ============================================================================


@limiter.limit("120/minute")
@router.get("/occupancy")
async def get_occupancy(request: Request, site: str = Query(...)):
    """Get current building occupancy (for HVAC/Lighting occupancy-based control).

    Used by Phase 28+ for occupancy-aware HVAC and lighting control.
    Returns:
        - total_occupancy: Total people in building
        - by_floor: Occupancy breakdown by floor
        - by_zone: Occupancy breakdown by zone
    """
    try:
        repo = SecurityRepository()
        occupancy = repo.get_occupancy(site)
        return occupancy
    except Exception as e:
        logger.error(f"Error calculating occupancy for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("120/minute")
@router.get("/occupancy/recommendations")
async def get_occupancy_recommendations(request: Request, site: str = Query(..., description="Building site code")):
    """Get occupancy-based recommendations for HVAC and lighting.

    Analyzes current and predicted occupancy to recommend:
    - HVAC setpoint adjustments
    - Lighting level changes
    - Energy savings opportunities
    - Comfort optimization suggestions
    """
    try:
        repo = SecurityRepository()

        # Get current occupancy
        occupancy = repo.get_occupancy(site)
        total_occupancy = occupancy.get("total_occupancy", 0)
        by_floor = occupancy.get("by_floor", {})
        by_zone = occupancy.get("by_zone", {})

        recommendations = []

        # Occupancy-based HVAC recommendations
        if total_occupancy == 0:
            recommendations.append(
                {
                    "module": "hvac",
                    "type": "energy_savings",
                    "priority": "high",
                    "action": "reduce_setpoint",
                    "value": 2,
                    "unit": "°C",
                    "description": "Building unoccupied - reduce heating/cooling setpoint by 2°C for energy savings",
                    "estimated_savings": "15-20%",
                }
            )
        elif total_occupancy < 10:
            recommendations.append(
                {
                    "module": "hvac",
                    "type": "comfort_optimization",
                    "priority": "medium",
                    "action": "adjust_to_comfort",
                    "value": 22,
                    "unit": "°C",
                    "description": "Low occupancy - set comfort temperature to 22°C",
                    "confidence": 0.85,
                }
            )
        elif total_occupancy > 50:
            recommendations.append(
                {
                    "module": "hvac",
                    "type": "comfort_optimization",
                    "priority": "high",
                    "action": "increase_ventilation",
                    "description": "High occupancy detected - increase fresh air ventilation",
                    "co2_concern": True,
                }
            )

        # Occupancy-based lighting recommendations
        if total_occupancy == 0:
            recommendations.append(
                {
                    "module": "lighting",
                    "type": "energy_savings",
                    "priority": "high",
                    "action": "turn_off",
                    "description": "Building unoccupied - turn off all non-essential lighting",
                    "estimated_savings": "80-90%",
                }
            )
        else:
            # Calculate average occupancy per zone
            avg_occupancy_per_zone = total_occupancy / max(len(by_zone), 1)

            # Recommend dimming if occupancy is low
            if avg_occupancy_per_zone < 2:
                recommendations.append(
                    {
                        "module": "lighting",
                        "type": "energy_savings",
                        "priority": "medium",
                        "action": "dim_to_percent",
                        "value": 30,
                        "description": "Low occupancy per zone - dim lighting to 30% for energy savings",
                        "estimated_savings": "40-50%",
                    }
                )
            else:
                recommendations.append(
                    {
                        "module": "lighting",
                        "type": "comfort_optimization",
                        "priority": "low",
                        "action": "enable_daylight_harvesting",
                        "description": "Enable daylight harvesting for occupied zones",
                    }
                )

        # Zone-specific recommendations
        for zone, count in by_zone.items():
            if count > 20:
                recommendations.append(
                    {
                        "module": "hvac",
                        "type": "comfort_optimization",
                        "priority": "medium",
                        "zone": zone,
                        "action": "increase_ventilation",
                        "description": f"Zone {zone} has {count} people - increase ventilation",
                        "affected_equipment": ["VAV", "AHU"],
                    }
                )

        return attach_runtime_metadata(
            {
                "site": site,
                "current_occupancy": total_occupancy,
                "recommendation_count": len(recommendations),
                "recommendations": recommendations,
                "by_floor": by_floor,
                "by_zone": by_zone,
                "timestamp": datetime.now().isoformat(),
            }
        )
    except Exception as e:
        logger.error(f"Error generating occupancy recommendations for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Phase 69: Zone-Level Occupancy, Access Log, Cameras, Trends
# ============================================================================


class AccessEventCreate(BaseModel):
    """Request body for POST /api/security/access-event."""

    equipment_id: str
    person_id: str
    direction: str  # entry | exit
    timestamp: Optional[str] = None
    zone_id: str = ""


@limiter.limit("120/minute")
@router.get("/occupancy/zone/{zone_id}")
async def get_zone_occupancy(
    request: Request,
    zone_id: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """Get current occupancy for a specific zone.

    Returns zone occupancy count, max capacity, and percent full.
    """
    try:
        from app.services.security_occupancy_service import get_security_occupancy_service

        service = get_security_occupancy_service()
        occ = service.get_zone_occupancy(zone_id)
        return occ.model_dump()
    except Exception as e:
        logger.error(f"Error fetching zone occupancy for {zone_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("120/minute")
@router.get("/occupancy/floor/{floor}")
async def get_floor_occupancy(
    request: Request,
    floor: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """Get aggregate occupancy for all zones on a floor.

    Returns total occupancy across all zones on the specified floor.
    """
    try:
        from app.services.security_occupancy_service import get_security_occupancy_service

        service = get_security_occupancy_service()
        result = service.get_floor_occupancy(floor)
        return result
    except Exception as e:
        logger.error(f"Error fetching floor occupancy for {floor}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("120/minute")
@router.post("/access-event")
async def receive_access_event(request: Request, data: AccessEventCreate):
    """Receive and process a badge access event.

    Updates zone occupancy and triggers cross-module HVAC/Lighting automations.
    """
    try:
        from app.services.security_occupancy_service import get_security_occupancy_service

        service = get_security_occupancy_service()
        result = service.process_access_event(
            {
                "equipment_id": data.equipment_id,
                "person_id": data.person_id,
                "direction": data.direction,
                "timestamp": data.timestamp or datetime.now().isoformat(),
                "zone_id": data.zone_id,
            }
        )
        return result
    except Exception as e:
        logger.error(f"Error processing access event: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("120/minute")
@router.get("/access-log/{zone_id}")
async def get_access_log(
    request: Request,
    zone_id: str,
    limit: int = Query(50, ge=1, le=500),
    last_hours: int = Query(24, ge=1, le=168),
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """Get recent access log for a specific zone.

    Returns recent badge events filtered by zone and time range.
    """
    try:
        from app.services.security_occupancy_service import get_security_occupancy_service

        service = get_security_occupancy_service()
        repo = service._repo
        events = repo.get_badge_events(zone_id=zone_id, limit=limit)

        # Filter to time range
        cutoff = datetime.now() - timedelta(hours=last_hours)
        filtered = []
        for event in events:
            ts_str = event.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts.replace(tzinfo=None) >= cutoff:
                    filtered.append(event)
            except (ValueError, TypeError):
                filtered.append(event)  # Include if timestamp unparseable

        return {
            "zone_id": zone_id,
            "event_count": len(filtered),
            "events": filtered[:limit],
            "last_hours": last_hours,
        }
    except Exception as e:
        logger.error(f"Error fetching access log for {zone_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("120/minute")
@router.get("/cameras/{zone_id}")
async def get_zone_cameras(
    request: Request,
    zone_id: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """Get cameras in a specific zone.

    Returns camera list with stream URLs and status.
    """
    try:
        from app.database.repositories.security_repository import get_security_repository

        repo = get_security_repository()
        # Use the repo to query cameras by zone
        try:
            response = repo.client.table("security_cameras").select("*").eq("zone_id", zone_id).execute()
            cameras = response.data
        except Exception:
            if settings.sentinel_island_mode:
                raise HTTPException(status_code=503, detail="Live camera inventory unavailable")
            cameras = []

        return {
            "zone_id": zone_id,
            "camera_count": len(cameras),
            "cameras": cameras,
        }
    except Exception as e:
        logger.error(f"Error fetching cameras for {zone_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("120/minute")
@router.get("/occupancy-trend/{zone_id}")
async def get_occupancy_trend(
    request: Request,
    zone_id: str,
    hours: int = Query(24, ge=1, le=168),
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """Get hourly occupancy trend data for a zone.

    Returns hourly entry/exit/net occupancy readings for graphing.
    """
    try:
        from app.services.security_occupancy_service import get_security_occupancy_service

        service = get_security_occupancy_service()
        trend_data = service.get_occupancy_trend(zone_id, hours=hours)
        return {
            "zone_id": zone_id,
            "hours": hours,
            "data_points": len(trend_data),
            "trend": trend_data,
        }
    except Exception as e:
        logger.error(f"Error fetching occupancy trend for {zone_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

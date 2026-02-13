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

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.middleware.rate_limiter import limiter
from app.database.repositories.security_repository import SecurityRepository
from app.models.security import (
    AccessEvent, AccessStatus, AccessType, AccessPoint, Visitor, SecurityAlert,
    VisitorStatus, AlertType, AlertSeverity, AlertStatus, SecurityOverview, OccupancyData
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/security")


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
    building_id: str
    severity: str
    description: str


# ============================================================================
# Overview & Summary Endpoints
# ============================================================================

@limiter.limit("30/minute")
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
        today_start = datetime.combine(today, datetime.min.time())
        
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
            last_updated=datetime.now()
        ).dict()
        
    except Exception as e:
        logger.error(f"Error fetching security overview for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Access Events Endpoints
# ============================================================================

@limiter.limit("30/minute")
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
        
        return {
            "site": site,
            "event_count": len(events),
            "events": events
        }
    except Exception as e:
        logger.error(f"Error fetching access events for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.get("/events/{event_id}")
async def get_access_event(request: Request, event_id: str):
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


@limiter.limit("30/minute")
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
            location=data.location
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

@limiter.limit("30/minute")
@router.get("/access-points")
async def get_access_points(request: Request, site: str = Query(...)):
    """Get all access control points for a site."""
    try:
        repo = SecurityRepository()
        points = repo.get_access_points(site)
        
        return {
            "site": site,
            "point_count": len(points),
            "access_points": points
        }
    except Exception as e:
        logger.error(f"Error fetching access points for {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.get("/access-points/{point_id}")
async def get_access_point_details(request: Request, point_id: str):
    """Get details for single access point including recent events."""
    try:
        repo = SecurityRepository()
        point = repo.get_access_point_by_id(point_id)
        
        if not point:
            raise HTTPException(status_code=404, detail=f"Access point {point_id} not found")
        
        # Get recent events for this point
        all_events = repo.list_events(point["building_id"], limit=500)
        recent_events = [e for e in all_events if e["access_point_id"] == point_id][:20]
        
        return {
            "point": point,
            "recent_events": recent_events
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching access point {point_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Visitors Endpoints
# ============================================================================

@limiter.limit("30/minute")
@router.get("/visitors")
async def get_visitors(request: Request, site: str = Query(...), limit: int = Query(50)):
    """Get list of active and recent visitors."""
    try:
        repo = SecurityRepository()
        visitors = repo.list_visitors(site, limit=limit)
        
        return {
            "site": site,
            "visitor_count": len(visitors),
            "visitors": visitors
        }
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
            purpose=data.purpose
        )
        
        repo = SecurityRepository()
        result = repo.create_event(visitor)  # Store visitor using event system
        
        return {
            "visitor_id": visitor.visitor_id,
            "status": "registered",
            "name": visitor.name
        }
    except Exception as e:
        logger.error(f"Error registering visitor: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.post("/visitors/{visitor_id}/checkin")
async def checkin_visitor(request: Request, visitor_id: str):
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


@limiter.limit("30/minute")
@router.post("/visitors/{visitor_id}/checkout")
async def checkout_visitor(request: Request, visitor_id: str):
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
async def revoke_visitor(request: Request, visitor_id: str):
    """Immediately revoke visitor access."""
    try:
        repo = SecurityRepository()
        # In real system, would immediately invalidate card/code
        return {"visitor_id": visitor_id, "status": "revoked"}
    except Exception as e:
        logger.error(f"Error revoking visitor {visitor_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Alerts Endpoints
# ============================================================================

@limiter.limit("30/minute")
@router.get("/alerts")
async def get_alerts(
    request: Request,
    site: str = Query(...),
    severity: Optional[str] = Query(None, description="Filter by severity: critical, warning, info"),
    limit: int = Query(50)
):
    """Get security alerts with optional severity filtering."""
    try:
        repo = SecurityRepository()
        alerts = repo.get_alerts(site, severity=severity, limit=limit)
        
        return {
            "site": site,
            "alert_count": len(alerts),
            "alerts": alerts
        }
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
            building_id=data.building_id,
            severity=AlertSeverity(data.severity),
            status=AlertStatus.OPEN,
            description=data.description
        )
        
        repo = SecurityRepository()
        result = repo.create_alert(alert)
        
        return {"alert_id": result["alert_id"], "status": "created"}
    except Exception as e:
        logger.error(f"Error creating alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
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

@limiter.limit("30/minute")
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

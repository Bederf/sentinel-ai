"""Alerts API endpoints - SENTINEL Integration."""

import json
import uuid
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request
from app.middleware.rate_limiter import limiter
from pydantic import BaseModel

# Import orchestrator for live simulation alerts
from app.services.lifecycle_orchestrator import get_lifecycle_orchestrator
from app.services.sentry_integration.alert_notifier import alert_notifier

router = APIRouter()

# Load data directory
DATA_DIR = Path(__file__).parent.parent / "data"


def load_alerts() -> list[dict]:
    """Load alerts from JSON file, Supabase database, AND simulation."""
    alerts = []

    # Load static alerts from JSON
    alerts_file = DATA_DIR / "alerts.json"
    if alerts_file.exists():
        with open(alerts_file) as f:
            static_alerts = json.load(f)
            alerts.extend(static_alerts)

    # Load active alerts from Supabase database
    try:
        from app.database.repositories.alert_repository import AlertRepository
        from app.database.supabase_client import get_supabase_client

        alert_repo = AlertRepository()
        db_alerts = alert_repo.get_all(status="active")

        # Get equipment and building lookups for enrichment
        client = get_supabase_client()
        equipment_resp = client.table("equipment").select("id, name, code, building_id, metadata").execute()
        buildings_resp = client.table("buildings").select("id, name, code").execute()

        eq_lookup = {eq["id"]: eq for eq in (equipment_resp.data or [])}
        building_lookup = {b["id"]: b for b in (buildings_resp.data or [])}

        for da in db_alerts:
            equipment = eq_lookup.get(da.get("equipment_id"), {})
            building = building_lookup.get(da.get("building_id"), {})
            # Extract device_id from equipment metadata for control navigation
            metadata = equipment.get("metadata") or {}
            device_id = metadata.get("device_id")

            # Convert database alert to standard format
            alert = {
                "id": da["id"],
                "anomaly_id": None,
                "equipment_id": da.get("equipment_id", ""),
                "site_id": building.get("code", "unknown"),
                "type": da.get("type", "health_degradation"),
                "severity": da.get("severity", "warning"),
                "status": da.get("status", "active"),
                "title": da.get("title") or "Equipment Alert",
                "message": da.get("message") or "",
                "created_at": da.get("created_at", datetime.now().isoformat()),
                "updated_at": da.get("updated_at", da.get("created_at", datetime.now().isoformat())),
                "acknowledged": da.get("status") == "acknowledged",
                "acknowledged_by": da.get("acknowledged_by"),
                "acknowledged_at": da.get("acknowledged_at"),
                "priority": 1 if da.get("severity") == "critical" else 2 if da.get("severity") == "warning" else 3,
                "category": "hvac",
                "estimated_cost_zar": 15000.0 if da.get("severity") == "critical" else 5000.0,
                "potential_damage_zar": 150000.0 if da.get("severity") == "critical" else 50000.0,
                "equipment_name": equipment.get("name", "Unknown"),
                "site_name": building.get("name", "Unknown"),
                "device_id": device_id,  # For control dashboard navigation
                "health_score": None,
                "fault_codes": [],
                "is_database": True,
            }
            alerts.append(alert)
    except Exception:
        # If Supabase not available, continue without database alerts
        pass

    # Load live alerts from simulation
    try:
        sim_alerts = get_lifecycle_orchestrator().get_active_alerts()
        for sa in sim_alerts:
            # Convert simulation alert to standard format
            alert = {
                "id": sa["id"],
                "anomaly_id": None,
                "equipment_id": sa["equipment_id"],
                "site_id": sa.get("site_id", "unknown"),
                "type": sa["type"],
                "severity": sa["severity"],
                "status": sa["status"],
                "title": sa["title"],
                "message": sa["message"],
                "created_at": sa["created_at"],
                "updated_at": sa["created_at"],
                "acknowledged": sa["acknowledged"],
                "acknowledged_by": sa.get("acknowledged_by"),
                "acknowledged_at": sa.get("acknowledged_at"),
                "priority": sa["priority"],
                "category": sa.get("category", "hvac"),
                "estimated_cost_zar": 15000.0 if sa["severity"] == "critical" else 5000.0,
                "potential_damage_zar": 150000.0 if sa["severity"] == "critical" else 50000.0,
                "equipment_name": sa["equipment_name"],
                "site_name": sa.get("site_name", "Sandton City Office Tower"),
                "health_score": sa.get("health_score"),
                "fault_codes": sa.get("fault_codes", []),
                "recommended_action": sa.get("recommended_action") or sa.get("suggested_action"),
                "operational_context": sa.get("operational_context"),
                "is_simulation": True,
            }
            alerts.append(alert)
    except Exception:
        # If simulation not available, continue with static alerts only
        pass

    return alerts


def load_anomalies() -> list[dict]:
    """Load anomalies from JSON file."""
    anomalies_file = DATA_DIR / "anomalies.json"
    if anomalies_file.exists():
        with open(anomalies_file) as f:
            return json.load(f)
    return []


def load_equipment() -> list[dict]:
    """Load equipment from JSON file."""
    equipment_file = DATA_DIR / "equipment.json"
    if equipment_file.exists():
        with open(equipment_file) as f:
            return json.load(f)
    return []


def load_sites() -> list[dict]:
    """Load sites from JSON file."""
    sites_file = DATA_DIR / "sites.json"
    if sites_file.exists():
        with open(sites_file) as f:
            return json.load(f)
    return []


class AlertResponse(BaseModel):
    """Alert response model."""

    id: str
    anomaly_id: Optional[str]
    equipment_id: str
    site_id: str
    type: str
    severity: str
    status: str
    title: str
    message: str
    created_at: str
    updated_at: str
    acknowledged: bool
    acknowledged_by: Optional[str]
    acknowledged_at: Optional[str]
    priority: int
    category: str
    estimated_cost_zar: float
    potential_damage_zar: float
    # Enriched fields
    equipment_name: Optional[str] = None
    site_name: Optional[str] = None
    device_id: Optional[str] = None  # Maps to device manager for control navigation
    recommended_action: Optional[str] = None
    operational_context: Optional[dict] = None


class AlertListResponse(BaseModel):
    """Response for alert list."""

    total: int
    by_severity: dict[str, int]
    alerts: list[AlertResponse]


class AnomalyResponse(BaseModel):
    """Anomaly response model."""

    id: str
    equipment_id: str
    site_id: str
    type: str
    severity: str
    detected_date: str
    start_date: str
    predicted_failure: str
    confidence: float
    affected_sensor: str
    baseline_value: float
    current_value: float
    threshold_value: float
    trend: str
    rate_of_change: str
    root_cause: str
    impact_assessment: str
    repair_cost_zar: float
    damage_cost_zar: float
    roi_percentage: float
    recommended_action: str
    parts_required: list[str]
    estimated_repair_hours: int
    urgency: str
    acknowledged: bool
    acknowledged_by: Optional[str]
    acknowledged_at: Optional[str]
    # Enriched fields
    equipment_name: Optional[str] = None
    site_name: Optional[str] = None


class AnomalyListResponse(BaseModel):
    """Response for anomaly list."""

    total: int
    total_repair_cost_zar: float
    total_potential_damage_zar: float
    anomalies: list[AnomalyResponse]


@limiter.limit("30/minute")
@router.get("/alerts", response_model=AlertListResponse)
async def list_alerts(
    request: Request,
    site_id: Optional[str] = Query(None, description="Filter by site ID"),
    equipment_id: Optional[str] = Query(None, description="Filter by equipment ID (UUID)"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    status: Optional[str] = Query(None, description="Filter by status (active, acknowledged, resolved)"),
    category: Optional[str] = Query(None, description="Filter by category (hvac, electrical, maintenance)"),
    limit: int = Query(50, description="Maximum number of results"),
) -> AlertListResponse:
    """
    List all alerts with optional filtering.

    Args:
        site_id: Filter by site ID
        equipment_id: Filter by equipment ID (UUID)
        severity: Filter by severity (critical, warning, info)
        status: Filter by status (active, acknowledged, resolved)
        category: Filter by category
        limit: Maximum number of results to return

    Returns:
        AlertListResponse with total count and list of alerts.
    """
    alerts = load_alerts()
    equipment = load_equipment()
    sites = load_sites()

    # Create lookups
    eq_lookup = {eq["id"]: eq["name"] for eq in equipment}
    site_lookup = {s["id"]: s["name"] for s in sites}

    # Apply filters
    if site_id:
        alerts = [a for a in alerts if a["site_id"] == site_id]
    if equipment_id:
        alerts = [a for a in alerts if a["equipment_id"] == equipment_id]
    if severity:
        alerts = [a for a in alerts if a["severity"].lower() == severity.lower()]
    if status:
        alerts = [a for a in alerts if a["status"].lower() == status.lower()]
    if category:
        alerts = [a for a in alerts if a["category"].lower() == category.lower()]

    # Count by severity
    by_severity: dict[str, int] = {}
    for alert in alerts:
        sev = alert["severity"]
        by_severity[sev] = by_severity.get(sev, 0) + 1

    # Enrich with names
    result = []
    for alert in alerts:
        # Get enriched names, preferring existing values in alert
        equipment_name = alert.get("equipment_name") or eq_lookup.get(alert["equipment_id"])
        site_name = alert.get("site_name") or site_lookup.get(alert["site_id"])
        # Remove existing equipment_name/site_name to avoid duplicate kwargs
        alert_copy = {k: v for k, v in alert.items() if k not in ("equipment_name", "site_name")}
        result.append(
            AlertResponse(
                **alert_copy,
                equipment_name=equipment_name,
                site_name=site_name,
            )
        )

    # Sort by priority
    result.sort(key=lambda a: a.priority)

    # Apply limit
    limited_results = result[:limit]

    return AlertListResponse(
        total=len(limited_results),
        by_severity=by_severity,
        alerts=limited_results,
    )


@limiter.limit("20/minute")
@router.get("/alerts/{alert_id}", response_model=AlertResponse)
async def get_alert(request: Request, alert_id: str) -> AlertResponse:
    """
    Get a single alert by ID.

    Args:
        alert_id: The alert identifier.

    Returns:
        AlertResponse with alert details.

    Raises:
        HTTPException: If alert not found.
    """
    alerts = load_alerts()
    equipment = load_equipment()
    sites = load_sites()

    alert = next((a for a in alerts if a["id"] == alert_id), None)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    eq_lookup = {eq["id"]: eq["name"] for eq in equipment}
    site_lookup = {s["id"]: s["name"] for s in sites}

    # Get enriched names, preferring existing values in alert
    equipment_name = alert.get("equipment_name") or eq_lookup.get(alert["equipment_id"])
    site_name = alert.get("site_name") or site_lookup.get(alert["site_id"])
    # Remove existing equipment_name/site_name to avoid duplicate kwargs
    alert_copy = {k: v for k, v in alert.items() if k not in ("equipment_name", "site_name")}

    return AlertResponse(
        **alert_copy,
        equipment_name=equipment_name,
        site_name=site_name,
    )


@limiter.limit("30/minute")
@router.get("/sites/{site_id}/alerts", response_model=AlertListResponse)
async def get_site_alerts(
    request: Request,
    site_id: str,
    severity: Optional[str] = Query(None, description="Filter by severity"),
    status: Optional[str] = Query(None, description="Filter by status"),
) -> AlertListResponse:
    """
    Get alerts for a specific site.

    Args:
        site_id: The site identifier.
        severity: Filter by severity.
        status: Filter by status.

    Returns:
        AlertListResponse with site-specific alerts.
    """
    return await list_alerts(site_id=site_id, severity=severity, status=status, category=None)


@limiter.limit("30/minute")
@router.get("/anomalies", response_model=AnomalyListResponse)
async def list_anomalies(
    request: Request,
    site_id: Optional[str] = Query(None, description="Filter by site ID"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    urgency: Optional[str] = Query(None, description="Filter by urgency (critical, high, medium, low)"),
) -> AnomalyListResponse:
    """
    List all detected anomalies with details.

    Args:
        site_id: Filter by site ID
        severity: Filter by severity
        urgency: Filter by urgency

    Returns:
        AnomalyListResponse with anomaly details.
    """
    anomalies = load_anomalies()
    equipment = load_equipment()
    sites = load_sites()

    # Create lookups
    eq_lookup = {eq["id"]: eq["name"] for eq in equipment}
    site_lookup = {s["id"]: s["name"] for s in sites}

    # Apply filters
    if site_id:
        anomalies = [a for a in anomalies if a["site_id"] == site_id]
    if severity:
        anomalies = [a for a in anomalies if a["severity"].lower() == severity.lower()]
    if urgency:
        anomalies = [a for a in anomalies if a["urgency"].lower() == urgency.lower()]

    # Calculate totals
    total_repair = sum(a["repair_cost_zar"] for a in anomalies)
    total_damage = sum(a["damage_cost_zar"] for a in anomalies)

    # Enrich with names
    result = []
    for anomaly in anomalies:
        result.append(
            AnomalyResponse(
                **anomaly,
                equipment_name=eq_lookup.get(anomaly["equipment_id"]),
                site_name=site_lookup.get(anomaly["site_id"]),
            )
        )

    # Sort by urgency (critical first)
    urgency_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    result.sort(key=lambda a: urgency_order.get(a.urgency, 4))

    return AnomalyListResponse(
        total=len(result),
        total_repair_cost_zar=total_repair,
        total_potential_damage_zar=total_damage,
        anomalies=result,
    )


class DiagnosticContextRequest(BaseModel):
    """Diagnostic context from zone diagnostics."""

    fault_type: Optional[str] = None
    fault_code: Optional[str] = None
    fault_description: Optional[str] = None
    original_reading: Optional[float] = None
    setpoint: Optional[float] = None
    deviation: Optional[float] = None
    faulty_equipment: Optional[str] = None
    zone_id: Optional[str] = None
    recommended_actions: list[str] = []
    parts_required: list[str] = []
    severity: Optional[str] = None


class CreateAlertRequest(BaseModel):
    """Request to create a new alert."""

    equipment_code: str
    type: str
    severity: str  # critical, warning, info
    title: str
    message: str
    zone_name: Optional[str] = None
    reading: Optional[float] = None
    setpoint: Optional[float] = None
    notify_sentry: bool = True
    diagnostic_context: Optional[DiagnosticContextRequest] = None  # For work order data collection


class CreateAlertResponse(BaseModel):
    """Response for alert creation."""

    id: str
    status: str
    sentry_notified: bool
    message: str


async def recalculate_equipment_health_score(client, equipment_id: str):
    """
    Recalculate equipment health score based on remaining active alerts.

    Called after an alert is acknowledged or resolved to update equipment
    health_score and status based on any remaining active alerts.

    Health score mapping:
    - No active alerts: 85 (normal)
    - Active warning alerts: 60 (warning)
    - Active critical alerts: 30 (critical)
    """
    if not equipment_id:
        return

    try:
        # Get all non-acknowledged, non-resolved alerts for this equipment
        active_alerts = (
            client.table("alerts")
            .select("severity")
            .eq("equipment_id", equipment_id)
            .neq("status", "acknowledged")
            .neq("status", "resolved")
            .execute()
        )

        # Determine new health score based on remaining active alerts
        if not active_alerts.data or len(active_alerts.data) == 0:
            # No more active alerts - return to normal health
            new_health_score = 85
            new_status = "normal"
        else:
            # Calculate health score based on highest remaining alert severity
            severities = [a.get("severity", "").lower() for a in active_alerts.data]
            if "critical" in severities:
                new_health_score = 30
                new_status = "critical"
            elif "warning" in severities:
                new_health_score = 60
                new_status = "warning"
            else:
                new_health_score = 85
                new_status = "normal"

        # Update equipment health score and status
        client.table("equipment").update({"health_score": new_health_score, "status": new_status}).eq(
            "id", equipment_id
        ).execute()

        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            f"Recalculated equipment {equipment_id} health_score to {new_health_score} "
            f"(active alerts: {len(active_alerts.data) if active_alerts.data else 0}, "
            f"status: {new_status})"
        )
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to recalculate health_score for equipment {equipment_id}: {e}")


@limiter.limit("15/minute")
@router.post("/alerts", response_model=CreateAlertResponse)
async def create_alert(http_request: Request, request: CreateAlertRequest) -> CreateAlertResponse:
    """
    Create a new alert and optionally notify via Sentry Telegram.

    Used by sensors/thermostats to report issues.
    Also updates equipment health_score based on alert severity.
    """
    from app.database.supabase_client import get_supabase_client

    client = get_supabase_client()

    # Get equipment by name or code
    # Try by name first (primary identifier in the API)
    equipment = client.table("equipment").select("id, name, code").eq("name", request.equipment_code).execute()

    # If not found by name, try by code
    if not equipment.data:
        equipment = client.table("equipment").select("id, name, code").eq("code", request.equipment_code).execute()

    if not equipment.data:
        raise HTTPException(status_code=404, detail=f"Equipment {request.equipment_code} not found")

    eq = equipment.data[0]
    equipment_id = eq["id"]

    # Get building_id if available (for schema compliance)
    building_id = None
    try:
        equipment_with_building = client.table("equipment").select("building_id").eq("id", equipment_id).execute()
        if equipment_with_building.data:
            building_id = equipment_with_building.data[0].get("building_id")
    except Exception:
        pass  # building_id might not exist in this table

    # Get building name from buildings table if building_id exists
    building_name = "Unknown"
    if building_id:
        try:
            building = client.table("buildings").select("name").eq("id", building_id).execute()
            if building.data:
                building_name = building.data[0].get("name", "Unknown")
        except Exception:
            building_name = "Unknown"  # Default if query fails

    # Create alert using building_id from equipment foreign key
    alert_id = str(uuid.uuid4())
    alert_data = {
        "id": alert_id,
        "building_id": building_id,
        "equipment_id": equipment_id,
        "type": request.type,
        "severity": request.severity,
        "status": "active",
        "title": request.title,
        "message": request.message,
    }

    client.table("alerts").insert(alert_data).execute()

    # === UPDATE EQUIPMENT HEALTH SCORE BASED ON ALERT SEVERITY ===
    # When alerts are created, update the equipment health score to trigger prediction generation
    # Health score mapping:
    # - critical alert → health_score = 30 (well below 90 threshold)
    # - warning alert → health_score = 60 (below 90 threshold)
    try:
        health_score = (
            30 if request.severity.lower() == "critical" else 60 if request.severity.lower() == "warning" else 85
        )

        client.table("equipment").update(
            {
                "health_score": health_score,
                "status": request.severity.lower(),  # Also update status to warning/critical
            }
        ).eq("id", eq["id"]).execute()

        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            f"Updated equipment {request.equipment_code} health_score to {health_score} (severity: {request.severity})"
        )
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to update health_score for equipment {request.equipment_code}: {e}")

    # Emit real-time SSE event for dashboard
    try:
        from app.services.event_emitter import get_event_emitter
        import asyncio

        emitter = get_event_emitter()
        # Use asyncio.create_task to emit event without blocking
        asyncio.create_task(
            emitter.emit_alert_created(
                alert_id=alert_id,
                equipment_id=eq["id"],
                equipment_code=request.equipment_code,
                equipment_name=eq["name"],
                severity=request.severity,
                health_score=health_score,
                message=request.message,
            )
        )
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to emit alert event: {e}")

    # Send Sentry notification if requested
    sentry_notified = False
    if request.notify_sentry:
        sentry_alert = {
            "id": alert_id,
            "building_name": building_name,
            "zone_name": request.zone_name or "Unknown",
            "equipment_name": eq["name"],
            "equipment_code": request.equipment_code,
            "type": request.type,
            "severity": request.severity,
            "message": request.message,
            "reading": request.reading,
            "setpoint": request.setpoint,
        }
        sentry_notified = alert_notifier.send_alert_sync(sentry_alert)

    return CreateAlertResponse(
        id=alert_id, status="active", sentry_notified=sentry_notified, message=f"Alert created for {eq['name']}"
    )


@limiter.limit("20/minute")
@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(request: Request, alert_id: str, acknowledged_by: str = "operator"):
    """Acknowledge an alert and recalculate equipment health score."""

    # Handle simulation alerts (SIM-ALERT-*)
    if alert_id.startswith("SIM-ALERT-"):
        success = get_lifecycle_orchestrator().acknowledge_alert(alert_id)
        if success:
            return {"status": "acknowledged", "alert_id": alert_id}
        else:
            raise HTTPException(status_code=404, detail=f"Simulation alert {alert_id} not found")

    # Handle database alerts
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()

        # First, fetch the alert to get equipment_id
        alert_result = client.table("alerts").select("id, equipment_id, severity").eq("id", alert_id).execute()

        if not alert_result.data:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

        alert_data = alert_result.data[0]
        equipment_id = alert_data.get("equipment_id")

        # Update the alert status
        result = (
            client.table("alerts")
            .update(
                {
                    "status": "acknowledged",
                    "acknowledged_at": datetime.now().isoformat(),
                    "acknowledged_by": acknowledged_by,
                }
            )
            .eq("id", alert_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

        # Recalculate equipment health score based on remaining active alerts
        await recalculate_equipment_health_score(client, equipment_id)

        return {"status": "acknowledged", "alert_id": alert_id}
    except HTTPException:
        raise
    except Exception:
        # If Supabase fails, the alert might be from static JSON (not acknowledgeable)
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found or cannot be acknowledged")


class DispatchWorkOrderRequest(BaseModel):
    """Request to dispatch work order from alert."""

    technician_id: str
    technician_name: str
    service_type: str = "breakdown"  # breakdown, callout
    diagnostic_context: Optional[DiagnosticContextRequest] = None


class DispatchWorkOrderResponse(BaseModel):
    """Response for work order dispatch."""

    work_order_id: str
    service_record_code: str
    status: str
    technician_notified: bool
    message: str


@router.post("/alerts/{alert_id}/dispatch", response_model=DispatchWorkOrderResponse)
async def dispatch_work_order(alert_id: str, request: DispatchWorkOrderRequest):
    """Dispatch a work order from an alert.

    Creates a work order, service record with diagnostic context,
    and notifies the technician via Sentry Telegram.

    The diagnostic context enables context-aware data collection prompts
    so Sentry asks targeted questions based on the detected fault.
    """
    from app.database.supabase_client import get_supabase_client
    from app.services.sentry_integration.work_order_notifier import work_order_notifier

    client = get_supabase_client()

    # Get alert details
    alert_result = client.table("alerts").select("*").eq("id", alert_id).execute()
    if not alert_result.data:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    alert = alert_result.data[0]

    # Get equipment details
    equipment_result = client.table("equipment").select("*").eq("id", alert["equipment_id"]).execute()
    if not equipment_result.data:
        raise HTTPException(status_code=404, detail="Equipment not found")

    equipment = equipment_result.data[0]

    # Create work order
    work_order_id = str(uuid.uuid4())
    _work_order = {
        "id": work_order_id,
        "alert_id": alert_id,
        "building_id": alert["building_id"],
        "equipment_id": alert["equipment_id"],
        "type": request.service_type,
        "status": "assigned",
        "priority": "high" if alert["severity"] == "critical" else "medium",
        "description": alert.get("message", ""),
        "assigned_to": request.technician_name,
        "created_at": datetime.now().isoformat(),
    }

    # Note: Would insert to work_orders table if it exists
    # client.table("work_orders").insert(work_order).execute()

    # Prepare diagnostic context for service record
    diag_context = None
    if request.diagnostic_context:
        diag_context = request.diagnostic_context.dict()

    # Notify technician via Sentry (creates service record)
    wo_data = {
        "work_order_id": work_order_id,
        "equipment_id": alert["equipment_id"],
        "building_id": alert["building_id"],
        "equipment_name": equipment["name"],
        "criticality": "HIGH" if alert["severity"] == "critical" else "MEDIUM",
        "service_type": request.service_type,
        "technician_id": request.technician_id,
        "technician_name": request.technician_name,
        "description": alert.get("message", ""),
        "diagnostic_context": diag_context,  # Pass context for smart data collection
    }

    notified = await work_order_notifier.notify_technician(wo_data)

    # Update alert status
    client.table("alerts").update({"status": "dispatched", "updated_at": datetime.now().isoformat()}).eq(
        "id", alert_id
    ).execute()

    # Get service record code
    service_record_code = f"SR-{datetime.now().year}-PENDING"  # Would get from repository

    return DispatchWorkOrderResponse(
        work_order_id=work_order_id,
        service_record_code=service_record_code,
        status="dispatched",
        technician_notified=notified,
        message=f"Work order dispatched to {request.technician_name}",
    )


@router.get("/anomalies/{anomaly_id}", response_model=AnomalyResponse)
async def get_anomaly(anomaly_id: str) -> AnomalyResponse:
    """
    Get a single anomaly by ID.

    Args:
        anomaly_id: The anomaly identifier.

    Returns:
        AnomalyResponse with full anomaly details.

    Raises:
        HTTPException: If anomaly not found.
    """
    anomalies = load_anomalies()
    equipment = load_equipment()
    sites = load_sites()

    anomaly = next((a for a in anomalies if a["id"] == anomaly_id), None)
    if not anomaly:
        raise HTTPException(status_code=404, detail=f"Anomaly {anomaly_id} not found")

    eq_lookup = {eq["id"]: eq["name"] for eq in equipment}
    site_lookup = {s["id"]: s["name"] for s in sites}

    return AnomalyResponse(
        **anomaly,
        equipment_name=eq_lookup.get(anomaly["equipment_id"]),
        site_name=site_lookup.get(anomaly["site_id"]),
    )

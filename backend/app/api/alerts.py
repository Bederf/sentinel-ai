"""Alerts API endpoints - SENTINEL Integration."""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.middleware.auth_middleware import require_query_site_access
from app.middleware.rate_limiter import limiter
from app.services.sentry_integration.alert_notifier import alert_notifier

router = APIRouter()
logger = logging.getLogger(__name__)

# Load data directory
DATA_DIR = Path(__file__).parent.parent / "data"


def load_alerts() -> list[dict]:
    """Load alerts from canonical sources."""
    alerts = []

    # Load static alerts from JSON for local simulator/dev workflows.
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
        equipment_resp = client.table("equipment").select("id, name, code, site_id, device_info").execute()
        buildings_resp = client.table("sites").select("id, name, code").execute()

        eq_lookup = {eq["id"]: eq for eq in (equipment_resp.data or [])}
        building_lookup = {b["id"]: b for b in (buildings_resp.data or [])}

        for da in db_alerts:
            equipment = eq_lookup.get(da.get("equipment_id"), {})
            building = building_lookup.get(da.get("site_id"), {})
            # Extract device_id from equipment device_info for control navigation
            device_info = equipment.get("device_info") or {}
            device_id = device_info.get("device_id")

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
    anomaly_id: str | None
    equipment_id: str | None
    site_id: str
    type: str
    severity: str
    status: str
    title: str
    message: str
    created_at: str
    updated_at: str
    acknowledged: bool
    acknowledged_by: str | None
    acknowledged_at: str | None
    priority: int
    category: str
    estimated_cost_zar: float
    potential_damage_zar: float
    # Enriched fields
    equipment_name: str | None = None
    site_name: str | None = None
    device_id: str | None = None  # Maps to device manager for control navigation
    recommended_action: str | None = None
    operational_context: dict | None = None
    # Additional fields from load_alerts
    health_score: float | None = None
    fault_codes: list[str] | None = None
    is_database: bool | None = None


class AlertListResponse(BaseModel):
    """Response for alert list."""

    total: int
    by_severity: dict[str, int]
    alerts: list[AlertResponse]
    pending_recommendations: int = 0


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
    acknowledged_by: str | None
    acknowledged_at: str | None
    # Enriched fields
    equipment_name: str | None = None
    site_name: str | None = None


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
    site_id: str | None = Query(None, description="Filter by site ID"),
    equipment_id: str | None = Query(None, description="Filter by equipment ID (UUID)"),
    severity: str | None = Query(None, description="Filter by severity"),
    status: str | None = Query(None, description="Filter by status (active, acknowledged, resolved)"),
    category: str | None = Query(None, description="Filter by category (hvac, electrical, maintenance)"),
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

    # Count pending ai_optimization recommendations for bell
    pending_recommendations = 0
    try:
        # Use first alert's site_id as context, or default to site-002
        rec_site = site_id or "site-002"
        # Count total pending without limit for accurate bell count
        from app.database.repositories import get_recommendation_repository

        rec_repo = get_recommendation_repository()
        normalized = rec_site
        if rec_site.startswith("site-"):
            num = rec_site.split("-")[1]
            normalized = f"S{num}"
        from app.models.recommendation import RecommendationStatus

        all_pending = await rec_repo.get_by_status(normalized, RecommendationStatus.PENDING, limit=1000)
        pending_recommendations = len(all_pending)
    except Exception:
        pass

    return AlertListResponse(
        total=len(limited_results),
        by_severity=by_severity,
        alerts=limited_results,
        pending_recommendations=pending_recommendations,
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
    severity: str | None = Query(None, description="Filter by severity"),
    status: str | None = Query(None, description="Filter by status"),
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
    site_id: str | None = Query(None, description="Filter by site ID"),
    severity: str | None = Query(None, description="Filter by severity"),
    urgency: str | None = Query(None, description="Filter by urgency (critical, high, medium, low)"),
    _auth=Depends(require_query_site_access("site_id")),
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

    fault_type: str | None = None
    fault_code: str | None = None
    fault_description: str | None = None
    original_reading: float | None = None
    setpoint: float | None = None
    deviation: float | None = None
    faulty_equipment: str | None = None
    zone_id: str | None = None
    recommended_actions: list[str] = []
    parts_required: list[str] = []
    severity: str | None = None


class CreateAlertRequest(BaseModel):
    """Request to create a new alert."""

    equipment_code: str
    type: str
    severity: str  # critical, warning, info
    title: str
    message: str
    zone_name: str | None = None
    reading: float | None = None
    setpoint: float | None = None
    notify_sentry: bool = True
    diagnostic_context: DiagnosticContextRequest | None = None  # For work order data collection


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

    # Get site_id if available (for schema compliance)
    site_id = None
    try:
        equipment_with_building = client.table("equipment").select("site_id").eq("id", equipment_id).execute()
        if equipment_with_building.data:
            site_id = equipment_with_building.data[0].get("site_id")
    except Exception:
        pass  # site_id might not exist in this table

    # Get building name from buildings table if site_id exists
    site_name = "Unknown"
    if site_id:
        try:
            building = client.table("sites").select("name").eq("id", site_id).execute()
            if building.data:
                site_name = building.data[0].get("name", "Unknown")
        except Exception:
            site_name = "Unknown"  # Default if query fails

    # Create alert using site_id from equipment foreign key
    alert_id = str(uuid.uuid4())
    alert_data = {
        "id": alert_id,
        "site_id": site_id,
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
        import asyncio

        from app.services.event_emitter import get_event_emitter

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
            "site_name": site_name,
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

    if alert_id.startswith("SIM-ALERT-"):
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

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

        # Auto-create work order if no open record exists for this equipment
        work_order_created = False
        work_order_id = None
        try:
            if equipment_id:
                eq_result = client.table("equipment").select("code, type").eq("id", equipment_id).limit(1).execute()
                eq_code = eq_result.data[0]["code"] if eq_result.data else None

                if eq_code:
                    # Check for any open service record
                    existing = (
                        client.table("service_records")
                        .select("id")
                        .eq("equipment_id", equipment_id)
                        .in_("status", ["assigned", "in_progress", "open", "pending"])
                        .limit(1)
                        .execute()
                    )

                    if not existing.data:
                        logger.info(
                            "Skipping legacy alert->work-order bridge for %s because "
                            "lifecycle orchestration is not part of SENTINEL",
                            alert_id,
                        )
        except Exception as wo_err:
            logger.warning("Auto-WO creation after acknowledge failed for %s: %s", alert_id, wo_err)

        return {
            "status": "acknowledged",
            "alert_id": alert_id,
            "work_order_created": work_order_created,
            "work_order_id": work_order_id,
        }
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
    diagnostic_context: DiagnosticContextRequest | None = None


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
        "site_id": alert["site_id"],
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
        "site_id": alert["site_id"],
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

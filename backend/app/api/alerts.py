"""Alerts API endpoints."""

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()

# Load data directory
DATA_DIR = Path(__file__).parent.parent / "data"


def load_alerts() -> list[dict]:
    """Load alerts from JSON file."""
    alerts_file = DATA_DIR / "alerts.json"
    if alerts_file.exists():
        with open(alerts_file) as f:
            return json.load(f)
    return []


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


@router.get("/alerts", response_model=AlertListResponse)
async def list_alerts(
    site_id: Optional[str] = Query(None, description="Filter by site ID"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    status: Optional[str] = Query(None, description="Filter by status (active, acknowledged, resolved)"),
    category: Optional[str] = Query(None, description="Filter by category (hvac, electrical, maintenance)"),
) -> AlertListResponse:
    """
    List all alerts with optional filtering.

    Args:
        site_id: Filter by site ID
        severity: Filter by severity (critical, warning, info)
        status: Filter by status (active, acknowledged, resolved)
        category: Filter by category

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
        result.append(
            AlertResponse(
                **alert,
                equipment_name=eq_lookup.get(alert["equipment_id"]),
                site_name=site_lookup.get(alert["site_id"]),
            )
        )

    # Sort by priority
    result.sort(key=lambda a: a.priority)

    return AlertListResponse(
        total=len(result),
        by_severity=by_severity,
        alerts=result,
    )


@router.get("/alerts/{alert_id}", response_model=AlertResponse)
async def get_alert(alert_id: str) -> AlertResponse:
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

    return AlertResponse(
        **alert,
        equipment_name=eq_lookup.get(alert["equipment_id"]),
        site_name=site_lookup.get(alert["site_id"]),
    )


@router.get("/sites/{site_id}/alerts", response_model=AlertListResponse)
async def get_site_alerts(
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


@router.get("/anomalies", response_model=AnomalyListResponse)
async def list_anomalies(
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

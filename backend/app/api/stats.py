"""Stats API endpoint for dashboard overview."""

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

# Load data directory
DATA_DIR = Path(__file__).parent.parent / "data"


def load_json(filename: str) -> list[dict] | dict:
    """Load JSON file from data directory."""
    filepath = DATA_DIR / filename
    if filepath.exists():
        with open(filepath) as f:
            return json.load(f)
    return []


class RegionStats(BaseModel):
    """Statistics per region."""

    region: str
    site_count: int
    equipment_count: int
    total_sqm: int
    alert_count: int


class EquipmentTypeStats(BaseModel):
    """Statistics per equipment type."""

    type: str
    count: int
    avg_health: float
    warning_count: int


class AlertSummary(BaseModel):
    """Alert summary by severity."""

    critical: int
    warning: int
    info: int
    total: int


class AnomalySummary(BaseModel):
    """Anomaly summary."""

    total: int
    total_repair_cost_zar: float
    total_potential_damage_zar: float
    potential_savings_zar: float


class EnergyOverview(BaseModel):
    """Energy overview stats."""

    total_sensors: int
    total_readings: int
    date_range_days: int


class StatsResponse(BaseModel):
    """Complete stats response for dashboard."""

    # Counts
    total_sites: int
    total_equipment: int
    total_sensors: int
    total_readings: int
    
    # Health
    avg_equipment_health: float
    equipment_warning_count: int
    equipment_critical_count: int
    
    # Alerts
    alerts: AlertSummary
    
    # Anomalies
    anomalies: AnomalySummary
    
    # By region
    by_region: list[RegionStats]
    
    # By equipment type
    by_equipment_type: list[EquipmentTypeStats]
    
    # Coverage
    total_sqm: int
    data_range_days: int


@router.get("/stats", response_model=StatsResponse)
async def get_stats() -> StatsResponse:
    """
    Get dashboard overview statistics.

    Returns comprehensive statistics for the dashboard including:
    - Total counts (sites, equipment, sensors, readings)
    - Equipment health summary
    - Alert and anomaly summaries
    - Breakdowns by region and equipment type

    Returns:
        StatsResponse with complete dashboard data.
    """
    # Load all data
    sites = load_json("sites.json")
    equipment = load_json("equipment.json")
    sensors = load_json("sensors.json")
    readings = load_json("readings.json")
    alerts = load_json("alerts.json")
    anomalies = load_json("anomalies.json")
    
    # Basic counts
    total_sites = len(sites)
    total_equipment = len(equipment)
    total_sensors = len(sensors)
    total_readings = len(readings)
    
    # Equipment health
    if equipment:
        avg_health = sum(e["health_score"] for e in equipment) / len(equipment)
        warning_count = sum(1 for e in equipment if e["status"] == "warning")
        critical_count = sum(1 for e in equipment if e["status"] == "critical")
    else:
        avg_health = 0
        warning_count = 0
        critical_count = 0
    
    # Active alerts by severity
    active_alerts = [a for a in alerts if a["status"] == "active"]
    alert_summary = AlertSummary(
        critical=sum(1 for a in active_alerts if a["severity"] == "critical"),
        warning=sum(1 for a in active_alerts if a["severity"] == "warning"),
        info=sum(1 for a in active_alerts if a["severity"] == "info"),
        total=len(active_alerts),
    )
    
    # Anomaly summary
    total_repair = sum(a["repair_cost_zar"] for a in anomalies)
    total_damage = sum(a["damage_cost_zar"] for a in anomalies)
    anomaly_summary = AnomalySummary(
        total=len(anomalies),
        total_repair_cost_zar=total_repair,
        total_potential_damage_zar=total_damage,
        potential_savings_zar=total_damage - total_repair,
    )
    
    # Stats by region
    region_stats: dict[str, dict] = {}
    for site in sites:
        region = site["region"]
        if region not in region_stats:
            region_stats[region] = {
                "region": region,
                "site_count": 0,
                "equipment_count": 0,
                "total_sqm": 0,
                "alert_count": 0,
            }
        region_stats[region]["site_count"] += 1
        region_stats[region]["total_sqm"] += site["sqm"]
    
    # Add equipment and alert counts to regions
    site_to_region = {s["id"]: s["region"] for s in sites}
    for eq in equipment:
        region = site_to_region.get(eq["site_id"])
        if region and region in region_stats:
            region_stats[region]["equipment_count"] += 1
    
    for alert in active_alerts:
        region = site_to_region.get(alert["site_id"])
        if region and region in region_stats:
            region_stats[region]["alert_count"] += 1
    
    by_region = [RegionStats(**stats) for stats in region_stats.values()]
    by_region.sort(key=lambda r: -r.site_count)
    
    # Stats by equipment type
    type_stats: dict[str, dict] = {}
    for eq in equipment:
        eq_type = eq["type"]
        if eq_type not in type_stats:
            type_stats[eq_type] = {
                "type": eq_type,
                "count": 0,
                "total_health": 0,
                "warning_count": 0,
            }
        type_stats[eq_type]["count"] += 1
        type_stats[eq_type]["total_health"] += eq["health_score"]
        if eq["status"] == "warning":
            type_stats[eq_type]["warning_count"] += 1
    
    by_equipment_type = [
        EquipmentTypeStats(
            type=stats["type"],
            count=stats["count"],
            avg_health=round(stats["total_health"] / stats["count"], 1),
            warning_count=stats["warning_count"],
        )
        for stats in type_stats.values()
    ]
    by_equipment_type.sort(key=lambda t: -t.count)
    
    # Total sqm
    total_sqm = sum(s["sqm"] for s in sites)
    
    # Date range
    if readings:
        timestamps = [r["timestamp"] for r in readings]
        from datetime import datetime
        dates = [datetime.fromisoformat(ts) for ts in timestamps]
        date_range = (max(dates) - min(dates)).days + 1
    else:
        date_range = 0
    
    return StatsResponse(
        total_sites=total_sites,
        total_equipment=total_equipment,
        total_sensors=total_sensors,
        total_readings=total_readings,
        avg_equipment_health=round(avg_health, 1),
        equipment_warning_count=warning_count,
        equipment_critical_count=critical_count,
        alerts=alert_summary,
        anomalies=anomaly_summary,
        by_region=by_region,
        by_equipment_type=by_equipment_type,
        total_sqm=total_sqm,
        data_range_days=date_range,
    )

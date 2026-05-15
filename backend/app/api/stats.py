"""Stats API endpoint for dashboard overview."""

import json
import logging
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

# Load data directory
DATA_DIR = Path(__file__).parent.parent / "data"

# Bridge equipment types to exclude from count (DALI lighting)
_BRIDGE_EXCLUDE_TYPES = {"lum", "lighting", "dali_luminaire", "dali_lum"}

# Supabase REST config — supports local dev and Cloudflare Worker prod
# Local: http://127.0.0.1:55321 (Supabase local dev instance)
# Prod: https://xxxx.supabase.co (via SUPABASE_REST_URL env var)
import os as _os
_SUPABASE_REST_URL = _os.getenv("SUPABASE_REST_URL", "http://127.0.0.1:55321/rest/v1")
_SUPABASE_ANON_KEY = _os.getenv("SUPABASE_REST_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0")


def _rest_query(table: str, params: str = "", select: str = "*") -> list[dict]:
    """Execute a direct REST query against local Supabase."""
    import httpx
    url = f"{_SUPABASE_REST_URL}/{table}?{params}&select={select}" if params else f"{_SUPABASE_REST_URL}/{table}?select={select}"
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, headers={"apikey": _SUPABASE_ANON_KEY})
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning(f"REST query failed for {table}: {e}")
        return []


def _rest_count(table: str, filters: str = "") -> int:
    """Get row count from Supabase via REST."""
    import httpx
    url = f"{_SUPABASE_REST_URL}/{table}?{filters}&select=id"
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, headers={"apikey": _SUPABASE_ANON_KEY})
            resp.raise_for_status()
            return len(resp.json())
    except Exception as e:
        logger.warning(f"REST count failed for {table}: {e}")
        return 0


def _get_bridge_equipment_count(site_id: str = "site-002") -> tuple[int, dict[str, int]]:
    """Query the site bridge for real-time equipment count (excluding luminaires).

    Returns:
        Tuple of (total_equipment, equipment_types) where equipment_types is a
        dict mapping type -> count, derived from the bridge's BACnet object catalog.
    """
    # Bridge URL and token from environment — avoids settings init dependency
    import os
    base_url = os.getenv("SIMBIOT_API_URL") or os.getenv("BRIDGE_BASE_URL")
    api_token = os.getenv("SIMBIOT_API_KEY") or os.getenv("BRIDGE_API_TOKEN")

    if not base_url or not api_token:
        return 0, {}

    try:
        import httpx
        url = f"{base_url.rstrip('/')}/api/sites/{site_id}/objects"
        headers = {"Authorization": f"Bearer {api_token}"}

        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, headers=headers, params={"limit": 1000})
            resp.raise_for_status()
            data = resp.json()

        objs = data if isinstance(data, list) else data.get("objects", data.get("data", []))
        equipment_ids: set[str] = set()
        type_to_equipment: dict[str, set[str]] = {}

        for obj in objs:
            eid = obj.get("equipment_id", "")
            etype = (obj.get("equipment_type") or "unknown").lower()
            obj_name = (obj.get("object_name") or "").lower()
            obj_type = (obj.get("object_type") or "").lower()

            if not eid or etype in _BRIDGE_EXCLUDE_TYPES:
                continue
            if "lum" in obj_type or "dali" in obj_name or "light" in obj_name:
                continue

            equipment_ids.add(eid)
            if etype not in type_to_equipment:
                type_to_equipment[etype] = set()
            type_to_equipment[etype].add(eid)

        type_counts = {t: len(ids) for t, ids in type_to_equipment.items()}
        return len(equipment_ids), type_counts

    except Exception:
        return 0, {}


def load_json(filename: str) -> list[dict] | dict:
    """Load JSON file from data directory."""
    filepath = DATA_DIR / filename
    if filepath.exists():
        with open(filepath) as f:
            return json.load(f)
    return []


def get_stats_from_supabase() -> dict | None:
    """Get stats from Supabase database via direct REST API.

    Bypasses Python client to avoid settings initialization issues.
    """
    try:
        # Get building/site count
        sites = _rest_query("sites", select="id,region,sqm")
        total_sites = len(sites)

        # Equipment count and status breakdown (bridge fallback not available via REST)
        equipment = _rest_query("equipment", select="status,health_score,type")
        total_equipment = len(equipment)
        warning_count = sum(1 for e in equipment if e.get("status") == "warning")
        critical_count = sum(1 for e in equipment if e.get("status") == "critical")
        health_scores = [e.get("health_score") for e in equipment if e.get("health_score") is not None]
        avg_health = round(sum(health_scores) / len(health_scores), 1) if health_scores else 0

        # Equipment type breakdown
        type_stats = {}
        for eq in equipment:
            eq_type = eq.get("type", "unknown")
            if eq_type not in type_stats:
                type_stats[eq_type] = {"type": eq_type, "count": 0, "total_health": 0, "warning_count": 0}
            type_stats[eq_type]["count"] += 1
            type_stats[eq_type]["total_health"] += eq.get("health_score") or 100
            if eq.get("status") == "warning":
                type_stats[eq_type]["warning_count"] += 1
        by_equipment_type = [
            {
                "type": s["type"],
                "count": s["count"],
                "avg_health": round(s["total_health"] / s["count"], 1) if s["count"] > 0 else 0,
                "warning_count": s["warning_count"],
            }
            for s in type_stats.values()
        ]
        by_equipment_type.sort(key=lambda t: -t["count"])

        # Active risks from predictions (consolidated risk system)
        predictions = _rest_query("predictions", "status=eq.active", select="severity")
        alert_critical = sum(1 for p in predictions if p.get("severity") == "critical")
        alert_warning = sum(1 for p in predictions if p.get("severity") == "warning")
        alert_info = 0
        alert_total = alert_critical + alert_warning

        # Sensor count
        sensors = _rest_query("sensors", select="id")
        total_sensors = len(sensors)

        # Readings count
        readings = _rest_query("sensor_readings", select="time")
        total_readings = len(readings)

        # Anomalies
        anomalies = _rest_query("anomalies", select="repair_cost_zar,damage_cost_zar")
        total_repair = sum(a.get("repair_cost_zar", 0) for a in anomalies)
        total_damage = sum(a.get("damage_cost_zar", 0) for a in anomalies)

        # Region aggregation
        region_stats = {}
        for b in sites:
            region = b.get("region", "Unknown")
            if region not in region_stats:
                region_stats[region] = {"region": region, "site_count": 0, "equipment_count": 0, "total_sqm": 0, "alert_count": 0}
            region_stats[region]["site_count"] += 1
            region_stats[region]["total_sqm"] += b.get("sqm") or 0
        by_region = list(region_stats.values())
        by_region.sort(key=lambda r: -r["site_count"])

        return {
            "total_sites": total_sites,
            "total_equipment": total_equipment,
            "total_sensors": total_sensors,
            "total_readings": total_readings,
            "avg_equipment_health": avg_health,
            "equipment_warning_count": warning_count,
            "equipment_critical_count": critical_count,
            "alert_critical": alert_critical,
            "alert_warning": alert_warning,
            "alert_info": alert_info,
            "alert_total": alert_total,
            "anomalies": anomalies,
            "total_repair": total_repair,
            "total_damage": total_damage,
            "by_region": by_region,
            "by_equipment_type": by_equipment_type,
            "total_sqm": sum((b.get("sqm") or 0) for b in sites),
        }
    except Exception as e:
        logger.warning(f"Failed to get stats from Supabase: {e}")
        return None


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
    # Flattened alert counts for frontend compatibility
    active_alerts: int
    critical_alerts: int

    # Anomalies
    anomalies: AnomalySummary

    # By region
    by_region: list[RegionStats]

    # By equipment type
    by_equipment_type: list[EquipmentTypeStats]

    # Coverage
    total_sqm: int
    data_range_days: int

    # Optional fields for frontend compatibility
    uptime_percent: float | None = None
    pending_anomalies: int = 0


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
    # Try Supabase first
    supabase_stats = get_stats_from_supabase()

    if supabase_stats:
        # Build response from Supabase data
        alert_summary = AlertSummary(
            critical=supabase_stats["alert_critical"],
            warning=supabase_stats["alert_warning"],
            info=supabase_stats["alert_info"],
            total=supabase_stats["alert_total"],
        )

        anomalies = supabase_stats["anomalies"]
        anomaly_summary = AnomalySummary(
            total=len(anomalies),
            total_repair_cost_zar=supabase_stats["total_repair"],
            total_potential_damage_zar=supabase_stats["total_damage"],
            potential_savings_zar=supabase_stats["total_damage"] - supabase_stats["total_repair"],
        )

        by_region = [RegionStats(**r) for r in supabase_stats["by_region"]]
        by_equipment_type = [EquipmentTypeStats(**t) for t in supabase_stats["by_equipment_type"]]

        return StatsResponse(
            total_sites=supabase_stats["total_sites"],
            total_equipment=supabase_stats["total_equipment"],
            total_sensors=supabase_stats["total_sensors"],
            total_readings=supabase_stats["total_readings"],
            avg_equipment_health=supabase_stats["avg_equipment_health"],
            equipment_warning_count=supabase_stats["equipment_warning_count"],
            equipment_critical_count=supabase_stats["equipment_critical_count"],
            alerts=alert_summary,
            active_alerts=alert_summary.total,
            critical_alerts=alert_summary.critical,
            anomalies=anomaly_summary,
            pending_anomalies=len(anomalies),
            by_region=by_region,
            by_equipment_type=by_equipment_type,
            total_sqm=supabase_stats["total_sqm"],
            data_range_days=30,  # Default for Supabase
            uptime_percent=None,
        )

    # Fallback to JSON files
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
        active_alerts=alert_summary.total,
        critical_alerts=alert_summary.critical,
        anomalies=anomaly_summary,
        pending_anomalies=len(anomalies),
        by_region=by_region,
        by_equipment_type=by_equipment_type,
        total_sqm=total_sqm,
        data_range_days=date_range,
        uptime_percent=None,
    )

"""
OCCUPANCY ANALYTICS API

Provides analytics endpoints for occupancy trends, zone utilization,
peak hour identification, and occupancy-driven control loop management.

Endpoints:
- GET  /api/occupancy/analytics/hourly-trend
- GET  /api/occupancy/analytics/zone-utilization
- GET  /api/occupancy/analytics/peak-hours
- POST /api/occupancy/control/trigger      — manually trigger one control cycle
- GET  /api/occupancy/control/status        — current zone control states
- GET  /api/occupancy/control/history       — audit trail from Supabase
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database.supabase_client import get_supabase_client
from app.middleware.auth_middleware import require_query_site_access

router = APIRouter(prefix="/occupancy/analytics", tags=["occupancy-analytics"])
control_router = APIRouter(prefix="/occupancy/control", tags=["occupancy-control"])


def _empty_live_response(site_id: str, reason: str) -> dict:
    return {
        "site_id": site_id,
        "data_source": "live",
        "data_available": False,
        "timestamp": datetime.now(UTC).isoformat(),
        "reason": reason,
        "note": "Static/simulated occupancy analytics are disabled. Only live site telemetry is used.",
    }


def _canonical_site_id(site_id: str) -> str:
    if site_id.upper().startswith("S") and site_id[1:].isdigit():
        return f"site-{site_id[1:]}"
    return site_id


@router.get("/hourly-trend")
async def get_hourly_occupancy_trend(
    site_id: str = Query(..., description="Building ID"),
    days: int = Query(1, ge=1, le=30, description="Number of days to return (1-30)"),
):
    """Get hourly occupancy trend from live site telemetry only."""
    canonical_site_id = _canonical_site_id(site_id)
    since = datetime.now(UTC) - timedelta(days=days)
    client = get_supabase_client()
    response = (
        client.table("equipment_sensor_readings")
        .select("sensor_type,value,recorded_at")
        .eq("site_id", canonical_site_id)
        .in_("sensor_type", ["total_occupancy", "occupied_zones", "zone_count"])
        .gte("recorded_at", since.isoformat())
        .order("recorded_at", desc=False)
        .limit(5000)
        .execute()
    )
    rows = response.data or []
    if not rows:
        return _empty_live_response(
            canonical_site_id, "No live occupancy telemetry rows found for the requested period."
        )

    buckets: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        try:
            recorded = datetime.fromisoformat(str(row["recorded_at"]).replace("Z", "+00:00"))
            hour_key = recorded.replace(minute=0, second=0, microsecond=0).isoformat()
            buckets.setdefault(hour_key, {}).setdefault(row["sensor_type"], []).append(float(row["value"]))
        except (KeyError, TypeError, ValueError):
            continue

    trend = []
    for hour_key, values in sorted(buckets.items()):
        avg_occupied_zones = sum(values.get("occupied_zones", [])) / len(values.get("occupied_zones", [1]))
        avg_zone_count = sum(values.get("zone_count", [])) / len(values.get("zone_count", [1]))
        avg_total_occupancy = sum(values.get("total_occupancy", [])) / len(values.get("total_occupancy", [1]))
        occupancy_percent = (avg_occupied_zones / avg_zone_count * 100) if avg_zone_count else None
        trend.append(
            {
                "hour": hour_key,
                "occupancy_percent": round(occupancy_percent, 1) if occupancy_percent is not None else None,
                "total_occupancy": round(avg_total_occupancy, 1),
                "occupied_zones": round(avg_occupied_zones, 1),
                "zone_count": round(avg_zone_count, 1),
            }
        )

    occupancies = [row["occupancy_percent"] for row in trend if row["occupancy_percent"] is not None]
    peak_threshold = 70.0
    peak_hours = [row["hour"] for row in trend if float(row["occupancy_percent"] or 0) >= peak_threshold]
    return {
        "site_id": canonical_site_id,
        "data_source": "live",
        "data_available": True,
        "days": days,
        "timestamp": datetime.now(UTC).isoformat(),
        "trend": trend,
        "daily_pattern": {
            "peak_hours": peak_hours,
            "peak_avg_occupancy": round(sum(occupancies) / len(occupancies), 1) if occupancies else None,
            "offpeak_avg_occupancy": None,
        },
    }


@router.get("/zone-utilization")
async def get_zone_utilization(
    site_id: str = Query(..., description="Building ID"),
    _auth=Depends(require_query_site_access("site_id")),
):
    """Get current zone utilization from live lighting/PIR telemetry only."""
    from app.services.lighting_service import get_lighting_service

    canonical_site_id = _canonical_site_id(site_id)
    live_data = await get_lighting_service().get_live_lighting_data(canonical_site_id)
    zones = live_data.get("zones") or []
    if not zones:
        return _empty_live_response(canonical_site_id, live_data.get("error") or "No live zone occupancy rows found.")

    zone_rows = [
        {
            "zone_id": zone.get("zone_id"),
            "utilization_percent": zone.get("occupancy_percent"),
            "total_sensors": zone.get("total_sensors"),
            "occupied_sensors": zone.get("occupied_sensors"),
            "current_occupancy": None,
            "status": "occupied" if (zone.get("occupied_sensors") or 0) > 0 else "empty",
            "last_updated": zone.get("last_updated"),
        }
        for zone in zones
    ]
    percentages = [z["utilization_percent"] for z in zone_rows if z["utilization_percent"] is not None]
    return {
        "site_id": canonical_site_id,
        "data_source": "live",
        "data_available": True,
        "timestamp": datetime.now(UTC).isoformat(),
        "zones": zone_rows,
        "total_occupancy": None,
        "average_utilization_percent": round(sum(percentages) / len(percentages), 1) if percentages else None,
        "note": "Zone utilization is PIR/lighting sensor utilization, not people count.",
    }


@router.get("/peak-hours")
async def get_peak_hours(site_id: str = Query(..., description="Building ID")):
    """Get peak-hour analysis from live hourly occupancy telemetry only."""
    trend_response = await get_hourly_occupancy_trend(site_id=site_id, days=1)
    if not trend_response.get("data_available"):
        return trend_response

    trend = trend_response.get("trend") or []
    occupancies = [row for row in trend if row.get("occupancy_percent") is not None]
    peak_rows = [row for row in occupancies if row["occupancy_percent"] >= 70]
    offpeak_rows = [row for row in occupancies if row["occupancy_percent"] < 70]
    peak_avg = sum(row["occupancy_percent"] for row in peak_rows) / len(peak_rows) if peak_rows else 0
    offpeak_avg = sum(row["occupancy_percent"] for row in offpeak_rows) / len(offpeak_rows) if offpeak_rows else 0

    return {
        "site_id": trend_response["site_id"],
        "data_source": "live",
        "data_available": True,
        "timestamp": datetime.now(UTC).isoformat(),
        "peak_hours": [row["hour"] for row in peak_rows],
        "offpeak_hours": [row["hour"] for row in offpeak_rows],
        "peak_occupancy_avg": round(peak_avg, 1),
        "offpeak_occupancy_avg": round(offpeak_avg, 1),
        "occupancy_differential": round(peak_avg - offpeak_avg, 1),
        "recommendations": [],
    }


# ===========================================================================
# Occupancy-Driven Control Loop (Phase 130)
# ===========================================================================


@control_router.post("/trigger")
async def trigger_occupancy_control(
    site_id: str = Query(..., description="Site to run control cycle for"),
):
    """Manually trigger one occupancy control cycle.

    Reads live PIR/lighting and security occupancy for every zone, adjusts HVAC setpoints
    and lighting brightness accordingly, and logs actions to
    ``occupancy_control_actions`` in Supabase.

    Returns a summary with the number of actions taken and any errors.
    """
    from app.services.occupancy_control_service import get_occupancy_control_service

    service = get_occupancy_control_service()
    result = await service.run_cycle(site_id=site_id)
    return {
        "status": "ok",
        "site_id": site_id,
        "timestamp": datetime.now().isoformat(),
        **result,
    }


@control_router.get("/status")
async def get_occupancy_control_status():
    """Return the current in-memory zone control states.

    Shows which zones have HVAC setpoints relaxed or lighting dimmed,
    their original values, and the last occupancy reading.
    """
    from app.config.settings import settings
    from app.services.occupancy_control_service import get_occupancy_control_service

    service = get_occupancy_control_service()
    zones = []
    for zone_id, state in service._zone_states.items():
        zones.append(
            {
                "zone_id": zone_id,
                "hvac_relaxed": state.hvac_relaxed,
                "lighting_dimmed": state.lighting_dimmed,
                "original_setpoint": state.original_setpoint,
                "original_brightness": state.original_brightness,
                "last_occupancy_pct": state.last_occupancy_pct,
                "last_action_time": state.last_action_time.isoformat() if state.last_action_time else None,
            }
        )
    return {
        "poll_enabled": settings.occupancy_poll_enabled,
        "poll_interval_seconds": settings.occupancy_poll_interval_seconds,
        "zones": zones,
        "zone_count": len(zones),
        "timestamp": datetime.now().isoformat(),
    }


@control_router.get("/history")
async def get_occupancy_control_history(
    site_id: str = Query(..., description="Site ID"),
    zone_id: str | None = Query(None, description="Filter by zone"),
    module: str | None = Query(None, description="Filter: 'hvac' or 'lighting'"),
    limit: int = Query(50, ge=1, le=500),
):
    """Query the ``occupancy_control_actions`` audit trail from Supabase.

    Returns the most recent control actions, optionally filtered by zone
    and module (hvac / lighting).
    """
    try:
        from app.database.connection import get_supabase_client

        client = get_supabase_client()
        if not client:
            raise HTTPException(status_code=503, detail="Supabase not available")

        query = (
            client.table("occupancy_control_actions")
            .select("*")
            .eq("site_id", site_id)
            .order("timestamp", desc=True)
            .limit(limit)
        )
        if zone_id:
            query = query.eq("zone_id", zone_id)
        if module:
            query = query.eq("module", module)

        result = query.execute()
        return {
            "site_id": site_id,
            "count": len(result.data) if result.data else 0,
            "actions": result.data or [],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")

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

from fastapi import APIRouter, Depends, Query, HTTPException
from datetime import datetime
from typing import Optional

from app.middleware.auth_middleware import require_query_site_access
from app.services.occupancy_profile_service import calculate_zone_occupancy

router = APIRouter(prefix="/occupancy/analytics", tags=["occupancy-analytics"])
control_router = APIRouter(prefix="/occupancy/control", tags=["occupancy-control"])


@router.get("/hourly-trend")
async def get_hourly_occupancy_trend(
    site_id: str = Query(..., description="Building ID"),
    days: int = Query(1, ge=1, le=30, description="Number of days to return (1-30)"),
):
    """
    Get hourly occupancy trend for the building.

    Returns occupancy percentage per hour for each zone type.
    Data is generated based on time-of-day heuristics (Phase 4).

    Args:
        site_id: Building ID (e.g., 'site-002' or registered building code)
        days: Number of days of historical data (1, 7, 30)

    Returns:
        {
            "site_id": "<building-id>",
            "days": 7,
            "hours": [0, 1, 2, ..., 23],
            "zones": {
                "office": [occupancy_percent_per_hour],
                "meeting": [...],
                "common": [...],
                "utility": [...],
                "entry": [...]
            },
            "daily_pattern": {
                "peak_hours": [9, 10, 11, 14, 15, 16],
                "offpeak_hours": [0-8, 17-23],
                "peak_avg_occupancy": 75,
                "offpeak_avg_occupancy": 15
            }
        }
    """
    # Generate hourly data (24 hours)
    hours = list(range(24))

    # Use same occupancy heuristics as Phase 4
    # Generate data for each zone type
    zone_types = ["office", "meeting", "common", "utility", "entry"]
    zones_data = {}

    for zone_type in zone_types:
        occupancy_by_hour = []
        for hour in hours:
            # Weekday pattern (use Monday as reference)
            occupancy_percent = calculate_zone_occupancy(
                hour=hour,
                day_of_week=0,  # Monday
                is_weekend=False,
                zone_type=zone_type,
            )
            occupancy_by_hour.append(round(occupancy_percent, 1))

        zones_data[zone_type] = occupancy_by_hour

    # Calculate peak hours (based on office/meeting zones)
    office_occupancy = zones_data["office"]
    peak_threshold = 70  # 70% occupancy
    peak_hours = [h for h, occ in enumerate(office_occupancy) if occ >= peak_threshold]
    offpeak_hours = [h for h, occ in enumerate(office_occupancy) if occ < peak_threshold]

    peak_avg = sum(office_occupancy[h] for h in peak_hours) / len(peak_hours) if peak_hours else 0
    offpeak_avg = sum(office_occupancy[h] for h in offpeak_hours) / len(offpeak_hours) if offpeak_hours else 0

    return {
        "site_id": site_id,
        "days": days,
        "timestamp": datetime.now().isoformat(),
        "hours": hours,
        "zones": zones_data,
        "daily_pattern": {
            "peak_hours": peak_hours,
            "offpeak_hours": offpeak_hours,
            "peak_avg_occupancy": round(peak_avg, 1),
            "offpeak_avg_occupancy": round(offpeak_avg, 1),
            "peak_hours_text": f"{min(peak_hours)}:00-{max(peak_hours) + 1}:00" if peak_hours else "N/A",
        },
    }


@router.get("/zone-utilization")
async def get_zone_utilization(
    site_id: str = Query(..., description="Building ID"),
    _auth=Depends(require_query_site_access("site_id")),
):
    """
    Get current zone utilization metrics.

    Returns current occupancy as percentage of max capacity for each zone.

    Args:
        site_id: Building ID

    Returns:
        {
            "site_id": "<building-id>",
            "timestamp": "2026-02-16T14:30:00Z",
            "zones": [
                {
                    "zone_id": "zone-1",
                    "zone_name": "Reception",
                    "floor": 0,
                    "max_occupancy": 6,
                    "current_occupancy": 3,
                    "utilization_percent": 50,
                    "status": "normal"  // "empty" | "normal" | "crowded" | "over_capacity"
                },
                ...
            ]
        }
    """
    # Simulate current occupancy (would use database in production)
    now = datetime.now()
    hour = now.hour
    day_of_week = now.weekday()
    is_weekend = day_of_week >= 5

    # Zone configurations (from zone_display_mappings)
    zones_config = [
        {"zone_id": "zone-1", "zone_name": "Reception", "floor": 0, "max_occupancy": 6, "type": "entry"},
        {"zone_id": "zone-2", "zone_name": "Workspace-A", "floor": 0, "max_occupancy": 20, "type": "office"},
        {"zone_id": "zone-4", "zone_name": "Common", "floor": 0, "max_occupancy": 8, "type": "common"},
        {"zone_id": "zone-5", "zone_name": "Utility", "floor": 0, "max_occupancy": 2, "type": "utility"},
        {"zone_id": "zone-3", "zone_name": "Meeting-1", "floor": 1, "max_occupancy": 10, "type": "meeting"},
        {"zone_id": "zone-6", "zone_name": "Meeting-2", "floor": 1, "max_occupancy": 8, "type": "meeting"},
        {"zone_id": "zone-7", "zone_name": "Kitchen", "floor": 1, "max_occupancy": 6, "type": "common"},
    ]

    zones_data = []

    for zone in zones_config:
        occupancy_percent = calculate_zone_occupancy(
            hour=hour, day_of_week=day_of_week, is_weekend=is_weekend, zone_type=zone["type"]
        )

        current_occupancy = max(0, int(zone["max_occupancy"] * occupancy_percent / 100))

        # Determine status
        if current_occupancy == 0:
            status = "empty"
        elif current_occupancy >= zone["max_occupancy"]:
            status = "over_capacity"
        elif occupancy_percent >= 80:
            status = "crowded"
        else:
            status = "normal"

        zones_data.append(
            {
                "zone_id": zone["zone_id"],
                "zone_name": zone["zone_name"],
                "floor": zone["floor"],
                "max_occupancy": zone["max_occupancy"],
                "current_occupancy": current_occupancy,
                "utilization_percent": round(occupancy_percent, 1),
                "status": status,
            }
        )

    return {
        "site_id": site_id,
        "timestamp": now.isoformat(),
        "zones": zones_data,
        "total_occupancy": sum(z["current_occupancy"] for z in zones_data),
        "average_utilization_percent": round(sum(z["utilization_percent"] for z in zones_data) / len(zones_data), 1),
    }


@router.get("/peak-hours")
async def get_peak_hours(site_id: str = Query(..., description="Building ID")):
    """
    Get peak hour analysis for the building.

    Peak hours are identified as times when occupancy exceeds 70%.

    Returns:
        {
            "site_id": "<building-id>",
            "peak_hours": [9, 10, 11, 14, 15, 16],
            "offpeak_hours": [0-8, 17-23],
            "peak_occupancy_avg": 82,
            "offpeak_occupancy_avg": 18,
            "recommendations": [
                "Increase HVAC capacity during peak hours (9-5pm)",
                "Schedule cleaning during offpeak hours (after 6pm)",
                "Optimize lighting: reduce in low-occupancy hours"
            ]
        }
    """
    # Get hourly trend to analyze peaks
    trend_response = await get_hourly_occupancy_trend(site_id=site_id, days=1)

    peak_hours = trend_response["daily_pattern"]["peak_hours"]
    offpeak_hours = trend_response["daily_pattern"]["offpeak_hours"]
    peak_avg = trend_response["daily_pattern"]["peak_avg_occupancy"]
    offpeak_avg = trend_response["daily_pattern"]["offpeak_avg_occupancy"]

    # Generate recommendations based on peak pattern
    recommendations = []

    if peak_hours:
        peak_hours_str = f"{min(peak_hours)}:00-{max(peak_hours) + 1}:00"
        recommendations.append(f"Peak occupancy {peak_hours_str} ({peak_avg}% avg) - optimize HVAC/lighting")

    if offpeak_avg < 20:
        recommendations.append("Low occupancy during offpeak (turn off lights, reduce HVAC)")

    if peak_avg > 85:
        recommendations.append("High peak occupancy - consider staggered schedules")

    recommendations.append("Schedule maintenance during lowest occupancy hours (nights/weekends)")

    return {
        "site_id": site_id,
        "timestamp": datetime.now().isoformat(),
        "peak_hours": peak_hours,
        "offpeak_hours": offpeak_hours,
        "peak_occupancy_avg": round(peak_avg, 1),
        "offpeak_occupancy_avg": round(offpeak_avg, 1),
        "occupancy_differential": round(peak_avg - offpeak_avg, 1),
        "peak_hours_text": f"{min(peak_hours):02d}:00-{max(peak_hours) + 1:02d}:00" if peak_hours else "N/A",
        "recommendations": recommendations,
    }


# ===========================================================================
# Occupancy-Driven Control Loop (Phase 130)
# ===========================================================================


@control_router.post("/trigger")
async def trigger_occupancy_control(
    site_id: str = Query(..., description="Site to run control cycle for"),
):
    """Manually trigger one occupancy control cycle.

    Reads DALI PIR + badge occupancy for every zone, adjusts HVAC setpoints
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
    from app.services.occupancy_control_service import get_occupancy_control_service
    from app.config.settings import settings

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
    zone_id: Optional[str] = Query(None, description="Filter by zone"),
    module: Optional[str] = Query(None, description="Filter: 'hvac' or 'lighting'"),
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

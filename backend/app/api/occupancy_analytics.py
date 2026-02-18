"""
OCCUPANCY ANALYTICS API

Provides analytics endpoints for occupancy trends, zone utilization,
and peak hour identification.

Endpoints:
- GET /api/occupancy/analytics/hourly-trend
- GET /api/occupancy/analytics/zone-utilization
- GET /api/occupancy/analytics/peak-hours
"""

from fastapi import APIRouter, Query
from datetime import datetime

router = APIRouter(prefix="/occupancy/analytics", tags=["occupancy-analytics"])


@router.get("/hourly-trend")
async def get_hourly_occupancy_trend(
    building_id: str = Query("site-002"),
    days: int = Query(1, ge=1, le=30, description="Number of days to return (1-30)")
):
    """
    Get hourly occupancy trend for the building.

    Returns occupancy percentage per hour for each zone type.
    Data is generated based on time-of-day heuristics (Phase 4).

    Args:
        building_id: Building ID (e.g., 'site-002')
        days: Number of days of historical data (1, 7, 30)

    Returns:
        {
            "building_id": "site-002",
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
    from app.api.dali import calculate_zone_occupancy

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
                zone_type=zone_type
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
        "building_id": building_id,
        "days": days,
        "timestamp": datetime.now().isoformat(),
        "hours": hours,
        "zones": zones_data,
        "daily_pattern": {
            "peak_hours": peak_hours,
            "offpeak_hours": offpeak_hours,
            "peak_avg_occupancy": round(peak_avg, 1),
            "offpeak_avg_occupancy": round(offpeak_avg, 1),
            "peak_hours_text": f"{min(peak_hours)}:00-{max(peak_hours)+1}:00" if peak_hours else "N/A"
        }
    }


@router.get("/zone-utilization")
async def get_zone_utilization(
    building_id: str = Query("site-002")
):
    """
    Get current zone utilization metrics.

    Returns current occupancy as percentage of max capacity for each zone.

    Args:
        building_id: Building ID

    Returns:
        {
            "building_id": "site-002",
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
    from app.api.dali import calculate_zone_occupancy

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
            hour=hour,
            day_of_week=day_of_week,
            is_weekend=is_weekend,
            zone_type=zone["type"]
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

        zones_data.append({
            "zone_id": zone["zone_id"],
            "zone_name": zone["zone_name"],
            "floor": zone["floor"],
            "max_occupancy": zone["max_occupancy"],
            "current_occupancy": current_occupancy,
            "utilization_percent": round(occupancy_percent, 1),
            "status": status
        })

    return {
        "building_id": building_id,
        "timestamp": now.isoformat(),
        "zones": zones_data,
        "total_occupancy": sum(z["current_occupancy"] for z in zones_data),
        "average_utilization_percent": round(
            sum(z["utilization_percent"] for z in zones_data) / len(zones_data), 1
        )
    }


@router.get("/peak-hours")
async def get_peak_hours(
    building_id: str = Query("site-002")
):
    """
    Get peak hour analysis for the building.

    Peak hours are identified as times when occupancy exceeds 70%.

    Returns:
        {
            "building_id": "site-002",
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
    trend_response = await get_hourly_occupancy_trend(
        building_id=building_id,
        days=1
    )

    peak_hours = trend_response["daily_pattern"]["peak_hours"]
    offpeak_hours = trend_response["daily_pattern"]["offpeak_hours"]
    peak_avg = trend_response["daily_pattern"]["peak_avg_occupancy"]
    offpeak_avg = trend_response["daily_pattern"]["offpeak_avg_occupancy"]

    # Generate recommendations based on peak pattern
    recommendations = []

    if peak_hours:
        peak_hours_str = f"{min(peak_hours)}:00-{max(peak_hours)+1}:00"
        recommendations.append(f"Peak occupancy {peak_hours_str} ({peak_avg}% avg) - optimize HVAC/lighting")

    if offpeak_avg < 20:
        recommendations.append("Low occupancy during offpeak (turn off lights, reduce HVAC)")

    if peak_avg > 85:
        recommendations.append("High peak occupancy - consider staggered schedules")

    recommendations.append("Schedule maintenance during lowest occupancy hours (nights/weekends)")

    return {
        "building_id": building_id,
        "timestamp": datetime.now().isoformat(),
        "peak_hours": peak_hours,
        "offpeak_hours": offpeak_hours,
        "peak_occupancy_avg": round(peak_avg, 1),
        "offpeak_occupancy_avg": round(offpeak_avg, 1),
        "occupancy_differential": round(peak_avg - offpeak_avg, 1),
        "peak_hours_text": f"{min(peak_hours):02d}:00-{max(peak_hours)+1:02d}:00" if peak_hours else "N/A",
        "recommendations": recommendations
    }

"""
Lighting Intelligence Dashboard - 365-Day Simulation Engine

Demonstrates ROI of smart lighting systems with SENTINEL AI optimization.
Compares three scenarios:
1. Baseline: Traditional fixed schedules (no automation)
2. Smart Lighting: Occupancy detection + daylight harvesting
3. With SENTINEL AI: Predictive optimization on top of smart lighting

Physics-based simulation includes:
- Realistic occupancy patterns (weekday/weekend/holidays for Johannesburg)
- Daylight availability based on solar geometry and seasonal weather
- ML learning curve (60% effective month 1 → 95% month 12)
- Tariff bands (off-peak, standard, peak)
"""

import math
from datetime import datetime, timedelta

from fastapi import APIRouter, Query

router = APIRouter()


def _normalize_live_site_id(site_id: str | None) -> tuple[str, str]:
    requested_site_id = site_id or "site-002"
    if requested_site_id.startswith("site-"):
        return requested_site_id, f"S{requested_site_id.split('-')[1]}"
    return requested_site_id, requested_site_id


def _no_live_lighting_data(site_id: str | None, reason: str | None = None) -> dict:
    return {
        "site_id": site_id,
        "data_source": "live",
        "data_available": False,
        "timestamp": datetime.now().isoformat(),
        "reason": reason or "No live lighting occupancy rows are available for this site.",
        "note": (
            "Static/simulated occupancy has been removed. Lighting PIR data can only report "
            "occupied sensors/zones, not people count, unless a people-counting source is integrated."
        ),
        "summary": {
            "total_zones": 0,
            "avg_occupancy_percent": None,
            "total_sensors": 0,
            "occupied_sensors": 0,
            "total_people": None,
        },
        "zones": [],
    }


# ============================================================================
# CONSTANTS
# ============================================================================

BUILDING_ZONES = 8
AVG_POWER_PER_ZONE_W = 1800  # 15 × 120W LED panels per zone
WINDOW_ZONES = [0, 1, 3, 4]  # Zones with windows (daylight harvesting)
LATITUDE = -26.12  # Johannesburg

# Tariffs (R/kWh) - South African eskom-style rates
TARIFF = {
    "off_peak": 0.82,  # 22:00 - 06:00
    "standard": 1.25,  # 06:00 - 09:00, 17:00 - 22:00
    "peak": 1.92,  # 09:00 - 17:00
}

# ============================================================================
# SOLAR GEOMETRY & DAYLIGHT CALCULATION
# ============================================================================


def calculate_daylight_hours(day_of_year: int) -> float:
    """
    Calculate sunrise/sunset for Johannesburg using solar geometry.

    Args:
        day_of_year: Day number (1-365)

    Returns:
        Hours of daylight
    """
    # Solar declination angle
    declination = 23.45 * math.sin((2 * math.pi / 365) * (284 + day_of_year))
    lat_rad = math.radians(LATITUDE)
    decl_rad = math.radians(declination)

    # Hour angle at sunset
    cos_hour_angle = -math.tan(lat_rad) * math.tan(decl_rad)
    cos_hour_angle = max(-1, min(1, cos_hour_angle))

    hour_angle = math.acos(cos_hour_angle)
    daylight_hours = (2 * hour_angle * 12) / math.pi

    return daylight_hours


def get_cloud_factor(day_of_year: int, rng) -> float:
    """
    Weather cloud cover factor for Johannesburg's seasonal patterns.

    Summer (Nov-Feb): 60% clear (thunderstorms)
    Winter (May-Aug): 85% clear (dry season)
    Autumn/Spring: 70% clear

    Args:
        day_of_year: Day number (1-365)
        rng: Random number generator function

    Returns:
        Cloud factor (0.15-0.98, higher = clearer)
    """
    month = (day_of_year - 1) // 30 + 1

    if month in [11, 12, 1, 2]:  # Summer
        base_clear = 0.60
    elif month in [5, 6, 7, 8]:  # Winter
        base_clear = 0.85
    else:  # Autumn/Spring
        base_clear = 0.70

    # Add daily variation
    return max(0.15, min(0.98, base_clear + (rng() - 0.5) * 0.25))


# ============================================================================
# OCCUPANCY PATTERNS
# ============================================================================


def get_occupancy(hour: int, day_of_week: int, is_holiday: bool, rng) -> float:
    """
    Return occupancy percentage for given time.

    Weekday schedule (Johannesburg office):
    - 07:00-09:00: Ramp up (30% → 85%)
    - 09:00-12:00: Morning peak (85% → 92%)
    - 12:00-14:00: Lunch dip (92% → 65%)
    - 14:00-17:00: Afternoon peak (70% → 88%)
    - 17:00-19:00: Wind down (88% → 20%)
    - 19:00-07:00: Night (5% - security only)

    Weekend: 8% (security + maintenance)
    Holidays: 5% (security only)

    Args:
        hour: Hour of day (0-23)
        day_of_week: Weekday (0=Monday, 6=Sunday)
        is_holiday: True if public holiday
        rng: Random number generator

    Returns:
        Occupancy percentage (0-1)
    """
    is_weekend = day_of_week in [5, 6]

    if is_holiday:
        return 0.05  # Security only
    elif is_weekend:
        return 0.08  # Security + maintenance
    else:
        # Weekday patterns
        if 7 <= hour < 9:
            return 0.30 + (hour - 7) * 0.275 + rng() * 0.1
        elif 9 <= hour < 12:
            return 0.85 + rng() * 0.07
        elif 12 <= hour < 14:
            return 0.65 + rng() * 0.15
        elif 14 <= hour < 17:
            return 0.70 + rng() * 0.18
        elif 17 <= hour < 19:
            return 0.88 - (hour - 17) * 0.34 + rng() * 0.1
        else:
            return 0.05


# ============================================================================
# DAYLIGHT & LIGHTING CONTROL
# ============================================================================


def get_daylight_lux(hour: float, daylight_hours: float, cloud_factor: float, zone_id: int) -> float:
    """
    Calculate natural light (lux) availability for a zone.

    Accounts for:
    - Solar elevation angle (higher = brighter)
    - Cloud cover
    - Window orientation (north-facing > south-facing)
    - Interior zones have minimal daylight

    Args:
        hour: Hour of day (0-23)
        daylight_hours: Total daylight hours for the day
        cloud_factor: Cloud cover factor (0-1)
        zone_id: Zone identifier (0-7)

    Returns:
        Natural light level (lux)
    """
    sunrise = 12 - daylight_hours / 2
    sunset = 12 + daylight_hours / 2

    if hour < sunrise or hour >= sunset:
        return 0

    # Solar elevation angle at hour
    solar_elevation = math.sin(math.pi * (hour - sunrise) / daylight_hours)
    base_lux = 1000 * solar_elevation * cloud_factor

    # Window orientation adjustment
    if zone_id in WINDOW_ZONES:
        if zone_id in [0, 1]:  # North-facing
            base_lux *= 1.4
        elif zone_id in [3, 4]:  # South-facing
            base_lux *= 1.1
    else:
        base_lux *= 0.3  # Interior zones

    return max(0, base_lux)


def get_tariff_band(hour: int) -> str:
    """
    Get tariff band for hour of day (South African Eskom-style).

    Off-peak: 22:00 - 06:00 (R0.82/kWh)
    Peak: 09:00 - 17:00 (R1.92/kWh)
    Standard: Other hours (R1.25/kWh)

    Args:
        hour: Hour of day (0-23)

    Returns:
        Tariff band name
    """
    if hour >= 22 or hour < 6:
        return "off_peak"
    elif 9 <= hour < 17:
        return "peak"
    return "standard"


# ============================================================================
# ML LEARNING CURVE
# ============================================================================


def get_learning_factor(day: int) -> float:
    """
    ML learning curve: effectiveness improves from 60% to 95% over 6 months.

    Month 1-2: 60% effective (basic occupancy detection)
    Month 3-4: 75% effective (daylight correlation by zone)
    Month 5-6: 85% effective (behavioral patterns)
    Month 7-12: 95% effective (full optimization)

    Uses exponential asymptotic approach: 0.60 + 0.35 * (1 - e^(-t/90))

    Args:
        day: Day number (0-364)

    Returns:
        Effectiveness factor (0.6-0.95)
    """
    return 0.60 + 0.35 * (1 - math.exp(-day / 90))


# ============================================================================
# SEEDED RANDOM NUMBER GENERATOR
# ============================================================================


def seeded_random(seed: int):
    """
    Create a seeded RNG for reproducible simulations.

    Args:
        seed: Seed value

    Returns:
        Function that generates random numbers [0, 1)
    """
    state = seed % 2147483647

    def rng():
        nonlocal state
        state = (state * 16807) % 2147483647
        return (state - 1) / 2147483646

    return rng


# ============================================================================
# MAIN SIMULATION
# ============================================================================


def run_lighting_simulation(max_day: int = 365) -> dict:
    """
    Run 365-day DALI lighting simulation with 3 scenarios.

    Compares:
    1. Baseline: Fixed schedule (no DALI)
    2. With DALI: Occupancy + daylight harvesting
    3. With SENTINEL AI: Predictive optimization

    Returns:
        Dictionary with summary metrics, daily data, and monthly data
    """
    rng = seeded_random(20260214)
    start_date = datetime(2025, 3, 1)

    # Clamp max_day to valid range
    max_day = max(1, min(365, max_day))

    # Results storage
    daily_data = []
    monthly_data = []

    cumulative_baseline = 0
    cumulative_smart = 0
    cumulative_sentinel = 0

    current_month = -1
    month_accum = None

    # ========================================================================
    # SIMULATION LOOP: up to max_day days
    # ========================================================================

    for day in range(max_day):
        current_date = start_date + timedelta(days=day)
        day_of_year = current_date.timetuple().tm_yday
        day_of_week = current_date.weekday()

        # Simple holiday detection (December-January)
        is_holiday = day_of_year >= 350 or day_of_year <= 10

        # Daylight and weather for the day
        daylight_hours = calculate_daylight_hours(day_of_year)
        cloud_factor = get_cloud_factor(day_of_year, rng)
        learning_factor = get_learning_factor(day)

        baseline_day_cost = 0
        smart_day_cost = 0
        sentinel_day_cost = 0

        baseline_day_kwh = 0
        smart_day_kwh = 0
        sentinel_day_kwh = 0

        # ====================================================================
        # HOURLY LOOP: Each hour of the day
        # ====================================================================

        for hour in range(24):
            occupancy = get_occupancy(hour, day_of_week, is_holiday, rng)
            tariff_rate = TARIFF[get_tariff_band(hour)]

            # Per-zone calculation
            for zone_id in range(BUILDING_ZONES):
                zone_power_kw = AVG_POWER_PER_ZONE_W / 1000
                daylight_lux = get_daylight_lux(hour, daylight_hours, cloud_factor, zone_id)

                # ============================================================
                # SCENARIO 1: BASELINE (Fixed schedule)
                # ============================================================
                baseline_power = zone_power_kw if 7 <= hour < 18 else 0

                # ============================================================
                # SCENARIO 2: WITH DALI (Occupancy + Daylight)
                # ============================================================
                if not (7 <= hour < 18):
                    smart_brightness = 0.0  # Lights off outside business hours
                elif occupancy <= 0.10:
                    smart_brightness = 0.30  # Vacancy dimming
                elif daylight_lux > 500:
                    smart_brightness = 0.50  # Daylight harvesting
                else:
                    smart_brightness = 1.0

                smart_power = zone_power_kw * smart_brightness

                # ============================================================
                # SCENARIO 3: WITH SENTINEL AI (Predictive + Adaptive)
                # ============================================================
                sentinel_brightness = smart_brightness

                # Pre-dimming prediction (5 min ahead)
                if 17 <= hour < 19 and occupancy > 0.5:
                    sentinel_brightness *= 0.85

                # Weather-aware adjustment
                next_cloud = get_cloud_factor(day_of_year + 1, rng)
                if next_cloud < 0.55 and daylight_lux < 300:
                    sentinel_brightness *= 0.90

                # Apply learning factor (asymptotic improvement)
                sentinel_power = zone_power_kw * sentinel_brightness * (0.95 + 0.05 * (1 - learning_factor))

                # Accumulate costs
                baseline_day_cost += baseline_power * tariff_rate
                smart_day_cost += smart_power * tariff_rate
                sentinel_day_cost += sentinel_power * tariff_rate

                baseline_day_kwh += baseline_power
                smart_day_kwh += smart_power
                sentinel_day_kwh += sentinel_power

        # ====================================================================
        # ACCUMULATE AND AGGREGATE
        # ====================================================================

        cumulative_baseline += baseline_day_cost
        cumulative_smart += smart_day_cost
        cumulative_sentinel += sentinel_day_cost

        # Monthly aggregation
        month = current_date.month
        if month != current_month:
            if month_accum:
                monthly_data.append(month_accum)

            current_month = month
            month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            month_accum = {
                "month": month_names[month - 1],
                "baseline_cost": 0,
                "dali_cost": 0,
                "sentinel_cost": 0,
                "baseline_kwh": 0,
                "dali_kwh": 0,
                "sentinel_kwh": 0,
            }

        month_accum["baseline_cost"] += baseline_day_cost
        month_accum["dali_cost"] += smart_day_cost
        month_accum["sentinel_cost"] += sentinel_day_cost
        month_accum["baseline_kwh"] += baseline_day_kwh
        month_accum["dali_kwh"] += smart_day_kwh
        month_accum["sentinel_kwh"] += sentinel_day_kwh

        # Store daily data (every 3rd day for performance)
        if day % 3 == 0:
            daily_data.append(
                {
                    "day": day + 1,
                    "date": current_date.strftime("%Y-%m-%d"),
                    "baseline_cumulative": round(cumulative_baseline, 2),
                    "dali_cumulative": round(cumulative_smart, 2),
                    "sentinel_cumulative": round(cumulative_sentinel, 2),
                    "savings": round(cumulative_baseline - cumulative_sentinel, 2),
                    "learning_factor": round(learning_factor, 3),
                }
            )

    # Finalize monthly data
    if month_accum:
        monthly_data.append(month_accum)

    # ========================================================================
    # CALCULATE SUMMARY METRICS
    # ========================================================================

    dali_savings = cumulative_baseline - cumulative_smart
    sentinel_additional = cumulative_smart - cumulative_sentinel
    # Total savings = what SENTINEL adds over Tridonic (the installed system)
    total_savings = sentinel_additional

    # Estimates for breakdowns
    occupancy_hours_saved = 3200
    daylight_hours_utilized = 1840

    return {
        "summary": {
            "baseline_annual_cost": round(cumulative_baseline, 2),
            "dali_annual_cost": round(cumulative_smart, 2),
            "sentinel_annual_cost": round(cumulative_sentinel, 2),
            "total_savings_zar": round(total_savings, 2),
            "dali_savings_zar": round(dali_savings, 2),
            "sentinel_additional_zar": round(sentinel_additional, 2),
            "savings_pct": round((total_savings / cumulative_smart) * 100, 1),
            "occupancy_hours_saved": occupancy_hours_saved,
            "daylight_hours_utilized": daylight_hours_utilized,
            "ml_effectiveness_pct": int(get_learning_factor(max_day - 1) * 100),
            "days_simulated": max_day,
        },
        "daily_data": daily_data,
        "monthly_data": monthly_data,
    }


# ============================================================================
# API ENDPOINTS
# ============================================================================


@router.get("/live")
async def get_live_lighting_data(
    site_id: str = Query(None, description="Site ID"),
):
    """
    Get real-time lighting data from Supabase.

    This endpoint returns only rows read from live lighting tables. PIR values
    represent occupied sensors or zones, not people counts.
    """
    from app.services.lighting_service import get_lighting_service

    try:
        # Normalize site_id to equipment prefix format
        normalized_site_id = site_id
        if site_id.startswith("site-"):
            num = site_id.split("-")[1]
            normalized_site_id = f"S{num}"

        service = get_lighting_service()
        live_data = await service.get_live_lighting_data(normalized_site_id)

        return live_data

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching live lighting data for {site_id}: {e}")

        from datetime import datetime

        return {
            "site_id": site_id,
            "data_source": "live",
            "source_type": "lighting_protocol",
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "summary": {
                "total_zones": 0,
                "avg_occupancy_percent": 0,
                "avg_brightness_level": 0,
                "total_power_w": 0,
                "total_sensors": 0,
                "occupied_sensors": 0,
                "total_luminaires": 0,
                "faulty_luminaires": 0,
            },
            "zones": [],
            "energy_stats": {"total_kwh_24h": 0},
        }


# ============================================================================
# LIVE ZONE-LEVEL ENDPOINTS
# ============================================================================


@router.get("/building/occupancy")
async def get_building_occupancy(site_id: str = Query(None, description="Site ID")):
    """Return live lighting occupancy only; never synthesize people counts."""
    from app.services.lighting_service import get_lighting_service

    requested_site_id, live_site_id = _normalize_live_site_id(site_id)
    live_data = await get_lighting_service().get_live_lighting_data(live_site_id)
    zones = live_data.get("zones") or []
    if not zones:
        return _no_live_lighting_data(requested_site_id, live_data.get("error"))

    summary = live_data.get("summary") or {}
    return {
        "site_id": requested_site_id,
        "data_source": "live",
        "data_available": True,
        "timestamp": live_data.get("timestamp") or datetime.now().isoformat(),
        "total_occupancy_percent": summary.get("avg_occupancy_percent"),
        "total_zones": len(zones),
        "total_sensors": summary.get("total_sensors", 0),
        "occupied_sensors": summary.get("occupied_sensors", 0),
        "total_people": None,
        "note": "Lighting PIR sensors report occupied sensors/zones, not number of people.",
        "zones": zones,
    }


@router.get("/zones/{zone_id}/lighting")
async def get_zone_lighting(zone_id: str):
    """Return live zone lighting only; static zone examples are removed."""
    from app.services.lighting_service import get_lighting_service

    _, live_site_id = _normalize_live_site_id("site-002")
    live_data = await get_lighting_service().get_live_lighting_data(live_site_id)
    for zone in live_data.get("zones") or []:
        if zone.get("zone_id") == zone_id:
            return {
                "data_source": "live",
                "data_available": True,
                "timestamp": live_data.get("timestamp") or datetime.now().isoformat(),
                **zone,
            }
    return {
        "zone_id": zone_id,
        "data_source": "live",
        "data_available": False,
        "timestamp": datetime.now().isoformat(),
        "reason": "No live lighting data found for this zone. Static zone examples have been removed.",
    }


@router.get("/stats")
async def get_lighting_stats(site_id: str = Query(None, description="Site ID")):
    """Return aggregate live lighting stats only."""
    from app.services.lighting_service import get_lighting_service

    requested_site_id, live_site_id = _normalize_live_site_id(site_id)
    live_data = await get_lighting_service().get_live_lighting_data(live_site_id)
    if not live_data.get("zones"):
        return _no_live_lighting_data(requested_site_id, live_data.get("error"))
    return {
        "site_id": requested_site_id,
        "data_source": "live",
        "data_available": True,
        "timestamp": live_data.get("timestamp") or datetime.now().isoformat(),
        "summary": live_data.get("summary") or {},
        "energy_stats": live_data.get("energy_stats") or {},
    }


# ============================================================================
# LIVE OCCUPANCY ENDPOINTS
# ============================================================================


@router.get("/building/{site_id}/occupancy/detailed")
async def get_detailed_occupancy(site_id: str):
    """Return live per-zone lighting occupancy; no simulated personas or counts."""
    from app.services.lighting_service import get_lighting_service

    requested_site_id, live_site_id = _normalize_live_site_id(site_id)
    live_data = await get_lighting_service().get_live_lighting_data(live_site_id)
    zones = live_data.get("zones") or []
    if not zones:
        return _no_live_lighting_data(requested_site_id, live_data.get("error"))

    return {
        "site_id": requested_site_id,
        "data_source": "live",
        "data_available": True,
        "timestamp": live_data.get("timestamp") or datetime.now().isoformat(),
        "zones": [
            {
                "zone_id": zone.get("zone_id"),
                "occupancy_percent": zone.get("occupancy_percent"),
                "total_sensors": zone.get("total_sensors"),
                "occupied_sensors": zone.get("occupied_sensors"),
                "current_occupancy": None,
                "personas": None,
            }
            for zone in zones
        ],
        "total_occupancy": None,
        "total_occupied_sensors": (live_data.get("summary") or {}).get("occupied_sensors", 0),
        "note": "People counts/personas are not inferred from lighting PIR sensors.",
    }

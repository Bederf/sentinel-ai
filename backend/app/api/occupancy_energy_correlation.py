"""
Occupancy-Energy Correlation API

Analyzes the relationship between occupancy levels and energy consumption,
showing cost impact of "lights left on" and HVAC inefficiencies.

Endpoints:
- GET /occupancy-energy/correlation - Time-series correlation data
- GET /occupancy-energy/scenarios - "Lights Left On" cost impact scenarios
- GET /occupancy-energy/savings-potential - HVAC/Lighting savings breakdown
"""

from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime, timedelta

router = APIRouter()

# Constants
LIGHTING_POWER_PER_ZONE = {
    "workspace": 1.5,  # kW per zone (1500W typical)
    "meeting": 0.8,  # kW per meeting room
    "support": 0.5,  # kW per support area (kitchen, etc)
    "utility": 0.3,  # kW per utility area
    "entry": 0.6,  # kW per reception
    "corridor": 0.4,  # kW per corridor segment
}

HVAC_BASELINE_POWER = 25.0  # kW baseline when occupied
HVAC_SETBACK_POWER = 8.0  # kW when unoccupied (maintenance mode)

ELECTRICITY_RATE = 5.0  # R/kWh (South Africa commercial rate)
CARBON_INTENSITY = 0.35  # kg CO₂/kWh (SA grid)


@router.get("/occupancy-energy/correlation")
async def get_correlation_data(
    site_id: str = "bld-002", date: Optional[str] = Query(None, description="ISO date for analysis")
):
    """
    Get time-series correlation between occupancy and energy consumption.

    Returns hourly data showing:
    - Occupancy %
    - Actual energy (baseline + proportional to occupancy)
    - Optimal energy (if HVAC/lighting scaled with occupancy)
    - Wasted energy (difference)
    - Cost of waste
    """
    sim_date = (
        datetime.fromisoformat(date) if date else datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    )

    correlation_data = []

    for hour in range(24):
        current_hour = sim_date + timedelta(hours=hour)
        occ_percent = _get_occupancy_for_hour(hour, current_hour.weekday())

        # Baseline energy (setback + minimal lighting)
        _baseline_kwh = (HVAC_SETBACK_POWER + 2.0) / 60  # 30 min worth

        # Actual energy (if HVAC runs at constant power, lights scale with occupancy)
        hvac_actual = (HVAC_BASELINE_POWER * 0.8) / 60  # 80% of peak
        lighting_actual = sum(LIGHTING_POWER_PER_ZONE.values()) * (occ_percent / 100) / 60
        actual_kwh = hvac_actual + lighting_actual

        # Optimal energy (HVAC + lights scale with occupancy)
        hvac_optimal = (HVAC_BASELINE_POWER * (occ_percent / 100)) / 60
        lighting_optimal = sum(LIGHTING_POWER_PER_ZONE.values()) * (occ_percent / 100) / 60
        optimal_kwh = hvac_optimal + lighting_optimal

        # Wasted energy
        wasted_kwh = actual_kwh - optimal_kwh
        if wasted_kwh < 0:
            wasted_kwh = 0

        cost_waste = wasted_kwh * ELECTRICITY_RATE
        carbon_waste = wasted_kwh * CARBON_INTENSITY

        correlation_data.append(
            {
                "hour": hour,
                "time": current_hour.strftime("%H:00"),
                "occupancy_percent": round(occ_percent, 1),
                "actual_kwh": round(actual_kwh, 2),
                "optimal_kwh": round(optimal_kwh, 2),
                "wasted_kwh": round(wasted_kwh, 2),
                "cost_waste_r": round(cost_waste, 2),
                "carbon_waste_kg": round(carbon_waste, 3),
            }
        )

    total_wasted = sum(d["wasted_kwh"] for d in correlation_data)
    total_cost = sum(d["cost_waste_r"] for d in correlation_data)
    total_carbon = sum(d["carbon_waste_kg"] for d in correlation_data)

    return {
        "date": sim_date.strftime("%Y-%m-%d"),
        "site_id": site_id,
        "hourly_data": correlation_data,
        "daily_summary": {
            "total_wasted_kwh": round(total_wasted, 2),
            "total_cost_wasted_r": round(total_cost, 2),
            "total_carbon_wasted_kg": round(total_carbon, 2),
            "peak_waste_hour": max(correlation_data, key=lambda x: x["wasted_kwh"])["hour"],
            "peak_waste_kwh": max(d["wasted_kwh"] for d in correlation_data),
        },
    }


@router.get("/occupancy-energy/scenarios")
async def get_lights_left_on_scenarios(site_id: str = "bld-002", date: Optional[str] = Query(None)):
    """
    Get "Lights Left On" cost impact scenarios.

    Shows what happens if:
    1. All lights stay on 24/7 (worst case)
    2. Lights stay on after hours (common case)
    3. Lights scale with occupancy (optimal case)
    """
    sim_date = (
        datetime.fromisoformat(date) if date else datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    )

    total_lighting_power = sum(LIGHTING_POWER_PER_ZONE.values())

    # Scenario 1: All lights on 24/7
    cost_24_7 = (total_lighting_power * 24) * ELECTRICITY_RATE
    carbon_24_7 = (total_lighting_power * 24) * CARBON_INTENSITY

    # Scenario 2: Lights on after hours (6pm-7am = 13 hours)
    cost_after_hours = (total_lighting_power * 13) * ELECTRICITY_RATE
    carbon_after_hours = (total_lighting_power * 13) * CARBON_INTENSITY

    # Scenario 3: Lights scale with occupancy (optimal)
    cost_optimal = 0
    carbon_optimal = 0
    for hour in range(24):
        occ_percent = _get_occupancy_for_hour(hour, sim_date.weekday())
        hour_cost = (total_lighting_power * (occ_percent / 100)) * ELECTRICITY_RATE
        hour_carbon = (total_lighting_power * (occ_percent / 100)) * CARBON_INTENSITY
        cost_optimal += hour_cost
        carbon_optimal += hour_carbon

    # Calculate excess waste
    waste_24_7_cost = cost_24_7 - cost_optimal
    waste_after_hours_cost = cost_after_hours - cost_optimal

    return {
        "date": sim_date.strftime("%Y-%m-%d"),
        "site_id": site_id,
        "scenarios": [
            {
                "name": "All Lights On 24/7",
                "description": "Worst case: all lights run continuously",
                "daily_cost_r": round(cost_24_7, 2),
                "daily_carbon_kg": round(carbon_24_7, 2),
                "excess_cost_r": round(waste_24_7_cost, 2),
                "excess_carbon_kg": round(carbon_24_7 - carbon_optimal, 2),
                "probability": "Low (system failure)",
                "icon": "alert-circle",
            },
            {
                "name": "Lights On After Hours",
                "description": "Common: lights left on after 6pm until morning",
                "daily_cost_r": round(cost_after_hours, 2),
                "daily_carbon_kg": round(carbon_after_hours, 2),
                "excess_cost_r": round(waste_after_hours_cost, 2),
                "excess_carbon_kg": round(carbon_after_hours - carbon_optimal, 2),
                "probability": "High (user behavior)",
                "icon": "lightbulb",
            },
            {
                "name": "Occupancy-Scaled Lighting (Optimal)",
                "description": "Best case: lights on proportional to occupancy",
                "daily_cost_r": round(cost_optimal, 2),
                "daily_carbon_kg": round(carbon_optimal, 2),
                "excess_cost_r": 0.0,
                "excess_carbon_kg": 0.0,
                "probability": "With DALI control",
                "icon": "check-circle",
            },
        ],
        "annual_impact": {
            "worst_case_cost_r": round(cost_24_7 * 365, 2),
            "common_case_cost_r": round(cost_after_hours * 365, 2),
            "optimal_cost_r": round(cost_optimal * 365, 2),
            "annual_savings_worst_r": round((cost_24_7 - cost_optimal) * 365, 2),
            "annual_savings_common_r": round((cost_after_hours - cost_optimal) * 365, 2),
        },
    }


@router.get("/occupancy-energy/savings-potential")
async def get_savings_potential(site_id: str = "bld-002", date: Optional[str] = Query(None)):
    """
    Get HVAC and Lighting savings breakdown.

    Shows potential energy and cost savings from:
    1. Occupancy-scaled HVAC (thermostat setback when empty)
    2. Occupancy-scaled Lighting (DALI daylight harvesting)
    3. Combined savings (both optimizations)
    """
    sim_date = (
        datetime.fromisoformat(date) if date else datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    )

    # Calculate baseline (current state): HVAC at constant 80%, lights scale with occupancy
    baseline_hvac_daily = (HVAC_BASELINE_POWER * 0.8) * 24
    baseline_lighting_daily = 0
    for hour in range(24):
        occ_percent = _get_occupancy_for_hour(hour, sim_date.weekday())
        baseline_lighting_daily += sum(LIGHTING_POWER_PER_ZONE.values()) * (occ_percent / 100)

    baseline_total = baseline_hvac_daily + baseline_lighting_daily
    baseline_cost = baseline_total * ELECTRICITY_RATE
    baseline_carbon = baseline_total * CARBON_INTENSITY

    # HVAC Optimization: Scale setpoint with occupancy
    optimized_hvac_daily = 0
    for hour in range(24):
        occ_percent = _get_occupancy_for_hour(hour, sim_date.weekday())
        # Use setback when < 30% occupancy
        hvac_power = HVAC_SETBACK_POWER if occ_percent < 30 else HVAC_BASELINE_POWER * (occ_percent / 100)
        optimized_hvac_daily += hvac_power

    hvac_savings_kwh = baseline_hvac_daily - optimized_hvac_daily
    hvac_savings_cost = hvac_savings_kwh * ELECTRICITY_RATE
    hvac_savings_carbon = hvac_savings_kwh * CARBON_INTENSITY

    # Lighting Optimization: Already baseline (lights scale with occupancy)
    # But with DALI: can add +5% savings from daylight harvesting when sunny
    dali_bonus_percent = 5  # 5% additional savings from DALI daylight harvesting
    lighting_base = baseline_lighting_daily
    lighting_with_dali = lighting_base * ((100 - dali_bonus_percent) / 100)
    lighting_savings_kwh = lighting_base - lighting_with_dali
    lighting_savings_cost = lighting_savings_kwh * ELECTRICITY_RATE
    lighting_savings_carbon = lighting_savings_kwh * CARBON_INTENSITY

    # Combined savings
    combined_total_kwh = hvac_savings_kwh + lighting_savings_kwh
    combined_total_cost = combined_total_kwh * ELECTRICITY_RATE
    combined_total_carbon = combined_total_kwh * CARBON_INTENSITY

    optimized_total = baseline_total - combined_total_kwh
    optimized_cost = baseline_cost - combined_total_cost
    optimized_carbon = baseline_carbon - combined_total_carbon

    return {
        "date": sim_date.strftime("%Y-%m-%d"),
        "site_id": site_id,
        "baseline": {
            "hvac_kwh": round(baseline_hvac_daily, 2),
            "lighting_kwh": round(baseline_lighting_daily, 2),
            "total_kwh": round(baseline_total, 2),
            "cost_r": round(baseline_cost, 2),
            "carbon_kg": round(baseline_carbon, 2),
        },
        "optimizations": [
            {
                "name": "HVAC Setback (Occupancy-Scaled)",
                "description": "Use setback (8 kW) when occupancy < 30%, otherwise scale with occupancy",
                "savings_kwh": round(hvac_savings_kwh, 2),
                "savings_cost_r": round(hvac_savings_cost, 2),
                "savings_carbon_kg": round(hvac_savings_carbon, 2),
                "savings_percent": round((hvac_savings_kwh / baseline_total) * 100, 1),
                "cost_per_kwh_saved_r": round(hvac_savings_cost / max(hvac_savings_kwh, 0.01), 2),
                "implementation": "Smart thermostat + occupancy sensor",
                "roi_months": 18,
            },
            {
                "name": "DALI Daylight Harvesting",
                "description": "Reduce artificial lighting by 5% when natural daylight sufficient",
                "savings_kwh": round(lighting_savings_kwh, 2),
                "savings_cost_r": round(lighting_savings_cost, 2),
                "savings_carbon_kg": round(lighting_savings_carbon, 2),
                "savings_percent": round((lighting_savings_kwh / baseline_total) * 100, 1),
                "cost_per_kwh_saved_r": round(lighting_savings_cost / max(lighting_savings_kwh, 0.01), 2),
                "implementation": "DALI ballasts + daylight sensors",
                "roi_months": 12,
            },
        ],
        "combined": {
            "total_savings_kwh": round(combined_total_kwh, 2),
            "total_savings_cost_r": round(combined_total_cost, 2),
            "total_savings_carbon_kg": round(combined_total_carbon, 2),
            "savings_percent": round((combined_total_kwh / baseline_total) * 100, 1),
        },
        "optimized_state": {
            "hvac_kwh": round(optimized_total - combined_total_kwh + hvac_savings_kwh - baseline_hvac_daily, 2),
            "lighting_kwh": round(baseline_lighting_daily - lighting_savings_kwh, 2),
            "total_kwh": round(optimized_total, 2),
            "cost_r": round(optimized_cost, 2),
            "carbon_kg": round(optimized_carbon, 2),
        },
        "annual_projections": {
            "baseline_cost_r": round(baseline_cost * 365, 2),
            "optimized_cost_r": round(optimized_cost * 365, 2),
            "annual_savings_r": round(combined_total_cost * 365, 2),
            "annual_carbon_reduction_kg": round(combined_total_carbon * 365, 2),
        },
    }


def _get_occupancy_for_hour(hour: int, day_of_week: int) -> float:
    """
    Get occupancy percentage for a given hour (0-23) on a given day.

    Weekday patterns:
    - 7-9am: Arrivals (30-85%)
    - 9am-12pm: Peak (85-92%)
    - 12-2pm: Lunch dip (65-80%)
    - 2-5pm: Afternoon (70-88%)
    - 5-7pm: Departures (88-20%)
    - Other: Off-hours (5%)

    Weekend: 5% base + some maintenance
    """
    is_weekend = day_of_week >= 5

    if is_weekend:
        return 5.0  # Minimal occupancy on weekends

    # Weekday patterns
    if 7 <= hour < 9:
        # Arrivals: 30% → 85%
        return 30.0 + (hour - 7) * 27.5
    elif 9 <= hour < 12:
        # Morning peak: 85-92%
        return 85.0 + (hour - 9) * 2.3
    elif 12 <= hour < 14:
        # Lunch dip: 65-80%
        return 65.0 + (hour - 12) * 7.5
    elif 14 <= hour < 17:
        # Afternoon: 70-88%
        return 70.0 + (hour - 14) * 6.0
    elif 17 <= hour < 19:
        # Departures: 88% → 20%
        return 88.0 - (hour - 17) * 34.0
    else:
        # Off-hours: 5%
        return 5.0

"""Water consumption simulation engine.

Simulates occupancy-driven water usage with seasonal variations,
municipal tariff integration, and automatic hourly calculation.

Model:
  Base Usage: 45L/occupant/day (typical commercial)
  Occupancy Scaling: 40% of power affected by occupancy (%age)
  Seasonal Variation: +20% summer (irrigation), -15% winter
  Cloud Cover: Affects external water usage (irrigation)
  Weather: Rain reduces irrigation by 60%

Integration: Called automatically by thermal_simulation_engine each hour.
Output: Updates power_meters table (S002-MTR-B1-WATER) and energy_consumption_history.
"""

import logging
from datetime import datetime
from typing import Dict, Optional, Tuple, Any
from app.database.supabase_client import get_supabase_client
from app.database.repositories.water_cost_repository import WaterCostRepository

logger = logging.getLogger(__name__)

# Water consumption parameters
BASELINE_OCCUPANT_USAGE_LITERS_PER_DAY = 45.0  # Sanitary fixtures
INTERNAL_ZONE_COUNT = 18  # From HVAC zones
BASELINE_WATER_PER_ZONE = (BASELINE_OCCUPANT_USAGE_LITERS_PER_DAY * 100) / 24  # Per hour, per zone (assume 100 occupants)
OCCUPANCY_WATER_SCALING = 0.40  # Occupancy affects 40% of water usage

# Seasonal and weather factors
SUMMER_IRRIGATION_FACTOR = 1.20  # +20% external irrigation in summer
WINTER_REDUCTION_FACTOR = 0.85  # -15% in winter (less irrigation)
RAIN_IRRIGATION_REDUCTION = 0.60  # 60% reduction when raining (irrigation off)
CLOUDY_IRRIGATION_REDUCTION = 0.15  # 15% reduction in cloudy weather (less evaporation)

# Johannesburg municipal tariff (Tier 3 structure)
# Based on 2024 rates for commercial buildings
JOHANNESBURG_TIER_1_LITERS = 100000.0  # First tier: up to 100,000L/month
JOHANNESBURG_TIER_1_RATE_R_PER_LITER = 7.95 / 1000  # R7.95 per 1000L
JOHANNESBURG_TIER_2_LITERS = 500000.0  # Second tier: 100k-500k L/month
JOHANNESBURG_TIER_2_RATE_R_PER_LITER = 12.50 / 1000  # R12.50 per 1000L
JOHANNESBURG_TIER_3_RATE_R_PER_LITER = 18.95 / 1000  # R18.95 per 1000L (above 500k)
JOHANNESBURG_SEWERAGE_RATE_R_PER_LITER = 6.30 / 1000  # R6.30 per 1000L (sewage treatment)
JOHANNESBURG_FIXED_MONTHLY_CHARGE = 285.00  # Monthly fixed charge


class WaterConsumptionEngine:
    """Engine for simulating water consumption with occupancy and seasonal effects."""

    def __init__(self, building_id: str):
        """Initialize water consumption engine.

        Args:
            building_id: Building/site identifier (e.g., 'site-002')
        """
        self.building_id = building_id
        self.client = get_supabase_client()
        self.cost_repo = WaterCostRepository()

    def calculate_water_consumption(
        self,
        simulated_hour: int,
        occupancy_data: Dict[str, float],
        cloud_cover_pct: float = 0.0,
        is_raining: bool = False,
        simulated_date: Optional[datetime] = None,
    ) -> Tuple[Dict[str, float], float]:
        """Calculate hourly water consumption across zones.

        Args:
            simulated_hour: Hour of day (0-23)
            occupancy_data: Zone occupancy percentages {zone_id: pct}
            cloud_cover_pct: Cloud cover percentage (0-100)
            is_raining: Whether it's raining
            simulated_date: Simulated date for seasonal calculation

        Returns:
            Tuple of (zone_consumption_dict, total_liters)
            zone_consumption_dict: {zone_id: liters_per_hour}
            total_liters: Sum of all zones for hour
        """
        if simulated_date is None:
            simulated_date = datetime.now()

        zone_consumption = {}
        total_consumption = 0.0

        # Get seasonal factor
        seasonal_factor = self._get_seasonal_factor(simulated_date)

        # Get irrigation factor (affected by weather)
        irrigation_factor = self._get_irrigation_factor(cloud_cover_pct, is_raining)

        # Calculate consumption for each zone
        for zone_id, occupancy_pct in occupancy_data.items():
            # Base water usage: proportional to occupancy
            base_water = BASELINE_WATER_PER_ZONE / 100.0  # Per zone per hour

            # Occupancy scaling: 40% of usage varies with occupancy
            occupancy_component = base_water * OCCUPANCY_WATER_SCALING * (occupancy_pct / 100.0)
            standby_component = base_water * (1.0 - OCCUPANCY_WATER_SCALING)

            # Total before seasonal adjustments
            zone_water_base = occupancy_component + standby_component

            # Apply seasonal and weather effects
            zone_water = zone_water_base * seasonal_factor * irrigation_factor

            # Ensure minimum (standby fixtures always use some water)
            zone_water = max(zone_water, standby_component * 0.5)

            zone_consumption[zone_id] = round(zone_water, 2)
            total_consumption += zone_water

        return zone_consumption, round(total_consumption, 2)

    def _get_seasonal_factor(self, simulated_date: datetime) -> float:
        """Calculate seasonal adjustment factor.

        Args:
            simulated_date: Date to calculate for

        Returns:
            Seasonal multiplier (0.85 winter to 1.20 summer)
        """
        month = simulated_date.month

        # Southern Hemisphere seasons
        if month in [12, 1, 2]:  # Summer (Dec-Feb)
            return SUMMER_IRRIGATION_FACTOR
        elif month in [3, 4, 5]:  # Autumn (Mar-May)
            return 1.05  # Slight increase
        elif month in [6, 7, 8]:  # Winter (Jun-Aug)
            return WINTER_REDUCTION_FACTOR
        else:  # Spring (Sep-Nov)
            return 1.05  # Slight increase

    def _get_irrigation_factor(self, cloud_cover_pct: float, is_raining: bool) -> float:
        """Calculate irrigation adjustment factor based on weather.

        Args:
            cloud_cover_pct: Cloud cover percentage (0-100)
            is_raining: Whether it's raining

        Returns:
            Irrigation multiplier
        """
        if is_raining:
            # Rain eliminates need for irrigation
            return 1.0 - RAIN_IRRIGATION_REDUCTION

        # Cloudy weather reduces irrigation need slightly
        cloud_factor = 1.0 - (cloud_cover_pct / 100.0) * CLOUDY_IRRIGATION_REDUCTION

        return cloud_factor

    async def _write_water_consumption(
        self,
        zone_consumption: Dict[str, float],
        total_liters: float,
        simulated_hour: int,
        simulated_date: datetime,
    ) -> None:
        """Write water consumption to database.

        Args:
            zone_consumption: Zone-level consumption dict
            total_liters: Total hourly consumption
            simulated_hour: Hour of day
            simulated_date: Simulated date
        """
        try:
            # Update power_meters table (for consistency with energy tracking)
            meter_id = f"{self.building_id.split('-')[-1]}-MTR-B1-WATER"

            meter_data = {
                "meter_id": meter_id,
                "active_power_kw": 0.0,  # Water doesn't use kW, but field needed
                "active_liters_per_hour": total_liters,
                "last_update": simulated_date.isoformat(),
            }

            # Upsert power_meters (soft insert if not exists)
            try:
                self.client.table("power_meters").upsert(meter_data).execute()
            except Exception as e:
                logger.warning(f"Could not upsert power_meters for water: {e}")

            # Record in energy_consumption_history (repurposed for water tracking)
            history_record = {
                "building_id": self.building_id,
                "meter_id": meter_id,
                "timestamp": simulated_date.isoformat(),
                "energy_kwh": 0.0,  # Not applicable for water
                "energy_type": "WATER",
                "simulated_hour": simulated_hour,
                "zone_details": zone_consumption,  # Per-zone breakdown
                "daylight_lux": 0.0,  # Not applicable
            }

            try:
                self.client.table("energy_consumption_history").insert(history_record).execute()
            except Exception as e:
                logger.warning(f"Could not insert water consumption history: {e}")

        except Exception as e:
            logger.error(f"Error writing water consumption: {e}")

    async def calculate_daily_water_cost(
        self,
        simulated_date: datetime,
        hourly_consumption_dict: Dict[int, float],  # {hour: liters}
    ) -> Dict[str, Any]:
        """Calculate daily water cost using tiered tariff.

        Args:
            simulated_date: Date to calculate for
            hourly_consumption_dict: Hourly consumption {0-23: liters}

        Returns:
            Daily cost breakdown
        """
        # Sum hourly consumption
        total_daily_liters = sum(hourly_consumption_dict.values())

        # Calculate tiered cost
        tier_1_usage = min(total_daily_liters, JOHANNESBURG_TIER_1_LITERS / 30.0)  # Daily allocation
        tier_1_cost = tier_1_usage * JOHANNESBURG_TIER_1_RATE_R_PER_LITER

        tier_2_usage = 0.0
        tier_2_cost = 0.0
        if total_daily_liters > JOHANNESBURG_TIER_1_LITERS / 30.0:
            tier_2_usage = min(
                total_daily_liters - (JOHANNESBURG_TIER_1_LITERS / 30.0),
                (JOHANNESBURG_TIER_2_LITERS - JOHANNESBURG_TIER_1_LITERS) / 30.0
            )
            tier_2_cost = tier_2_usage * JOHANNESBURG_TIER_2_RATE_R_PER_LITER

        tier_3_usage = 0.0
        tier_3_cost = 0.0
        if total_daily_liters > JOHANNESBURG_TIER_2_LITERS / 30.0:
            tier_3_usage = total_daily_liters - (JOHANNESBURG_TIER_2_LITERS / 30.0)
            tier_3_cost = tier_3_usage * JOHANNESBURG_TIER_3_RATE_R_PER_LITER

        # Sewerage charge (typically = water usage charge)
        sewerage_cost = total_daily_liters * JOHANNESBURG_SEWERAGE_RATE_R_PER_LITER

        # Fixed daily allocation (monthly / 30)
        fixed_daily = JOHANNESBURG_FIXED_MONTHLY_CHARGE / 30.0

        total_cost = tier_1_cost + tier_2_cost + tier_3_cost + sewerage_cost + fixed_daily

        return {
            "date": simulated_date.date().isoformat(),
            "total_liters": round(total_daily_liters, 2),
            "tier_1_liters": round(tier_1_usage, 2),
            "tier_1_cost_r": round(tier_1_cost, 2),
            "tier_2_liters": round(tier_2_usage, 2),
            "tier_2_cost_r": round(tier_2_cost, 2),
            "tier_3_liters": round(tier_3_usage, 2),
            "tier_3_cost_r": round(tier_3_cost, 2),
            "sewerage_cost_r": round(sewerage_cost, 2),
            "fixed_charge_r": round(fixed_daily, 2),
            "total_cost_r": round(total_cost, 2),
            "average_rate_r_liter": round(total_cost / total_daily_liters, 4) if total_daily_liters > 0 else 0.0,
            "hourly_breakdown": hourly_consumption_dict,
        }


async def update_simulation_water(
    building_id: str,
    simulated_hour: int,
    occupancy_data: Dict[str, float],
    cloud_cover_pct: float = 0.0,
    is_raining: bool = False,
    simulated_date: Optional[datetime] = None,
) -> Tuple[Dict[str, float], float]:
    """Public API for water consumption calculation.

    Called hourly from lifecycle_orchestrator via thermal_simulation_engine.

    Args:
        building_id: Building/site ID
        simulated_hour: Current hour (0-23)
        occupancy_data: Zone occupancy percentages
        cloud_cover_pct: Cloud cover (0-100)
        is_raining: Rain status
        simulated_date: Simulated date

    Returns:
        Tuple of (zone_consumption, total_liters)
    """
    engine = WaterConsumptionEngine(building_id)
    zone_consumption, total_liters = engine.calculate_water_consumption(
        simulated_hour=simulated_hour,
        occupancy_data=occupancy_data,
        cloud_cover_pct=cloud_cover_pct,
        is_raining=is_raining,
        simulated_date=simulated_date,
    )

    # Write to database
    await engine._write_water_consumption(
        zone_consumption=zone_consumption,
        total_liters=total_liters,
        simulated_hour=simulated_hour,
        simulated_date=simulated_date or datetime.now(),
    )

    return zone_consumption, total_liters


def get_water_consumption_engine(building_id: str) -> WaterConsumptionEngine:
    """Get singleton instance of WaterConsumptionEngine.

    Args:
        building_id: Building identifier

    Returns:
        WaterConsumptionEngine instance
    """
    return WaterConsumptionEngine(building_id)

"""
Lighting Energy Simulation Engine

Simulates realistic lighting energy consumption based on:
- Occupancy levels per zone (people density)
- Daylight availability (time of day, season, cloud cover)
- DALI controls (occupancy detection + daylight harvesting)
- Equipment health and dimming response

Creates realistic lighting power consumption that feeds:
- Dashboard energy dashboards
- AI/ML training data for occupancy correlations
- Cost calculations via municipal tariffs
- ROI analysis for lighting upgrades (DALI vs baseline)

Integration point: Called from thermal_simulation_engine each hour
"""

import logging
import math
from datetime import datetime, date
from typing import Optional, Dict, Any, List
import json

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class LightingSimulationEngine:
    """Calculates and updates zone lighting consumption during simulation."""

    # Lighting hardware parameters (per zone)
    BASELINE_POWER_PER_ZONE = 1.8  # kW (15 LED panels × 120W)
    DALI_MIN_DIM = 0.05  # 5% minimum (DALI spec)

    # Occupancy detection response
    OCCUPANCY_SENSOR_RESPONSE = 0.3  # 30% occupancy triggers lights
    OCCUPANCY_POWER_SCALING = 0.6  # Occupancy affects only 60% of power (rest is base)

    # Daylight harvesting
    DAYLIGHT_THRESHOLD_LUX = 300  # Below this: full artificial light needed
    DAYLIGHT_HARVEST_FACTOR = 0.8  # Dimming effectiveness
    CLOUDY_REDUCTION = 0.3  # Cloudy weather reduces daylight by 30%
    RAIN_REDUCTION = 0.6  # Rain reduces daylight by 60%

    # Zone characteristics
    WINDOW_ZONES = {
        "Zone-001": True,   # Level 0 Zone A (window)
        "Zone-002": False,  # Level 0 Zone B (interior)
        "Zone-101": True,   # Level 1 Zone A (window)
        "Zone-102": False,  # Level 1 Zone B (interior)
        "Zone-201": True,   # Level 2 Zone A (window)
        "Zone-202": False,  # Level 2 Zone B (interior)
        "Zone-R": False,    # Common area
        "Entry": True,      # Entry with skylight
    }

    def __init__(self, building_id: str):
        self.building_id = building_id
        self.supabase = get_supabase_client()

        # Cache zone metadata
        self._zone_cache: Dict[str, Dict[str, Any]] = {}
        self._lighting_power_cache: Dict[str, float] = {}  # zone_id -> power_kw

        # Daily tracking for energy history
        self._daily_hourly_lighting: Dict[int, float] = {}  # hour -> total lighting kW

    async def calculate_lighting_power(
        self,
        simulated_hour: int,
        occupancy_data: Dict[str, float],  # zone_id -> occupancy_percent
        daylight_lux: float,  # Current daylight (lux)
        cloud_cover_pct: float,  # 0-100
        is_raining: bool,  # Weather condition
        simulated_date: Optional[datetime] = None,
    ) -> Dict[str, float]:
        """
        Calculate lighting power consumption per zone.

        Considers:
        - Occupancy detection (triggers lights on)
        - Daylight harvesting (dims lights as daylight increases)
        - DALI dimming response (0-100% power)
        - Zone characteristics (window vs interior)

        Args:
            simulated_hour: Hour of day (0-23)
            occupancy_data: Zone occupancy percentages {zone_id: occupancy_pct}
            daylight_lux: Available daylight (0-1000+ lux)
            cloud_cover_pct: Cloud cover 0-100%
            is_raining: Whether it's raining
            simulated_date: Date for occupancy patterns

        Returns:
            {zone_id: power_kw} per zone
        """
        try:
            # Load zone metadata if not cached
            if not self._zone_cache:
                await self._load_zone_metadata()

            zone_power = {}
            total_power = 0.0

            for zone_id, zone_config in self._zone_cache.items():
                occupancy_pct = occupancy_data.get(zone_id, 0.0)

                # Calculate lighting power for this zone
                power_kw = self._calculate_zone_lighting_power(
                    zone_id=zone_id,
                    occupancy_pct=occupancy_pct,
                    daylight_lux=daylight_lux,
                    cloud_cover_pct=cloud_cover_pct,
                    is_raining=is_raining,
                    zone_config=zone_config,
                )

                zone_power[zone_id] = round(power_kw, 2)
                total_power += power_kw
                self._lighting_power_cache[zone_id] = power_kw

            # Track total for daily aggregation
            self._daily_hourly_lighting[simulated_hour] = round(total_power, 2)

            # Write to database
            await self._write_lighting_power(
                simulated_hour=simulated_hour,
                zone_power=zone_power,
                total_power=total_power,
                daylight_lux=daylight_lux,
            )

            logger.debug(
                f"[LIGHTING] Hour {simulated_hour:02d}: "
                f"Zones={len(zone_power)}, Total={total_power:.1f}kW, "
                f"Daylight={daylight_lux:.0f}lux, Cloud={cloud_cover_pct:.0f}%"
            )

            return zone_power

        except Exception as e:
            logger.error(f"[LIGHTING] Failed to calculate power: {e}", exc_info=True)
            return {}

    def _calculate_zone_lighting_power(
        self,
        zone_id: str,
        occupancy_pct: float,
        daylight_lux: float,
        cloud_cover_pct: float,
        is_raining: bool,
        zone_config: Dict[str, Any],
    ) -> float:
        """
        Calculate lighting power for a single zone.

        Physics Model:
        1. Base power when off: near zero (LED standby)
        2. Occupancy triggers lights (threshold: 30% occupancy)
        3. Occupancy drives base power (60% of power)
        4. Daylight harvesting (DALI) reduces power
        5. Night hours: full power if occupied
        """

        # === Occupancy Detection ===
        # Lights turn on when occupancy > threshold
        if occupancy_pct < self.OCCUPANCY_SENSOR_RESPONSE:
            return 0.02  # Standby power (LED driver, negligible)

        # === Base Power Calculation ===
        baseline_power = self.BASELINE_POWER_PER_ZONE

        # Occupancy scales some of the power (rest is fixed base load)
        occupancy_scaling = self.OCCUPANCY_POWER_SCALING * (occupancy_pct / 100.0)
        power_with_occupancy = baseline_power * (1.0 - self.OCCUPANCY_POWER_SCALING + occupancy_scaling)

        # === Daylight Harvesting (DALI Dimming) ===
        # Only for zones with windows
        has_windows = self.WINDOW_ZONES.get(zone_id, False)

        if has_windows and daylight_lux > 0:
            # Adjust daylight for weather
            effective_lux = daylight_lux
            if cloud_cover_pct > 50:
                effective_lux *= (1.0 - (self.CLOUDY_REDUCTION * (cloud_cover_pct / 100.0)))
            if is_raining:
                effective_lux *= (1.0 - self.RAIN_REDUCTION)

            # Calculate daylight contribution
            if effective_lux >= self.DAYLIGHT_THRESHOLD_LUX:
                # Sufficient daylight - harvest it
                # More daylight = more dimming
                daylight_excess = effective_lux - self.DAYLIGHT_THRESHOLD_LUX
                daylight_factor = max(self.DALI_MIN_DIM, 1.0 - (daylight_excess / 500.0) * self.DAYLIGHT_HARVEST_FACTOR)
            else:
                # Not enough daylight
                daylight_factor = 1.0

            power_with_occupancy *= daylight_factor

        # === Night Setback (Optional) ===
        # Could add reduced lighting during off-hours, but DALI usually turns off entirely

        # Clamp to min (DALI minimum dim)
        power_kw = max(self.DALI_MIN_DIM * baseline_power, power_with_occupancy)

        logger.debug(
            f"[LIGHT CALC] {zone_id}: occ={occupancy_pct:.0f}% "
            f"lux={daylight_lux:.0f} → {power_kw:.2f}kW"
        )

        return power_kw

    async def _load_zone_metadata(self) -> None:
        """Load zone configuration from database."""
        try:
            response = self.supabase.table("hvac_zones").select(
                "id, zone_id, zone_name, floor, typical_occupancy, area_sqm"
            ).eq("building_id", self.building_id).execute()

            for zone in response.data:
                self._zone_cache[zone["zone_id"]] = {
                    "zone_name": zone.get("zone_name"),
                    "floor": zone.get("floor"),
                    "typical_occupancy": zone.get("typical_occupancy", 10),
                    "area_sqm": zone.get("area_sqm", 50),
                }

            logger.info(f"[LIGHTING] Loaded {len(self._zone_cache)} zones")
        except Exception as e:
            logger.error(f"[LIGHTING] Failed to load zone metadata: {e}")

    async def _write_lighting_power(
        self,
        simulated_hour: int,
        zone_power: Dict[str, float],
        total_power: float,
        daylight_lux: float,
    ) -> None:
        """
        Write lighting power to power_meters table.

        Updates the lighting feeder meter with total power.
        """
        try:
            # Calculate hourly energy (kW * 1 hour = kWh)
            lighting_kwh = round(total_power, 2)

            # Update power_meters table for lighting feeder
            hvac_meter_update = {
                "meter_id": "S002-MTR-B1-LIGHT",  # Lighting Distribution feeder
                "active_power_kw": round(total_power, 2),
                "last_update": datetime.utcnow().isoformat() + "Z",
            }

            self.supabase.table("power_meters").upsert(
                hvac_meter_update,
                on_conflict="meter_id"
            ).execute()

            # Record hourly energy consumption
            energy_record = {
                "building_id": self.building_id,
                "meter_id": "S002-MTR-B1-LIGHT",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "energy_kwh": lighting_kwh,
                "energy_type": "LIGHTING",
                "simulated_hour": simulated_hour,
                "zone_details": zone_power,
                "daylight_lux": round(daylight_lux, 1),
            }

            self.supabase.table("energy_consumption_history").insert(
                energy_record
            ).execute()

            logger.debug(
                f"[LIGHTING] Updated meter S002-MTR-B1-LIGHT: "
                f"{total_power:.1f}kW, {lighting_kwh:.2f}kWh at hour {simulated_hour:02d}"
            )

        except Exception as e:
            logger.error(f"[LIGHTING] Failed to write power: {e}", exc_info=True)

    async def calculate_daily_lighting_cost(
        self,
        simulated_date: datetime,
    ) -> Dict[str, Any]:
        """
        Calculate total daily lighting cost and savings.

        Uses energy_cost_service to apply tariff rates.
        """
        try:
            from app.services.energy_cost_service import EnergyCostService

            cost_svc = EnergyCostService(building_id=self.building_id)

            # Sum all hourly lighting power
            total_daily_kwh = sum(self._daily_hourly_lighting.values())

            # Calculate average power
            hours_with_data = len(self._daily_hourly_lighting)
            avg_power_kw = total_daily_kwh / hours_with_data if hours_with_data > 0 else 0

            # Estimate cost (simplified: use average hourly rate)
            avg_hourly_cost = 0.0
            for hour in range(24):
                hourly_power = self._daily_hourly_lighting.get(hour, 0.0)
                if hourly_power > 0:
                    tariff_band = cost_svc.get_hourly_rate(hour, simulated_date)
                    hourly_cost = (hourly_power * tariff_band.total_rate_c_kwh) / 100.0
                    avg_hourly_cost += hourly_cost

            return {
                "date": simulated_date.isoformat()[:10],
                "total_energy_kwh": round(total_daily_kwh, 2),
                "total_cost_r": round(avg_hourly_cost, 2),
                "average_power_kw": round(avg_power_kw, 2),
                "daily_hours": hours_with_data,
            }

        except Exception as e:
            logger.error(f"[LIGHTING] Failed to calculate daily cost: {e}")
            return {}


# Singleton instance per building
_lighting_engines: Dict[str, LightingSimulationEngine] = {}


def get_lighting_engine(building_id: str) -> LightingSimulationEngine:
    """Get or create lighting engine for building."""
    if building_id not in _lighting_engines:
        _lighting_engines[building_id] = LightingSimulationEngine(building_id)
    return _lighting_engines[building_id]


async def update_simulation_lighting(
    building_id: str,
    simulated_hour: int,
    occupancy_data: Dict[str, float],
    daylight_lux: float,
    cloud_cover_pct: float = 0.0,
    is_raining: bool = False,
    simulated_date: Optional[datetime] = None,
) -> Dict[str, float]:
    """
    Public API to calculate lighting power during simulation.

    Args:
        building_id: Building ID
        simulated_hour: Hour (0-23)
        occupancy_data: Zone occupancy percentages
        daylight_lux: Available daylight in lux
        cloud_cover_pct: Cloud cover 0-100%
        is_raining: Whether it's raining
        simulated_date: Date for tariff calculations

    Returns:
        Zone lighting power {zone_id: power_kw}

    Example:
        lighting_power = await update_simulation_lighting(
            building_id="site-002",
            simulated_hour=11,
            occupancy_data={"Zone-001": 85, "Zone-101": 60, ...},
            daylight_lux=750,
            cloud_cover_pct=10,
            is_raining=False,
            simulated_date=datetime.now()
        )
    """
    engine = get_lighting_engine(building_id)
    return await engine.calculate_lighting_power(
        simulated_hour=simulated_hour,
        occupancy_data=occupancy_data,
        daylight_lux=daylight_lux,
        cloud_cover_pct=cloud_cover_pct,
        is_raining=is_raining,
        simulated_date=simulated_date,
    )

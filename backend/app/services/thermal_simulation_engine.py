"""
Thermal Simulation Engine

Simulates realistic zone temperature behavior based on:
- Occupancy levels (people generate ~100W heat each)
- HVAC setpoints and fan speed
- Ambient conditions (temperature, solar gain)
- Thermal mass (building's heat capacity)
- Previous temperature (thermal inertia)

This creates realistic sensor readings that feed ML models and AI recommendations.

Integration point: Called from lifecycle_orchestrator._process_hour() each simulated hour
"""

import logging
from datetime import datetime, date
from typing import Optional, Dict, Any

from app.database.supabase_client import get_supabase_client
from app.services.energy_cost_service import EnergyCostService
from app.services.lighting_simulation_engine import update_simulation_lighting
from app.services.water_consumption_engine import update_simulation_water

logger = logging.getLogger(__name__)


class ThermalSimulationEngine:
    """Calculates and updates zone temperatures during simulation."""

    def __init__(self, building_id: str, consider_equipment_health: bool = False):
        self.building_id = building_id
        self.supabase = get_supabase_client()

        # Initialize cost service for tariff calculations
        self.cost_service = EnergyCostService(building_id=building_id)

        # Thermal parameters (building-specific, can be customized)
        self.OCCUPANT_HEAT_GAIN = 100  # Watts per person
        self.EQUIPMENT_HEAT_GAIN = 50  # Watts per zone baseline
        self.THERMAL_MASS_FACTOR = 0.7  # Inertia: how much temp carries over (0-1)
        self.HVAC_RESPONSE_FACTOR = 0.5  # How quickly HVAC reaches setpoint
        self.SOLAR_GAIN_FACTOR = 1.2  # Afternoon solar gain multiplier
        self.NIGHT_SETBACK_OFFSET = -2  # Degrees offset for night mode

        # Equipment Health Degradation
        # Set to True for maintenance/fault simulations to model HVAC performance degradation
        # Set to False (default) for normal simulations where equipment stays healthy
        self.CONSIDER_EQUIPMENT_HEALTH = consider_equipment_health

        # Cache zone metadata to avoid repeated DB queries
        self._zone_cache: Dict[str, Dict[str, Any]] = {}
        self._last_temps: Dict[str, float] = {}  # Track previous hour temps
        self._equipment_health_cache: Dict[str, int] = {}  # equipment_id -> health_score

        # HVAC Power Consumption Parameters
        # FCU = Fan Coil Unit, AHU = Air Handling Unit
        self.FCU_BASELINE_POWER = 2.0  # kW when running at base load
        self.AHU_BASELINE_POWER = 5.0  # kW when running at base load
        self.FCU_MAX_POWER = 8.0  # kW at maximum load
        self.AHU_MAX_POWER = 25.0  # kW at maximum load
        self.CHILLER_COP = 3.5  # Coefficient of Performance (typical value)
        self.CHILLER_MIN_POWER = 15.0  # kW minimum power when running

        # Power consumption tracking
        self._hvac_power_cache: Dict[str, float] = {}  # zone_id -> power_kw
        self._chiller_power_cache: float = 0.0  # Total chiller power

        # Daily cost tracking (resets each day)
        self._daily_hourly_power: Dict[int, float] = {}  # {hour: total_hvac_kw}
        self._current_simulation_date: Optional[date] = None

    async def update_zone_temperatures(
        self,
        simulated_hour: int,
        occupancy_data: Dict[str, float],  # zone_id -> occupancy_percent
        ambient_temp: float,  # Current ambient temperature (°C)
        is_night_mode: bool,  # Is building in night setback?
        hvac_status: Optional[Dict[str, Any]] = None,  # Optional HVAC overrides
        simulated_date: Optional[datetime] = None,  # Date for tariff band calculation
    ) -> Dict[str, float]:
        """
        Calculate and update temperature for all zones in the building.

        Args:
            simulated_hour: Hour of day (0-23)
            occupancy_data: Zone occupancy percentages {zone_id: occupancy_pct}
            ambient_temp: Ambient air temperature (°C)
            is_night_mode: Whether building is in night setback mode
            hvac_status: Optional HVAC control status {zone_id: {setpoint, fan_speed}}

        Returns:
            Dictionary of updated zone temperatures {zone_id: temp_celsius}
        """
        try:
            # Load zone metadata if not cached
            if not self._zone_cache:
                await self._load_zone_metadata()

            calculated_temps = {}

            for zone_id, zone_config in self._zone_cache.items():
                # Get current occupancy for this zone (default 0%)
                occupancy_pct = occupancy_data.get(zone_id, 0.0)

                # Get HVAC setpoint for this zone
                setpoint = zone_config.get("setpoint", 22.0)
                if is_night_mode:
                    setpoint += self.NIGHT_SETBACK_OFFSET

                # Calculate new temperature
                new_temp = self._calculate_zone_temperature(
                    zone_id=zone_id,
                    simulated_hour=simulated_hour,
                    occupancy_pct=occupancy_pct,
                    ambient_temp=ambient_temp,
                    setpoint=setpoint,
                    zone_config=zone_config,
                )

                calculated_temps[zone_id] = new_temp

                # Update in-memory last temp for next hour's calculation
                self._last_temps[zone_id] = new_temp

            # Write sensor readings to database
            await self._write_sensor_readings(
                simulated_hour=simulated_hour,
                zone_temps=calculated_temps,
                occupancy_data=occupancy_data,
                ambient_temp=ambient_temp,
                is_night_mode=is_night_mode,
            )

            # Calculate and write HVAC power consumption
            power_result = await self.calculate_hvac_power_consumption(
                simulated_hour=simulated_hour,
                zone_temps=calculated_temps,
                occupancy_data=occupancy_data,
                ambient_temp=ambient_temp,
            )

            # Track daily power and calculate cost at end of day
            if simulated_date:
                total_hvac = power_result.get("total_hvac_power", 0.0)
                await self.track_and_calculate_daily_cost(
                    simulated_hour=simulated_hour,
                    total_hvac_power=total_hvac,
                    simulated_date=simulated_date,
                )

            # === Calculate Lighting Energy ===
            # DALI controls reduce lighting during high daylight periods
            daylight_lux = self._estimate_daylight_lux(
                simulated_hour=simulated_hour,
                cloud_cover=getattr(self, '_current_cloud_cover', 0.0),
            )

            await update_simulation_lighting(
                building_id=self.building_id,
                simulated_hour=simulated_hour,
                occupancy_data=occupancy_data,
                daylight_lux=daylight_lux,
                cloud_cover_pct=getattr(self, '_current_cloud_cover', 0.0),
                is_raining=getattr(self, '_current_is_raining', False),
                simulated_date=simulated_date,
            )

            await update_simulation_water(
                building_id=self.building_id,
                simulated_hour=simulated_hour,
                occupancy_data=occupancy_data,
                cloud_cover_pct=getattr(self, '_current_cloud_cover', 0.0),
                is_raining=getattr(self, '_current_is_raining', False),
                simulated_date=simulated_date,
            )

            logger.debug(
                f"[THERMAL] Updated {len(calculated_temps)} zones at hour {simulated_hour:02d}:00 | "
                f"Ambient: {ambient_temp:.1f}°C | "
                f"Avg occupancy: {sum(occupancy_data.values()) / max(len(occupancy_data), 1):.0f}%"
            )

            return calculated_temps

        except Exception as e:
            logger.error(f"[THERMAL ERROR] Failed to update zone temperatures: {e}", exc_info=True)
            return {}

    def _calculate_zone_temperature(
        self,
        zone_id: str,
        simulated_hour: int,
        occupancy_pct: float,
        ambient_temp: float,
        setpoint: float,
        zone_config: Dict[str, Any],
    ) -> float:
        """
        Calculate new zone temperature based on thermal dynamics.

        Physics model:
            ΔT = (Heat_in - Heat_out) / Thermal_mass
            Heat_in = Occupancy_gain + Equipment_gain + Solar_gain
            Heat_out = HVAC_cooling + Wall_losses
            HVAC_Response *= Equipment_Health_Factor (if enabled)
        """

        # Get previous temperature (or use setpoint as initial)
        prev_temp = self._last_temps.get(zone_id, setpoint)

        # === Heat Generation ===
        # Occupancy heat (people + equipment)
        typical_occupancy = zone_config.get("typical_occupancy", 10)
        people_count = max(1, int(typical_occupancy * (occupancy_pct / 100.0)))
        occupancy_heat = people_count * self.OCCUPANT_HEAT_GAIN  # Watts

        # Equipment baseline heat (lighting, computers, etc.)
        equipment_heat = self.EQUIPMENT_HEAT_GAIN * (occupancy_pct / 100.0 + 0.2)  # Always on

        # Solar gain (higher in afternoon, especially in summer)
        # Peaks at hour 14 (2pm), minimal before 8am and after 18pm
        solar_hour_factor = self._calculate_solar_factor(simulated_hour)
        solar_gain = (ambient_temp - 15) * solar_hour_factor  # Only add if warmer than baseline

        total_heat_generation = occupancy_heat + equipment_heat + solar_gain

        # === HVAC Response ===
        # How quickly does HVAC push zone toward setpoint?
        # Fan speed affects this: auto/high = fast, low/off = slow
        fan_speed = zone_config.get("fan_speed", "auto")
        fan_response_factor = {
            "off": 0.1,
            "low": 0.3,
            "medium": 0.5,
            "auto": 0.7,
            "high": 0.9,
        }.get(fan_speed, 0.7)

        # Equipment health degradation (if enabled)
        # Simulates HVAC performance loss due to degraded equipment
        hvac_health_factor = 1.0
        equipment_health_note = ""

        if self.CONSIDER_EQUIPMENT_HEALTH:
            # Get equipment serving this zone
            fcu_id = zone_config.get("fcu_id")
            if fcu_id and fcu_id in self._equipment_health_cache:
                health_score = self._equipment_health_cache[fcu_id]
                # Health impact: at 100% = 1.0 factor, at 50% = 0.5, at 0% = 0.0
                hvac_health_factor = max(0.0, health_score / 100.0)
                equipment_health_note = f" [HEALTH: {health_score}% → factor {hvac_health_factor:.2f}]"

        # HVAC tries to pull zone toward setpoint (reduced by equipment health if degraded)
        hvac_effect = (setpoint - prev_temp) * fan_response_factor * self.HVAC_RESPONSE_FACTOR * hvac_health_factor

        # === Building Losses ===
        # Natural cooling/heating toward ambient (through walls, ventilation)
        wall_loss_rate = 0.15  # How much zone temp approaches ambient per hour
        ambient_loss = (ambient_temp - prev_temp) * wall_loss_rate

        # === Thermal Inertia ===
        # Building mass resists temperature changes (~70% of previous temp remains)
        inertia_contribution = prev_temp * self.THERMAL_MASS_FACTOR

        # === Final Temperature Calculation ===
        # Temperature change per hour (simplified)
        temp_change = (total_heat_generation / 1000) + hvac_effect + ambient_loss

        # New temperature: blend previous temp (inertia) with change
        new_temp = (inertia_contribution + temp_change) / (self.THERMAL_MASS_FACTOR + 1)

        # Clamp to reasonable bounds (5°C - 35°C)
        new_temp = max(5.0, min(35.0, new_temp))

        logger.debug(
            f"[TEMP CALC] {zone_id} h={simulated_hour:02d}: "
            f"prev={prev_temp:.1f}°C → new={new_temp:.1f}°C | "
            f"occ={occupancy_pct:.0f}% heat={total_heat_generation:.0f}W | "
            f"hvac={hvac_effect:+.1f}°C loss={ambient_loss:+.1f}°C{equipment_health_note}"
        )

        return new_temp

    def _calculate_solar_factor(self, hour: int) -> float:
        """
        Solar gain factor by hour of day.
        Peaks in early afternoon, minimal at night.
        """
        # Simplified solar profile
        if hour < 8 or hour > 18:
            return 0.0  # No direct solar at night
        elif 8 <= hour < 11:
            return 0.3  # Morning: sun angle low
        elif 11 <= hour < 14:
            return 0.8  # Midday: high angle
        elif 14 <= hour < 16:
            return 1.2  # Afternoon: peak
        elif 16 <= hour < 18:
            return 0.5  # Late afternoon: declining
        else:
            return 0.0

    def _estimate_daylight_lux(self, simulated_hour: int, cloud_cover: float) -> float:
        """
        Estimate available daylight in lux based on hour and cloud cover.

        Uses simplified solar geometry:
        - Peak daylight: 1000 lux at solar noon (hour 12)
        - Minimum: 0 lux at night (before 6am, after 6pm)
        - Cloud cover reduces by 30-60%

        Returns:
            Estimated daylight in lux (0-1000+)
        """
        # No daylight at night
        if simulated_hour < 6 or simulated_hour > 18:
            return 0.0

        # Clear sky profile (peak at noon)
        if 6 <= simulated_hour < 12:
            # Morning rise: linear increase
            base_lux = (simulated_hour - 6) / 6.0 * 1000.0
        elif 12 <= simulated_hour < 18:
            # Afternoon decline: linear decrease
            base_lux = (18.0 - simulated_hour) / 6.0 * 1000.0
        else:
            base_lux = 1000.0

        # Reduce for cloud cover (30-60% reduction based on coverage)
        cloud_factor = 1.0 - (cloud_cover / 100.0 * 0.6)
        daylight_lux = base_lux * max(0.1, cloud_factor)  # Min 10% even overcast

        return round(daylight_lux, 1)

    async def _load_zone_metadata(self) -> None:
        """Load zone configuration (setpoint, occupancy, fan speed) from database."""
        try:
            response = self.supabase.table("hvac_zones").select(
                "id, zone_id, zone_name, floor, typical_occupancy, area_sqm, setpoint, heating_setpoint, cooling_setpoint, fan_speed, status, fcu_id"
            ).eq("building_id", self.building_id).execute()

            for zone in response.data:
                self._zone_cache[zone["zone_id"]] = {
                    "id": zone["id"],
                    "zone_name": zone["zone_name"],
                    "floor": zone["floor"],
                    "typical_occupancy": zone.get("typical_occupancy", 10),
                    "area_sqm": zone.get("area_sqm", 50),
                    "setpoint": zone.get("setpoint", 22.0),
                    "heating_setpoint": zone.get("heating_setpoint", 20.0),
                    "cooling_setpoint": zone.get("cooling_setpoint", 24.0),
                    "fan_speed": zone.get("fan_speed", "auto"),
                    "status": zone.get("status", "idle"),
                    "fcu_id": zone.get("fcu_id"),  # Link to FCU equipment for health checks
                }

            # Load equipment health if enabled
            if self.CONSIDER_EQUIPMENT_HEALTH:
                await self._load_equipment_health()

            logger.info(f"[THERMAL] Loaded metadata for {len(self._zone_cache)} zones in {self.building_id}")
        except Exception as e:
            logger.error(f"[THERMAL] Failed to load zone metadata: {e}", exc_info=True)

    async def _load_equipment_health(self) -> None:
        """
        Load equipment health scores for HVAC equipment.

        Used for maintenance/fault simulations to degrade HVAC performance
        based on equipment health degradation.

        Health mapping:
        - 100% = Full HVAC response
        - 75% = 75% HVAC response
        - 50% = 50% HVAC response (equipment degraded)
        - <50% = Significant performance loss
        """
        try:
            # Get all HVAC equipment (FCU, AHU, CHILLER, VAV) for this building
            response = self.supabase.table("equipment").select(
                "id, code, type, health_score"
            ).eq("building_id", self.building_id).in_(
                "type", ["FCU", "AHU", "CHILLER", "VAV", "fcu", "ahu", "chiller", "vav"]
            ).execute()

            for equipment in response.data:
                eq_id = equipment["id"]
                health = equipment.get("health_score", 100)
                self._equipment_health_cache[eq_id] = health

                if health < 100:
                    logger.info(
                        f"[THERMAL] Equipment {equipment['code']} health: {health}% "
                        f"(HVAC response will be reduced)"
                    )

            logger.debug(f"[THERMAL] Loaded health for {len(self._equipment_health_cache)} equipment items")
        except Exception as e:
            logger.warning(f"[THERMAL] Could not load equipment health: {e}")

    async def _write_sensor_readings(
        self,
        simulated_hour: int,
        zone_temps: Dict[str, float],
        occupancy_data: Dict[str, float],
        ambient_temp: float,
        is_night_mode: bool,
    ) -> None:
        """
        Write temperature sensor readings to database.
        Called once per simulated hour for each zone.
        """
        try:
            # Build rows for sensor_readings table
            sensor_readings = []

            for zone_id, zone_config in self._zone_cache.items():
                temp = zone_temps.get(zone_id, zone_config.get("setpoint", 22.0))
                occupancy = occupancy_data.get(zone_id, 0.0)

                # Find sensor code for this zone
                sensor_code = f"{zone_id}-TEMP"

                # Get sensor ID from database
                sensor_response = self.supabase.table("sensors").select("id").eq("code", sensor_code).execute()

                if not sensor_response.data:
                    logger.warning(f"[THERMAL] Sensor not found: {sensor_code}")
                    continue

                sensor_id = sensor_response.data[0]["id"]

                # Create reading row
                # Timestamp is NOW (real time), but we track simulated hour in metadata
                reading_row = {
                    "sensor_id": sensor_id,
                    "time": datetime.utcnow().isoformat() + "Z",
                    "value": round(temp, 2),
                    "quality": "good",
                    "metadata": {
                        "simulated_hour": simulated_hour,
                        "occupancy_pct": round(occupancy, 1),
                        "ambient_temp": round(ambient_temp, 1),
                        "night_mode": is_night_mode,
                        "zone_id": zone_id,
                        "zone_name": zone_config.get("zone_name"),
                    },
                }

                sensor_readings.append(reading_row)

            if sensor_readings:
                # Insert batch of readings
                self.supabase.table("sensor_readings").insert(sensor_readings).execute()

                logger.debug(
                    f"[THERMAL] Inserted {len(sensor_readings)} sensor readings "
                    f"for hour {simulated_hour:02d}:00"
                )

        except Exception as e:
            logger.error(f"[THERMAL] Failed to write sensor readings: {e}", exc_info=True)

    async def calculate_hvac_power_consumption(
        self,
        simulated_hour: int,
        zone_temps: Dict[str, float],
        occupancy_data: Dict[str, float],
        ambient_temp: float,
    ) -> Dict[str, float]:
        """
        Calculate HVAC power consumption per zone and for chiller.

        Returns:
            {
                "zone_power": {zone_id: power_kw},
                "chiller_power": power_kw,
                "total_hvac_power": power_kw
            }
        """
        try:
            zone_power = {}
            total_zone_cooling_demand = 0.0

            for zone_id, zone_config in self._zone_cache.items():
                current_temp = zone_temps.get(zone_id, zone_config.get("setpoint", 22.0))
                setpoint = zone_config.get("setpoint", 22.0)
                occupancy_pct = occupancy_data.get(zone_id, 0.0)
                fcu_id = zone_config.get("fcu_id")

                # Calculate temperature offset (how far from setpoint)
                temp_offset = abs(current_temp - setpoint)

                # Calculate cooling load for this zone (in kW)
                # Load increases with temp_offset and occupancy
                cooling_load = temp_offset * 0.5 + (occupancy_pct / 100.0) * 2.0

                # Determine equipment type and calculate power
                equipment_type = "FCU"  # Default
                if zone_config.get("zone_name", "").startswith("Entry"):
                    equipment_type = "AHU"  # Entry zones use AHU

                if equipment_type == "FCU":
                    baseline = self.FCU_BASELINE_POWER
                    max_power = self.FCU_MAX_POWER
                else:  # AHU
                    baseline = self.AHU_BASELINE_POWER
                    max_power = self.AHU_MAX_POWER

                # Power ∝ cooling_load (normalized 0-1)
                load_fraction = min(1.0, cooling_load / 5.0)
                hvac_power = baseline + (max_power - baseline) * load_fraction

                # Apply equipment health factor if enabled
                if self.CONSIDER_EQUIPMENT_HEALTH and fcu_id in self._equipment_health_cache:
                    health_score = self._equipment_health_cache[fcu_id]
                    hvac_power *= (health_score / 100.0)

                # Only consume power if occupancy > 0 or temp deviation > 1°C
                if occupancy_pct < 5 and temp_offset < 1.0:
                    hvac_power *= 0.1  # Minimal power in unoccupied idle zones

                zone_power[zone_id] = round(hvac_power, 2)
                total_zone_cooling_demand += cooling_load
                self._hvac_power_cache[zone_id] = hvac_power

            # Calculate chiller power
            # Chiller power = (Total cooling load / COP) + margin for distribution
            chiller_load_kw = total_zone_cooling_demand * 1.2  # 20% margin for chilled water distribution
            chiller_power = max(self.CHILLER_MIN_POWER, chiller_load_kw / self.CHILLER_COP)
            self._chiller_power_cache = round(chiller_power, 2)

            # Write power to database
            await self._write_power_consumption(
                simulated_hour=simulated_hour,
                zone_power=zone_power,
                chiller_power=chiller_power,
            )

            total_hvac = sum(zone_power.values()) + chiller_power

            logger.debug(
                f"[POWER] Hour {simulated_hour:02d}: "
                f"Zones={sum(zone_power.values()):.1f}kW + "
                f"Chiller={chiller_power:.1f}kW = "
                f"Total {total_hvac:.1f}kW"
            )

            return {
                "zone_power": zone_power,
                "chiller_power": chiller_power,
                "total_hvac_power": total_hvac,
            }

        except Exception as e:
            logger.error(f"[POWER] Failed to calculate HVAC power: {e}", exc_info=True)
            return {"zone_power": {}, "chiller_power": 0.0, "total_hvac_power": 0.0}

    async def _write_power_consumption(
        self,
        simulated_hour: int,
        zone_power: Dict[str, float],
        chiller_power: float,
    ) -> None:
        """
        Write HVAC power consumption to power_meters table.

        Updates the active_power_kw field for:
        - HVAC feeder (sum of all zone + chiller)
        - Can be extended to track chiller separately if meter exists
        """
        try:
            # Calculate total HVAC power
            total_hvac_power = sum(zone_power.values()) + chiller_power

            # Update HVAC feeder power meter
            # This meter tracks all HVAC consumption (zones + chiller)
            hvac_feeder_update = {
                "meter_id": "S002-MTR-B1-HVAC",  # HVAC Plant Room meter
                "active_power_kw": round(total_hvac_power, 2),
                "last_update": datetime.utcnow().isoformat() + "Z",
            }

            # Upsert into power_meters table
            response = self.supabase.table("power_meters").upsert(
                hvac_feeder_update,
                on_conflict="meter_id"
            ).execute()

            # Also track hourly energy consumption
            # Convert kW * 1 hour to kWh
            kwh_consumed = round(total_hvac_power, 2)  # 1 hour = 1 * kW = kWh

            # Create energy consumption history record
            # This feeds the dashboard and AI recommendations
            energy_record = {
                "building_id": self.building_id,
                "meter_id": "S002-MTR-B1-HVAC",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "energy_kwh": kwh_consumed,
                "energy_type": "HVAC",
                "simulated_hour": simulated_hour,
                "zone_details": zone_power,  # Store per-zone breakdown for analysis
                "chiller_power_kw": chiller_power,
            }

            # Insert into energy_consumption_history
            try:
                self.supabase.table("energy_consumption_history").insert(
                    energy_record
                ).execute()
            except Exception as e:
                logger.warning(f"[POWER] Could not record energy history: {e}")

            logger.debug(
                f"[POWER] Updated power meter S002-MTR-B1-HVAC: "
                f"{total_hvac_power:.1f}kW, {kwh_consumed:.2f}kWh for hour {simulated_hour:02d}"
            )

        except Exception as e:
            logger.error(f"[POWER] Failed to write power consumption: {e}", exc_info=True)

    async def track_and_calculate_daily_cost(
        self,
        simulated_hour: int,
        total_hvac_power: float,
        simulated_date: datetime,
    ) -> None:
        """
        Track hourly power and calculate daily cost at end of day (hour 23).

        Called automatically from lifecycle orchestrator each hour.
        """
        try:
            # Reset tracking if date changed
            if self._current_simulation_date != simulated_date.date():
                self._daily_hourly_power = {}
                self._current_simulation_date = simulated_date.date()

            # Track this hour's power
            self._daily_hourly_power[simulated_hour] = round(total_hvac_power, 2)

            # At end of day (hour 23), calculate and record daily cost
            if simulated_hour == 23:
                daily_cost = await self.cost_service.calculate_daily_cost(
                    simulated_date=simulated_date,
                    hourly_power_data=self._daily_hourly_power,
                )

                # Write to database for dashboard
                await self.cost_service.write_daily_cost_summary(
                    simulated_date=simulated_date,
                    daily_cost=daily_cost,
                )

                logger.info(
                    f"[COST] Daily summary for {simulated_date.date()}: "
                    f"{daily_cost['total_energy_kwh']:.1f}kWh = R{daily_cost['total_cost_r']:.2f} "
                    f"(avg {daily_cost['average_rate_r_kwh']:.3f}R/kWh)"
                )
        except Exception as e:
            logger.error(f"[COST] Failed to track/calculate daily cost: {e}", exc_info=True)


# Singleton instance per building
_thermal_engines: Dict[str, ThermalSimulationEngine] = {}


def get_thermal_engine(
    building_id: str,
    consider_equipment_health: bool = False
) -> ThermalSimulationEngine:
    """
    Get or create thermal engine for building.

    Args:
        building_id: Building identifier
        consider_equipment_health: If True, HVAC response degrades with equipment health
                                  Set to True for maintenance/fault simulations
                                  Default False for normal simulations
    """
    # Create new engine if needed or if health consideration changes
    cache_key = f"{building_id}:health={consider_equipment_health}"

    if building_id not in _thermal_engines:
        _thermal_engines[building_id] = ThermalSimulationEngine(
            building_id,
            consider_equipment_health=consider_equipment_health
        )

    return _thermal_engines[building_id]


async def update_simulation_temperatures(
    building_id: str,
    simulated_hour: int,
    occupancy_data: Dict[str, float],
    ambient_temp: float,
    is_night_mode: bool = False,
    consider_equipment_health: bool = False,
    simulated_date: Optional[datetime] = None,
) -> Dict[str, float]:
    """
    Public API to update zone temperatures during simulation.

    Args:
        building_id: Building ID
        simulated_hour: Hour (0-23)
        occupancy_data: Zone occupancy percentages
        ambient_temp: Ambient temperature
        is_night_mode: Whether in night setback mode
        consider_equipment_health: Enable equipment health degradation
                                  Set to True for maintenance/fault simulations
                                  Default False for normal simulations
        simulated_date: Current simulation date (for tariff band calculation)

    Usage in lifecycle_orchestrator:
        from app.services.thermal_simulation_engine import update_simulation_temperatures

        # Normal simulation (equipment healthy):
        temps = await update_simulation_temperatures(
            building_id=self.building_id,
            simulated_hour=hour,
            occupancy_data={"Zone-001": 75, "Zone-101": 50, ...},
            ambient_temp=18.5,
            is_night_mode=(hour >= 22 or hour < 6),
            consider_equipment_health=False  # Default
        )

        # Maintenance/Fault simulation (equipment can degrade):
        temps = await update_simulation_temperatures(
            building_id=self.building_id,
            simulated_hour=hour,
            occupancy_data=occupancy_data,
            ambient_temp=ambient_temp,
            is_night_mode=is_night_mode,
            consider_equipment_health=True  # Enable health degradation
        )
    """
    engine = get_thermal_engine(building_id, consider_equipment_health=consider_equipment_health)
    return await engine.update_zone_temperatures(
        simulated_hour=simulated_hour,
        occupancy_data=occupancy_data,
        ambient_temp=ambient_temp,
        is_night_mode=is_night_mode,
        simulated_date=simulated_date,
    )

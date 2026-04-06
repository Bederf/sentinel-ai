"""
Thermal Simulation Engine

Simulates realistic building physics:
- Zone temperatures (occupancy heat, solar gain, HVAC cooling, thermal mass)
- CO2 levels (occupant generation, ventilation dilution, outdoor baseline)
- Chiller plant with N+1 redundancy (lead/lag staging, cascade on fault)
- HVAC power consumption (zone FCUs/AHUs + chiller plant)

This creates realistic sensor readings that feed ML models and AI recommendations.

Integration point: Called from lifecycle_orchestrator._process_hour() each simulated hour
"""

import logging
from datetime import date, datetime
from typing import Any

from app.database.supabase_client import get_supabase_client
from app.services.cost_validation_engine import get_cost_validation_engine
from app.services.energy_cost_service import EnergyCostService
from app.services.lighting_simulation_engine import update_simulation_lighting
from app.services.power_meter_validation_engine import get_power_meter_validation_engine
from app.services.simulation_store import get_simulation_store
from app.services.water_consumption_engine import update_simulation_water

logger = logging.getLogger(__name__)


class ThermalSimulationEngine:
    """Calculates and updates zone temperatures during simulation."""

    def __init__(self, site_id: str, consider_equipment_health: bool = False):
        self.site_id = site_id
        self.supabase = get_supabase_client()
        self.sim_store = get_simulation_store(site_id)

        # Initialize cost service for tariff calculations
        self.cost_service = EnergyCostService(site_id=site_id)

        # Thermal parameters (building-specific, can be customized)
        self.OCCUPANT_HEAT_GAIN = 100  # Watts per person
        self.EQUIPMENT_HEAT_GAIN = 150  # Watts per zone baseline (450 sqm zone)
        self.THERMAL_MASS_FACTOR = 0.92  # Inertia: 9000 sqm concrete office retains ~92% per hour
        self.HVAC_RESPONSE_FACTOR = 0.5  # How quickly HVAC reaches setpoint
        self.SOLAR_GAIN_FACTOR = 1.2  # Afternoon solar gain multiplier
        self.NIGHT_SETBACK_OFFSET = -2  # Degrees offset for night mode

        # Equipment Health Degradation
        # Set to True for maintenance/fault simulations to model HVAC performance degradation
        # Set to False (default) for normal simulations where equipment stays healthy
        self.CONSIDER_EQUIPMENT_HEALTH = consider_equipment_health

        # Cache zone metadata to avoid repeated DB queries
        self._zone_cache: dict[str, dict[str, Any]] = {}
        self._last_temps: dict[str, float] = {}  # Track previous hour temps
        self._equipment_health_cache: dict[str, int] = {}  # equipment_id -> health_score
        self._sensor_id_cache: dict[str, str] = {}  # sensor_code -> sensor_id (UUID)
        self._sensor_cache_loaded: bool = False

        # CO2 Simulation Parameters
        self.OUTDOOR_CO2_PPM = 420.0  # Outdoor baseline (2026 global avg)
        self.CO2_PER_PERSON_PER_HOUR = 20.0  # ppm rise per person per hour (typical office zone)
        self.VENTILATION_DILUTION_RATE = 0.4  # Fraction of CO2 above baseline removed per hour by AHU
        self.DCV_CO2_THRESHOLD = 800.0  # ppm — demand-controlled ventilation kicks in harder
        self.DCV_BOOST_FACTOR = 1.5  # Extra ventilation multiplier above threshold

        # CO2 state tracking
        self._zone_co2: dict[str, float] = {}  # zone_id -> current CO2 ppm

        # HVAC Power Consumption Parameters
        # FCU = Fan Coil Unit, AHU = Air Handling Unit
        self.FCU_BASELINE_POWER = 5.0  # kW when running at base load (450 sqm zone ≈ 3 FCUs)
        self.AHU_BASELINE_POWER = 15.0  # kW when running at base load
        self.FCU_MAX_POWER = 18.0  # kW at maximum load
        self.AHU_MAX_POWER = 45.0  # kW at maximum load

        # Chiller Plant — N+1 Redundancy
        # Two chillers: lead handles base load, lag picks up on high demand or lead fault
        self.CHILLER_COP = 3.5  # Coefficient of Performance at full load
        self.CHILLER_PART_LOAD_COP = {  # COP varies with load fraction
            0.0: 0.0,
            0.2: 2.0,
            0.4: 3.0,
            0.6: 3.5,
            0.8: 3.4,
            1.0: 3.2,
        }
        self.CHILLER_MIN_POWER = 25.0  # kW minimum power when running
        self.CHILLER_CAPACITY_KW = 350.0  # kW cooling capacity per chiller (9,000 sqm building)
        self.CHILLER_IDS = ["S002-CHILLER-B1-001", "S002-CHILLER-B1-002"]

        # Chiller plant state
        self._chiller_states: dict[str, dict[str, Any]] = {
            cid: {"role": "lead" if i == 0 else "lag", "running": False, "load_pct": 0.0, "health": 100.0}
            for i, cid in enumerate(self.CHILLER_IDS)
        }

        # Power consumption tracking
        self._hvac_power_cache: dict[str, float] = {}  # zone_id -> power_kw
        self._chiller_power_cache: float = 0.0  # Total chiller power

        # Daily cost tracking (resets each day)
        self._daily_hourly_power: dict[int, float] = {}  # {hour: total_hvac_kw}
        self._current_simulation_date: date | None = None

    async def update_zone_temperatures(
        self,
        simulated_hour: int,
        occupancy_data: dict[str, float],  # zone_id -> occupancy_percent
        ambient_temp: float,  # Current ambient temperature (°C)
        is_night_mode: bool,  # Is building in night setback?
        hvac_status: dict[str, Any] | None = None,  # Optional HVAC overrides
        simulated_date: datetime | None = None,  # Date for tariff band calculation
    ) -> dict[str, float]:
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

                # Calculate CO2 level for this zone
                fan_speed = zone_config.get("fan_speed", "auto")
                fan_response = {"off": 0.1, "low": 0.3, "medium": 0.5, "auto": 0.7, "high": 0.9}.get(fan_speed, 0.7)
                self._calculate_zone_co2(
                    zone_id=zone_id,
                    occupancy_pct=occupancy_pct,
                    fan_response_factor=fan_response,
                    zone_config=zone_config,
                )

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
                simulated_date=simulated_date,
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
                cloud_cover=getattr(self, "_current_cloud_cover", 0.0),
            )

            await update_simulation_lighting(
                site_id=self.site_id,
                simulated_hour=simulated_hour,
                occupancy_data=occupancy_data,
                daylight_lux=daylight_lux,
                cloud_cover_pct=getattr(self, "_current_cloud_cover", 0.0),
                is_raining=getattr(self, "_current_is_raining", False),
                simulated_date=simulated_date,
            )

            await update_simulation_water(
                site_id=self.site_id,
                simulated_hour=simulated_hour,
                occupancy_data=occupancy_data,
                cloud_cover_pct=getattr(self, "_current_cloud_cover", 0.0),
                is_raining=getattr(self, "_current_is_raining", False),
                simulated_date=simulated_date,
            )

            avg_co2 = sum(self._zone_co2.values()) / max(len(self._zone_co2), 1)
            logger.debug(
                f"[THERMAL] Updated {len(calculated_temps)} zones at hour {simulated_hour:02d}:00 | "
                f"Ambient: {ambient_temp:.1f}°C | "
                f"Avg occupancy: {sum(occupancy_data.values()) / max(len(occupancy_data), 1):.0f}% | "
                f"Avg CO2: {avg_co2:.0f}ppm"
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
        zone_config: dict[str, Any],
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
        typical_occupancy = zone_config.get("typical_occupancy") or 10
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
        wall_loss_rate = 0.04  # How much zone temp approaches ambient per hour (well-insulated 9000 sqm)
        ambient_loss = (ambient_temp - prev_temp) * wall_loss_rate

        # === Final Temperature Calculation ===
        # Temperature change per hour (simplified)
        temp_change = (total_heat_generation / 1000) + hvac_effect + ambient_loss

        # Thermal inertia: building mass retains most of previous temperature
        # Only (1 - THERMAL_MASS_FACTOR) of the change applies per hour
        new_temp = prev_temp + temp_change * (1 - self.THERMAL_MASS_FACTOR)

        # Building safety floor: BMS night setback keeps zones above 19°C
        # (heating kicks in before reaching the 18°C safety minimum)
        new_temp = max(19.0, min(35.0, new_temp))

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

    # ------------------------------------------------------------------
    # CO2 Simulation
    # ------------------------------------------------------------------

    def _calculate_zone_co2(
        self,
        zone_id: str,
        occupancy_pct: float,
        fan_response_factor: float,
        zone_config: dict[str, Any],
    ) -> float:
        """Calculate zone CO2 level based on occupancy and ventilation.

        Physics model (simplified mass-balance per hour):
            CO2_new = CO2_prev
                    + generation (people breathing)
                    - dilution   (AHU fresh-air exchange)
                    + infiltration toward outdoor baseline

        When CO2 exceeds the DCV threshold the AHU increases fresh-air,
        modelled by multiplying the dilution rate by DCV_BOOST_FACTOR.
        """
        prev_co2 = self._zone_co2.get(zone_id, self.OUTDOOR_CO2_PPM)

        # --- Generation: people produce CO2 ---
        typical_occ = zone_config.get("typical_occupancy") or 10
        people_count = max(0, int(typical_occ * (occupancy_pct / 100.0)))
        generation = people_count * self.CO2_PER_PERSON_PER_HOUR  # ppm rise

        # --- Dilution: ventilation removes CO2 above outdoor baseline ---
        dilution_rate = self.VENTILATION_DILUTION_RATE * fan_response_factor
        if prev_co2 > self.DCV_CO2_THRESHOLD:
            dilution_rate *= self.DCV_BOOST_FACTOR  # DCV kicks in harder
        dilution = (prev_co2 - self.OUTDOOR_CO2_PPM) * dilution_rate

        # --- Infiltration: slow drift toward outdoor baseline ---
        infiltration = (self.OUTDOOR_CO2_PPM - prev_co2) * 0.05

        new_co2 = prev_co2 + generation - dilution + infiltration
        new_co2 = max(self.OUTDOOR_CO2_PPM, min(2000.0, new_co2))  # clamp

        self._zone_co2[zone_id] = new_co2
        return new_co2

    # ------------------------------------------------------------------
    # Chiller Plant — N+1 Redundancy
    # ------------------------------------------------------------------

    def _interpolate_cop(self, load_fraction: float) -> float:
        """Interpolate COP from part-load curve.

        The curve is defined as {load_fraction: COP} in CHILLER_PART_LOAD_COP.
        Linear interpolation between the two nearest points.
        """
        load_fraction = max(0.0, min(1.0, load_fraction))
        points = sorted(self.CHILLER_PART_LOAD_COP.items())

        # Exact match
        for lf, cop in points:
            if abs(lf - load_fraction) < 1e-6:
                return cop

        # Find bracketing points
        for i in range(len(points) - 1):
            lf_lo, cop_lo = points[i]
            lf_hi, cop_hi = points[i + 1]
            if lf_lo <= load_fraction <= lf_hi:
                t = (load_fraction - lf_lo) / (lf_hi - lf_lo)
                return cop_lo + t * (cop_hi - cop_lo)

        return points[-1][1]  # fallback: full-load COP

    def _update_chiller_plant(self, total_cooling_demand_kw: float) -> float:
        """Update chiller plant state and return total chiller electrical power (kW).

        N+1 redundancy logic:
        - Lead chiller handles up to 100% of its capacity.
        - If demand exceeds lead capacity OR lead health < 50%, lag starts.
        - If lead faults (health < 20%), lag takes full load.
        - Each running chiller's electrical power = cooling_output / COP(load_fraction).
        """
        total_capacity = self.CHILLER_CAPACITY_KW  # per chiller

        # Identify lead and lag
        lead_id = next((cid for cid, s in self._chiller_states.items() if s["role"] == "lead"), self.CHILLER_IDS[0])
        lag_id = next((cid for cid, s in self._chiller_states.items() if s["role"] == "lag"), self.CHILLER_IDS[1])
        lead = self._chiller_states[lead_id]
        lag = self._chiller_states[lag_id]

        # Health-aware capacity: degraded chiller can't deliver full cooling
        lead_effective_capacity = total_capacity * (lead["health"] / 100.0)
        lag_effective_capacity = total_capacity * (lag["health"] / 100.0)

        # --- Cascade logic ---
        lead_faulted = lead["health"] < 20.0
        demand_exceeds_lead = total_cooling_demand_kw > lead_effective_capacity
        lead_degraded = lead["health"] < 50.0

        total_power = 0.0

        if lead_faulted:
            # Lead is down — lag takes full load
            lead["running"] = False
            lead["load_pct"] = 0.0

            lag_load = min(total_cooling_demand_kw, lag_effective_capacity)
            lag_frac = lag_load / total_capacity if total_capacity > 0 else 0
            lag["running"] = lag_load > 0
            lag["load_pct"] = round(lag_frac * 100, 1)

            cop = self._interpolate_cop(lag_frac)
            total_power = lag_load / cop if cop > 0 else 0

            logger.warning(
                f"[CHILLER] Lead {lead_id} FAULTED (health={lead['health']:.0f}%). "
                f"Lag {lag_id} serving {lag_load:.1f}kW @ COP {cop:.2f}"
            )
        elif demand_exceeds_lead or lead_degraded:
            # Lead can't handle alone — split load
            lead_load = min(total_cooling_demand_kw, lead_effective_capacity)
            remaining = max(0, total_cooling_demand_kw - lead_load)
            lag_load = min(remaining, lag_effective_capacity)

            lead_frac = lead_load / total_capacity if total_capacity > 0 else 0
            lag_frac = lag_load / total_capacity if total_capacity > 0 else 0

            lead["running"] = lead_load > 0
            lead["load_pct"] = round(lead_frac * 100, 1)
            lag["running"] = lag_load > 0
            lag["load_pct"] = round(lag_frac * 100, 1)

            lead_cop = self._interpolate_cop(lead_frac)
            lag_cop = self._interpolate_cop(lag_frac)

            lead_power = lead_load / lead_cop if lead_cop > 0 else 0
            lag_power = lag_load / lag_cop if lag_cop > 0 else 0
            total_power = lead_power + lag_power
        else:
            # Lead handles it alone — lag standby
            lead_frac = total_cooling_demand_kw / total_capacity if total_capacity > 0 else 0
            lead_frac = min(1.0, lead_frac)

            lead["running"] = total_cooling_demand_kw > 0
            lead["load_pct"] = round(lead_frac * 100, 1)
            lag["running"] = False
            lag["load_pct"] = 0.0

            cop = self._interpolate_cop(lead_frac)
            total_power = total_cooling_demand_kw / cop if cop > 0 else 0

        # Minimum power when any chiller is running
        if any(s["running"] for s in self._chiller_states.values()):
            total_power = max(self.CHILLER_MIN_POWER, total_power)

        return round(total_power, 2)

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
            # Resolve building code to UUID if needed (hvac_zones.site_id is UUID)
            site_uuid = self.site_id
            try:
                bldg = self.supabase.table("sites").select("id").eq("code", self.site_id).maybe_single().execute()
                if bldg and bldg.data:
                    site_uuid = bldg.data["id"]
            except Exception:
                pass  # Fall through with original value

            response = (
                self.supabase.table("hvac_zones")
                .select(
                    "id, zone_id, zone_name, floor, typical_occupancy, "
                    "area_sqm, setpoint, heating_setpoint, cooling_setpoint, "
                    "fan_speed, status, fcu_id"
                )
                .eq("site_id", site_uuid)
                .execute()
            )

            for zone in response.data:
                self._zone_cache[zone["zone_id"]] = {
                    "id": zone["id"],
                    "zone_name": zone.get("zone_name") or "Unknown",
                    "floor": zone.get("floor") or 0,
                    "typical_occupancy": zone.get("typical_occupancy") or 10,
                    "area_sqm": zone.get("area_sqm") or 50,
                    "setpoint": zone.get("setpoint") or 22.0,
                    "heating_setpoint": zone.get("heating_setpoint") or 20.0,
                    "cooling_setpoint": zone.get("cooling_setpoint") or 24.0,
                    "fan_speed": zone.get("fan_speed") or "auto",
                    "status": zone.get("status") or "idle",
                    "fcu_id": zone.get("fcu_id"),  # Link to FCU equipment for health checks
                }

            # Seed zone temperatures to setpoint (building is already conditioned)
            # This prevents unrealistic cold-start alerts on simulation boot
            for zone_id, zc in self._zone_cache.items():
                if zone_id not in self._last_temps:
                    self._last_temps[zone_id] = zc.get("setpoint", 22.0)

            # Load equipment health if enabled
            if self.CONSIDER_EQUIPMENT_HEALTH:
                await self._load_equipment_health()

            logger.info(f"[THERMAL] Loaded metadata for {len(self._zone_cache)} zones in {self.site_id}")
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
            # Resolve building code to UUID if needed (equipment.site_id is UUID)
            site_uuid = self.site_id
            try:
                bldg = self.supabase.table("sites").select("id").eq("code", self.site_id).maybe_single().execute()
                if bldg and bldg.data:
                    site_uuid = bldg.data["id"]
            except Exception:
                pass

            # Get all HVAC equipment (FCU, AHU, CHILLER, VAV) for this building
            response = (
                self.supabase.table("equipment")
                .select("id, code, type, health_score")
                .eq("site_id", site_uuid)
                .in_("type", ["FCU", "AHU", "CHILLER", "VAV", "fcu", "ahu", "chiller", "vav"])
                .execute()
            )

            for equipment in response.data:
                eq_id = equipment["id"]
                health = equipment.get("health_score", 100)
                self._equipment_health_cache[eq_id] = health

                if health < 100:
                    logger.info(
                        f"[THERMAL] Equipment {equipment['code']} health: {health}% (HVAC response will be reduced)"
                    )

            logger.debug(f"[THERMAL] Loaded health for {len(self._equipment_health_cache)} equipment items")
        except Exception as e:
            logger.warning(f"[THERMAL] Could not load equipment health: {e}")

    def update_health_cache(self, health_dict: dict[str, float]) -> None:
        """Update equipment health cache from external source (e.g., orchestrator).

        Called each simulated hour so the thermal engine uses current health values
        rather than stale day-1 values from the initial DB load.

        Args:
            health_dict: equipment_code -> health_score (0-100)
        """
        updated = 0
        for eq_code, health in health_dict.items():
            # Match by equipment code — zone_cache links zones to FCUs via fcu_id
            # The _equipment_health_cache keys are equipment IDs (UUIDs), but we also
            # need to update by code. Check both the code and try to match fcu_id.
            self._equipment_health_cache[eq_code] = health
            updated += 1

        # Also map codes to zone fcu_ids for zones that reference equipment by ID
        for zone_id, zone_config in self._zone_cache.items():
            fcu_id = zone_config.get("fcu_id")
            if fcu_id and fcu_id in health_dict:
                self._equipment_health_cache[fcu_id] = health_dict[fcu_id]

        # Also update chiller plant health from equipment codes
        for cid in self.CHILLER_IDS:
            if cid in health_dict:
                self._chiller_states[cid]["health"] = health_dict[cid]

        if updated > 0:
            degraded = sum(1 for h in self._equipment_health_cache.values() if h < 95)
            if degraded > 0:
                logger.debug(f"[THERMAL] Health cache updated: {updated} items, {degraded} degraded")

    async def _write_sensor_readings(
        self,
        simulated_hour: int,
        zone_temps: dict[str, float],
        occupancy_data: dict[str, float],
        ambient_temp: float,
        is_night_mode: bool,
    ) -> None:
        """Write temperature and CO2 sensor readings to JSON simulation store."""
        try:
            readings = []

            for zone_id, zone_config in self._zone_cache.items():
                temp = zone_temps.get(zone_id, zone_config.get("setpoint", 22.0))
                occupancy = occupancy_data.get(zone_id, 0.0)

                readings.append(
                    {
                        "sensor_code": f"{zone_id}-TEMP",
                        "time": datetime.utcnow().isoformat() + "Z",
                        "value": round(temp, 2),
                        "quality": "good",
                        "simulated_hour": simulated_hour,
                        "occupancy_pct": round(occupancy, 1),
                        "ambient_temp": round(ambient_temp, 1),
                        "night_mode": is_night_mode,
                        "zone_id": zone_id,
                    }
                )

                co2_value = self._zone_co2.get(zone_id, self.OUTDOOR_CO2_PPM)
                readings.append(
                    {
                        "sensor_code": f"{zone_id}-CO2",
                        "time": datetime.utcnow().isoformat() + "Z",
                        "value": round(co2_value, 1),
                        "quality": "good",
                        "simulated_hour": simulated_hour,
                        "occupancy_pct": round(occupancy, 1),
                        "zone_id": zone_id,
                        "unit": "ppm",
                    }
                )

            if readings:
                self.sim_store.write_sensor_readings(readings)
                logger.debug(f"[THERMAL] Wrote {len(readings)} sensor readings for hour {simulated_hour:02d}:00")

        except Exception as e:
            logger.error(f"[THERMAL] Failed to write sensor readings: {e}", exc_info=True)

    async def calculate_hvac_power_consumption(
        self,
        simulated_hour: int,
        zone_temps: dict[str, float],
        occupancy_data: dict[str, float],
        ambient_temp: float,
        simulated_date: datetime | None = None,
    ) -> dict[str, float]:
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
                # Load increases with temp_offset and occupancy, scaled by zone area
                area_factor = zone_config.get("area_sqm", 450) / 120.0
                cooling_load = (temp_offset * 0.5 + (occupancy_pct / 100.0) * 2.0) * area_factor

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

                # Power ∝ cooling_load (normalized 0-1, scaled by zone area)
                load_fraction = min(1.0, cooling_load / (5.0 * area_factor))
                hvac_power = baseline + (max_power - baseline) * load_fraction

                # Apply equipment health factor if enabled
                if self.CONSIDER_EQUIPMENT_HEALTH and fcu_id in self._equipment_health_cache:
                    health_score = self._equipment_health_cache[fcu_id]
                    hvac_power *= health_score / 100.0

                # Only consume power if occupancy > 0 or temp deviation > 1°C
                if occupancy_pct < 5 and temp_offset < 1.0:
                    hvac_power *= 0.1  # Minimal power in unoccupied idle zones

                zone_power[zone_id] = round(hvac_power, 2)
                total_zone_cooling_demand += cooling_load
                self._hvac_power_cache[zone_id] = hvac_power

            # Calculate chiller power via N+1 plant model
            # 20% margin for chilled water distribution losses
            chiller_load_kw = total_zone_cooling_demand * 1.2
            chiller_power = self._update_chiller_plant(chiller_load_kw)
            self._chiller_power_cache = chiller_power

            # Write power to database
            await self._write_power_consumption(
                simulated_hour=simulated_hour,
                zone_power=zone_power,
                chiller_power=chiller_power,
                simulated_date=simulated_date,
            )

            total_hvac = sum(zone_power.values()) + chiller_power

            # Chiller plant summary for logging
            running_chillers = [cid for cid, s in self._chiller_states.items() if s["running"]]
            logger.debug(
                f"[POWER] Hour {simulated_hour:02d}: "
                f"Zones={sum(zone_power.values()):.1f}kW + "
                f"Chiller={chiller_power:.1f}kW ({len(running_chillers)} running) = "
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
        zone_power: dict[str, float],
        chiller_power: float,
        simulated_date: datetime | None = None,
    ) -> None:
        """
        Write HVAC power consumption to power_meters table.

        Updates the active_power_kw field for:
        - HVAC feeder (sum of all zone + chiller)
        - Can be extended to track chiller separately if meter exists
        """
        try:
            total_hvac_power = sum(zone_power.values()) + chiller_power
            kwh_consumed = round(total_hvac_power, 2)

            # Write to simulation store (JSON), not Supabase
            self.sim_store.update_power_meter("S002-MTR-B1-HVAC", total_hvac_power)

            # Use simulated date, not real clock
            date_str = simulated_date.strftime("%Y-%m-%d") if simulated_date else datetime.utcnow().strftime("%Y-%m-%d")
            self.sim_store.update_energy_history(date_str, "hvac_kwh", kwh_consumed)

            logger.debug(
                f"[POWER] HVAC meter: {total_hvac_power:.1f}kW, +{kwh_consumed:.2f}kWh for hour {simulated_hour:02d}"
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

                # After writing daily cost summary, run validation engines
                try:
                    # A.3: Validate power meter readings against baseline
                    pmv_engine = get_power_meter_validation_engine(self.site_id)
                    validation_result = await pmv_engine.validate_daily_power(
                        simulated_date=simulated_date,
                        hourly_power_data=self._daily_hourly_power,
                    )
                    if validation_result:
                        logger.info(
                            f"[VALIDATION] Power meter: {validation_result.get('validation_status', 'unknown')} "
                            f"(variance: {validation_result.get('variance_pct', 0):.1f}%)"
                        )
                except Exception as e:
                    logger.warning(f"[VALIDATION] Power meter validation skipped: {e}")

                try:
                    # A.4: Validate cost against expected (monthly boundary check)
                    cv_engine = get_cost_validation_engine(self.site_id)
                    cost_validation = await cv_engine.validate_daily_cost(
                        simulated_date=simulated_date,
                        daily_cost=daily_cost,
                    )
                    if cost_validation:
                        logger.info(
                            f"[VALIDATION] Cost: {cost_validation.get('validation_status', 'unknown')} "
                            f"(variance: {cost_validation.get('variance_pct', 0):.1f}%)"
                        )
                except Exception as e:
                    logger.warning(f"[VALIDATION] Cost validation skipped: {e}")

        except Exception as e:
            logger.error(f"[COST] Failed to track/calculate daily cost: {e}", exc_info=True)


# Singleton instance per building
_thermal_engines: dict[str, ThermalSimulationEngine] = {}


def get_thermal_engine(site_id: str, consider_equipment_health: bool = False) -> ThermalSimulationEngine:
    """
    Get or create thermal engine for building.

    Args:
        site_id: Building identifier
        consider_equipment_health: If True, HVAC response degrades with equipment health
                                  Set to True for maintenance/fault simulations
                                  Default False for normal simulations
    """
    # Create new engine if needed or if health consideration changes
    if site_id not in _thermal_engines:
        _thermal_engines[site_id] = ThermalSimulationEngine(
            site_id, consider_equipment_health=consider_equipment_health
        )

    return _thermal_engines[site_id]


async def update_simulation_temperatures(
    site_id: str,
    simulated_hour: int,
    occupancy_data: dict[str, float],
    ambient_temp: float,
    is_night_mode: bool = False,
    consider_equipment_health: bool = False,
    simulated_date: datetime | None = None,
) -> dict[str, float]:
    """
    Public API to update zone temperatures during simulation.

    Args:
        site_id: Building ID
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
            site_id=self.site_id,
            simulated_hour=hour,
            occupancy_data={"Zone-001": 75, "Zone-101": 50, ...},
            ambient_temp=18.5,
            is_night_mode=(hour >= 22 or hour < 6),
            consider_equipment_health=False  # Default
        )

        # Maintenance/Fault simulation (equipment can degrade):
        temps = await update_simulation_temperatures(
            site_id=self.site_id,
            simulated_hour=hour,
            occupancy_data=occupancy_data,
            ambient_temp=ambient_temp,
            is_night_mode=is_night_mode,
            consider_equipment_health=True  # Enable health degradation
        )
    """
    engine = get_thermal_engine(site_id, consider_equipment_health=consider_equipment_health)
    return await engine.update_zone_temperatures(
        simulated_hour=simulated_hour,
        occupancy_data=occupancy_data,
        ambient_temp=ambient_temp,
        is_night_mode=is_night_mode,
        simulated_date=simulated_date,
    )

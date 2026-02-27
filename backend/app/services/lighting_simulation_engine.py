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

Also generates per-luminaire sceneCOM telemetry (energy, diagnostics,
emergency gear) so SENTINEL has realistic data in demo/dev mode.

Integration point: Called from thermal_simulation_engine each hour
"""

import hashlib
import logging
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from app.database.supabase_client import get_supabase_client
from app.services.simulation_store import get_simulation_store

logger = logging.getLogger(__name__)


class LightingSimulationEngine:
    """Calculates and updates zone lighting consumption during simulation."""

    # Lighting hardware parameters (per zone)
    BASELINE_POWER_PER_ZONE = 4.5  # kW (450 sqm × 10 W/sqm modern LED office)
    DALI_MIN_DIM = 0.05  # 5% minimum (DALI spec)

    # Occupancy detection response
    OCCUPANCY_SENSOR_RESPONSE = 0.3  # 30% occupancy triggers lights
    OCCUPANCY_POWER_SCALING = 0.6  # Occupancy affects only 60% of power (rest is base)

    # Daylight harvesting
    DAYLIGHT_THRESHOLD_LUX = 300  # Below this: full artificial light needed
    DAYLIGHT_HARVEST_FACTOR = 0.8  # Dimming effectiveness
    CLOUDY_REDUCTION = 0.3  # Cloudy weather reduces daylight by 30%
    RAIN_REDUCTION = 0.6  # Rain reduces daylight by 60%

    # Zone characteristics — True = has windows (perimeter), False = interior
    # Zone naming: Zone-{id} where North/East/South = perimeter, Central/West = interior
    WINDOW_ZONES = {
        # L0
        "Zone-001": True,  # L0 North (perimeter)
        "Zone-021": True,  # L0 East (perimeter)
        "Zone-041": False,  # L0 Central (interior)
        "Zone-061": False,  # L0 West (interior)
        "Zone-081": True,  # L0 South (perimeter)
        # L1
        "Zone-101": True,  # L1 North (perimeter)
        "Zone-121": True,  # L1 East (perimeter)
        "Zone-141": False,  # L1 Central (interior)
        "Zone-161": False,  # L1 West (interior)
        "Zone-181": True,  # L1 South (perimeter)
        # L2
        "Zone-201": True,  # L2 North (perimeter)
        "Zone-221": True,  # L2 East (perimeter)
        "Zone-241": False,  # L2 Central (interior)
        "Zone-261": False,  # L2 West (interior)
        "Zone-281": True,  # L2 South (perimeter)
        # L3
        "Zone-301": True,  # L3 North (perimeter)
        "Zone-321": True,  # L3 East (perimeter)
        "Zone-341": False,  # L3 Central (interior)
        "Zone-361": False,  # L3 West (interior)
        "Zone-381": True,  # L3 South (perimeter)
    }

    # sceneCOM telemetry simulation parameters
    LUMINAIRE_SQM_PER_FIXTURE = 8.0  # 1 LED panel per 8 sqm (office standard)
    LIGHTING_POWER_DENSITY_W_SQM = 10.0  # 10 W/sqm modern LED office lighting
    DRIVER_AMBIENT_TEMP_C = 35.0  # Plenum ambient (above ceiling)
    DRIVER_TEMP_RISE_FACTOR = 0.33  # °C per watt → ~40°C rise at 120W full load
    DRIVER_TEMP_NOISE_C = 2.0  # Random ±noise on driver temp
    DRIVER_WARN_TEMP_C = 85.0  # Driver health = "warning"
    DRIVER_FAULT_TEMP_C = 95.0  # Driver health = "fault"
    LAMP_HOUR_INCREMENT = 1  # Hours per simulation step
    LIGHT_OUTPUT_DEGRADATION_RATE = 0.002  # % loss per 1000 hours (L90 at 50k)
    COLOUR_SHIFT_PER_10K_HOURS = 0.005  # SDCM shift per 10k hours
    EMERGENCY_GEAR_RATIO = 0.10  # 10% of luminaires have emergency gear
    EMERGENCY_BATTERY_NOMINAL_PCT = 96  # Nominal full charge %
    EMERGENCY_BATTERY_DAILY_DRAIN = 0.05  # % per day self-discharge
    FAULT_PROBABILITY_PER_HOUR = 0.0001  # ~0.01% per luminaire per hour (~2.4% pa)
    FAULT_TYPES = ["lamp_failure", "driver_overtemp", "ballast_fault", "comm_error"]

    def __init__(self, building_id: str):
        self.building_id = building_id
        self.supabase = get_supabase_client()
        self.sim_store = get_simulation_store(building_id)

        # Cache zone metadata
        self._zone_cache: Dict[str, Dict[str, Any]] = {}
        self._lighting_power_cache: Dict[str, float] = {}  # zone_id -> power_kw

        # Daily tracking for energy history
        self._daily_hourly_lighting: Dict[int, float] = {}  # hour -> total lighting kW

        # --- sceneCOM telemetry state ---
        # Per-luminaire persistent state: {luminaire_id: {...}}
        self._luminaire_state: Dict[str, Dict[str, Any]] = {}
        # Latest telemetry snapshot (populated each hour)
        self._latest_telemetry: Dict[str, Any] = {}
        # Zone-to-luminaire mapping: {zone_id: [luminaire_ids]}
        self._zone_luminaires: Dict[str, List[str]] = {}
        # Deterministic RNG seeded per building for reproducible faults
        self._rng = random.Random(int(hashlib.md5(building_id.encode()).hexdigest()[:8], 16))

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
                simulated_date=simulated_date,
            )

            # Generate per-luminaire sceneCOM telemetry
            self._generate_scenecom_telemetry(
                zone_power=zone_power,
                occupancy_data=occupancy_data,
                daylight_lux=daylight_lux,
                simulated_hour=simulated_hour,
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
                effective_lux *= 1.0 - (self.CLOUDY_REDUCTION * (cloud_cover_pct / 100.0))
            if is_raining:
                effective_lux *= 1.0 - self.RAIN_REDUCTION

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

        logger.debug(f"[LIGHT CALC] {zone_id}: occ={occupancy_pct:.0f}% lux={daylight_lux:.0f} → {power_kw:.2f}kW")

        return power_kw

    # ------------------------------------------------------------------
    # sceneCOM telemetry generation
    # ------------------------------------------------------------------

    def get_latest_telemetry(self) -> Dict[str, Any]:
        """Return the latest sceneCOM telemetry snapshot.

        Structure::

            {
                "timestamp": "...",
                "luminaires": [{ luminaire_id, zone_id, active_power_w, ... }],
                "sensors": [{ sensor_id, zone_id, occupancy_count, lux, ... }],
                "controllers": [{ controller_id, zones_served, mqtt_connected, ... }],
                "emergency_gear": [{ luminaire_id, battery_pct, charge_status, ... }],
                "faults": [{ luminaire_id, fault_type, ... }],
            }
        """
        return self._latest_telemetry

    def _ensure_luminaire_topology(self) -> None:
        """Build zone→luminaire mapping from zone metadata (lazy init)."""
        if self._zone_luminaires:
            return

        for zone_id, zone_config in self._zone_cache.items():
            area = zone_config.get("area_sqm", 50)
            count = max(2, int(area / self.LUMINAIRE_SQM_PER_FIXTURE))
            # Derive per-luminaire rated power from zone power budget
            zone_budget_w = area * self.LIGHTING_POWER_DENSITY_W_SQM
            rated_power_w = round(zone_budget_w / count, 1)
            lum_ids = []
            for i in range(count):
                lum_id = f"LUM-{zone_id}-{i + 1:03d}"
                lum_ids.append(lum_id)
                # Initialise persistent state if first run
                if lum_id not in self._luminaire_state:
                    is_emergency = i < max(1, int(count * self.EMERGENCY_GEAR_RATIO))
                    self._luminaire_state[lum_id] = {
                        "zone_id": zone_id,
                        "rated_power_w": rated_power_w,
                        "lamp_hours": self._rng.randint(0, 5000),
                        "accumulated_energy_kwh": round(self._rng.uniform(0, 50), 2),
                        "fault_status": False,
                        "fault_code": None,
                        "is_emergency": is_emergency,
                        "emergency_battery_pct": (self.EMERGENCY_BATTERY_NOMINAL_PCT if is_emergency else None),
                        "emergency_last_test": None,
                        "emergency_test_result": None,
                    }
            self._zone_luminaires[zone_id] = lum_ids

        total = sum(len(v) for v in self._zone_luminaires.values())
        logger.info(
            f"[SCENECOM] Built luminaire topology: {total} luminaires across {len(self._zone_luminaires)} zones"
        )

    def _generate_scenecom_telemetry(
        self,
        zone_power: Dict[str, float],
        occupancy_data: Dict[str, float],
        daylight_lux: float,
        simulated_hour: int,
    ) -> None:
        """Generate per-luminaire sceneCOM telemetry from zone-level power.

        Populates ``self._latest_telemetry`` with energy, diagnostics,
        emergency gear, and sensor data — the same fields a real sceneCOM
        controller would expose via REST / MQTT.
        """
        self._ensure_luminaire_topology()

        now_iso = datetime.utcnow().isoformat() + "Z"
        luminaire_records: List[Dict[str, Any]] = []
        sensor_records: List[Dict[str, Any]] = []
        controller_zones: Dict[str, List[str]] = {}  # controller_id → zone_ids
        emergency_records: List[Dict[str, Any]] = []
        fault_records: List[Dict[str, Any]] = []

        for zone_id, lum_ids in self._zone_luminaires.items():
            zone_power_kw = zone_power.get(zone_id, 0.0)
            zone_power_w = zone_power_kw * 1000.0
            occupancy_pct = occupancy_data.get(zone_id, 0.0)

            # Get rated power for this zone's luminaires (all same within a zone)
            sample_rated = self._luminaire_state[lum_ids[0]]["rated_power_w"]
            # Per-luminaire power, clamped to rated capacity
            per_lum_power_w = min(zone_power_w / len(lum_ids), sample_rated) if lum_ids else 0.0

            # Determine dim level (0-254 DALI scale)
            dim_ratio = per_lum_power_w / sample_rated if sample_rated > 0 else 0.0
            dim_ratio = min(1.0, dim_ratio)
            dali_level = int(round(dim_ratio * 254))

            # Assign zone to a sceneCOM controller (1 per floor)
            zone_config = self._zone_cache.get(zone_id, {})
            floor = zone_config.get("floor", "L0")
            ctrl_id = f"SCOM-{self.building_id}-{floor}"
            controller_zones.setdefault(ctrl_id, []).append(zone_id)

            for lum_id in lum_ids:
                state = self._luminaire_state[lum_id]

                # --- Energy telemetry ---
                # Add ±5% noise per luminaire for realism
                noise = 1.0 + self._rng.uniform(-0.05, 0.05)
                active_power_w = round(per_lum_power_w * noise, 1)
                energy_increment = active_power_w / 1000.0  # kWh per hour
                state["accumulated_energy_kwh"] = round(state["accumulated_energy_kwh"] + energy_increment, 3)
                state["lamp_hours"] += self.LAMP_HOUR_INCREMENT

                # --- Driver diagnostics ---
                driver_temp = (
                    self.DRIVER_AMBIENT_TEMP_C
                    + active_power_w * self.DRIVER_TEMP_RISE_FACTOR
                    + self._rng.uniform(-self.DRIVER_TEMP_NOISE_C, self.DRIVER_TEMP_NOISE_C)
                )
                driver_temp = round(driver_temp, 1)

                if state["fault_status"]:
                    driver_health = "fault"
                elif driver_temp >= self.DRIVER_FAULT_TEMP_C:
                    driver_health = "fault"
                    state["fault_status"] = True
                    state["fault_code"] = "driver_overtemp"
                elif driver_temp >= self.DRIVER_WARN_TEMP_C:
                    driver_health = "warning"
                else:
                    driver_health = "ok"

                # Light output degradation (L90 at 50k hours)
                hours = state["lamp_hours"]
                light_output_pct = round(100.0 - (hours / 1000.0) * self.LIGHT_OUTPUT_DEGRADATION_RATE, 1)
                light_output_pct = max(70.0, light_output_pct)  # Floor at L70

                # Colour shift (SDCM drift)
                colour_shift = round((hours / 10000.0) * self.COLOUR_SHIFT_PER_10K_HOURS, 4)

                # --- Random fault injection ---
                if not state["fault_status"] and self._rng.random() < self.FAULT_PROBABILITY_PER_HOUR:
                    state["fault_status"] = True
                    state["fault_code"] = self._rng.choice(self.FAULT_TYPES)

                if state["fault_status"]:
                    fault_records.append(
                        {
                            "luminaire_id": lum_id,
                            "zone_id": zone_id,
                            "fault_type": state["fault_code"],
                            "driver_temp_c": driver_temp,
                            "lamp_hours": hours,
                            "timestamp": now_iso,
                        }
                    )

                luminaire_records.append(
                    {
                        "luminaire_id": lum_id,
                        "zone_id": zone_id,
                        "controller_id": ctrl_id,
                        "dali_level": dali_level,
                        "active_power_w": active_power_w,
                        "accumulated_energy_kwh": state["accumulated_energy_kwh"],
                        "rated_power_w": state["rated_power_w"],
                        "driver_temp_c": driver_temp,
                        "driver_health": driver_health,
                        "light_output_pct": light_output_pct,
                        "colour_shift_sdcm": colour_shift,
                        "lamp_hours": hours,
                        "fault_status": state["fault_status"],
                        "fault_code": state["fault_code"],
                        "timestamp": now_iso,
                    }
                )

                # --- Emergency gear ---
                if state["is_emergency"]:
                    battery = state["emergency_battery_pct"]
                    # Self-discharge
                    battery -= self.EMERGENCY_BATTERY_DAILY_DRAIN / 24.0
                    # Recharge when mains power is on (dim_ratio > 0)
                    if dim_ratio > 0.1 and battery < self.EMERGENCY_BATTERY_NOMINAL_PCT:
                        battery += 0.1  # Trickle charge
                    battery = round(min(self.EMERGENCY_BATTERY_NOMINAL_PCT, max(0, battery)), 1)
                    state["emergency_battery_pct"] = battery

                    if battery > 80:
                        charge_status = "charged"
                    elif battery > 20:
                        charge_status = "charging"
                    else:
                        charge_status = "fault"

                    # Schedule monthly function test at 02:00 on day 1
                    last_test = state.get("emergency_last_test")
                    if simulated_hour == 2 and last_test is None:
                        state["emergency_last_test"] = now_iso
                        state["emergency_test_result"] = "pass" if battery > 50 else "fail"

                    compliance_due = None
                    if state.get("emergency_last_test"):
                        try:
                            lt = datetime.fromisoformat(state["emergency_last_test"].replace("Z", "+00:00"))
                            compliance_due = (lt + timedelta(days=30)).isoformat()
                        except (ValueError, TypeError):
                            pass

                    emergency_records.append(
                        {
                            "luminaire_id": lum_id,
                            "zone_id": zone_id,
                            "battery_pct": battery,
                            "charge_status": charge_status,
                            "last_function_test": state.get("emergency_last_test"),
                            "test_result": state.get("emergency_test_result"),
                            "compliance_due": compliance_due,
                            "timestamp": now_iso,
                        }
                    )

            # --- Sensor telemetry (one per zone) ---
            # Derive occupancy count from percent and typical occupancy
            typical = zone_config.get("typical_occupancy", 10)
            occ_count = max(0, int(round(occupancy_pct / 100.0 * typical)))
            sensor_records.append(
                {
                    "sensor_id": f"PIR-{zone_id}",
                    "zone_id": zone_id,
                    "controller_id": ctrl_id,
                    "occupancy": occupancy_pct >= self.OCCUPANCY_SENSOR_RESPONSE,
                    "occupancy_count": occ_count,
                    "lux_level": round(daylight_lux * (0.3 if not self.WINDOW_ZONES.get(zone_id, False) else 1.0), 1),
                    "sensor_health": "ok",
                    "timestamp": now_iso,
                }
            )

        # --- Controller telemetry ---
        controller_records = []
        for ctrl_id, zones in controller_zones.items():
            lum_count = sum(len(self._zone_luminaires.get(z, [])) for z in zones)
            fault_count = sum(
                1
                for z in zones
                for lid in self._zone_luminaires.get(z, [])
                if self._luminaire_state.get(lid, {}).get("fault_status")
            )
            controller_records.append(
                {
                    "controller_id": ctrl_id,
                    "building_id": self.building_id,
                    "zones_served": zones,
                    "luminaire_count": lum_count,
                    "fault_count": fault_count,
                    "mqtt_connected": True,
                    "polling_interval_sec": 30,
                    "firmware_version": "sceneCOM-evo-3.2.1",
                    "status": "online" if fault_count == 0 else "degraded",
                    "timestamp": now_iso,
                }
            )

        self._latest_telemetry = {
            "timestamp": now_iso,
            "building_id": self.building_id,
            "luminaires": luminaire_records,
            "sensors": sensor_records,
            "controllers": controller_records,
            "emergency_gear": emergency_records,
            "faults": fault_records,
            "summary": {
                "total_luminaires": len(luminaire_records),
                "total_faults": len(fault_records),
                "total_emergency": len(emergency_records),
                "total_active_power_w": round(sum(r["active_power_w"] for r in luminaire_records), 1),
            },
        }

        logger.debug(
            f"[SCENECOM] Generated telemetry: "
            f"{len(luminaire_records)} luminaires, "
            f"{len(fault_records)} faults, "
            f"{len(emergency_records)} emergency gear"
        )

    async def _load_zone_metadata(self) -> None:
        """Load zone configuration from database."""
        try:
            # Resolve building code to UUID if needed (hvac_zones.building_id is UUID)
            building_uuid = self.building_id
            try:
                bldg = (
                    self.supabase.table("buildings").select("id").eq("code", self.building_id).maybe_single().execute()
                )
                if bldg and bldg.data:
                    building_uuid = bldg.data["id"]
            except Exception:
                pass  # Fall through with original value

            response = (
                self.supabase.table("hvac_zones")
                .select("id, zone_id, zone_name, floor, typical_occupancy, area_sqm")
                .eq("building_id", building_uuid)
                .execute()
            )

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
        simulated_date: Optional[datetime] = None,
    ) -> None:
        """
        Write lighting power to power_meters table.

        Updates the lighting feeder meter with total power.
        """
        try:
            lighting_kwh = round(total_power, 2)
            # Use simulated date, not real clock
            date_str = simulated_date.strftime("%Y-%m-%d") if simulated_date else datetime.utcnow().strftime("%Y-%m-%d")

            # Write to simulation store (JSON), not Supabase
            self.sim_store.update_power_meter("S002-MTR-B1-LIGHT", total_power)
            self.sim_store.update_energy_history(date_str, "lighting_kwh", lighting_kwh)

            logger.debug(f"[LIGHTING] Meter: {total_power:.1f}kW, +{lighting_kwh:.2f}kWh at hour {simulated_hour:02d}")

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

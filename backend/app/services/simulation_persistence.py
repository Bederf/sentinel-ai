"""
Persist simulation state to Supabase for dashboard visibility.

Called every simulation hour by LifecycleOrchestrator._process_hour().
Writes equipment health, sensor readings, and energy data so that
existing dashboards show live building operation.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class SimulationPersistence:
    """Writes simulation state to Supabase for real-time dashboard visibility."""

    def __init__(self, site_id: str = "site-002"):
        self.site_id = site_id
        self._supabase = None

    @property
    def supabase(self):
        if self._supabase is None:
            try:
                from app.database.supabase_client import get_supabase_client

                self._supabase = get_supabase_client()
            except Exception as e:
                logger.warning(f"Supabase not available: {e}")
        return self._supabase

    async def persist_hourly_state(
        self,
        simulated_time: datetime,
        equipment_states: Dict[str, Dict[str, Any]],
        schedule_state: Any,
        energy_kw: float,
        ambient_temp: float,
        humidity: float,
    ) -> Dict[str, Any]:
        """
        Persist all simulation state for the current hour.

        Args:
            simulated_time: Current simulation timestamp
            equipment_states: {equipment_code: {health_score, status, sensor_readings}}
            schedule_state: Current BuildingSchedule state
            energy_kw: Current hour power consumption
            ambient_temp: Outside temperature
            humidity: Outside humidity

        Returns:
            Summary of what was persisted
        """
        results = {
            "equipment_updated": 0,
            "readings_written": 0,
            "alerts_generated": 0,
            "errors": [],
        }

        # 1. Update equipment health scores
        for code, state in equipment_states.items():
            try:
                await self._update_equipment_health(code, state)
                results["equipment_updated"] += 1
            except Exception as e:
                results["errors"].append(f"equipment {code}: {e}")

        # 2. Write sensor readings
        try:
            count = await self._write_sensor_readings(simulated_time, equipment_states, ambient_temp, humidity)
            results["readings_written"] = count
        except Exception as e:
            results["errors"].append(f"sensor_readings: {e}")

        # 3. Write energy consumption
        try:
            await self._write_energy_reading(simulated_time, energy_kw)
        except Exception as e:
            results["errors"].append(f"energy: {e}")

        # 4. Write zone history (temp, humidity, CO2 per zone)
        try:
            zones_written = await self._write_zone_history(simulated_time, equipment_states, schedule_state)
            results["zones_written"] = zones_written
        except Exception as e:
            results["errors"].append(f"zone_history: {e}")

        # 5. Write equipment sensor readings to equipment_sensor_readings
        try:
            esr_count = await self._write_equipment_sensor_readings(simulated_time, equipment_states)
            results["equipment_readings_written"] = esr_count
        except Exception as e:
            results["errors"].append(f"equipment_sensor_readings: {e}")

        # 6. Update hvac_zones with current readings (for complaint handler)
        try:
            await self._update_hvac_zones_live(simulated_time, equipment_states, schedule_state)
        except Exception as e:
            results["errors"].append(f"hvac_zones_live: {e}")

        if results["errors"]:
            logger.warning(f"Persistence errors: {results['errors']}")
        else:
            logger.info(
                f"Persisted: {results['equipment_updated']} equipment, "
                f"{results['readings_written']} readings, "
                f"{results.get('zones_written', 0)} zones, {energy_kw:.1f} kW"
            )

        return results

    async def _update_equipment_health(self, equipment_code: str, state: Dict[str, Any]):
        """Update equipment health_score and status in Supabase."""
        if not self.supabase:
            return

        health_score = state.get("health_score")
        if health_score is None:
            return

        # Determine status from health
        if health_score >= 70:
            status = "online"
        elif health_score >= 40:
            status = "degraded"
        else:
            status = "offline"

        try:
            self.supabase.table("equipment").update(
                {
                    "health_score": health_score,
                    "status": status,
                    "updated_at": datetime.utcnow().isoformat(),
                }
            ).eq("code", equipment_code).execute()
        except Exception as e:
            # Fallback: update JSON file
            logger.debug(f"Supabase update failed for {equipment_code}, using JSON fallback: {e}")
            await self._update_json_fallback(equipment_code, health_score, status)

    async def _write_sensor_readings(
        self,
        simulated_time: datetime,
        equipment_states: Dict[str, Dict[str, Any]],
        ambient_temp: float,
        humidity: float,
    ) -> int:
        """Write sensor readings for all equipment."""
        if not self.supabase:
            return 0

        readings = []
        for code, state in equipment_states.items():
            for point_name, value in state.get("sensor_readings", {}).items():
                readings.append(
                    {
                        "equipment_code": code,
                        "point_name": point_name,
                        "value": value,
                        "timestamp": simulated_time.isoformat(),
                        "site_id": self.site_id,
                    }
                )

        # Add ambient weather readings
        readings.append(
            {
                "equipment_code": f"{self.site_id.upper().replace('-', '')}-WEATHER",
                "point_name": "outdoor_temperature",
                "value": ambient_temp,
                "timestamp": simulated_time.isoformat(),
                "site_id": self.site_id,
            }
        )
        readings.append(
            {
                "equipment_code": f"{self.site_id.upper().replace('-', '')}-WEATHER",
                "point_name": "outdoor_humidity",
                "value": humidity,
                "timestamp": simulated_time.isoformat(),
                "site_id": self.site_id,
            }
        )

        if readings:
            try:
                self.supabase.table("sensor_readings").upsert(readings).execute()
            except Exception:
                logger.debug("sensor_readings table may not exist, skipping")

        return len(readings)

    async def _write_energy_reading(self, simulated_time: datetime, energy_kw: float):
        """Write energy consumption reading."""
        if not self.supabase:
            return

        try:
            self.supabase.table("energy_readings").upsert(
                {
                    "site_id": self.site_id,
                    "timestamp": simulated_time.isoformat(),
                    "power_kw": energy_kw,
                    "source": "simulation",
                }
            ).execute()
        except Exception:
            logger.debug("energy_readings table may not exist, skipping")

    async def _write_zone_history(
        self,
        simulated_time: datetime,
        equipment_states: Dict[str, Dict[str, Any]],
        schedule_state: Any,
    ) -> int:
        """Aggregate zone-level readings from equipment and write to hvac_zone_history.

        Extracts temperature from FCU/VAV readings, CO2 and humidity from zone sensors,
        and writes one record per zone per hour.
        """
        if not self.supabase:
            return 0

        # Get building UUID
        try:
            bld_resp = self.supabase.table("buildings").select("id").eq("code", self.site_id).execute()
            if not bld_resp.data:
                return 0
            building_uuid = bld_resp.data[0]["id"]
        except Exception:
            return 0

        # Collect zone data from equipment readings
        zone_data: Dict[str, Dict[str, Any]] = {}

        for code, state in equipment_states.items():
            readings = state.get("sensor_readings", {})
            equip_type = state.get("type", "").lower()

            # Map equipment to zone
            parts = code.split("-")
            if len(parts) >= 3:
                zone_id = f"Zone-{'-'.join(parts[2:])}"
            else:
                continue

            if zone_id not in zone_data:
                zone_data[zone_id] = {}

            # Extract readings by equipment type
            if equip_type in ("fcu",):
                if "room_temp" in readings:
                    zone_data[zone_id]["temp"] = readings["room_temp"]
            elif equip_type in ("vav",):
                if "zone_temp" in readings:
                    zone_data[zone_id].setdefault("temp", readings["zone_temp"])
            elif equip_type in ("temp_sensor",):
                if "zone_temp" in readings:
                    zone_data[zone_id].setdefault("temp", readings["zone_temp"])
            elif equip_type in ("co2_sensor", "zone_sensor"):
                if "co2_ppm" in readings:
                    zone_data[zone_id]["co2"] = int(readings["co2_ppm"])
                if "humidity_pct" in readings:
                    zone_data[zone_id]["humidity"] = readings["humidity_pct"]
            elif equip_type in ("humidity_sensor",):
                if "humidity_pct" in readings:
                    zone_data[zone_id]["humidity"] = readings["humidity_pct"]

        # Get setpoint from schedule state
        setpoint = 22.0
        if hasattr(schedule_state, "setpoint_offset"):
            setpoint = 22.0 + schedule_state.setpoint_offset

        # Get occupancy
        occupancy_pct = 0
        if hasattr(schedule_state, "target_occupancy_pct"):
            occupancy_pct = schedule_state.target_occupancy_pct

        # Build records
        records = []
        for zone_id, data in zone_data.items():
            if not data.get("temp"):
                continue  # Skip zones without temperature data
            records.append(
                {
                    "time": simulated_time.isoformat(),
                    "zone_id": zone_id,
                    "building_id": building_uuid,
                    "temp": data.get("temp"),
                    "humidity": data.get("humidity"),
                    "co2": data.get("co2"),
                    "setpoint": setpoint,
                    "status": "running" if data.get("temp") else "off",
                    "occupancy": int(occupancy_pct * 20 / 100) if occupancy_pct else 0,
                }
            )

        if records:
            try:
                self.supabase.table("hvac_zone_history").insert(records).execute()
            except Exception as e:
                logger.debug(f"hvac_zone_history write failed: {e}")

        return len(records)

    async def _write_equipment_sensor_readings(
        self,
        simulated_time: datetime,
        equipment_states: Dict[str, Dict[str, Any]],
    ) -> int:
        """Write equipment-level sensor readings to equipment_sensor_readings table."""
        if not self.supabase:
            return 0

        records = []
        for code, state in equipment_states.items():
            for point_name, value in state.get("sensor_readings", {}).items():
                records.append(
                    {
                        "equipment_id": code,
                        "sensor_type": point_name,
                        "value": float(value) if value is not None else 0.0,
                        "unit": self._get_unit(point_name),
                        "recorded_at": simulated_time.isoformat(),
                        "building_id": self.site_id,
                    }
                )

        if records:
            try:
                # Insert in batches of 100 to avoid payload limits
                for i in range(0, len(records), 100):
                    batch = records[i : i + 100]
                    self.supabase.table("equipment_sensor_readings").insert(batch).execute()
            except Exception as e:
                logger.debug(f"equipment_sensor_readings write failed: {e}")

        return len(records)

    async def _update_hvac_zones_live(
        self,
        simulated_time: datetime,
        equipment_states: Dict[str, Dict[str, Any]],
        schedule_state: Any,
    ):
        """Update hvac_zones table with current readings so complaint handler sees live data."""
        if not self.supabase:
            return

        # Aggregate zone readings (same logic as _write_zone_history)
        zone_data: Dict[str, Dict[str, Any]] = {}
        for code, state in equipment_states.items():
            readings = state.get("sensor_readings", {})
            equip_type = state.get("type", "").lower()
            parts = code.split("-")
            if len(parts) >= 3:
                zone_id = f"Zone-{'-'.join(parts[2:])}"
            else:
                continue
            if zone_id not in zone_data:
                zone_data[zone_id] = {}
            if equip_type in ("fcu",) and "room_temp" in readings:
                zone_data[zone_id]["temp"] = readings["room_temp"]
            elif equip_type in ("vav",) and "zone_temp" in readings:
                zone_data[zone_id].setdefault("temp", readings["zone_temp"])
            elif equip_type in ("temp_sensor",) and "zone_temp" in readings:
                zone_data[zone_id].setdefault("temp", readings["zone_temp"])
            elif equip_type in ("co2_sensor", "zone_sensor") and "co2_ppm" in readings:
                zone_data[zone_id]["co2"] = int(readings["co2_ppm"])
            if equip_type in ("humidity_sensor",) and "humidity_pct" in readings:
                zone_data[zone_id]["humidity"] = readings["humidity_pct"]

        # Get setpoint from schedule
        setpoint = 22.0
        if hasattr(schedule_state, "setpoint_offset"):
            setpoint = 22.0 + schedule_state.setpoint_offset

        # Update each zone in hvac_zones
        for zone_id, data in zone_data.items():
            if not data.get("temp"):
                continue
            update = {
                "current_temp": data["temp"],
                "setpoint": setpoint,
                "status": "running",
                "last_updated": simulated_time.isoformat(),
            }
            if data.get("humidity") is not None:
                update["current_humidity"] = data["humidity"]
            if data.get("co2") is not None:
                update["current_co2"] = data["co2"]
            try:
                self.supabase.table("hvac_zones").update(update).eq("zone_id", zone_id).execute()
            except Exception as e:
                logger.debug(f"hvac_zones update failed for {zone_id}: {e}")

    @staticmethod
    def _get_unit(point_name: str) -> str:
        """Map sensor point name to unit."""
        units = {
            "zone_temp": "°C",
            "room_temp": "°C",
            "supply_temp": "°C",
            "return_temp": "°C",
            "supply_air_temp": "°C",
            "outdoor_temperature": "°C",
            "damper_position": "%",
            "valve_position": "%",
            "fan_speed_pct": "%",
            "speed_pct": "%",
            "load_pct": "%",
            "brightness_pct": "%",
            "battery_level": "%",
            "co2_ppm": "ppm",
            "humidity_pct": "%",
            "outdoor_humidity": "%",
            "airflow_lps": "L/s",
            "flow_lps": "L/s",
            "power_kw": "kW",
            "differential_pressure_kpa": "kPa",
            "cop": "ratio",
            "power_factor": "ratio",
        }
        return units.get(point_name, "")

    async def _update_json_fallback(self, equipment_code: str, health_score: float, status: str):
        """Update equipment JSON file as fallback."""
        import json
        from pathlib import Path

        site_code = self.site_id
        equip_dir = Path(f"backend/app/data/buildings/{site_code}/equipment")
        equip_file = equip_dir / f"{equipment_code}.json"

        if equip_file.exists():
            try:
                data = json.loads(equip_file.read_text())
                data["health_score"] = health_score
                data["status"] = status
                equip_file.write_text(json.dumps(data, indent=2))
            except Exception as e:
                logger.debug(f"JSON fallback failed for {equipment_code}: {e}")


_persistence_instance: Optional[SimulationPersistence] = None


def get_simulation_persistence(site_id: str = "site-002") -> SimulationPersistence:
    global _persistence_instance
    if _persistence_instance is None:
        _persistence_instance = SimulationPersistence(site_id=site_id)
    return _persistence_instance

"""
SENTINEL Persistence Layer — writes data to Supabase and feeds ML pipeline.

Called every simulation hour by LifecycleOrchestrator._process_hour().
SENTINEL is data-agnostic: it receives equipment readings from whatever
source is active (real BMS via SIMBIOT, or simulation engine) and:
  1. Persists to JSON simulation store (local fast store)
  2. Syncs to Supabase equipment.operating_data (dashboard/API)
  3. Feeds ML pipeline after successful Supabase write
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from app.services.simulation_store import get_simulation_store

logger = logging.getLogger(__name__)


class SimulationPersistence:
    """SENTINEL persistence: writes to Supabase, feeds ML pipeline."""

    def __init__(self, site_id: str = "site-002"):
        self.site_id = site_id
        self.store = get_simulation_store(site_id)

        # ML feeder — accumulates sensor data and triggers training
        from app.services.sentinel_ml_feeder import SentinelMLFeeder

        self.ml_feeder = SentinelMLFeeder()

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
                self._update_equipment_health(code, state)
                results["equipment_updated"] += 1
            except Exception as e:
                results["errors"].append(f"equipment {code}: {e}")

        # 2. Write sensor readings
        try:
            count = self._write_sensor_readings(simulated_time, equipment_states, ambient_temp, humidity)
            results["readings_written"] = count
        except Exception as e:
            results["errors"].append(f"sensor_readings: {e}")

        # 3. Write energy consumption
        try:
            self._write_energy_reading(simulated_time, energy_kw)
        except Exception as e:
            results["errors"].append(f"energy: {e}")

        # 4. Write zone history (temp, humidity, CO2 per zone)
        try:
            zones_written = self._write_zone_history(simulated_time, equipment_states, schedule_state)
            results["zones_written"] = zones_written
        except Exception as e:
            results["errors"].append(f"zone_history: {e}")

        # 5. Sync to Supabase equipment.operating_data
        try:
            supabase_count = self._sync_to_supabase(simulated_time, equipment_states)
            results["supabase_synced"] = supabase_count
        except Exception as e:
            results["errors"].append(f"supabase_sync: {e}")

        # 6. Feed ML pipeline (after Supabase write — SENTINEL feeds ML)
        try:
            self.ml_feeder.ingest(equipment_states, simulated_time)
            ml_results = self.ml_feeder.train_if_ready()
            if ml_results:
                successful = [r for r in ml_results if "error" not in r]
                logger.info(f"[ML FEEDER] Trained {len(successful)} models from SENTINEL data")
                results["ml_models_trained"] = len(successful)
            results["ml_hours_ingested"] = self.ml_feeder.hours_ingested
        except Exception as e:
            results["errors"].append(f"ml_feeder: {e}")

        if results["errors"]:
            logger.warning(f"Persistence errors: {results['errors']}")
        else:
            logger.info(
                f"Persisted: {results['equipment_updated']} equipment, "
                f"{results['readings_written']} readings, "
                f"{results.get('zones_written', 0)} zones, "
                f"{results.get('supabase_synced', 0)} supabase, {energy_kw:.1f} kW"
            )

        return results

    def _update_equipment_health(self, equipment_code: str, state: Dict[str, Any]):
        """Update equipment health_score and status in JSON store."""
        health_score = state.get("health_score")
        if health_score is None:
            return

        if health_score >= 70:
            status = "online"
        elif health_score >= 40:
            status = "degraded"
        else:
            status = "offline"

        self.store.update_equipment_state(
            equipment_code,
            {
                "health_score": health_score,
                "status": status,
                "updated_at": datetime.utcnow().isoformat(),
            },
        )

    def _sync_to_supabase(
        self,
        simulated_time: datetime,
        equipment_states: Dict[str, Dict[str, Any]],
    ) -> int:
        """Sync equipment operating_data, health_score, and status to Supabase.

        Uses batch SQL via psycopg2 for efficiency — one round-trip for all equipment.
        """
        import psycopg2
        import psycopg2.extras

        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@127.0.0.1:55322/postgres",
        )

        # Supabase status constraint: normal, warning, critical, offline, maintenance
        def health_to_status(score: float) -> str:
            if score >= 70:
                return "normal"
            elif score >= 40:
                return "warning"
            else:
                return "critical"

        updates = []
        for code, state in equipment_states.items():
            health_score = state.get("health_score")
            sensor_readings = state.get("sensor_readings", {})
            if not sensor_readings and health_score is None:
                continue

            # Build operating_data: {point_name: {value, timestamp, source}}
            operating_data = {}
            ts = simulated_time.isoformat()
            for point_name, value in sensor_readings.items():
                operating_data[point_name] = {
                    "value": value,
                    "timestamp": ts,
                    "source": "sentinel",
                }

            status = health_to_status(health_score) if health_score is not None else "normal"
            h = int(round(health_score)) if health_score is not None else 100

            updates.append((code, json.dumps(operating_data), h, status))

        if not updates:
            return 0

        try:
            conn = psycopg2.connect(database_url)
            conn.autocommit = True
            cur = conn.cursor()

            # Batch update using a VALUES list
            values_sql = ",".join(cur.mogrify("(%s, %s::jsonb, %s::int, %s)", row).decode() for row in updates)

            cur.execute(f"""
                UPDATE equipment AS e SET
                    operating_data = v.operating_data,
                    health_score = v.health_score,
                    status = v.status,
                    updated_at = now()
                FROM (VALUES {values_sql})
                    AS v(code, operating_data, health_score, status)
                WHERE e.code = v.code
            """)

            updated = cur.rowcount
            cur.close()
            conn.close()
            return updated

        except Exception as e:
            logger.error(f"Supabase sync failed: {e}")
            raise

    def _write_sensor_readings(
        self,
        simulated_time: datetime,
        equipment_states: Dict[str, Dict[str, Any]],
        ambient_temp: float,
        humidity: float,
    ) -> int:
        """Write sensor readings for all equipment."""
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
            self.store.write_sensor_readings(readings)

        return len(readings)

    def _write_energy_reading(self, simulated_time: datetime, energy_kw: float):
        """Write energy consumption reading."""
        date_str = simulated_time.date().isoformat()
        self.store.update_energy_history(date_str, "total_kwh", energy_kw)

    def _write_zone_history(
        self,
        simulated_time: datetime,
        equipment_states: Dict[str, Dict[str, Any]],
        schedule_state: Any,
    ) -> int:
        """Aggregate zone-level readings from equipment and write to zone history."""
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

        setpoint = 22.0
        if hasattr(schedule_state, "setpoint_offset"):
            setpoint = 22.0 + schedule_state.setpoint_offset

        occupancy_pct = 0
        if hasattr(schedule_state, "target_occupancy_pct"):
            occupancy_pct = schedule_state.target_occupancy_pct

        records = []
        for zone_id, data in zone_data.items():
            if not data.get("temp"):
                continue
            records.append(
                {
                    "time": simulated_time.isoformat(),
                    "zone_id": zone_id,
                    "building_id": self.site_id,
                    "temp": data.get("temp"),
                    "humidity": data.get("humidity"),
                    "co2": data.get("co2"),
                    "setpoint": setpoint,
                    "status": "running" if data.get("temp") else "off",
                    "occupancy": int(occupancy_pct * 20 / 100) if occupancy_pct else 0,
                }
            )

        if records:
            self.store.write_zone_history(records)

        return len(records)

    # === Solar & BESS snapshot persistence ===

    async def persist_solar_snapshot(
        self,
        simulated_time: datetime,
        equipment_states: Dict[str, Dict[str, Any]],
        building_load_kw: float,
        tariff_band: str,
        tariff_rate: float,
        hour_index: int,
        scenario: str = "lifecycle_365",
        year: int = 2026,
    ) -> bool:
        """Write one row to solar hourly snapshots from equipment states."""
        # Extract solar generation from inverter equipment
        solar_gen_kw = 0.0
        for code, state in equipment_states.items():
            if state.get("type", "").lower() == "inverter":
                readings = state.get("sensor_readings", {})
                solar_gen_kw += readings.get("ac_power_kw", 0.0)

        # Extract BESS state
        bess_soc_pct = 50.0
        bess_charge_kw = 0.0
        bess_discharge_kw = 0.0
        grid_import_kw = 0.0
        for code, state in equipment_states.items():
            if state.get("type", "").lower() == "bess":
                readings = state.get("sensor_readings", {})
                bess_soc_pct = readings.get("state_of_charge_pct", 50.0)
                bess_charge_kw = readings.get("charge_power_kw", 0.0)
                bess_discharge_kw = readings.get("discharge_power_kw", 0.0)
                grid_import_kw = readings.get("grid_import_kw", 0.0)
                break

        grid_export_kw = max(
            0.0,
            solar_gen_kw - building_load_kw - bess_charge_kw + bess_discharge_kw,
        )

        sim_date = simulated_time.date()
        hour_of_day = simulated_time.hour
        day_of_year = sim_date.timetuple().tm_yday

        row = {
            "site_id": self.site_id,
            "scenario": scenario,
            "year": year,
            "hour": hour_index,
            "date": sim_date.isoformat(),
            "month": sim_date.month,
            "day_of_year": day_of_year,
            "hour_of_day": hour_of_day,
            "solar_gen_kw": round(solar_gen_kw, 1),
            "building_load_kw": round(building_load_kw, 1),
            "bess_soc_pct": round(bess_soc_pct, 1),
            "bess_charge_kw": round(bess_charge_kw, 1),
            "bess_discharge_kw": round(bess_discharge_kw, 1),
            "grid_import_kw": round(grid_import_kw, 1),
            "grid_export_kw": round(grid_export_kw, 1),
            "tariff_band": tariff_band,
            "tariff_rate_c_kwh": round(tariff_rate, 2),
        }

        self.store.write_solar_snapshot(row)
        return True

    async def persist_solar_daily(
        self,
        simulated_date,
        solar_gen_kwh: float,
        building_load_kwh: float,
        bess_charge_kwh: float,
        bess_discharge_kwh: float,
        grid_import_kwh: float,
        grid_export_kwh: float,
        peak_generation_kw: float,
        avg_bess_soc_pct: float,
        scenario: str = "lifecycle_365",
        year: int = 2026,
    ) -> bool:
        """Write one row to solar daily aggregates at end of simulated day."""
        day_of_year = simulated_date.timetuple().tm_yday

        row = {
            "site_id": self.site_id,
            "scenario": scenario,
            "year": year,
            "date": simulated_date.isoformat(),
            "month": simulated_date.month,
            "day_of_year": day_of_year,
            "solar_gen_kwh": round(solar_gen_kwh, 1),
            "building_load_kwh": round(building_load_kwh, 1),
            "bess_charge_kwh": round(bess_charge_kwh, 1),
            "bess_discharge_kwh": round(bess_discharge_kwh, 1),
            "grid_import_kwh": round(grid_import_kwh, 1),
            "grid_export_kwh": round(grid_export_kwh, 1),
            "peak_generation_kw": round(peak_generation_kw, 1),
            "avg_bess_soc_pct": round(avg_bess_soc_pct, 1),
        }

        self.store.write_solar_daily(row)
        return True


_persistence_instance: Optional[SimulationPersistence] = None


def get_simulation_persistence(site_id: str = "site-002") -> SimulationPersistence:
    global _persistence_instance
    if _persistence_instance is None:
        _persistence_instance = SimulationPersistence(site_id=site_id)
    return _persistence_instance

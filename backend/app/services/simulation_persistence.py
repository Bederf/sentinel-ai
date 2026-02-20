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

        if results["errors"]:
            logger.warning(f"Persistence errors: {results['errors']}")
        else:
            logger.info(
                f"Persisted: {results['equipment_updated']} equipment, "
                f"{results['readings_written']} readings, {energy_kw:.1f} kW"
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

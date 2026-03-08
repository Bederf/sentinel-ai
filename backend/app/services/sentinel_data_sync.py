"""
SENTINEL Data Sync — syncs BMS data to Supabase and feeds ML pipeline.

SENTINEL is the intelligence layer that receives equipment readings from
whatever data source is active (simulation engine, real BMS via SIMBIOT,
CSV replay) and:
  1. Batch-updates equipment operating_data, health_score, status in Supabase
  2. Updates hvac_zones.current_temp from FCU/VAV readings
  3. Feeds ML pipeline for training and inference

This module owns all Supabase writes for equipment telemetry data.
The simulation layer (simulation_persistence.py) writes JSON only.
"""

import json
import logging
from app.core.site_resolver import get_primary_site_code
import os
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class SentinelDataSync:
    """SENTINEL Supabase sync + ML pipeline feeder."""

    def __init__(self, site_id: str | None = None):
        self.site_id = site_id or get_primary_site_code() or "unknown"

        # ML feeder — accumulates sensor data and triggers training
        from app.services.sentinel_ml_feeder import SentinelMLFeeder

        self.ml_feeder = SentinelMLFeeder()

    async def ingest_equipment_states(
        self,
        equipment_states: Dict[str, Dict[str, Any]],
        simulated_time: datetime,
    ) -> Dict[str, Any]:
        """
        Ingest equipment states into SENTINEL: Supabase + ML pipeline.

        Args:
            equipment_states: {equipment_code: {health_score, status, sensor_readings, type}}
            simulated_time: Current timestamp (simulation or real)

        Returns:
            Summary dict with counts and errors
        """
        results = {
            "supabase_synced": 0,
            "zones_updated": 0,
            "errors": [],
        }

        # 1. Batch update equipment in Supabase
        try:
            results["supabase_synced"] = self._batch_update_equipment(simulated_time, equipment_states)
        except Exception as e:
            results["errors"].append(f"supabase_sync: {e}")

        # 2. Update zone temperatures from FCU/VAV readings
        try:
            results["zones_updated"] = self._update_zone_temps(equipment_states)
        except Exception as e:
            results["errors"].append(f"zone_temps: {e}")

        # 3. Feed ML pipeline
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
            logger.warning(f"SENTINEL sync errors: {results['errors']}")
        else:
            logger.info(
                f"SENTINEL synced: {results['supabase_synced']} equipment, {results['zones_updated']} zone temps"
            )

        return results

    def _batch_update_equipment(
        self,
        simulated_time: datetime,
        equipment_states: Dict[str, Dict[str, Any]],
    ) -> int:
        """Batch update equipment operating_data, health_score, status in Supabase.

        Uses psycopg2 batch SQL for efficiency — one round-trip for all equipment.
        """
        import psycopg2

        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@127.0.0.1:55322/postgres",
        )

        def health_to_status(score: float) -> str:
            """Map health score to Supabase status constraint."""
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

            values_sql = ",".join(cur.mogrify("(%s, %s::jsonb, %s::int, %s)", row).decode() for row in updates)

            cur.execute(
                f"""
                UPDATE equipment AS e SET
                    operating_data = v.operating_data,
                    health_score = v.health_score,
                    status = v.status,
                    updated_at = now()
                FROM (VALUES {values_sql})
                    AS v(code, operating_data, health_score, status)
                WHERE e.code = v.code
            """
            )

            updated = cur.rowcount
            cur.close()
            conn.close()
            return updated

        except Exception as e:
            logger.error(f"Supabase equipment sync failed: {e}")
            raise

    def _update_zone_temps(
        self,
        equipment_states: Dict[str, Dict[str, Any]],
    ) -> int:
        """Update hvac_zones.current_temp from FCU/VAV room temperature readings.

        Zone mapping is 1:1 after equipment code fix:
        S002-FCU-{zone_num} → Zone-{zone_num}
        """
        import psycopg2

        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@127.0.0.1:55322/postgres",
        )

        zone_updates = []
        for code, state in equipment_states.items():
            equip_type = state.get("type", "").lower()
            readings = state.get("sensor_readings", {})

            # Extract zone number from equipment code: S002-FCU-{zone_num}
            parts = code.split("-")
            if len(parts) < 3:
                continue

            zone_num = parts[2]

            # FCU room_temp takes priority, VAV zone_temp as fallback
            temp = None
            if equip_type == "fcu" and "room_temp" in readings:
                temp = readings["room_temp"]
            elif equip_type == "vav" and "zone_temp" in readings:
                temp = readings["zone_temp"]

            if temp is not None:
                zone_id = f"Zone-{zone_num}"
                zone_updates.append((zone_id, float(temp)))

        if not zone_updates:
            return 0

        # Deduplicate: FCU reading wins over VAV for same zone
        seen = {}
        for zone_id, temp in zone_updates:
            if zone_id not in seen:
                seen[zone_id] = temp

        try:
            conn = psycopg2.connect(database_url)
            conn.autocommit = True
            cur = conn.cursor()

            values = list(seen.items())
            values_sql = ",".join(cur.mogrify("(%s, %s::numeric)", (zid, temp)).decode() for zid, temp in values)

            cur.execute(
                f"""
                UPDATE hvac_zones AS z SET
                    current_temp = v.temp,
                    last_updated = now()
                FROM (VALUES {values_sql})
                    AS v(zone_id, temp)
                WHERE z.zone_id = v.zone_id
            """
            )

            updated = cur.rowcount
            cur.close()
            conn.close()
            return updated

        except Exception as e:
            logger.error(f"Zone temp sync failed: {e}")
            raise


_sentinel_sync_instance: Optional[SentinelDataSync] = None


def get_sentinel_data_sync(site_id: str | None = None) -> SentinelDataSync:
    global _sentinel_sync_instance
    if _sentinel_sync_instance is None:
        _sentinel_sync_instance = SentinelDataSync(site_id=site_id)
    return _sentinel_sync_instance

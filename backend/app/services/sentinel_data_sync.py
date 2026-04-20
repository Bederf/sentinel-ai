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
import os
from datetime import datetime
from typing import Any

from app.api.metrics import sentinel_data_freshness_violations_total
from app.core.site_resolver import get_primary_site_code
from app.services.audit_logger import audit_structured_logger
from app.services.ml_config import (
    DATA_FRESHNESS_MAX_HOURS,
    MIN_LSTM_TRAINING_HOURS,
    get_ml_trust_weight,
)

logger = logging.getLogger(__name__)


def _blend_health_score(
    base_health: float,
    sensor_readings: dict,
    ml_hours_ingested: float,
) -> float:
    """Blend rule-based health score with LSTM anomaly score.

    Activates only after ML_GATE_LSTM_HOURS threshold. Below that or when
    lstm_anomaly_score is absent, returns base_health unchanged.

    Formula: final = base_health * (1 - trust_weight) + (1 - lstm_anomaly) * 100 * trust_weight
    """
    lstm_anomaly = sensor_readings.get("lstm_anomaly_score") if sensor_readings else None

    if lstm_anomaly is None or ml_hours_ingested < MIN_LSTM_TRAINING_HOURS:
        return base_health

    trust_weight = get_ml_trust_weight(ml_hours_ingested)
    ml_health = (1.0 - lstm_anomaly) * 100.0
    blended = (base_health * (1.0 - trust_weight)) + (ml_health * trust_weight)
    return round(blended, 2)


class SentinelDataSync:
    """SENTINEL Supabase sync + ML pipeline feeder."""

    def __init__(self, site_id: str | None = None):
        self.site_id = site_id or get_primary_site_code() or "unknown"

        # ML feeder — accumulates sensor data and triggers training
        from app.services.sentinel_ml_feeder import SentinelMLFeeder

        self.ml_feeder = SentinelMLFeeder(site_id=self.site_id)

    async def ingest_equipment_states(
        self,
        equipment_states: dict[str, dict[str, Any]],
        simulated_time: datetime,
        data_source: str = "bridge_poll",
    ) -> dict[str, Any]:
        """
        Ingest equipment states into SENTINEL: Supabase + ML pipeline.

        Args:
            equipment_states: {equipment_code: {health_score, status, sensor_readings, type}}
            simulated_time: Current timestamp (simulation or real)
            data_source: Tag for ML model filtering — "bridge_poll", "bms_event",
                        "inspection", "work_order_feedback"

        Returns:
            Summary dict with counts and errors
        """
        results = {
            "supabase_synced": 0,
            "sensor_readings_written": 0,
            "zones_updated": 0,
            "errors": [],
        }

        # ML pipeline first — score anomaly and LSTM before writing to Supabase.
        # This ensures operating_data includes the latest scores on the same poll cycle.
        #
        # ── Data freshness gate ────────────────────────────────────────────────
        # Block stale telemetry from reaching ML inference to avoid polluting
        # models with outdated baselines. Uses integration_repository which
        # already computes data_freshness_hours from last_sync_at timestamps.
        freshness_threshold = DATA_FRESHNESS_MAX_HOURS  # 24h
        try:
            from app.database.repositories.integration_repository import IntegrationRepository

            integration_repo = IntegrationRepository()
            freshness_data = integration_repo.get_data_quality_metrics(site_id=self.site_id)
            data_freshness_hours = freshness_data.get("data_freshness_hours") or 9999
        except Exception as e:
            logger.warning(f"[ML FEEDER] Could not compute freshness — proceeding without gate: {e}")
            data_freshness_hours = 0.0  # Proceed if freshness check fails (fail-open)

        if data_freshness_hours > freshness_threshold:
            violation_msg = (
                f"site_id={self.site_id} "
                f"data_freshness_hours={data_freshness_hours:.1f} "
                f"threshold_hours={freshness_threshold} "
                f"skip_reason=stale_telemetry_blocked_before_ml_ingest"
            )
            logger.warning(f"[ML FEEDER] Freshness gate rejected: {violation_msg}")
            audit_structured_logger.warning(
                f"event=data_freshness_violation "
                f"site_id={self.site_id} "
                f"data_freshness_hours={data_freshness_hours:.1f} "
                f"threshold_hours={freshness_threshold}"
            )
            sentinel_data_freshness_violations_total.labels(site_id=self.site_id).inc()
            # Do NOT call ml_feeder.ingest() — data is too stale
        else:
            # Fresh — proceed with ML ingestion
            try:
                self.ml_feeder.ingest(equipment_states, simulated_time, data_source=data_source)
                ml_results = self.ml_feeder.train_if_ready()
                if ml_results:
                    successful = [r for r in ml_results if "error" not in r]
                    logger.info(f"[ML FEEDER] Trained {len(successful)} models from SENTINEL data")
                    results["ml_models_trained"] = len(successful)
                results["ml_hours_ingested"] = self.ml_feeder.hours_ingested

                # 1a. Compute IF anomaly scores and inject into equipment_states.
                anomaly_scores = self.ml_feeder.score_anomaly()
                if anomaly_scores:
                    for code, score in anomaly_scores.items():
                        if code in equipment_states:
                            equipment_states[code].setdefault("sensor_readings", {})["anomaly_score"] = score
                    results["anomaly_scores_written"] = len(anomaly_scores)

                # 1b. Compute LSTM-derived anomaly scores (requires 500h minimum).
                # Written as a separate key so both signals coexist.
                lstm_scores = self.ml_feeder.score_lstm_anomaly()
                if lstm_scores:
                    for code, score in lstm_scores.items():
                        if code in equipment_states:
                            equipment_states[code].setdefault("sensor_readings", {})["lstm_anomaly_score"] = score
                    results["lstm_anomaly_scores_written"] = len(lstm_scores)

                # 1c. Compute autoencoder-derived anomaly scores (if trained model available).
                ae_scores = self.ml_feeder.score_autoencoder_anomaly()
                if ae_scores:
                    for code, score in ae_scores.items():
                        if code in equipment_states:
                            equipment_states[code].setdefault("sensor_readings", {})["autoencoder_anomaly_score"] = (
                                score
                            )
                    results["autoencoder_scores_written"] = len(ae_scores)
            except Exception as e:
                results["errors"].append(f"ml_feeder: {e}")

        # 2. Batch update equipment in Supabase (with ML scores now injected)
        try:
            results["supabase_synced"] = self._batch_update_equipment(simulated_time, equipment_states)
        except Exception as e:
            results["errors"].append(f"supabase_sync: {e}")

        # 3. Persist individual sensor readings to equipment_sensor_readings
        try:
            results["sensor_readings_written"] = self._write_sensor_readings(simulated_time, equipment_states)
        except Exception as e:
            results["errors"].append(f"sensor_readings: {e}")

        # 4. Update zone temperatures from FCU/VAV readings
        try:
            results["zones_updated"] = self._update_zone_temps(equipment_states)
        except Exception as e:
            results["errors"].append(f"zone_temps: {e}")

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
        equipment_states: dict[str, dict[str, Any]],
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

            # Blend LSTM anomaly into health_score when gate is met.
            # health_score from caller is the "base" rule-based score.
            ml_hours = self.ml_feeder.hours_ingested
            final_health_score = _blend_health_score(health_score, sensor_readings, ml_hours)

            if final_health_score != health_score:
                logger.info(
                    "health_score_blended",
                    equipment_id=code,
                    base_health=health_score,
                    lstm_anomaly=sensor_readings.get("lstm_anomaly_score"),
                    trust_weight=get_ml_trust_weight(ml_hours),
                    final_health=final_health_score,
                    ml_hours=ml_hours,
                )

            # Build operating_data: {point_name: {value, timestamp, source}}
            operating_data = {}
            ts = simulated_time.isoformat()
            for point_name, value in sensor_readings.items():
                operating_data[point_name] = {
                    "value": value,
                    "timestamp": ts,
                    "source": "sentinel",
                }

            status = health_to_status(final_health_score)
            h = int(round(final_health_score))

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

    def _write_sensor_readings(
        self,
        simulated_time: datetime,
        equipment_states: dict[str, dict[str, Any]],
    ) -> int:
        """Persist individual sensor readings to equipment_sensor_readings.

        Writes one row per (equipment, sensor_type) per sync cycle.
        Sampled at most once per simulated hour to avoid table explosion.
        """
        import psycopg2

        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@127.0.0.1:55322/postgres",
        )

        # Unit hints for common BMS point names
        _UNITS: dict[str, str] = {
            "room_temp": "°C",
            "zone_temp": "°C",
            "supply_temp": "°C",
            "return_temp": "°C",
            "chilled_water_supply_temp": "°C",
            "chilled_water_return_temp": "°C",
            "outdoor_temp": "°C",
            "damper_position": "%",
            "valve_position": "%",
            "fan_speed": "%",
            "occupancy": "%",
            "power_kw": "kW",
            "energy_kwh": "kWh",
            "illuminance": "lux",
            "soc_pct": "%",
            "voltage": "V",
            "current": "A",
            "frequency": "Hz",
            "power_factor": "",
        }

        rows = []
        ts = simulated_time
        for code, state in equipment_states.items():
            readings = state.get("sensor_readings", {})
            if not readings:
                continue
            equip_type = state.get("type", "unknown")
            for point_name, value in readings.items():
                if not isinstance(value, (int, float)):
                    continue
                rows.append(
                    (
                        code,  # equipment_id (text = code)
                        point_name,  # sensor_type
                        float(value),  # value
                        _UNITS.get(point_name),  # unit (nullable)
                        ts,  # recorded_at
                        self.site_id,  # site_id
                        json.dumps({"equipment_type": equip_type}),  # metadata
                    )
                )

        if not rows:
            return 0

        try:
            conn = psycopg2.connect(database_url)
            conn.autocommit = True
            cur = conn.cursor()

            values_sql = ",".join(
                cur.mogrify(
                    "(%s, %s, %s::double precision, %s, %s::timestamptz, %s, %s::jsonb)",
                    row,
                ).decode()
                for row in rows
            )

            cur.execute(
                f"""
                INSERT INTO equipment_sensor_readings
                    (equipment_id, sensor_type, value, unit, recorded_at, site_id, metadata)
                VALUES {values_sql}
                ON CONFLICT DO NOTHING
                """
            )

            written = cur.rowcount
            cur.close()
            conn.close()
            return written

        except Exception as e:
            logger.error(f"Sensor readings write failed: {e}")
            raise

    def _update_zone_temps(
        self,
        equipment_states: dict[str, dict[str, Any]],
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


_sentinel_sync_instance: SentinelDataSync | None = None


def get_sentinel_data_sync(site_id: str | None = None) -> SentinelDataSync:
    global _sentinel_sync_instance
    if _sentinel_sync_instance is None:
        _sentinel_sync_instance = SentinelDataSync(site_id=site_id)
    return _sentinel_sync_instance

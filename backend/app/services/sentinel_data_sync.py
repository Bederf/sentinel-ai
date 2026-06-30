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
from datetime import UTC, date, datetime
from typing import Any

from app.api.metrics import sentinel_data_freshness_violations_total
from app.config.settings import settings
from app.core.site_scope import is_site_002_out_of_scope_l3
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


EQUIPMENT_EXPECTED_LIFE: dict[str, int] = {
    "chiller": 20,
    "ahu": 15,
    "fcu": 15,
    "vav": 20,
    "pump": 15,
    "cooling_tower": 20,
    "bess": 10,
    "generator": 25,
    "ups": 10,
    "solar_panel": 25,
}


def calculate_age_based_health(
    install_date: date,
    equipment_type: str,
    last_service_date: date | None,
) -> tuple[float, str]:
    """Calculate health score from static factors only.
    Used when no live telemetry is available.
    Returns (health_score, confidence).
    """
    today = date.today()
    expected_life = EQUIPMENT_EXPECTED_LIFE.get(equipment_type.lower(), 20)

    age_years = (today - install_date).days / 365
    age_health = max(0.0, 100.0 - (age_years / expected_life * 40.0))

    service_penalty = 0.0
    if last_service_date:
        days_since_service = (today - last_service_date).days
        service_interval = 365
        if days_since_service > service_interval * 1.5:
            service_penalty = 15.0
        elif days_since_service > service_interval:
            service_penalty = 8.0
    else:
        service_penalty = 10.0

    health_score = round(max(30.0, age_health - service_penalty), 1)
    return health_score, "low"


def _check_sensor_quality(point_name: str, value: float) -> str:
    """Inline quality gate for sensor readings before persistence.

    Returns 'ok' or 'rejected' based on range validation.
    Rejected readings are still written (with quality_flag='rejected')
    so they can be audited.
    """
    import math

    if math.isnan(value):
        return "rejected"
    name_lower = point_name.lower()
    if "temp" in name_lower and "color_temp" not in name_lower and (value < -50.0 or value > 100.0):
        return "rejected"
    if "pressure" in name_lower and (value < 0.0 or value > 5000.0):
        return "rejected"
    if "co2" in name_lower and (value < 0.0 or value > 5000.0):
        return "rejected"
    if "humidity" in name_lower and (value < 0.0 or value > 100.0):
        return "rejected"
    return "ok"


class SentinelDataSync:
    """SENTINEL Supabase sync + ML pipeline feeder."""

    def __init__(self, site_id: str | None = None):
        raw = site_id or get_primary_site_code() or "unknown"
        # Normalize to site-XXX format (not SXXX legacy)
        if raw.startswith("S") and not raw.startswith("site-"):
            num = raw[1:]  # "S002" → "002"
            raw = f"site-{num}"
        self.site_id = raw

        # ML feeder — accumulates sensor data and triggers training
        from app.services.sentinel_ml_feeder import SentinelMLFeeder

        self.ml_feeder = SentinelMLFeeder()

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
        data_freshness_hours = 9999.0  # Default: block ML ingest
        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            # Resolve site code → UUID for log_sources query (site_id is UUID there)
            # Normalize to site-XXX format for sites table query (sites table uses "site-002" not "S002")
            site_code_for_query = self.site_id
            if self.site_id.startswith("S"):
                # Convert S002 → site-002 for sites table lookup
                num = self.site_id[1:]  # "002"
                site_code_for_query = f"site-{num}"

            sites_resp = client.table("sites").select("id").eq("code", site_code_for_query).execute()
            if sites_resp.data:
                site_uuid = sites_resp.data[0]["id"]
                sources_resp = client.table("log_sources").select("last_sync_at").eq("site_id", site_uuid).execute()
                if sources_resp.data and sources_resp.data[0].get("last_sync_at"):
                    now = datetime.now(tz=UTC)
                    sync_at = sources_resp.data[0]["last_sync_at"]
                    sync_time = datetime.fromisoformat(sync_at.replace("Z", "+00:00"))
                    if sync_time.tzinfo is None:
                        sync_time = sync_time.replace(tzinfo=UTC)
                    data_freshness_hours = (now - sync_time).total_seconds() / 3600
                    logger.info(
                        f"[ML FEEDER] Freshness check: site_id={self.site_id} site_code={site_code_for_query} last_sync={sync_at} freshness_hours={data_freshness_hours:.2f}"
                    )
        except Exception as e:
            logger.warning(f"[ML FEEDER] Freshness check error for site_id={self.site_id}: {e}")
            data_freshness_hours = 9999.0  # Block ML ingest if freshness check fails
        else:
            logger.info(
                f"[ML FEEDER] Freshness check: no log_sources entry for site_id={self.site_id} site_code={site_code_for_query}"
            )

        if data_freshness_hours > freshness_threshold:
            logger.warning(
                f"[ML FEEDER] Freshness gate rejected: site_id={self.site_id} data_freshness_hours={data_freshness_hours:.1f} threshold_hours={freshness_threshold}"
            )
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
                from app.services.module_registry_service import ModuleRegistryService

                self.ml_feeder.ingest(
                    equipment_states,
                    simulated_time,
                    data_source=data_source,
                    site_id=ModuleRegistryService._normalize_site_id(self.site_id),
                )
                ml_results = self.ml_feeder.train_if_ready()
                if ml_results:
                    successful = [r for r in ml_results if "error" not in r]
                    logger.info(f"[ML FEEDER] Trained {len(successful)} models from SENTINEL data")
                    results["ml_models_trained"] = len(successful)
                results["ml_hours_ingested"] = self.ml_feeder.hours_ingested

                # Persist ml_hours_ingested to sites table so it survives restarts
                # Note: sites table uses "site-002" format, not "S002"
                site_code_for_persist = self.site_id
                if self.site_id.startswith("S"):
                    num = self.site_id[1:]
                    site_code_for_persist = f"site-{num}"

                # Calculate actual ML hours from telemetry timestamps (restart-proof).
                # If the calculate call raises (e.g. DB unreachable in subprocess
                # context), skip BOTH the persist and the scoring — a wrong
                # persisted value would silently reset the cumulative counter.
                persisted_hours: float | None = None
                try:
                    actual_hours = await self.ml_feeder.calculate_actual_ml_hours(self.site_id)
                except Exception as e:
                    logger.warning(
                        f"[ML FEEDER] calculate_actual_ml_hours failed for "
                        f"{self.site_id}: {e} — skipping persist + scoring this poll"
                    )
                    actual_hours = None
                if actual_hours is not None and actual_hours > 0:
                    persisted_hours = actual_hours
                try:
                    import psycopg2

                    # Per CLAUDE.md: APScheduler subprocess contexts don't
                    # inherit env vars. settings.database_url is loaded from
                    # .env at import time and is the authoritative source.
                    database_url = (
                        settings.database_url
                        or os.getenv("DATABASE_URL")
                        or "postgresql://postgres:postgres@127.0.0.1:55322/postgres"
                    )
                    if not database_url:
                        raise ValueError("DATABASE_URL not set (settings.database_url empty, env var missing)")
                    if persisted_hours is None:
                        raise ValueError("persisted_hours unavailable — calculate_actual_ml_hours failed")
                    conn = psycopg2.connect(database_url)
                    conn.autocommit = True
                    cur = conn.cursor()
                    cur.execute(
                        """
                        UPDATE sites SET ml_hours_ingested = %s, updated_at = now()
                        WHERE code = %s
                        """,
                        (persisted_hours, site_code_for_persist),
                    )
                    cur.close()
                    conn.close()
                    logger.info(
                        f"[ML FEEDER] Persisted ml_hours_ingested={persisted_hours:.1f} (counter={self.ml_feeder.hours_ingested}) for site {self.site_id}"
                    )
                except Exception as e:
                    logger.warning(f"[ML FEEDER] Could not persist ml_hours_ingested: {e}")
                    persisted_hours = None  # ensure scoring is also skipped

                # 1a. Compute IF anomaly scores and inject into equipment_states.
                # Use persisted ml_hours_ingested from Supabase rather than the
                # in-memory counter which resets to 0 on every restart.
                # persisted_hours may be None if the calculate/persist failed —
                # skip scoring rather than score against an in-memory 0.
                ml_hours_for_scoring = int(persisted_hours) if (persisted_hours and persisted_hours > 0) else None
                if ml_hours_for_scoring is not None:
                    anomaly_scores = self.ml_feeder.score_anomaly(hours_ingested=ml_hours_for_scoring)
                else:
                    anomaly_scores = {}
                if anomaly_scores:
                    for code, score in anomaly_scores.items():
                        if code in equipment_states:
                            equipment_states[code].setdefault("sensor_readings", {})["anomaly_score"] = score
                    results["anomaly_scores_written"] = len(anomaly_scores)

                # 1b. Compute LSTM-derived anomaly scores (requires 500h minimum).
                # Written as a separate key so both signals coexist.
                lstm_scores = self.ml_feeder.score_lstm_anomaly(hours_ingested=ml_hours_for_scoring)
                if lstm_scores:
                    for code, score in lstm_scores.items():
                        if code in equipment_states:
                            equipment_states[code].setdefault("sensor_readings", {})["lstm_anomaly_score"] = score
                    results["lstm_anomaly_scores_written"] = len(lstm_scores)

                # 1c. Compute autoencoder-derived anomaly scores (if trained model available).
                ae_scores = self.ml_feeder.score_autoencoder_anomaly(hours_ingested=ml_hours_for_scoring)
                if ae_scores:
                    for code, score in ae_scores.items():
                        if code in equipment_states:
                            equipment_states[code].setdefault("sensor_readings", {})["autoencoder_anomaly_score"] = (
                                score
                            )
                    results["autoencoder_scores_written"] = len(ae_scores)

                # 1d. Persist ML scores to equipment_analytics for promotion gate queries.
                if site_uuid and (anomaly_scores or lstm_scores or ae_scores):
                    try:
                        # Build equipment code → id mapping for upsert
                        equip_code_to_id: dict[str, str] = {}
                        for eq in equipment_states.values():
                            meta = eq.get("_meta", {})
                            if meta.get("equipment_id"):
                                equip_code_to_id[meta.get("code", "")] = meta["equipment_id"]

                        if not equip_code_to_id:
                            # Fallback: query equipment table for code→id mapping
                            from app.database.supabase_client import get_supabase_client

                            client = get_supabase_client()
                            codes = list(equipment_states.keys())
                            resp = client.table("equipment").select("id, code").in_("code", codes).execute()
                            equip_code_to_id = {r["code"]: r["id"] for r in (resp.data or [])}

                        model_ver = getattr(self.ml_feeder, "model_version", None) or "sentinel-v1"
                        count = self._upsert_equipment_analytics(
                            site_uuid=site_uuid,
                            equipment_code_to_id=equip_code_to_id,
                            anomaly_scores=anomaly_scores,
                            lstm_scores=lstm_scores,
                            ae_scores=ae_scores,
                            model_version=model_ver,
                            simulated_time=simulated_time,
                        )
                        results["equipment_analytics_written"] = count
                    except Exception as e:
                        logger.debug("equipment_analytics persist skipped: %s", e)
            except Exception as e:
                results["errors"].append(f"ml_feeder: {e}")

        # 2. Batch update equipment in Supabase (with ML scores now injected)
        try:
            results["supabase_synced"] = await self._batch_update_equipment(simulated_time, equipment_states)
        except Exception as e:
            results["errors"].append(f"supabase_sync: {e}")

        # 2a. Calculate age-based health for equipment with no live telemetry
        try:
            results["no_telemetry_health_updated"] = await self._update_no_telemetry_health(
                simulated_time, equipment_states
            )
        except Exception as e:
            results["errors"].append(f"no_telemetry_health: {e}")

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

    async def _batch_update_equipment(
        self,
        simulated_time: datetime,
        equipment_states: dict[str, dict[str, Any]],
    ) -> int:
        """Batch update equipment operating_data, health_score, status in Supabase.

        Uses psycopg2 batch SQL for efficiency — one round-trip for all equipment.
        Calculates health from sensor readings when pre-computed score is unavailable.
        """
        import psycopg2

        database_url = settings.database_url or os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL not set")

        def health_to_status(score: float | None) -> str:
            """Map health score to Supabase status constraint."""
            if score is None:
                return "unknown"
            if score >= 70:
                return "normal"
            elif score >= 40:
                return "warning"
            else:
                return "critical"

        # Initialize health calculator for computing scores from sensors
        from app.services.health_rating_calculator import HealthRatingCalculator

        health_calc = HealthRatingCalculator()

        # Get equipment metadata from DB for health calculations and trend tracking
        equipment_codes = list(equipment_states.keys())
        equipment_meta = {}

        def _derive_age_years(equipment: dict[str, Any]) -> float | None:
            source_date = equipment.get("install_date") or equipment.get("commissioning_date")
            if not source_date:
                return None
            try:
                if isinstance(source_date, date):
                    installed_on = source_date
                else:
                    installed_on = datetime.fromisoformat(str(source_date)).date()
                return round((date.today() - installed_on).days / 365.25, 2)
            except Exception:
                return None

        def _derive_runtime_hours(equipment: dict[str, Any]) -> float | None:
            operating_data = equipment.get("operating_data")
            if not isinstance(operating_data, dict):
                return None
            value = operating_data.get("runtime_hours")
            if isinstance(value, dict):
                value = value.get("value")
            try:
                return float(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            resp = (
                client.table("equipment")
                .select("id, code, type, install_date, commissioning_date, operating_data, health_score, updated_at")
                .in_("code", equipment_codes)
                .execute()
            )
            if resp.data:
                for eq in resp.data:
                    eq["age_years"] = _derive_age_years(eq)
                    eq["runtime_hours"] = _derive_runtime_hours(eq)
                equipment_meta = {eq["code"]: eq for eq in resp.data}
        except Exception as e:
            logger.warning(f"Could not fetch equipment metadata: {e}")

        ml_hours = self.ml_feeder.hours_ingested

        updates = []
        for code, state in equipment_states.items():
            health_score = state.get("health_score")
            sensor_readings = state.get("sensor_readings", {})
            if not sensor_readings and health_score is None:
                continue

            # Skip non-scoreable equipment types (lighting_panel, access_control, etc.)
            from app.config.health_config import get_scoreability

            eq_meta = equipment_meta.get(code, {})
            eq_type = eq_meta.get("type", "")
            score_cfg = get_scoreability(eq_type)
            if not score_cfg.get("scoreable", False):
                continue

            # FIXED: Calculate health from sensor readings when no pre-computed score
            if health_score is None and sensor_readings:
                try:
                    eq_meta = equipment_meta.get(code, {})
                    # Get existing operating_data for anomaly scores
                    existing_op = (
                        eq_meta.get("operating_data", {}) if isinstance(eq_meta.get("operating_data"), dict) else {}
                    )

                    health_score = await health_calc.calculate_from_sensors(
                        equipment_id=code,
                        equipment=eq_meta,
                        sensor_readings=sensor_readings,
                        operating_data=existing_op,
                    )
                    if health_score is not None:
                        logger.debug(f"Health calculated from sensors: {code}={health_score}")
                except Exception as e:
                    logger.warning(f"Failed to calculate health from sensors for {code}: {e}")
                    # Continue with None - will skip update or use default

            # Blend LSTM anomaly into health_score when gate is met.
            # health_score from caller is the "base" rule-based score.
            final_health_score = _blend_health_score(health_score, sensor_readings, ml_hours)

            if final_health_score is not None and health_score is not None and final_health_score != health_score:
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

            # Compute confidence and trend from available signals
            eq_meta = equipment_meta.get(code, {})
            existing_op = eq_meta.get("operating_data", {}) if isinstance(eq_meta.get("operating_data"), dict) else {}
            has_live = bool(sensor_readings)
            op_age = None
            if existing_op:
                # Estimate data age from first timestamp found in operating_data
                for pt_data in existing_op.values():
                    if isinstance(pt_data, dict) and pt_data.get("timestamp"):
                        try:
                            op_ts = datetime.fromisoformat(str(pt_data["timestamp"]).replace("Z", "+00:00"))
                            op_age = int((simulated_time - op_ts).total_seconds() / 60)
                            break
                        except Exception:
                            pass
            if op_age is None:
                # Fallback: compute freshness from equipment.updated_at
                eq_updated = eq_meta.get("updated_at")
                if eq_updated:
                    try:
                        eq_ts = datetime.fromisoformat(str(eq_updated).replace("Z", "+00:00"))
                        if eq_ts.tzinfo is None:
                            eq_ts = eq_ts.replace(tzinfo=UTC)
                        op_age = int((simulated_time - eq_ts).total_seconds() / 60)
                    except Exception:
                        pass
            confidence = health_calc.calculate_confidence(has_live, op_age, ml_hours)

            prev_score = eq_meta.get("health_score")
            # Preserve previous health score when new calculation yields nothing
            if final_health_score is None and prev_score is not None:
                final_health_score = float(prev_score)

            status = health_to_status(final_health_score)
            h = round(final_health_score) if final_health_score is not None else None
            trend = health_calc.calculate_trend(final_health_score or 0, prev_score)
            data_freshness = op_age  # already computed above

            updates.append(
                (
                    code,
                    json.dumps(operating_data),
                    h,
                    status,
                    confidence,
                    trend,
                    data_freshness,
                    simulated_time.isoformat(),
                )
            )

        if not updates:
            return 0

        try:
            conn = psycopg2.connect(database_url)
            conn.autocommit = True
            cur = conn.cursor()

            values_sql = ",".join(
                cur.mogrify("(%s, %s::jsonb, %s::int, %s, %s, %s, %s::int, %s::timestamptz)", row).decode()
                for row in updates
            )

            cur.execute(
                f"""
                UPDATE equipment AS e SET
                    operating_data = v.operating_data,
                    health_score = v.health_score,
                    status = v.status,
                    health_confidence = v.confidence,
                    health_trend = v.trend,
                    last_ml_update = v.last_ml_update,
                    data_freshness_minutes = v.data_freshness,
                    updated_at = now()
                FROM (VALUES {values_sql})
                    AS v(code, operating_data, health_score, status, confidence, trend, data_freshness, last_ml_update)
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

    async def _update_no_telemetry_health(
        self,
        simulated_time: datetime,
        equipment_states: dict[str, dict[str, Any]],
    ) -> int:
        """Calculate and persist age-based health scores for equipment without live telemetry.

        Queries all equipment for the current site, finds those not present in the
        current telemetry cycle, and assigns an age-based health score derived
        from install_date, equipment type, and service recency.

        Returns:
            Number of equipment updated.
        """
        import psycopg2

        database_url = settings.database_url or os.getenv("DATABASE_URL")
        if not database_url:
            return 0

        from app.database.repositories.equipment_repository import EquipmentRepository

        # Resolve site code -> UUID
        site_code = self.site_id
        if site_code.startswith("S"):
            num = site_code[1:]
            site_code = f"site-{num}"

        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        sites_resp = client.table("sites").select("id").eq("code", site_code).execute()
        if not sites_resp.data:
            return 0
        site_uuid = sites_resp.data[0]["id"]

        # Get all equipment for this site
        eq_repo = EquipmentRepository()
        all_equipment = eq_repo.get_all(site_id=site_uuid)

        telemetry_codes = set(equipment_states.keys())

        updates: list[tuple[str, int, str, str, str]] = []
        for eq in all_equipment:
            code = eq.get("code", "")
            if code in telemetry_codes:
                continue

            # Skip non-scoreable equipment types
            from app.config.health_config import get_scoreability

            score_cfg = get_scoreability(eq.get("type", ""))
            if not score_cfg.get("scoreable", False):
                continue

            raw_install = eq.get("install_date")
            if not raw_install:
                continue

            install_dt = date.fromisoformat(raw_install) if isinstance(raw_install, str) else raw_install

            raw_service = eq.get("last_service")
            service_dt: date | None = None
            if raw_service:
                service_dt = date.fromisoformat(raw_service) if isinstance(raw_service, str) else raw_service

            score, confidence = calculate_age_based_health(
                install_date=install_dt,
                equipment_type=eq.get("type", ""),
                last_service_date=service_dt,
            )

            health_int = round(score)
            current_trend = eq.get("health_trend", "unknown")
            updates.append((code, health_int, confidence, current_trend, simulated_time.isoformat()))
            logger.debug(
                f"[HEALTH] {code} \u2014 age-based score: {score}%% (no telemetry, install_date={raw_install})"
            )

        if not updates:
            return 0

        try:
            conn = psycopg2.connect(database_url)
            conn.autocommit = True
            cur = conn.cursor()

            values_sql = ",".join(
                cur.mogrify("(%s, %s::int, %s, %s, %s::timestamptz)", row).decode() for row in updates
            )

            cur.execute(
                f"""
                UPDATE equipment AS e SET
                    health_score = v.health_score,
                    health_confidence = v.health_confidence,
                    health_trend = v.health_trend,
                    data_freshness_minutes = NULL,
                    last_ml_update = NULL,
                    updated_at = now()
                FROM (VALUES {values_sql})
                    AS v(code, health_score, health_confidence, health_trend, last_ml_update)
                WHERE e.code = v.code
                """
            )
            updated = cur.rowcount
            cur.close()
            conn.close()
            logger.info(f"[HEALTH] Updated {updated} no-telemetry equipment with age-based scores")
            return updated
        except Exception as e:
            logger.error(f"[HEALTH] No-telemetry batch update failed: {e}")
            return 0

    def _upsert_equipment_analytics(
        self,
        site_uuid: str,
        equipment_code_to_id: dict[str, str],
        anomaly_scores: dict[str, float],
        lstm_scores: dict[str, float],
        ae_scores: dict[str, float],
        model_version: str | None,
        simulated_time: datetime,
    ) -> int:
        """Batch upsert ML anomaly scores to equipment_analytics table.

        One row per equipment that has at least one score. Uses ON CONFLICT
        (equipment_id, scored_at) to handle same-cycle duplicates.
        """
        import psycopg2

        database_url = settings.database_url or os.getenv("DATABASE_URL")
        if not database_url:
            return 0

        rows = []
        for code, score in anomaly_scores.items():
            equip_id = equipment_code_to_id.get(code)
            if not equip_id:
                continue
            rows.append(
                {
                    "equipment_id": equip_id,
                    "site_id": site_uuid,
                    "anomaly_score": score,
                    "lstm_anomaly_score": lstm_scores.get(code),
                    "autoencoder_anomaly_score": ae_scores.get(code),
                    "model_version": model_version,
                    "scored_at": simulated_time,
                }
            )

        if not rows:
            return 0

        try:
            conn = psycopg2.connect(database_url)
            conn.autocommit = True
            cur = conn.cursor()

            for row in rows:
                cur.execute(
                    """
                    INSERT INTO equipment_analytics
                        (site_id, equipment_id, anomaly_score, lstm_anomaly_score,
                         autoencoder_anomaly_score, model_version, scored_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (equipment_id, scored_at) DO UPDATE SET
                        anomaly_score = EXCLUDED.anomaly_score,
                        lstm_anomaly_score = EXCLUDED.lstm_anomaly_score,
                        autoencoder_anomaly_score = EXCLUDED.autoencoder_anomaly_score,
                        model_version = EXCLUDED.model_version
                    """,
                    (
                        row["site_id"],
                        row["equipment_id"],
                        row["anomaly_score"],
                        row["lstm_anomaly_score"],
                        row["autoencoder_anomaly_score"],
                        row["model_version"],
                        row["scored_at"],
                    ),
                )

            count = len(rows)
            cur.close()
            conn.close()
            return count
        except Exception as e:
            logger.warning(f"equipment_analytics upsert failed: {e}")
            return 0

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

        database_url = settings.database_url or os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL not set")

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
            "energy_import_kwh": "kWh",
            "energy_export_kwh": "kWh",
            "thermal_energy_kwh": "kWh",
            "total_consumption_m3": "m3",
            "illuminance": "lux",
            "soc_pct": "%",
            "voltage": "V",
            "current": "A",
            "frequency": "Hz",
            "power_factor": "",
        }

        rows = []
        rejected_count = 0
        skipped_scope_count = 0
        ts = simulated_time
        for code, state in equipment_states.items():
            if is_site_002_out_of_scope_l3(self.site_id, code):
                skipped_scope_count += 1
                continue
            readings = state.get("sensor_readings", {})
            if not readings:
                continue
            equip_type = state.get("type", "unknown")
            for point_name, value in readings.items():
                if not isinstance(value, (int, float)):
                    continue
                quality_flag = _check_sensor_quality(point_name, float(value))
                if quality_flag == "rejected":
                    rejected_count += 1
                rows.append(
                    (
                        code,  # equipment_id (text = code)
                        point_name,  # sensor_type
                        float(value),  # value
                        _UNITS.get(point_name),  # unit (nullable)
                        ts,  # recorded_at
                        self.site_id,  # site_id
                        json.dumps({"equipment_type": equip_type}),  # metadata
                        quality_flag,  # quality_flag
                    )
                )

        if not rows:
            return 0

        if rejected_count > 0:
            logger.info("[SENTINEL SYNC] Quality gate rejected %d sensor readings", rejected_count)
        if skipped_scope_count > 0:
            logger.warning(
                "[SENTINEL SYNC] Ignored %d Site 002 L3 equipment states outside tenant scope",
                skipped_scope_count,
            )

        try:
            conn = psycopg2.connect(database_url)
            conn.autocommit = True
            cur = conn.cursor()

            values_sql = ",".join(
                cur.mogrify(
                    "(%s, %s, %s::double precision, %s, %s::timestamptz, %s, %s::jsonb, %s)",
                    row,
                ).decode()
                for row in rows
            )

            cur.execute(
                f"""
                INSERT INTO equipment_sensor_readings
                    (equipment_id, sensor_type, value, unit, recorded_at, site_id, metadata, quality_flag)
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
        """Update hvac_zones from FCU/VAV sensor readings.

        Also syncs IAQ fields (co2_ppm, humidity_pct) when provided by bridge.
        Zone mapping: S002-FCU-{zone_num} → Zone-{zone_num}

        Multi-site aware: uses self.site_id to scope zone codes correctly.
        """
        import psycopg2

        database_url = settings.database_url or os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL not set")

        # Collect all fields per zone — deduplication happens per field type
        zone_data: dict[str, dict[str, Any]] = {}  # zone_id -> {temp, co2_ppm, humidity_pct}

        for code, state in equipment_states.items():
            if is_site_002_out_of_scope_l3(self.site_id, code):
                continue
            equip_type = state.get("type", "").lower()
            readings = state.get("sensor_readings", {})

            # Extract zone number from equipment code: S002-FCU-{zone_num}
            parts = code.split("-")
            if len(parts) < 3:
                continue

            zone_num = parts[2]
            zone_id = f"Zone-{zone_num}"

            if zone_id not in zone_data:
                zone_data[zone_id] = {"temp": None, "co2_ppm": None, "humidity_pct": None}

            # Temperature: FCU room_temp takes priority over VAV zone_temp
            if equip_type == "fcu" and "room_temp" in readings and zone_data[zone_id]["temp"] is None:
                zone_data[zone_id]["temp"] = float(readings["room_temp"])
            elif equip_type == "vav" and "zone_temp" in readings and zone_data[zone_id]["temp"] is None:
                zone_data[zone_id]["temp"] = float(readings["zone_temp"])

            # IAQ fields from FCU sensor_readings (bridge populates co2_ppm)
            if "co2_ppm" in readings:
                zone_data[zone_id]["co2_ppm"] = float(readings["co2_ppm"])
            if "humidity_pct" in readings:
                zone_data[zone_id]["humidity_pct"] = float(readings["humidity_pct"])

        # Filter to zones that have at least one field to update
        zones_to_update = {
            zid: fields for zid, fields in zone_data.items() if any(v is not None for v in fields.values())
        }
        if not zones_to_update:
            return 0

        try:
            conn = psycopg2.connect(database_url)
            conn.autocommit = True
            cur = conn.cursor()

            # Batch update using VALUES constructor + JOIN for efficiency
            values_sql = ",".join(
                cur.mogrify(
                    "(%s, %s::numeric, %s::numeric, %s::numeric)",
                    (zid, fields["temp"], fields["co2_ppm"], fields["humidity_pct"]),
                ).decode()
                for zid, fields in zones_to_update.items()
            )

            cur.execute(
                f"""
                UPDATE hvac_zones AS z SET
                    current_temp = COALESCE(v.temp, z.current_temp),
                    co2_ppm = COALESCE(v.co2_ppm, z.co2_ppm),
                    humidity_pct = COALESCE(v.humidity_pct, z.humidity_pct),
                    iaq_last_updated = CASE WHEN v.co2_ppm IS NOT NULL OR v.humidity_pct IS NOT NULL THEN now() ELSE z.iaq_last_updated END,
                    last_updated = now()
                FROM (VALUES {values_sql})
                    AS v(zone_id, temp, co2_ppm, humidity_pct)
                WHERE z.zone_id = v.zone_id
            """
            )

            updated = cur.rowcount
            cur.close()
            conn.close()
            return updated

        except Exception as e:
            logger.error(f"Zone temp/IAQ sync failed: {e}")
            raise


_sentinel_sync_instances: dict[str, SentinelDataSync] = {}


def get_sentinel_data_sync(site_id: str | None = None) -> SentinelDataSync:
    # Per-site cache — prevents singleton poisoning when different callers
    # pass different site_id formats (site-002 vs S002) for the same site.
    from app.core.site_resolver import get_primary_site_code, normalize_site_id

    # Normalize to internal format so both "site-002" and "S002" resolve to same key
    key = normalize_site_id(site_id or get_primary_site_code() or "unknown", to_supabase=False)
    if key not in _sentinel_sync_instances:
        _sentinel_sync_instances[key] = SentinelDataSync(site_id=key)
    return _sentinel_sync_instances[key]

"""ML Model Configuration — loaded from Supabase, fallback to hardcoded defaults.

Supabase is the source of truth. Hardcoded values here are shipped as a
baseline seed; the `ml_model_config` Supabase table overrides at runtime.

Per-site feature discovery:
    Call `discover_site_ml_features(site_id)` during onboarding and periodically.
    It scans `telemetry_hourly`, classifies continuous numeric sensors,
    and writes site-specific feature lists into `ml_model_config`.
    Every site has different BMS points — this is the mechanism that makes ML
    features site-agnostic without hardcoding sensor names.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger("sentinel.ml.config")

# ── Hardcoded defaults (shipped baseline — Supabase overrides at runtime) ──

HARDCODED_LSTM_FEATURES: dict[str, list[str]] = {
    "chiller": ["chw_supply_temp", "chw_return_temp", "suction_pressure", "discharge_pressure", "compressor_current"],
    "ahu": ["supply_temp", "return_temp", "filter_dp", "fan_current", "mixed_air_temp"],
    "fcu": ["supply_temp", "fan_current", "valve_position"],
    "vav": ["airflow", "damper_position", "zone_temp", "supply_temp"],
    "pump": ["flow_rate", "discharge_pressure", "motor_current", "vibration", "temperature"],
    "cooling_tower": ["basin_temp", "fan_speed", "water_level", "fan_current"],
    "generator": ["battery_voltage", "oil_pressure", "coolant_temp", "load_pct"],
    "ups": ["battery_voltage", "load_pct", "temperature"],
    "bess": ["soc_pct", "charge_power_kw", "discharge_power_kw", "cell_temp"],
    "inverter": ["dc_input_power_kw", "ac_output_power_kw", "efficiency_pct", "inverter_temp"],
    "split": ["room_temp", "supply_temp", "fan_speed", "valve_position"],
    "transformer": ["winding_temp", "oil_temp", "load_pct", "tap_position"],
    "crac": ["supply_temp", "return_temp", "humidity_pct", "compressor_current"],
    "ats": ["mains_voltage", "generator_voltage", "position", "transfer_status"],
    "pfc": ["power_factor", "reactive_power_kvar", "current_a", "voltage_v"],
    "compressor": ["motor_current", "discharge_pressure", "suction_pressure", "temperature"],
    "fan": ["fan_current", "fan_speed", "vibration"],
    "motor": ["motor_current", "temperature", "vibration"],
    "solar_panel": ["power_kw", "voltage_v", "current_a", "efficiency_pct"],
    "pv_array": ["power_kw", "voltage_v", "current_a", "efficiency_pct"],
    "dali_controller": ["power_watts", "brightness", "lux", "occupancy", "lamp_hours", "driver_temp"],
    "luminaire": ["power_watts", "brightness", "lamp_hours"],
    "meter": ["active_power_kw", "energy_kwh", "power_factor"],
    "water_meter": ["flow_rate", "totalizer", "pressure"],
    "flow_meter": ["flow_rate", "totalizer", "pressure"],
    "door": ["door_status", "cycle_count"],
    "badge_reader": ["access_count", "auth_fail_count"],
    "camera": ["health_status", "bitrate", "fps"],
    "access_control": ["access_count", "auth_fail_count", "door_status"],
    "fire_panel": ["alarm_count", "fault_count", "power_status"],
    "detector": ["smoke_level", "temperature", "health_status"],
}

HARDCODED_AUTOENCODER_FEATURES: dict[str, list[str]] = {
    "chiller": ["chw_supply_temp", "chw_return_temp", "suction_pressure", "discharge_pressure", "compressor_current"],
    "ahu": ["supply_temp", "return_temp", "filter_dp", "fan_current", "mixed_air_temp"],
    "fcu": ["supply_temp", "fan_current", "valve_position"],
    "vav": ["airflow", "damper_position", "zone_temp", "supply_temp"],
    "pump": ["flow_rate", "discharge_pressure", "motor_current", "vibration", "temperature"],
    "cooling_tower": ["basin_temp", "fan_speed", "water_level", "fan_current"],
    "generator": ["battery_voltage", "oil_pressure", "coolant_temp", "load_pct"],
    "ups": ["battery_voltage", "load_pct", "temperature"],
    "bess": ["soc_pct", "charge_power_kw", "discharge_power_kw", "cell_temp"],
    "inverter": ["dc_input_power_kw", "ac_output_power_kw", "efficiency_pct", "inverter_temp"],
    "split": ["room_temp", "supply_temp", "fan_speed", "valve_position"],
    "transformer": ["winding_temp", "oil_temp", "load_pct", "tap_position"],
    "crac": ["supply_temp", "return_temp", "humidity_pct", "compressor_current"],
    "ats": ["mains_voltage", "generator_voltage", "position", "transfer_status"],
    "pfc": ["power_factor", "reactive_power_kvar", "current_a", "voltage_v"],
    "compressor": ["motor_current", "discharge_pressure", "suction_pressure", "temperature"],
    "fan": ["fan_current", "fan_speed", "vibration"],
    "motor": ["motor_current", "temperature", "vibration"],
    "solar_panel": ["power_kw", "voltage_v", "current_a", "efficiency_pct"],
    "pv_array": ["power_kw", "voltage_v", "current_a", "efficiency_pct"],
    "dali_controller": ["power_watts", "brightness", "lux", "occupancy", "lamp_hours", "driver_temp"],
    "luminaire": ["power_watts", "brightness", "lamp_hours"],
    "meter": ["active_power_kw", "energy_kwh", "power_factor"],
    "water_meter": ["flow_rate", "totalizer", "pressure"],
    "flow_meter": ["flow_rate", "totalizer", "pressure"],
}

HARDCODED_FAILURE_TYPES: dict[str, list[str]] = {
    "chiller": ["compressor_failure", "refrigerant_leak", "condenser_fouling", "oil_issue", "electrical"],
    "ahu": ["fan_motor", "belt_failure", "coil_fouling", "damper_actuator", "filter_blockage"],
    "fcu": ["fan_motor", "valve_actuator", "thermostat", "filter_blockage"],
    "generator": ["battery_failure", "fuel_system", "starter_motor", "alternator", "cooling_system"],
    "ups": ["battery_failure", "inverter", "capacitor", "overload"],
    "dali_controller": ["lamp_failure", "driver_fault", "emergency_battery_fault"],
}

HARDCODED_EXPECTED_LIFE: dict[str, float] = {
    "chiller": 20,
    "ahu": 15,
    "fcu": 12,
    "vav": 15,
    "pump": 10,
    "cooling_tower": 15,
    "generator": 20,
    "ups": 10,
    "bess": 10,
    "inverter": 12,
    "split": 10,
    "transformer": 25,
    "crac": 12,
    "ats": 15,
    "pfc": 10,
    "compressor": 10,
    "fan": 8,
    "motor": 10,
    "solar_panel": 25,
    "pv_array": 25,
    "dali_controller": 7,
    "luminaire": 7,
    "meter": 15,
    "water_meter": 10,
    "flow_meter": 10,
    "door": 5,
    "badge_reader": 5,
    "camera": 5,
    "access_control": 5,
    "fire_panel": 10,
    "detector": 10,
}

HARDCODED_ML_TRAINABLE: set[str] = set(HARDCODED_LSTM_FEATURES.keys())


# ── Configuration cache (loaded once from Supabase) ──

_ml_config_cache: dict[str, list[dict[str, Any]]] | None = None
_cache_loaded = False


def _load_from_supabase() -> dict[str, list[dict[str, Any]]]:
    """Load all ml_model_config rows from Supabase. Keyed by (site_id, equipment_type)."""
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        resp = client.table("ml_model_config").select("*").execute()
        if not resp.data:
            return {}
        result: dict[str, list[dict[str, Any]]] = {}
        for row in resp.data:
            site_id = row.get("site_id") or ""  # NULL becomes ""
            eq_type = row.get("equipment_type", "")
            entry: dict[str, Any] = {"site_id": site_id, "equipment_type": eq_type}
            if row.get("lstm_features"):
                entry["lstm_features"] = (
                    json.loads(row["lstm_features"]) if isinstance(row["lstm_features"], str) else row["lstm_features"]
                )
            if row.get("autoencoder_features"):
                entry["autoencoder_features"] = (
                    json.loads(row["autoencoder_features"])
                    if isinstance(row["autoencoder_features"], str)
                    else row["autoencoder_features"]
                )
            if row.get("failure_types"):
                entry["failure_types"] = (
                    json.loads(row["failure_types"]) if isinstance(row["failure_types"], str) else row["failure_types"]
                )
            if row.get("expected_life_years") is not None:
                entry["expected_life_years"] = float(row["expected_life_years"])
            if row.get("ml_trainable") is not None:
                entry["ml_trainable"] = bool(row["ml_trainable"])
            result.setdefault(eq_type, []).append(entry)
        return result
    except Exception as exc:
        logger.warning("[ML CONFIG] Failed to load from Supabase: %s — using hardcoded defaults", exc)
        return {}


def _get_config() -> dict[str, list[dict[str, Any]]]:
    global _ml_config_cache, _cache_loaded
    if not _cache_loaded:
        _ml_config_cache = _load_from_supabase()
        _cache_loaded = True
    return _ml_config_cache or {}


def _resolve_config(equipment_type: str, site_id: str | None = None) -> dict[str, Any] | None:
    """Get config for equipment_type, preferring site-specific over global NULL template."""
    rows = _get_config().get(equipment_type, [])
    if not rows:
        return None
    site_key = site_id or ""
    exact = next((r for r in rows if r.get("site_id") == site_key), None)
    if exact:
        return exact
    global_row = next((r for r in rows if not r.get("site_id")), None)
    return global_row


def reload_config() -> None:
    global _cache_loaded
    _cache_loaded = False


def register_site_equipment_type(
    site_id: str,
    equipment_type: str,
    lstm_features: list[str] | None = None,
    autoencoder_features: list[str] | None = None,
    failure_types: list[str] | None = None,
    expected_life_years: float | None = None,
    ml_trainable: bool = True,
) -> None:
    """Register a site-specific equipment type config in Supabase.

    Called during SIMBIOT onboarding wizard after equipment discovery.
    Overrides the global NULL template for this site.
    """
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        payload: dict[str, Any] = {
            "site_id": site_id,
            "equipment_type": equipment_type,
            "ml_trainable": ml_trainable,
        }
        if lstm_features is not None:
            payload["lstm_features"] = json.dumps(lstm_features)
        if autoencoder_features is not None:
            payload["autoencoder_features"] = json.dumps(autoencoder_features)
        if failure_types is not None:
            payload["failure_types"] = json.dumps(failure_types)
        if expected_life_years is not None:
            payload["expected_life_years"] = expected_life_years
        client.table("ml_model_config").upsert(payload, on_conflict="site_id,equipment_type").execute()
        reload_config()
    except Exception as exc:
        logger.warning("[ML CONFIG] Failed to register %s for site %s: %s", equipment_type, site_id, exc)


def get_lstm_features(equipment_type: str, site_id: str | None = None) -> list[str]:
    cfg = _resolve_config(equipment_type, site_id)
    if cfg and cfg.get("lstm_features"):
        return cfg["lstm_features"]
    return HARDCODED_LSTM_FEATURES.get(equipment_type, [])


def get_autoencoder_features(equipment_type: str, site_id: str | None = None) -> list[str]:
    cfg = _resolve_config(equipment_type, site_id)
    if cfg and cfg.get("autoencoder_features"):
        return cfg["autoencoder_features"]
    return HARDCODED_AUTOENCODER_FEATURES.get(equipment_type, [])


def get_failure_types(equipment_type: str, site_id: str | None = None) -> list[str]:
    cfg = _resolve_config(equipment_type, site_id)
    if cfg and cfg.get("failure_types"):
        return cfg["failure_types"]
    return HARDCODED_FAILURE_TYPES.get(equipment_type, ["general_failure"])


def get_expected_life_years(equipment_type: str, site_id: str | None = None) -> float:
    cfg = _resolve_config(equipment_type, site_id)
    if cfg and cfg.get("expected_life_years") is not None:
        return float(cfg["expected_life_years"])
    return HARDCODED_EXPECTED_LIFE.get(equipment_type, 15.0)


def is_ml_trainable(equipment_type: str, site_id: str | None = None) -> bool:
    cfg = _resolve_config(equipment_type, site_id)
    if cfg and cfg.get("ml_trainable") is not None:
        return bool(cfg["ml_trainable"])
    return equipment_type in HARDCODED_ML_TRAINABLE


def list_ml_trainable_types(site_id: str | None = None) -> list[str]:
    rows = _get_config()
    if not rows:
        return list(HARDCODED_ML_TRAINABLE)
    all_types = set(HARDCODED_ML_TRAINABLE)
    for eq_type, entries in rows.items():
        site_specific = next((e for e in entries if e.get("site_id") == (site_id or "")), None)
        global_entry = next((e for e in entries if not e.get("site_id")), None)
        entry = site_specific or global_entry
        if entry and entry.get("ml_trainable", True):
            all_types.add(eq_type)
        elif entry and not entry.get("ml_trainable", True) and eq_type in all_types:
            all_types.discard(eq_type)
    return sorted(all_types)


# ── Sensor type classification ──────────────────────────────────────────────

# Patterns that disqualify a sensor_type as an ML feature.
# These are binary/categorical/cumulative/config values — not useful for
# anomaly detection or LSTM forecasting.
_EXCLUDE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p)
    for p in [
        r".*_status$",
        r".*_state$",
        r".*_flag$",
        r".*_code$",
        r".*_alarm$",
        r".*_alarm_.*",
        r".*_command$",
        r".*_cmd$",
        r".*_online$",
        r".*_fault$",
        r".*_active$",
        r".*_enabled$",
        r".*_method$",
        r".*_function$",
        r".*_type$",
        r".*_hours$",
        r".*_cycles$",
        r".*_count$",
        r".*_reads_today$",
        r".*_events$",
        r".*_time_ms$",
        r".*_time_total$",
        r".*_time_hours$",
        r"anomaly_score",
        r"autoencoder_anomaly_score",
        r"lstm_anomaly_score",
        r"setpoint$",
        r"setpoint_.*",
        r".*_setpoint$",
        r".*yield.*",
        r"on_off",
        r"unlock_.*",
        r".*_schedule.*",
        r"min_level",
        r"max_level",
        r"physical_min_level",
        r"network_node_count",
        r"zone_count",
        r"total_doors.*",
        r"total_readers",
        r"total_drivers",
        r"active_drivers",
        r"active_occupants",
        r"occupied_zones",
        r"total_occupancy",
        r"peak_zone_density",
        r".*_uptime_.*",
        r"bacnet_interface_status",
        r"arc_fault_protection",
        r"container_door_status",
        r"emergency_.*",
        r"diag_code",
        r"alarm_code",
        r"fault_code",
        r"last_diagnostic_code",
        r"last_access_result",
        r"speedwire_connect",
        r"sma_portal_status",
        r"rest_api_status",
        r"database_status",
        r"grid_connection_status",
        r"isolation_resistance_mohm",
        r"arc_fault_protection",
        r"cable_loss_percent",
        r"soiling_loss_percent",
        r"mismatch_loss_percent",
        r"degradation_factor_percent",
        r"capacity_factor_percent",
        r"performance_ratio_percent",
        r".*_ratio_percent",
        r"etm_.*",
        r"corridor_function",
        r"lum_data_enabled",
        r"switch_dim_available",
        r"constant_light_output",
        r"dimming_method",
        r"fade_time_ms",
        r"scene_.*",
        r"group_.*",
        r"device_type",
        r"guard_.*",
        r"tailgate_attempt",
        r"riser_alarm",
        r"dry_contact_alarm",
        r"meter_status",
        r"leak_detected",
        r"total_consumption_liters",
        r"monthly_consumption_kl",
        r"c_rate",
        r"overvoltage_fault",
        r"undervoltage_fault",
        r"short_circuit_fault",
        r"cell_over_temp_fault",
    ]
]

# Keywords that confirm a sensor_type is a continuous numeric measurement.
# A sensor must match at least one to be included.
_INCLUDE_KEYWORDS = [
    "temp",
    "temperature",
    "pressure",
    "press",
    "flow",
    "lpm",
    "lps",
    "speed",
    "rpm",
    "position",
    "current",
    "voltage",
    "power_kw",
    "power_w",
    "power_watts",
    "_kw",
    "_kva",
    "co2",
    "co2_ppm",
    "humidity",
    "lux",
    "brightness",
    "soc_",
    "_soc",
    "filter_dp",
    "efficiency",
    "irradiation",
    "module_temp",
    "basin_temp",
    "winding_temp",
    "oil_temp",
    "coolant_temp",
    "inverter_temp",
    "driver_temp",
    "ambient_temp",
    "isolation_transformer_temp",
    "pcs_module_temp",
    "battery_module_temp",
    "fuel_level",
    "vibration",
    "power_factor",
    "frequency",
    "reactive_power",
    "energy_kwh",
    "fan_speed",
    "vfd_speed",
    "damper",
    "valve_position",
    "condenser_flow",
    "cond_supply",
    "cond_return",
    "chw_supply",
    "chw_return",
    "supply_air",
    "return_air",
    "return_temp",
    "supply_temp",
    "room_temp",
    "zone_temp",
    "staging_state",
    "compressor_current",
    "charge_discharge",
    "battery_current",
    "battery_voltage",
    "battery_soc",
    "dc_current",
    "dc_voltage",
    "ac_current",
    "ac_voltage",
    "string_",
    "mppt_",
    "array_current",
    "array_voltage",
    "array_dc_power",
    "array_ac_power",
    "grid_consumption_power",
    "grid_feed_power",
    "grid_frequency",
    "peak_flow",
    "flow_rate_average",
    "daily_consumption_m3",
    "total_consumption_m3",
    "pressure_bar",
    "hvac_kw",
    "lighting_kw",
    "total_kw",
]


def _is_ml_feature(sensor_type: str) -> bool:
    """Return True if sensor_type is a continuous numeric ML feature."""
    st = sensor_type.lower()
    # Check exclusions first
    if any(p.fullmatch(st) for p in _EXCLUDE_PATTERNS):
        return False
    # Must match at least one include keyword
    return any(kw in st for kw in _INCLUDE_KEYWORDS)


# Equipment type → code prefix fragment used to identify equipment in equipment_id
_EQUIP_TYPE_PREFIXES: dict[str, str] = {
    "ahu": "-AHU-",
    "chiller": "-CHILLER-",
    "fcu": "-FCU-",
    "vav": "-VAV-",
    "pump": "-PUMP-",
    "cooling_tower": "-CT-",
    "bess": "-BESS-",
    "inverter": "-PV-INV-",
    "pv_array": "-PV-ARRAY-",
    "water_meter": "-WATER-",
    "dali_controller": "-LCA-",
    "luminaire": "-LTG-",
    "generator": "-GEN-",
    "ups": "-UPS-",
    "transformer": "-TX-",
    "boiler": "-BOILER-",
    "weather": "-WEATHER-",
}


def discover_site_ml_features(
    site_id: str,
    lookback_days: int = 30,
    min_readings: int = 10,
) -> dict[str, list[str]]:
    """Scan telemetry_hourly for a site and register per-site ML features.

    Uses an aggregate SQL query (MIN/MAX/COUNT per sensor_type) to efficiently
    detect continuous numeric sensors with real variance — without fetching raw rows.
    Runs at onboarding and periodically (weekly retraining trigger).

    Returns:
        Dict of {equipment_type: [sensor_type, ...]} for what was registered.
    """
    try:
        import psycopg2
        from app.config.settings import settings

        db_url = settings.database_url
        if not db_url:
            logger.warning("[ML DISCOVER] DATABASE_URL not set — cannot discover features for %s", site_id)
            return {}
        conn = psycopg2.connect(db_url)
    except Exception as e:
        logger.warning("[ML DISCOVER] DB connection unavailable: %s", e)
        return {}

    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
    except Exception as e:
        conn.close()
        logger.warning("[ML DISCOVER] Supabase unavailable for writes: %s", e)
        return {}

    since = (datetime.now(UTC) - timedelta(days=lookback_days)).isoformat()
    registered: dict[str, list[str]] = {}

    try:
        cur = conn.cursor()
        for equip_type, prefix in _EQUIP_TYPE_PREFIXES.items():
            cur.execute(
                """
                SELECT point_name,
                       COUNT(*)                  AS n,
                       MIN(value_avg::numeric)   AS min_v,
                       MAX(value_avg::numeric)   AS max_v
                FROM   telemetry_hourly
                WHERE  site_id      = %s
                  AND  equipment_id LIKE %s
                  AND  hour_bucket  >= %s
                  AND  value_avg    IS NOT NULL
                GROUP BY point_name
                HAVING COUNT(*) >= %s
                """,
                (site_id, f"%{prefix}%", since, min_readings),
            )
            rows = cur.fetchall()
            if not rows:
                continue

            features: list[str] = []
            for sensor_type, _n, min_v, max_v in rows:
                if not _is_ml_feature(sensor_type):
                    continue
                # Exclude constant sensors — no variance means no signal for anomaly detection
                try:
                    if float(max_v) - float(min_v) < 0.001:
                        continue
                except (TypeError, ValueError):
                    continue
                features.append(sensor_type)

            if not features:
                continue

            features.sort()
            try:
                client.table("ml_model_config").upsert(
                    {
                        "site_id": site_id,
                        "equipment_type": equip_type,
                        "lstm_features": json.dumps(features),
                        "autoencoder_features": json.dumps(features),
                        "ml_trainable": True,
                        "last_discovered_at": datetime.now(UTC).isoformat(),
                        "updated_at": datetime.now(UTC).isoformat(),
                    },
                    on_conflict="site_id,equipment_type",
                ).execute()
                registered[equip_type] = features
                logger.info(
                    "[ML DISCOVER] %s/%s: registered %d features: %s",
                    site_id,
                    equip_type,
                    len(features),
                    features,
                )
            except Exception as e:
                logger.warning("[ML DISCOVER] Failed to register %s/%s: %s", site_id, equip_type, e)

        cur.close()
    finally:
        conn.close()

    reload_config()
    return registered

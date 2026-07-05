"""
Shadow Mode Bridge Polling — feeds live BMS data to the ML pipeline.

Polls the site bridge (http://10.99.0.1:8080) for:
  1. /api/sites/{site_id}/zones        — per-zone temperature / CO2 readings
  2. /api/sites/{site_id}/telemetry   — aggregated power / water / equipment summary
  3. /api/sites/{site_id}/alarms       — BACnet alarm events (Fault Classifier buffer)
  4. /api/sites/{site_id}/objects     — 410-point BACnet catalog (cached once)
  5. /api/sites/{site_id}/trends/{id} — per-sensor history (richer LSTM sequences)

Architecture:
  Bridge → ShadowModePollingService.poll() → SentinelDataSync.ingest_equipment_states()
         → SentinelMLFeeder.ingest(data_source="bridge_poll")
         → SentinelMLFeeder.ingest_fault_events(data_source="bms_event")

Fault events from /alarms accumulate in SentinelMLFeeder._fault_events buffer.
When 500+ events are buffered → train Fault Classifier.
"""

import asyncio
import collections
import contextlib
import logging
import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.core.site_scope import contains_site_002_out_of_scope_l3_reference, is_site_002_out_of_scope_l3
from app.core.site_resolver import normalize_site_id  # noqa: F401

# ─── Equipment display name formatters ──────────────────────────────────────────


def _format_unknown_name(eq_code: str) -> str:
    """Format display name for UNKNOWN-type equipment (sensors)."""
    code = eq_code.strip().upper()
    # e.g. "R-004" or "R004" → outdoor air sensor
    if code.startswith("R"):
        return "Outdoor Air Sensor Roof"
    if code.startswith("B"):
        return "Sensor Basement"
    if code.startswith("L"):
        return f"Sensor {code.replace('-', ' ')}"
    if "-" in code:
        return f"Sensor {code.replace('-', ' ')}"
    return f"Unknown Equipment {code}"


def _format_display_name(eq_type: str, eq_code: str) -> str:
    """Convert equipment code to human-readable name.

    Format: S002-{TYPE}-{LOCATION}  →  "{TYPE} {floor} Zone {N}"

    Location codes:
      Numeric: 105 → Level 1 Zone 5, 203 → Level 2 Zone 3, 001 → Ground Zone 1
      Letter:  B01 → Basement Zone 1,  R01 → Roof Zone 1
      Legacy:   B1-001 → Basement Zone 1  (normalized)

    Examples:
      _format_display_name("AHU", "105")   → "AHU Level 1 Zone 5"
      _format_display_name("FCU", "203")   → "FCU Level 2 Zone 3"
      _format_display_name("VAV", "003")   → "VAV Ground Zone 3"
      _format_display_name("RTU", "R01")   → "RTU Roof Zone 1"
      _format_display_name("DB", "B01")    → "DB Basement Zone 1"
    """
    if eq_type.upper() == "UNKNOWN":
        return _format_unknown_name(eq_code)

    code = eq_code.strip().upper()

    # Legacy: B1-001, L2-A — strip the trailing -### or normalize
    legacy_match = re.match(r"^([BL])(\d)[-]?\d+$", code)
    if legacy_match:
        prefix = legacy_match.group(1)  # B or L
        num = legacy_match.group(2)
        floor_part = "Basement" if prefix == "B" else f"Level {num}"
        return f"{eq_type} {floor_part}"

    # Roof: R01, R1
    if code.startswith("R"):
        zone = re.sub(r"^R", "", code) or "01"
        return f"{eq_type} Roof Zone {int(zone):02d}"

    # Basement: B01
    if code.startswith("B"):
        zone = re.sub(r"^B", "", code) or "01"
        return f"{eq_type} Basement Zone {int(zone):02d}"

    # Numeric: 001, 105, 203
    if code.isdigit():
        level = int(code[0])  # first digit = floor number
        zone_num = int(code[1:])  # remaining digits = zone within floor
        floor_name = "Ground" if level == 0 else f"Level {level}"
        return f"{eq_type} {floor_name} Zone {zone_num}"

    # Fallback: just title-case the code
    return f"{eq_type} {code}"


def _parse_eq_code_parts(code: str) -> tuple[str, str]:
    """Split S002-{TYPE}-{LOCATION} into (type, location_code)."""
    # e.g. "S002-AHU-105" → ("AHU", "105")
    # or    "S002-UNKNOWN-R-004" → ("UNKNOWN", "R-004")
    parts = code.split("-")
    if len(parts) >= 3:
        # site = parts[0]  # "S002"
        eq_type = parts[1].upper()
        eq_code = "-".join(parts[2:])  # "105" or "R-004"
        return eq_type, eq_code
    return "UNKNOWN", code


logger = logging.getLogger("sentinel.shadow_mode")


def _site_secret_suffix(site_id: str) -> str:
    """Return a stable env-var suffix for site-specific secrets."""
    return re.sub(r"[^A-Z0-9]+", "_", str(site_id or "").upper()).strip("_")


def site_bridge_token_env_candidates(site_id: str) -> list[str]:
    """Return conventional env secret names for a site's bridge token."""
    suffix = _site_secret_suffix(site_id)
    compact_suffix = suffix.replace("_", "")
    return [
        f"BRIDGE_API_TOKEN_{suffix}",
        f"SIMBIOT_API_KEY_{suffix}",
        f"BRIDGE_API_TOKEN_{compact_suffix}",
        f"SIMBIOT_API_KEY_{compact_suffix}",
    ]


def resolve_site_bridge_token(
    site_id: str,
    connection_config: dict[str, Any] | None = None,
    *,
    allow_config_token: bool = True,
    allow_global_fallback: bool = True,
) -> str:
    """Resolve a bridge token with site-scoped env secrets taking priority.

    Stored adapter tokens are retained only as a compatibility fallback. Live
    sites should use env-managed secrets such as BRIDGE_API_TOKEN_SITE_002 so a
    stale database token cannot mask the correct credential.
    """
    config = connection_config or {}
    explicit_env_names = [
        str(config.get(key) or "").strip() for key in ("token_env", "token_secret_env", "api_token_env", "secret_env")
    ]
    explicit_env_names = [name for name in explicit_env_names if name]

    candidates = [
        *explicit_env_names,
        *site_bridge_token_env_candidates(site_id),
    ]
    for env_name in candidates:
        token = os.getenv(env_name)
        if token:
            return token

    if allow_config_token and config.get("token"):
        return str(config["token"])

    if allow_global_fallback:
        from app.config.settings import settings

        return str(
            getattr(settings, "simbiot_api_key", None)
            or getattr(settings, "bridge_api_token", None)
            or os.getenv("SIMBIOT_API_KEY")
            or os.getenv("BRIDGE_API_TOKEN")
            or ""
        )

    return ""


DALI_LIGHTING_READING_NAMES = {
    "brightness",
    "power_watts",
    "power_w",
    "power",
    "lamp_wattage_rated",
    "lamp_wattage",
    "energy_kwh",
    "occupancy",
    "on_off",
    "lamp_status",
    "lamp_failure",
    "lamp_failures",
    "fault_state",
    "system_status",
    "status",
    "control_gear_status",
    "lux",
    "lamp_hours",
    "lamp_operating_hours",
    "gear_operating_hours",
    "lamp_on_time_total",
    "lamp_on_time",
    "driver_temp",
    "color_temp",
    "color_temp_k",
    "driver_voltage",
    "driver_current",
    "lamp_strikes",
    "lamp_failure_count",
    "lamp_strike_count",
    "emergency_battery",
    "emergency_battery_hours",
    "emergency_mode",
    "input_voltage",
    "output_current",
    "motion_count",
    "standby_level",
    "firmware_version",
    "fw_version",
    "device_type",
    "luminaire_type",
    "serial_number",
    "gtin",
    "manufacturer_id",
    "unique_device_id",
    "device_uid",
    "power_factor",
    "max_level",
    "min_level",
    "physical_min_level",
    "last_diagnostic_code",
    "diag_code",
    "scene_active",
    "scene_0_7",
    "scene_8_15",
    "group_0_7",
    "group_8_15",
    "group_command",
    "groups_0_7",
    "groups_8_15",
    "gear_hours",
}

SYNTHETIC_ALARM_PATTERNS = [
    "synthetic alarm",
    "desigo feed validation",
]


def _is_synthetic_alarm(message_text: str) -> bool:
    if not message_text:
        return False
    text_lower = message_text.lower()
    return any(pattern in text_lower for pattern in SYNTHETIC_ALARM_PATTERNS)


def _bridge_marks_synthetic_alarm(alarm: dict[str, Any]) -> bool | None:
    for key in ("is_synthetic", "synthetic_alarm"):
        value = alarm.get(key)
        if isinstance(value, bool):
            return value
    return None


def _normalize_bridge_equipment_status(status: str | None) -> str:
    normalized = (status or "offline").lower()
    if normalized in ("online", "normal", "ok", "running"):
        return "normal"
    if normalized in ("needs_attention", "warning", "degraded"):
        return "needs_attention"
    if normalized in ("offline", "maintenance", "critical", "unknown"):
        return normalized
    return "unknown"


def _bridge_zone_alias(zone_id: str) -> str | None:
    """Return bridge numeric alias for canonical zone IDs.

    Supabase owns the canonical zone model. Some bridge telemetry still reports
    simple numeric IDs like Zone-101 for Zone-L1-1; allow only aliases derived
    from Supabase-owned zones.
    """
    match = re.match(r"^Zone-L(\d+)-(\d+)$", str(zone_id or "").strip(), re.IGNORECASE)
    if not match:
        return None
    level = int(match.group(1))
    zone_number = int(match.group(2))
    if zone_number <= 0:
        return None
    return f"Zone-{level}{zone_number:02d}"


def _bridge_zone_id_from_equipment_code(site_prefix: str, equipment_code: str) -> str | None:
    """Return numeric bridge zone ID for zone-scoped terminal equipment."""
    pattern = rf"^{re.escape(site_prefix)}-(FCU|VAV|DALI|LTG|LUM)-(\d{{3}})$"
    match = re.match(pattern, str(equipment_code or "").strip().upper())
    if not match:
        return None
    return f"Zone-{match.group(2)}"


def _normalize_dali_parameter_name(raw: str) -> str:
    name = raw.strip()
    name = re.sub(r"(?<=[a-z])(?=[A-Z])", "_", name)
    name = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", name)
    name = name.lower().replace(" ", "_")
    for prefix in ("a_", "b_", "c_", "d_", "e_", "n_", "s_", "w_"):
        if name.startswith(prefix):
            stripped = name[len(prefix) :]
            if stripped:
                return stripped
    return name


def _is_dali_lighting_mapping(mapping: dict[str, Any]) -> bool:
    equipment_id = str(mapping.get("extracted_asset_id") or "")
    parameter_name = _normalize_dali_parameter_name(str(mapping.get("parameter_name") or ""))
    return "-DALI-" in equipment_id and parameter_name in DALI_LIGHTING_READING_NAMES


def _lighting_energy_payload_from_state(
    *,
    site_id: str,
    equipment_id: str,
    zone_id: str | None,
    readings: dict[str, Any],
    observed_at: datetime,
) -> dict[str, Any] | None:
    """Build a lighting_energy row from a DALI zone state.

    DALI bridge telemetry is zone-level, not individual-luminaire telemetry, so
    active_luminaires is left null unless the bridge later provides a real count.
    """
    if not zone_id or not str(zone_id).startswith("Zone-"):
        return None

    total_watts = _safe_float(readings.get("power_watts"))
    avg_dim_level = _safe_float(readings.get("brightness"))
    if total_watts is None and avg_dim_level is None:
        return None

    return {
        "time": observed_at.isoformat(),
        "controller_id": equipment_id,
        "zone_id": zone_id,
        "total_watts": total_watts,
        "active_luminaires": None,
        "avg_dim_level": avg_dim_level,
        "site_id": site_id,
    }


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        return float(value)
    except (TypeError, ValueError):
        return None


def _zone_suffix_from_bridge_zone_id(zone_id: str) -> str | None:
    numeric = re.match(r"^Zone-(\d{3})$", str(zone_id or "").strip(), re.IGNORECASE)
    if numeric:
        return numeric.group(1)

    level_alias = re.match(r"^Zone-L(\d+)-(\d+)$", str(zone_id or "").strip(), re.IGNORECASE)
    if level_alias:
        floor = int(level_alias.group(1))
        seq = int(level_alias.group(2))
        return f"{floor * 100 + seq:03d}"

    return None


def _zone_sensor_state_from_bridge_zone(
    *,
    site_prefix: str,
    zone_id: str,
    zone: dict[str, Any],
    occupancy_pct: float | None,
) -> tuple[str, dict[str, Any]] | None:
    zone_suffix = _zone_suffix_from_bridge_zone_id(zone_id)
    if not zone_suffix:
        return None

    readings: dict[str, float] = {}
    if (temp := _safe_float(zone.get("temperature_c"))) is not None:
        readings["room_temp_c"] = temp
    if (co2 := _safe_float(zone.get("co2_ppm"))) is not None:
        readings["co2_ppm"] = co2
    if occupancy_pct is not None:
        readings["occupancy"] = float(occupancy_pct)

    if not readings:
        return None

    return (
        f"{site_prefix}-ZONE-{zone_suffix}",
        {
            "type": "zone_sensor",
            "sensor_readings": readings,
        },
    )


def _site_aggregate_occupancy_summary(zone_occupancy_samples: list[float]) -> tuple[int, float]:
    """Summarize per-zone occupancy samples for the site aggregate row."""
    occupied_zones = sum(1 for pct in zone_occupancy_samples if pct > 0.0)
    peak_zone_density = max(zone_occupancy_samples) if zone_occupancy_samples else 0.0
    return occupied_zones, peak_zone_density


class ShadowModePollingService:
    """Polls the site bridge and feeds live data to the ML pipeline."""

    def __init__(
        self,
        site_id: str = "site-002",
        bridge_url: str | None = None,
        bridge_token: str | None = None,
    ):
        self.site_id = site_id
        # Derive equipment code prefix from site_id: "site-002" → "S002"
        self._site_prefix = site_id.replace("site-", "S").upper()
        self._override_bridge_url = bridge_url
        self._override_bridge_token = bridge_token
        self._poll_count = 0
        self._last_poll_result: dict[str, Any] | None = None  # Cached result of last poll
        # Rolling window of recent total_kw readings for anomaly detection (last 12 = ~1h at 5min cycles)
        self._total_kw_history: collections.deque[float] = collections.deque(maxlen=12)
        self._last_anomaly_alert_at: datetime | None = None  # Throttle: one alert per hour max
        # Cached BACnet object catalog: maps object_id → metadata
        # Loaded once on first poll, refreshed weekly.
        self._object_catalog: dict[str, dict[str, Any]] = {}
        self._catalog_loaded_at: datetime | None = None
        # Zone number → AHU equipment code mapping built from catalog
        self._zone_to_ahu: dict[str, str] = {}
        # Sensor codes for trends polling (built from catalog)
        self._trends_sensor_codes: list[str] = []
        # Supabase is the source of truth for building zones. Bridge zone
        # telemetry is accepted only when it maps to one of these IDs.
        self._valid_bridge_zone_ids: set[str] = set()
        # Energy accumulation state (kWh, accumulated since last DB write)
        self._energy_accumulator: dict[str, float] = {
            "hvac_kwh": 0.0,
            "lighting_kwh": 0.0,
            "other_kwh": 0.0,
            "total_kwh": 0.0,
        }
        self._energy_accum_start: datetime | None = None  # Start of current accumulation period
        self._energy_last_poll: datetime | None = None  # Last poll timestamp for kWh calc
        # Phase 1a: FCU state tracker for waste opportunity detection
        from app.services.fcu_state_tracker import FCUStateTracker
        from app.services.fcu_state_tracker_backend import SupabaseBackend

        # Build zone_type_resolver from Supabase inventory (static, cached)
        zone_type_map = self._build_zone_type_map()
        self._valid_bridge_zone_ids = set(zone_type_map)
        self.fcu_state_tracker = FCUStateTracker(
            zone_type_resolver=lambda zid: zone_type_map.get(zid, ""),
            backend=SupabaseBackend(site_id=site_id),
        )

    def _build_zone_type_map(self) -> dict[str, str]:
        """Load zone_id → zone_type mapping from Supabase zones table.

        Zone types are static configuration — fetched once, cached for session.
        Supabase is the source of truth; JSON files and bridge-provided zone
        IDs must not create zones.
        """
        try:
            from app.config.settings import settings
            from supabase import create_client

            if not getattr(settings, "supabase_url", None):
                return {}
            client = create_client(settings.supabase_url, settings.supabase_service_role_key)
            # Get site UUID
            site_row = client.table("sites").select("id").eq("code", self.site_id).execute()
            if not site_row.data:
                return {}
            site_uuid = site_row.data[0]["id"]
            zone_type_map: dict[str, str] = {}

            def add_zone(zone_id: str | None, zone_type: str = "open_office") -> None:
                cleaned = str(zone_id or "").strip()
                if not cleaned:
                    return
                zone_type_map.setdefault(cleaned, zone_type)
                alias = _bridge_zone_alias(cleaned)
                if alias:
                    zone_type_map.setdefault(alias, zone_type)

            zones_rows = client.table("zones").select("zone_id, zone_type").eq("site_id", site_uuid).execute()
            for row in zones_rows.data or []:
                add_zone(row.get("zone_id"), str(row.get("zone_type") or "open_office"))

            hvac_rows = client.table("hvac_zones").select("zone_id").eq("site_id", site_uuid).execute()
            for row in hvac_rows.data or []:
                add_zone(row.get("zone_id"))

            logger.info("[SHADOW] Loaded %d Supabase-authorized zone IDs for %s", len(zone_type_map), self.site_id)
            return zone_type_map
        except Exception as exc:
            logger.warning(f"[SHADOW] Could not load zone types from Supabase: {exc}")
            return {}

    def _get_bridge_credentials(self) -> tuple[str, str]:
        """Return (base_url, api_token).

        Uses per-instance overrides first, then the enabled per-site bridge
        adapter config in Supabase, then legacy settings env vars.
        """
        if self._override_bridge_url and self._override_bridge_token:
            return self._override_bridge_url.rstrip("/"), self._override_bridge_token

        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            result = (
                client.table("site_adapter_config")
                .select("connection_config")
                .eq("site_id", self.site_id)
                .eq("protocol", "bridge")
                .eq("enabled", True)
                .limit(1)
                .execute()
            )
            if result.data:
                config = result.data[0].get("connection_config") or {}
                base = config.get("base_url")
                token = resolve_site_bridge_token(self.site_id, config)
                if base and token:
                    return str(base).rstrip("/"), str(token)
        except Exception as exc:
            logger.debug("[SHADOW] Site bridge config lookup failed for %s: %s", self.site_id, exc)

        from app.config.settings import settings

        base = getattr(settings, "simbiot_api_url", None) or getattr(settings, "bridge_base_url", None)
        if not base:
            raise RuntimeError("Bridge URL not configured — set SIMBIOT_API_URL or BRIDGE_BASE_URL")
        token = getattr(settings, "simbiot_api_key", None) or getattr(settings, "bridge_api_token", None)
        if not token:
            raise RuntimeError("Bridge API token not configured — set SIMBIOT_API_KEY or BRIDGE_API_TOKEN")
        return base.rstrip("/"), token

    @staticmethod
    def _extract_bridge_point_value(data: dict[str, Any]) -> Any | None:
        """Return a numeric point value from supported bridge payload shapes."""
        for key in ("value", "present_value", "presentValue", "point_value"):
            if data.get(key) is not None:
                return data.get(key)
        return None

    @staticmethod
    def _extract_bridge_sample_value(sample: dict[str, Any]) -> Any | None:
        """Return a trend sample value from supported bridge payload shapes."""
        for key in ("value", "present_value", "presentValue", "point_value"):
            if sample.get(key) is not None:
                return sample.get(key)
        return None

    def _fetch_point_asset_mapping_pages(self, client: Any, site_uuid: str, *, page_size: int = 1000) -> list[dict]:
        """Fetch mapping rows using explicit pages to avoid PostgREST's 1000-row cap."""
        rows: list[dict] = []
        start = 0
        while True:
            result = (
                client.table("point_asset_mappings")
                .select("bms_point_id, extracted_asset_id, parameter_name, parameter_type, mapping_source, is_verified")
                .eq("site_id", site_uuid)
                .order("bms_point_id")
                .range(start, start + page_size - 1)
                .execute()
            )
            batch = result.data or []
            rows.extend(batch)
            if len(batch) < page_size:
                break
            start += page_size
        return rows

    def _equipment_zone_inventory_blocker(self, equipment_code: str) -> tuple[str, str] | None:
        """Return (zone_id, reason) when bridge terminal equipment is outside Supabase inventory."""
        if is_site_002_out_of_scope_l3(self.site_id, equipment_code):
            return None
        zone_id = _bridge_zone_id_from_equipment_code(self._site_prefix, equipment_code)
        if not zone_id:
            return None
        if zone_id in self._valid_bridge_zone_ids:
            return None
        return zone_id, "derived_zone_not_in_supabase_inventory"

    def _equipment_code_allowed_by_supabase_zone_inventory(self, equipment_code: str) -> bool:
        """Allow bridge terminal equipment only when its zone exists in Supabase."""
        blocker = self._equipment_zone_inventory_blocker(equipment_code)
        if not blocker:
            return True
        zone_id, _reason = blocker
        logger.warning(
            "[SHADOW] Ignoring bridge equipment %s for %s: derived zone %s is not in Supabase zone inventory",
            equipment_code,
            self.site_id,
            zone_id,
        )
        return False

    def _record_discovered_bridge_equipment(
        self,
        bridge_code: str,
        canonical_code: str,
        bridge_status_data: dict[str, Any] | None = None,
        *,
        reason: str = "new_bridge_equipment",
        derived_zone_id: str | None = None,
    ) -> None:
        """Record bridge equipment that must be reviewed before onboarding.

        Supabase remains the source of truth. This only creates or refreshes a
        pending discovery row; it never creates zones or active equipment.
        """
        try:
            if is_site_002_out_of_scope_l3(self.site_id, canonical_code) or is_site_002_out_of_scope_l3(
                self.site_id,
                bridge_code,
            ):
                logger.warning(
                    "[SHADOW] Ignoring bridge equipment %s/%s for %s: Site 002 L3 is outside tenant scope",
                    bridge_code,
                    canonical_code,
                    self.site_id,
                )
                return

            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            eq_type, _ = self._parse_equipment_code(canonical_code)
            payload = bridge_status_data or {}
            now_iso = datetime.now(tz=UTC).isoformat()
            existing = (
                client.table("bridge_discovered_equipment")
                .select("id, seen_count, status")
                .eq("site_id", self.site_id)
                .eq("canonical_code", canonical_code)
                .limit(1)
                .execute()
            )
            update_payload = {
                "bridge_code": bridge_code,
                "equipment_type": eq_type,
                "derived_zone_id": derived_zone_id,
                "reason": reason,
                "payload": payload,
                "last_seen_at": now_iso,
                "updated_at": now_iso,
            }
            if existing.data:
                row = existing.data[0]
                update_payload["seen_count"] = int(row.get("seen_count") or 0) + 1
                client.table("bridge_discovered_equipment").update(update_payload).eq("id", row["id"]).execute()
                return

            client.table("bridge_discovered_equipment").insert(
                {
                    "site_id": self.site_id,
                    "bridge_code": bridge_code,
                    "canonical_code": canonical_code,
                    "equipment_type": eq_type,
                    "derived_zone_id": derived_zone_id,
                    "status": "pending",
                    "reason": reason,
                    "payload": payload,
                    "first_seen_at": now_iso,
                    "last_seen_at": now_iso,
                    "seen_count": 1,
                }
            ).execute()
        except Exception as exc:
            logger.warning(
                "[SHADOW] Failed to record discovered bridge equipment %s for %s: %s",
                canonical_code,
                self.site_id,
                exc,
            )

    async def _load_object_catalog(self, base: str, headers: dict[str, str]) -> None:
        """Load and cache the BACnet object catalog. Called once on first poll."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{base}/api/sites/{self.site_id}/objects",
                    headers=headers,
                    params={"limit": 500},
                )
                resp.raise_for_status()
                data = resp.json()

            objs = data.get("objects", [])
            self._object_catalog = {o["object_id"]: o for o in objs}
            self._catalog_loaded_at = datetime.now(tz=UTC)

            # Build zone → AHU mapping from catalog
            # e.g. zone "Zone-001" (floor B1) → AHU "S002-AHU-B1-001"
            self._zone_to_ahu = {}
            for obj in objs:
                equip_id = obj.get("equipment_id", "")
                equip_type = obj.get("equipment_type", "")
                # Find zone from AHU equipment IDs
                # e.g. "S002-AHU-B1-001" → floor "B1", zone "001"
                if equip_type == "ahu":
                    # Parse "S002-AHU-B1-001" → (site, type, floor, seq)
                    parts = equip_id.split("-")
                    if len(parts) >= 4:
                        _, _typ, floor, seq = parts[0], parts[1], parts[2], parts[3]
                        zone_num = seq
                        zone_id = f"Zone-{zone_num}"
                        if zone_id not in self._zone_to_ahu:
                            self._zone_to_ahu[zone_id] = equip_id

            # Build trends sensor code list — ALL sensors from the catalog.
            # LSTM/autoencoder train on whatever is available; more sensors = better
            # coverage. The poll loop batches to 20 per cycle to stay within time
            # budget, so we don't need to filter here — queue everything.
            sensor_codes: set[str] = set()
            setpoint_codes: set[str] = set()
            SENSOR_POINT_TYPES = {"sensor", "analog_input", "binary_input"}
            SETPOINT_POINT_TYPES = {"setpoint", "analog_value", "analog_output", "command"}
            for obj in objs:
                point_type = obj.get("point_type", "")
                obj_id = obj.get("object_id", "")

                if point_type in SENSOR_POINT_TYPES and obj_id:
                    # Convert "CH-1.ChwSupplyTemp" → "CH-1-ChwSupplyTemp" for bridge API
                    sensor_codes.add(obj_id.replace(".", "-"))

                if point_type in SETPOINT_POINT_TYPES and obj_id:
                    # Collect setpoint object IDs for separate polling pass
                    setpoint_codes.add(obj_id.replace(".", "-"))

            # Add explicit zone temp trends only for Supabase-authorized bridge
            # zone IDs. Do not create synthetic Zone-001..020 assumptions.
            for zone_id in sorted(self._valid_bridge_zone_ids):
                if re.match(r"^Zone-\d{3}$", zone_id):
                    sensor_codes.add(f"{zone_id}-temp")

            # Build floor→AHU map from AHU equipment IDs in catalog
            floor_to_ahu: dict[str, str] = {}
            for obj in objs:
                if obj.get("equipment_type") == "ahu":
                    equip_id = obj.get("equipment_id", "")
                    # "S002-AHU-B1-001" → floor "B1"
                    parts = equip_id.split("-")
                    if len(parts) >= 3:
                        floor = parts[2]  # "B1", "L1", "L2", "L3"
                        if floor not in floor_to_ahu:
                            floor_to_ahu[floor] = equip_id

            # Add AHU trends for each known floor
            for _floor, ahu_id in floor_to_ahu.items():
                sensor_codes.add(f"{ahu_id}-supply_air_temp")
                sensor_codes.add(f"{ahu_id}-fan_speed_pct")

            self._trends_sensor_codes = sorted(sensor_codes)
            self._setpoint_codes = sorted(setpoint_codes)
            logger.info(
                f"[SHADOW] Object catalog loaded: {len(objs)} objects, "
                f"{len(self._object_catalog)} indexed, {len(self._zone_to_ahu)} zone→AHU mappings, "
                f"{len(self._trends_sensor_codes)} trend sensors, {len(self._setpoint_codes)} setpoint points"
            )

        except Exception as e:
            logger.warning(f"[SHADOW] Failed to load object catalog: {e}")

    def _normalize_to_db_code(self, code: str) -> str:
        """Normalize a bridge equipment code to the SENTINEL DB format.

        Tier 1 (occupied zone): {site}-{type}-{3digit} e.g. S002-FCU-101
        Tier 2 (plant room):    {site}-{type}-{location}-{seq} e.g. S002-CHILLER-B1-001
        Bridge codes in B{n}-{seq} format are already canonical — no transformation.
        """
        c = code.replace("_", "-")
        prefix = f"{self._site_prefix}-"
        if c.startswith(prefix):
            c = c[len(prefix) :]
        if self._site_prefix == "S002":
            legacy_aliases = {
                "AHU-001": "AHU-B1-001",
                "AHU-002": "AHU-202",
                "AHU-003": "AHU-R-001",
            }
            if c in legacy_aliases:
                return f"{prefix}{legacy_aliases[c]}"
        m = re.match(r"^(.+)-L(\d)-(\d+)$", c)
        if m:
            floor = int(m.group(2))
            seq = int(m.group(3))
            return f"{prefix}{m.group(1)}-{floor * 100 + seq:03d}"
        m = re.match(r"^(.+)-L(\d)-([A-Z])$", c)
        if m:
            floor = int(m.group(2))
            zone_num = ord(m.group(3)) - ord("A") + 1
            if 1 <= zone_num <= 5:
                return f"{prefix}{m.group(1)}-{floor * 100 + zone_num:03d}"
        return code

    async def poll(self) -> dict[str, Any]:
        """Poll bridge and feed data to ML pipeline. Call this on each poll cycle."""
        self._poll_count += 1
        now = datetime.now(tz=UTC)
        result: dict[str, Any] = {"poll_count": self._poll_count, "errors": []}

        try:
            base, token = self._get_bridge_credentials()
        except Exception as e:
            logger.error(f"[SHADOW] Bridge credentials error: {e}")
            result["errors"].append(str(e))
            return result

        headers = {"Authorization": f"Bearer {token}"}

        # ── 4a. Fetch fault alarms — always, regardless of telemetry sampling ──
        # BACnet alarms are a persistent queue: the bridge returns the same alarm
        # on every poll until it clears. Alarm polling must never be sampled or
        # filtered by age — every poll is a complete snapshot of active alarms.
        fault_count = await self._poll_alarms(base, headers)
        result["faults_polled"] = fault_count

        # ── Ingestion quality gate — tied to onboarding phase ─────────────────
        # Raw bridge telemetry must poll every cycle for data-freshness SLOs.
        # Sampling belongs downstream in model/baseline consumers, not here;
        # otherwise enabled sites can look stale simply because the poller
        # intentionally skipped source telemetry.
        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            phase_rows = client.table("sites").select("onboarding_phase").eq("code", self.site_id).limit(1).execute()
            phase = (phase_rows.data[0]["onboarding_phase"] if phase_rows.data else "commissioning") or "commissioning"
            result["gate"] = phase
        except Exception:
            pass
        # ────────────────────────────────────────────────────────────────────────

        # ── 1. Load object catalog on first poll ──────────────────────────────
        if not self._object_catalog:
            await self._load_object_catalog(base, headers)

        errors: list[str] = []

        async def _fetch_with_retry(path: str) -> dict | None:
            for attempt in range(2):
                try:
                    transport = httpx.AsyncHTTPTransport(
                        limits=httpx.Limits(max_connections=1, max_keepalive_connections=0)
                    )
                    async with httpx.AsyncClient(timeout=5.0, transport=transport) as client:
                        resp = await client.get(f"{base}{path}", headers=headers)
                        resp.raise_for_status()
                        return resp.json()
                except httpx.ConnectError:
                    logger.warning(f"[SHADOW] {path} attempt {attempt + 1}: ConnectError — retrying")
                    await asyncio.sleep(1.0)
                    continue
                except Exception as e:
                    if attempt == 0:
                        logger.warning(f"[SHADOW] {path} attempt {attempt + 1}: {e!r} — retrying")
                        await asyncio.sleep(1.0)
                        continue
                    return None

        # ── 2. Fetch zone readings ────────────────────────────────────────────
        zone_states: dict[str, dict[str, Any]] = {}
        try:
            # Get site-level fused occupancy verdict once for this poll cycle
            fused_site_verdict = None
            try:
                from app.services.occupancy_fusion_service import get_occupancy_fusion_service

                fused_site_verdict = await get_occupancy_fusion_service().get_fused_occupancy(
                    self.site_id, force_refresh=False
                )
            except Exception as e:
                logger.debug("[SHADOW] Occupancy fusion unavailable for %s: %s", self.site_id, e)

            data = await _fetch_with_retry(f"/api/sites/{self.site_id}/zones")
            if data is None:
                raise httpx.ConnectError("retry exhausted")

            zones = data.get("zones", [])
            logger.debug(f"[SHADOW] Got {len(zones)} zone readings")

            # Pre-fetch DALI zone occupancy for all zones (in-memory, fast)
            dali_occupancy_by_zone: dict[str, float] = {}
            zone_occupancy_samples: list[float] = []
            try:
                from app.services.lighting_service import get_lighting_service

                ls = get_lighting_service()
                for z in zones:
                    zid = z.get("zone_id", "")
                    if zid:
                        occ = ls.get_zone_occupancy(zid)
                        if occ is not None:
                            dali_occupancy_by_zone[zid] = occ.occupancy_percent
            except Exception:
                pass

            # The bridge /zones payload carries no cooling_setpoint or fan/valve
            # state, so read each FCU's telemetry back from equipment
            # operating_data (kept fresh every cycle by the sentinel sync).
            # Without this the FCU state tracker can never infer running state.
            fcu_telemetry_by_equip = self._load_fcu_telemetry()

            for z in zones:
                zone_id: str = z.get("zone_id", "")
                if zone_id not in self._valid_bridge_zone_ids:
                    logger.warning(
                        "[SHADOW] Ignoring bridge zone %s for %s: not in Supabase zone inventory", zone_id, self.site_id
                    )
                    continue
                zone_num = _zone_suffix_from_bridge_zone_id(zone_id)
                if not zone_num:
                    continue
                equip_code = f"{self._site_prefix}-FCU-{zone_num}"

                temp = z.get("temperature_c")
                co2 = z.get("co2_ppm")

                readings: dict[str, float] = {}
                if temp is not None:
                    readings["room_temp"] = float(temp)
                if co2 is not None:
                    readings["co2_ppm"] = float(co2)

                if readings:
                    zone_states[equip_code] = {
                        "type": "fcu",
                        "sensor_readings": readings,
                    }

                # Determine zone occupancy: use DALI PIR (in-memory) if available,
                # otherwise fall back to fused site-level verdict, then schedule.
                direct_occ_pct = dali_occupancy_by_zone.get(zone_id)
                # Only DIRECT per-zone measurements may feed the site aggregate
                # (occupied_zones on S002-SITE-AGG). The fused verdict is itself
                # derived from that aggregate — counting fanned-out fused values
                # here closes a feedback loop that latched "all 15 zones
                # occupied" through closed overnight hours (Finding 2,
                # 2026-07-04 pipeline verification).
                if direct_occ_pct is not None:
                    zone_occupancy_samples.append(float(direct_occ_pct))
                zone_occ_pct = direct_occ_pct
                if zone_occ_pct is None and fused_site_verdict is not None:
                    zone_occ_pct = fused_site_verdict.occupancy_percent

                # Same rule for the S002-ZONE-* sensor write path: the lighting
                # service counts every persisted "occupancy" reading > 0 as an
                # occupied PIR sensor, which feeds the fusion's lighting_pir
                # signal. Writing the fused fan-out here re-created the Finding 2
                # feedback loop one layer down (fused floored at ~32.6% through a
                # closed Sunday night while every real PIR/badge/water signal
                # read 0). Only direct measurements may be persisted as readings.
                zone_sensor_state = _zone_sensor_state_from_bridge_zone(
                    site_prefix=self._site_prefix,
                    zone_id=zone_id,
                    zone=z,
                    occupancy_pct=direct_occ_pct,
                )
                if zone_sensor_state:
                    zone_sensor_code, state = zone_sensor_state
                    zone_states[zone_sensor_code] = state

                # Phase 1a: feed zone poll to FCU state tracker
                fcu_telemetry = fcu_telemetry_by_equip.get(equip_code, {})
                setpoint_c = z.get("cooling_setpoint")
                if setpoint_c is None:
                    setpoint_c = fcu_telemetry.get("setpoint")
                # Direct running measurement: fan stage > 0 means the FCU is
                # consuming energy; valve position is the fallback signal when
                # fan_speed is absent. Beats the temp-delta heuristic, which
                # rides ±2°C inter-poll sensor noise.
                fan_speed = fcu_telemetry.get("fan_speed")
                valve_pct = fcu_telemetry.get("valve_position")
                if fan_speed is not None:
                    fcu_running = fan_speed > 0.0
                elif valve_pct is not None:
                    fcu_running = valve_pct > 5.0
                else:
                    fcu_running = None
                self.fcu_state_tracker.record_poll(
                    zone_id=zone_id,
                    occupancy_pct=zone_occ_pct if zone_occ_pct is not None else 0.0,
                    room_temp_c=z.get("temperature_c"),
                    setpoint_c=setpoint_c,
                    timestamp=now,
                    fcu_running=fcu_running,
                )

            result["zones_polled"] = len(zone_states)

        except httpx.HTTPStatusError as e:
            logger.warning(f"[SHADOW] Zone poll HTTP {e.response.status_code}: {e.response.text[:200]}")
            errors.append(f"zones: HTTP {e.response.status_code}")
        except Exception as e:
            logger.warning(f"[SHADOW] Zone poll error: {e}")
            errors.append(f"zones: {e}")

        # Stagger requests to avoid bridge connection pool exhaustion
        await asyncio.sleep(1.5)

        # ── 3. Fetch aggregated telemetry ────────────────────────────────────
        agg_states: dict[str, dict[str, Any]] = {}
        try:
            data = await _fetch_with_retry(f"/api/sites/{self.site_id}/telemetry")
            if data is None:
                raise httpx.ConnectError("retry exhausted")

            power = data.get("power", {})
            water = data.get("water", {})
            equip_summary = data.get("equipment_summary", {})

            hvac_kw = power.get("hvac_kw")
            lighting_kw = power.get("lighting_kw")
            total_kw = power.get("total_kw")
            flow_lpm = water.get("flow_lpm")
            pressure_bar = water.get("pressure_bar")

            agg_readings: dict[str, float] = {}
            if hvac_kw is not None:
                agg_readings["hvac_kw"] = float(hvac_kw)
            if lighting_kw is not None:
                agg_readings["lighting_kw"] = float(lighting_kw)
            if total_kw is not None:
                total_kw_float = float(total_kw)
                agg_readings["total_kw"] = total_kw_float
                self._check_power_anomaly(total_kw_float, now)
            # Accumulate energy from power readings (kW → kWh)
            if hvac_kw is not None and lighting_kw is not None and total_kw is not None:
                self._accumulate_energy(float(hvac_kw), float(lighting_kw), float(total_kw), now)
            if flow_lpm is not None:
                agg_readings["flow_lpm"] = float(flow_lpm)
            if pressure_bar is not None:
                agg_readings["pressure_bar"] = float(pressure_bar)

            if agg_readings:
                agg_states[f"{self._site_prefix}-CHILLER-AGG"] = {
                    "type": "site_aggregate",
                    "sensor_readings": agg_readings,
                }

            # ── Map water telemetry to water meter equipment ─────────────────
            total_m3 = water.get("total_m3")
            water_readings: dict[str, float] = {}
            if flow_lpm is not None:
                water_readings["flow_rate_lpm"] = float(flow_lpm)
            if pressure_bar is not None:
                water_readings["pressure_bar"] = float(pressure_bar)
            if total_m3 is not None:
                water_readings["total_consumption_m3"] = float(total_m3)

            if water_readings:
                agg_states[f"{self._site_prefix}-WATER-MTR-001"] = {
                    "type": "water_meter",
                    "sensor_readings": water_readings,
                }

            # ── Map chiller telemetry to individual equipment ────────────────
            chiller_data = data.get("chiller", {})
            chiller_readings: dict[str, float] = {}
            chiller_field_map = {
                "supply_temp_c": "chw_supply_temp",
                "return_temp_c": "chw_return_temp",
                "condenser_flow_ls": "condenser_flow",
                "condenser_supply_temp_c": "cond_supply_temp",
                "condenser_return_temp_c": "cond_return_temp",
                "compressor_current_1_a": "compressor_current_1",
                "compressor_current_2_a": "compressor_current_2",
                "staging_state": "staging_state",
            }
            for bridge_key, op_key in chiller_field_map.items():
                val = chiller_data.get(bridge_key)
                if val is not None:
                    chiller_readings[op_key] = float(val)
            if chiller_readings:
                agg_states[f"{self._site_prefix}-CHILLER-B1-001"] = {
                    "type": "chiller",
                    "sensor_readings": chiller_readings,
                }

            # Map cooling tower fan speed from chiller block
            ct_fan = chiller_data.get("cooling_tower_fan_speed_pct")
            if ct_fan is not None:
                agg_states[f"{self._site_prefix}-CT-R-001"] = {
                    "type": "cooling_tower",
                    "sensor_readings": {"fan_speed_pct": float(ct_fan)},
                }

            # ── Map AHU telemetry to individual equipment ────────────────────
            # Bridge telemetry ahu1/ahu2/ahu3 maps to zone-code format in Supabase.
            # Also handles list format (site-005) with unit_id per AHU.
            ahu_data = data.get("ahu", {})
            ahu_field_map = {
                "supply_air_temp_c": "supply_air_temp",
                "return_air_temp_c": "return_air_temp",
                "fan_speed": "fan_speed",
                "filter_dp_pa": "filter_dp",
                "damper_position": "damper_position",
                "run_state": "run_state",
            }
            if isinstance(ahu_data, list):
                # List format (site-005): [{unit_id, supply_air_temp_c, ...}, ...]
                floor_seq: dict[str, int] = {}
                for ahu in ahu_data:
                    unit_id: str = ahu.get("unit_id", "")
                    if not unit_id:
                        continue
                    # Extract floor from unit_id e.g. "UMH-AHU-B1-LAUN.fan" → "B1"
                    parts = unit_id.split("-")
                    floor = next((p for p in parts if re.match(r"^[BLR]\d*$", p)), "L0")
                    seq = floor_seq.get(floor, 0) + 1
                    floor_seq[floor] = seq
                    # Generate floor code matching naming convention:
                    # B1 → B01, B02 ; L2 → 201, 202 ; L3 → 301, 302 ; G → 001, 002
                    floor_match = re.match(r"^B(\d+)$", floor)
                    if floor_match:
                        floor_code = f"B{int(floor_match.group(1)):02d}{seq:01d}"
                    elif floor in ("G", "R"):
                        floor_code = f"{seq:03d}"
                    else:
                        level = int(re.sub(r"[^0-9]", "", floor) or "0")
                        floor_code = f"{level * 100 + seq:03d}"
                    equip_code = f"{self._site_prefix}-AHU-{floor_code}"
                    ahu_readings = {}
                    for bridge_key, op_key in ahu_field_map.items():
                        val = ahu.get(bridge_key)
                        if val is not None:
                            with contextlib.suppress(ValueError, TypeError):
                                ahu_readings[op_key] = float(val)
                    if ahu_readings:
                        agg_states[equip_code] = {
                            "type": "ahu",
                            "sensor_readings": ahu_readings,
                        }
            else:
                # Dict format (site-002 legacy): {"ahu1": {...aggregated readings...}}
                ahu_map = {
                    "ahu1": f"{self._site_prefix}-AHU-B1-001",
                    "ahu2": f"{self._site_prefix}-AHU-202",
                    "ahu3": f"{self._site_prefix}-AHU-R-001",
                }
                for ahu_prefix, equip_code in ahu_map.items():
                    ahu_readings = {}
                    for bridge_suffix, op_key in ahu_field_map.items():
                        key = f"{ahu_prefix}_{bridge_suffix}"
                        val = ahu_data.get(key)
                        if val is not None:
                            with contextlib.suppress(ValueError, TypeError):
                                ahu_readings[op_key] = float(val)
                    if ahu_readings:
                        agg_states[equip_code] = {
                            "type": "ahu",
                            "sensor_readings": ahu_readings,
                        }

            zone_count = data.get("zone_count", 0)
            equip_online = equip_summary.get("online", 0)
            if zone_count or equip_online:
                agg_states[f"{self._site_prefix}-SITE-AGG"] = {
                    "type": "site_aggregate",
                    "sensor_readings": {
                        "zone_count": float(zone_count),
                        "equip_online": float(equip_online),
                    },
                }

            # ── Map BESS telemetry to battery equipment ──────────────────────
            bess_data = data.get("bess", {})
            if bess_data:
                bess_readings: dict[str, float] = {}
                bess_field_map = {
                    "soc_percent": "soc_pct",
                    "charge_discharge_power_kw": "power_kw",
                    "energy_stored_kwh": "energy_kwh",
                    "battery_module_temp_max_c": "temp_max_c",
                    "battery_voltage_dc_v": "voltage_v",
                    "battery_current_dc_a": "current_a",
                    "c_rate": "c_rate",
                    "grid_frequency_hz": "grid_frequency_hz",
                    "power_factor": "power_factor",
                    "ambient_temp_c": "ambient_temp_c",
                }
                for bridge_key, op_key in bess_field_map.items():
                    val = bess_data.get(bridge_key)
                    if val is not None:
                        bess_readings[op_key] = float(val)

                system_status = bess_data.get("system_status", "")
                if system_status:
                    bess_readings["system_status"] = (
                        1.0 if system_status in ("online", "running", "charging", "discharging") else 0.0
                    )

                if bess_readings:
                    agg_states[f"{self._site_prefix}-BESS-B1-001"] = {
                        "type": "bess",
                        "sensor_readings": bess_readings,
                    }
                    logger.info(
                        "[SHADOW] BESS telemetry ingested: SOC=%.1f%%, power=%.1fkW, energy=%.1fkWh for %s",
                        bess_readings.get("soc_pct", 0),
                        bess_readings.get("power_kw", 0),
                        bess_readings.get("energy_kwh", 0),
                        f"{self._site_prefix}-BESS-B1-001",
                    )

            # ── Map security telemetry to access control system ──────────────
            security_data = data.get("security", {})
            if security_data:
                security_readings: dict[str, float] = {}
                entries = security_data.get("entries")
                denied = security_data.get("denied")
                forced_door = security_data.get("forced_door")

                if entries is not None:
                    security_readings["entry_count"] = float(entries)
                if denied is not None:
                    security_readings["access_denied_count"] = float(denied)
                if forced_door is not None:
                    security_readings["forced_door_count"] = float(forced_door)

                if security_readings:
                    agg_states[f"{self._site_prefix}-CCURE-SVR"] = {
                        "type": "access_control_server",
                        "sensor_readings": security_readings,
                    }

            result["telemetry_fetched"] = True

        except httpx.HTTPStatusError as e:
            logger.warning(f"[SHADOW] Telemetry poll HTTP {e.response.status_code}: {e.response.text[:200]}")
            errors.append(f"telemetry: HTTP {e.response.status_code}")
        except Exception as e:
            logger.warning(f"[SHADOW] Telemetry poll error: {e}")
            errors.append(f"telemetry: {e}")

        # ── 3b. Fetch occupancy from badge/visitor events ───────────────────
        # Wire occupancy into the ML feeder via S002-SITE-AGG
        try:
            from app.database.repositories.security_repository import SecurityRepository

            repo = SecurityRepository()
            occ = repo.get_occupancy(self.site_id)
            total_occ = occ.get("total_occupancy", 0)

            if f"{self._site_prefix}-SITE-AGG" in agg_states:
                occupied_zones, peak_zone_density = _site_aggregate_occupancy_summary(zone_occupancy_samples)
                agg_states[f"{self._site_prefix}-SITE-AGG"]["sensor_readings"]["total_occupancy"] = float(total_occ)
                agg_states[f"{self._site_prefix}-SITE-AGG"]["sensor_readings"]["occupied_zones"] = float(occupied_zones)
                agg_states[f"{self._site_prefix}-SITE-AGG"]["sensor_readings"]["peak_zone_density"] = float(
                    peak_zone_density
                )
            result["occupancy_fetched"] = True
        except Exception as e:
            logger.debug(f"[SHADOW] Occupancy poll skipped: {e}")
            errors.append(f"occupancy: {e}")

        # Stagger requests to avoid bridge connection pool exhaustion
        await asyncio.sleep(1.5)

        # ── 3c. Fetch BESS/Solar/Generator data from bridge objects ─────────
        # Polls the BACnet object catalog for energy equipment telemetry
        try:
            objects_data = await _fetch_with_retry(f"/api/sites/{self.site_id}/objects")
            if objects_data is None:
                raise httpx.ConnectError("retry exhausted")
            objects = objects_data.get("objects", [])

            # Group objects by equipment
            energy_equipment: dict[str, dict[str, Any]] = {}
            for obj in objects:
                eq_id = obj.get("equipment_id", "")
                # Filter for BESS, Solar, PV, Generator, Inverter equipment
                if any(x in eq_id.upper() for x in ["BESS", "PV", "SOLAR", "GEN", "INV", "INVERTER"]):
                    if eq_id not in energy_equipment:
                        energy_equipment[eq_id] = {"type": obj.get("equipment_type", "unknown"), "readings": {}}
                    point_name = obj.get("object_name", "")
                    # Map key telemetry points
                    if any(
                        x in point_name.lower()
                        for x in ["soc", "power", "voltage", "current", "temp", "energy", "status"]
                    ):
                        # Note: objects endpoint returns metadata, not live values
                        # We need to fetch the current value separately
                        pass

            # Fetch live values from /points endpoint for key energy equipment
            energy_equipment_ids = [
                eq_id for eq_id in energy_equipment if any(x in eq_id for x in ["BESS-B1-001", "PV-ARRAY", "GEN-B1"])
            ]

            for eq_id in energy_equipment_ids[:5]:  # Limit to top 5 to avoid timeout
                try:
                    points_data = await _fetch_with_retry(f"/api/sites/{self.site_id}/points?equipment_id={eq_id}")
                    points = points_data.get("points", [])

                    readings: dict[str, float] = {}
                    eq_type = "unknown"

                    for point in points:
                        point_name = point.get("name", "")
                        value = point.get("value")

                        # Map BESS telemetry
                        if "BESS" in eq_id.upper():
                            eq_type = "bess"
                            if "soc_percent" in point_name.lower():
                                readings["soc_pct"] = float(value)
                            elif "charge_discharge_power_kw" in point_name.lower():
                                readings["power_kw"] = float(value)
                            elif "energy_stored_kwh" in point_name.lower():
                                readings["energy_kwh"] = float(value)
                            elif "battery_module_temp_max_c" in point_name.lower():
                                readings["temp_max_c"] = float(value)
                            elif "battery_voltage_dc_v" in point_name.lower():
                                readings["voltage_v"] = float(value)

                        # Map Solar/PV telemetry
                        elif any(x in eq_id.upper() for x in ["PV", "SOLAR"]):
                            eq_type = "solar"
                            if "power_kw" in point_name.lower():
                                readings["power_kw"] = float(value)
                            elif "voltage_v" in point_name.lower():
                                readings["voltage_v"] = float(value)
                            elif "current_a" in point_name.lower():
                                readings["current_a"] = float(value)

                        # Map Generator telemetry
                        elif "GEN" in eq_id.upper():
                            eq_type = "generator"
                            if "status" in point_name.lower():
                                readings["status"] = float(1.0 if value in ["running", "on", "true", "1"] else 0.0)
                            elif "health_score" in point_name.lower():
                                readings["health_score"] = float(value) if value else 0.0

                    if readings:
                        agg_states[eq_id] = {
                            "type": eq_type,
                            "sensor_readings": readings,
                        }

                except Exception as e:
                    logger.debug(f"[SHADOW] Energy equipment poll failed for {eq_id}: {e}")

            # Also fetch detailed water meter points
            try:
                water_points_data = await _fetch_with_retry(
                    f"/api/sites/{self.site_id}/points?equipment_id={self._site_prefix}-WATER-MTR-001"
                )
                water_points = water_points_data.get("points", [])

                water_detailed_readings: dict[str, float] = {}
                for point in water_points:
                    point_name = point.get("name", "")
                    value = point.get("value")
                    if value is None:
                        continue

                    if "flow_rate" in point_name.lower() and "average" not in point_name.lower():
                        water_detailed_readings["flow_rate_lps"] = float(value)
                    elif "total_consumption_m3" in point_name.lower():
                        water_detailed_readings["total_m3"] = float(value)
                    elif "daily_consumption" in point_name.lower():
                        water_detailed_readings["daily_m3"] = float(value)
                    elif "monthly_consumption" in point_name.lower():
                        water_detailed_readings["monthly_kl"] = float(value)
                    elif "supply_pressure" in point_name.lower():
                        water_detailed_readings["pressure_kpa"] = float(value)
                    elif "supply_temperature" in point_name.lower():
                        water_detailed_readings["temp_c"] = float(value)
                    elif "leak_detected" in point_name.lower():
                        water_detailed_readings["leak_detected"] = float(1.0 if value in ["true", "1", True] else 0.0)

                if water_detailed_readings:
                    # Merge with existing water meter readings or create new entry
                    if f"{self._site_prefix}-WATER-MTR-001" in agg_states:
                        agg_states[f"{self._site_prefix}-WATER-MTR-001"]["sensor_readings"].update(
                            water_detailed_readings
                        )
                    else:
                        agg_states[f"{self._site_prefix}-WATER-MTR-001"] = {
                            "type": "water_meter",
                            "sensor_readings": water_detailed_readings,
                        }

            except Exception as e:
                logger.debug(f"[SHADOW] Water meter detailed poll failed: {e}")

            result["energy_equipment_fetched"] = len(
                [eq for eq in agg_states if any(x in eq for x in ["BESS", "PV", "GEN", "INV", "WATER"])]
            )

        except Exception as e:
            logger.warning(f"[SHADOW] Energy equipment poll error: {e}")
            errors.append(f"energy_equipment: {e}")

        # Section 4 moved to _poll_alarms(), called before the sampling gate above.

        # ── 5. Fetch trends for richer LSTM sequences (async batch) ───────────
        # Poll the most ML-relevant sensor trends. History accumulates in bridge;
        # once populated, these give LSTM sequences for chiller + AHU + outdoor.
        trends_states: dict[str, dict[str, Any]] = {}
        if self._trends_sensor_codes:
            # Poll up to 20 sensors per cycle to stay within time budget
            sensor_batch = self._trends_sensor_codes[:20]
            try:
                # Reuse a single client for all trend calls — prevents connection pool
                # starvation that causes downstream /points calls to timeout (issue #shadow-poll).
                async with httpx.AsyncClient(timeout=30.0) as trend_client:

                    async def fetch_trend(sensor_code: str) -> tuple[str, dict[str, Any] | None]:
                        try:
                            r = await trend_client.get(
                                f"{base}/api/sites/{self.site_id}/trends/{sensor_code}",
                                headers=headers,
                                params={"limit": 100},
                            )
                            r.raise_for_status()
                            d = r.json()
                            samples = d.get("samples", [])
                            if samples:
                                # Use most recent sample
                                latest = samples[-1]
                                return sensor_code, {
                                    "timestamp": latest.get("ts"),
                                    "value": latest.get("value"),
                                    "unit": d.get("unit"),
                                }
                            return sensor_code, None
                        except Exception:
                            return sensor_code, None

                    trend_results = await asyncio.gather(
                        *[fetch_trend(sc) for sc in sensor_batch],
                        return_exceptions=True,
                    )

                for tr in trend_results:
                    if isinstance(tr, Exception):
                        continue
                    sensor_code, sample = tr
                    if sample and sample.get("value") is not None:
                        # Map sensor_code → equipment + reading name
                        equip_code, reading_name = self._resolve_sensor(sensor_code)
                        if equip_code and reading_name:
                            if equip_code not in trends_states:
                                trends_states[equip_code] = {"type": "", "sensor_readings": {}}
                            equip_type = trends_states[equip_code]["type"]
                            if not equip_type:
                                trends_states[equip_code]["type"] = self._equip_type_from_sensor(sensor_code)
                            trends_states[equip_code]["sensor_readings"][reading_name] = float(sample["value"])

                result["trends_polled"] = len(sensor_batch)
                result["trends_with_data"] = sum(
                    1
                    for code, s in zip(sensor_batch, trend_results, strict=False)
                    if not isinstance(s, Exception) and s[1] is not None
                )

            except Exception as e:
                logger.warning(f"[SHADOW] Trends poll error: {e}")

        # ── 5b. Poll setpoint points and write to equipment operating_data ────
        # Setpoints (cooling_setpoint, supply_temp_sp, etc.) are needed by AI-OPT
        # to generate setpoint-adjustment recommendations instead of maintenance recs.
        # Each setpoint is read and written to operating_data on the equipment record.
        if getattr(self, "_setpoint_codes", None):
            sp_batch = self._setpoint_codes[:20]  # Same batch budget as trends
            try:
                from app.database.repositories.equipment_repository import EquipmentRepository

                eq_repo = EquipmentRepository()

                async def fetch_setpoint(sp_code: str) -> tuple[str, dict | None]:
                    try:
                        async with httpx.AsyncClient(timeout=10.0) as client:
                            r = await client.get(
                                f"{base}/api/sites/{self.site_id}/trends/{sp_code}",
                                headers=headers,
                                params={"limit": 1},
                            )
                            r.raise_for_status()
                            d = r.json()
                            samples = d.get("samples", [])
                            if samples:
                                return sp_code, {"value": samples[-1].get("value"), "unit": d.get("unit")}
                    except Exception:
                        pass
                    return sp_code, None

                sp_results = await asyncio.gather(
                    *[fetch_setpoint(sp) for sp in sp_batch],
                    return_exceptions=True,
                )

                sp_written = 0
                for sp_result in sp_results:
                    if isinstance(sp_result, Exception):
                        continue
                    sp_code, sample = sp_result
                    if not sample or sample.get("value") is None:
                        continue

                    equip_code, point_name = self._resolve_sensor(sp_code)
                    if not equip_code or not point_name:
                        continue

                    # Write setpoint value to equipment operating_data
                    try:
                        point_values = {
                            point_name: {
                                "value": float(sample["value"]),
                                "timestamp": datetime.now(tz=UTC).isoformat(),
                                "source": "setpoint_poll",
                            }
                        }
                        eq_repo.update_operating_data(equip_code, point_values)
                        sp_written += 1
                    except Exception as e:
                        logger.debug(f"[SHADOW] Failed to write setpoint {sp_code} → {equip_code}.{point_name}: {e}")

                if sp_written > 0:
                    logger.info(f"[SHADOW] Setpoint poll: {sp_written} written to operating_data")
                result["setpoints_polled"] = sp_written

            except Exception as e:
                logger.warning(f"[SHADOW] Setpoint poll error: {e}")

        # ── 5c. Poll verified SIMBIOT meter mappings ────────────────────────
        # Meters are static assets, but their verified BACnet points still need
        # to be sampled into equipment_sensor_readings for carbon/utility use.
        simbiot_meter_states = await self._poll_verified_meter_mappings(base, headers)
        result["simbiot_meter_points"] = sum(
            len(state.get("sensor_readings", {})) for state in simbiot_meter_states.values()
        )

        # ── 5d. Poll mapped bridge object points ─────────────────────────────
        # /points lists equipment online/offline state; mapped point IDs hold
        # the actual telemetry for VAVs, pumps, cooling towers, and AHUs.
        mapped_point_states = await self._poll_mapped_bridge_points(base, headers)
        result["mapped_bridge_points"] = sum(
            len(state.get("sensor_readings", {})) for state in mapped_point_states.values()
        )
        result["lighting_energy_rows"] = await self._write_lighting_energy_from_states(mapped_point_states)

        # ── 6. Sync equipment online/offline status from /points ─────────────
        points_result = await self._sync_equipment_status(base, headers)
        result["equipment_updated"] = points_result["updated"]
        result["equipment_created"] = points_result.get("created", 0)
        result["equipment_missing_from_bridge"] = points_result["missing_from_bridge"]

        # ── 7. Merge all states ───────────────────────────────────────────────
        # Trends states have higher fidelity (chiller supply temp from BACnet
        # vs aggregated HVAC_kW from /telemetry), so they take priority over
        # the aggregated entries for the same equipment code.
        equipment_states: dict[str, dict[str, Any]] = {**agg_states, **zone_states}
        for code, state in trends_states.items():
            if state["sensor_readings"]:
                equipment_states[code] = state
        # Merge DALI controller and power meter states from /points endpoint
        # (extracted in _sync_equipment_status and returned via points_result)
        for code, state in points_result.get("vav_states", {}).items():
            equipment_states[code] = state
        for code, state in points_result.get("dali_states", {}).items():
            equipment_states[code] = state
        for code, state in points_result.get("meter_states", {}).items():
            equipment_states[code] = state
        for code, state in mapped_point_states.items():
            if code in equipment_states:
                equipment_states[code].setdefault("sensor_readings", {}).update(state.get("sensor_readings", {}))
                if not equipment_states[code].get("type") and state.get("type"):
                    equipment_states[code]["type"] = state.get("type")
            else:
                equipment_states[code] = state

        # Normalize equipment codes: bridge codes to DB canonical form.
        # Tier 2 plant room codes (B{n}-{seq}) are already canonical — no-op.
        normalized = {}
        for code, state in equipment_states.items():
            db_code = self._normalize_to_db_code(code)
            if db_code != code:
                logger.debug("[SHADOW] Normalized equipment code: %s → %s", code, db_code)
            if is_site_002_out_of_scope_l3(self.site_id, db_code) or is_site_002_out_of_scope_l3(self.site_id, code):
                logger.warning(
                    "[SHADOW] Ignoring bridge equipment %s/%s for %s: Site 002 L3 is outside tenant scope",
                    code,
                    db_code,
                    self.site_id,
                )
                continue
            blocker = self._equipment_zone_inventory_blocker(db_code)
            if blocker:
                zone_id, reason = blocker
                logger.warning(
                    "[SHADOW] Ignoring bridge equipment %s for %s: derived zone %s is not in Supabase zone inventory",
                    db_code,
                    self.site_id,
                    zone_id,
                )
                self._record_discovered_bridge_equipment(
                    bridge_code=code,
                    canonical_code=db_code,
                    bridge_status_data=state,
                    reason=reason,
                    derived_zone_id=zone_id,
                )
                continue
            normalized[db_code] = state
        equipment_states = normalized

        # SIMBIOT mappings are already canonical equipment IDs. Merge after raw
        # bridge-code normalization so sub-meters like S002-MTR-B1-001 are not
        # collapsed to the main basement meter.
        for code, state in simbiot_meter_states.items():
            if code in equipment_states:
                equipment_states[code].setdefault("sensor_readings", {}).update(state.get("sensor_readings", {}))
            else:
                equipment_states[code] = state

        if not equipment_states:
            logger.warning(f"[SHADOW] Poll {self._poll_count}: no data — errors={errors}")
            result["errors"] = errors
            return result

        # ── 7. Feed SentinelDataSync (Supabase + ML pipeline) ─────────────────
        try:
            from app.services.sentinel_data_sync import get_sentinel_data_sync

            sync = get_sentinel_data_sync(site_id=self.site_id)
            await sync.ingest_equipment_states(equipment_states, now, data_source="bridge_poll")
            result["equipment_states"] = len(equipment_states)
            result["ml_hours_ingested"] = sync.ml_feeder.hours_ingested
            result["fault_buffer_size"] = sync.ml_feeder.fault_event_count
        except Exception as e:
            logger.warning(f"[SHADOW] SentinelDataSync error: {e}")
            errors.append(f"sync: {e}")

        result["errors"] = errors
        self._last_poll_result = result

        # Upsert log_sources so monitoring dashboard reflects bridge activity
        if equipment_states:
            self._upsert_log_source(len(equipment_states))

        logger.warning(
            f"[SHADOW] Poll {self._poll_count}: {len(equipment_states)} states, "
            f"zones={result.get('zones_polled', 0)}, faults={result.get('faults_polled', 0)}, "
            f"trends={result.get('trends_with_data', 0)}, "
            f"ml_hours={result.get('ml_hours_ingested', '?')}, "
            f"fault_buf={result.get('fault_buffer_size', '?')}, "
            f"equip_updated={result.get('equipment_updated', 0)}, "
            f"equip_created={result.get('equipment_created', 0)}, "
            f"errors={errors or 'none'}"
        )
        return result

    async def _poll_verified_meter_mappings(self, base: str, headers: dict[str, str]) -> dict[str, dict[str, Any]]:
        """Read verified SIMBIOT meter mappings from the bridge."""
        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            site_resp = client.table("sites").select("id").eq("code", self.site_id).limit(1).execute()
            if not site_resp.data:
                return {}
            site_uuid = site_resp.data[0]["id"]
            mappings = [
                row
                for row in self._fetch_point_asset_mapping_pages(client, site_uuid)
                if row.get("is_verified") is True
                and row.get("mapping_source") == "simbiot_manual"
                and str(row.get("parameter_type") or "").startswith("meter:")
            ]
        except Exception as exc:
            logger.debug("[SHADOW] SIMBIOT meter mapping load failed: %s", exc)
            return {}

        if not mappings:
            return {}

        async def fetch_mapping(mapping: dict[str, Any]) -> tuple[dict[str, Any], Any | None]:
            point_id = mapping.get("bms_point_id")
            if not point_id:
                return mapping, None
            async with httpx.AsyncClient(timeout=10.0) as client:
                try:
                    resp = await client.get(f"{base}/api/sites/{self.site_id}/points/{point_id}", headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    value = self._extract_bridge_point_value(data)
                    if value is not None:
                        return mapping, value
                except Exception:
                    pass

                try:
                    resp = await client.get(
                        f"{base}/api/sites/{self.site_id}/trends/{point_id}",
                        headers=headers,
                        params={"limit": 1},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    samples = data.get("samples") or []
                    value = self._extract_bridge_sample_value(samples[-1]) if samples else None
                    if value is not None:
                        return mapping, value
                except Exception:
                    pass

            return mapping, None

        results = await asyncio.gather(*(fetch_mapping(mapping) for mapping in mappings), return_exceptions=True)
        states: dict[str, dict[str, Any]] = {}
        for result in results:
            if isinstance(result, Exception):
                continue
            mapping, value = result
            if value is None:
                continue
            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                continue

            equipment_id = mapping.get("extracted_asset_id")
            parameter_name = mapping.get("parameter_name")
            if not equipment_id or not parameter_name:
                continue
            if equipment_id not in states:
                states[equipment_id] = {"type": "meter", "sensor_readings": {}}
            reading_name = "equipment_online" if parameter_name == "run_state" else parameter_name
            states[equipment_id]["sensor_readings"][reading_name] = numeric_value

        return states

    async def _poll_mapped_bridge_points(self, base: str, headers: dict[str, str]) -> dict[str, dict[str, Any]]:
        """Read mapped bridge object points into equipment sensor states."""
        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            site_resp = client.table("sites").select("id").eq("code", self.site_id).limit(1).execute()
            if not site_resp.data:
                return {}
            site_uuid = site_resp.data[0]["id"]
            mappings = [
                row
                for row in self._fetch_point_asset_mapping_pages(client, site_uuid)
                if row.get("mapping_source") in {"bridge_objects", "catalog_resolver"}
            ]
        except Exception as exc:
            logger.debug("[SHADOW] Bridge point mapping load failed: %s", exc)
            return {}

        candidate_mappings = []
        for mapping in mappings:
            equipment_id = str(mapping.get("extracted_asset_id") or "")
            point_id = str(mapping.get("bms_point_id") or "")
            parameter_name = str(mapping.get("parameter_name") or "")
            if not equipment_id or not point_id:
                continue
            if any(skip in point_id.lower() for skip in ("health_score", "updated_at")):
                continue
            if not parameter_name and not any(
                token in point_id.upper() for token in ("ROOMTEMP", "DAMPER", "RUN_STATE", "FAN_SPEED", "FILTER_DP")
            ):
                continue
            candidate_mappings.append(mapping)

        if not candidate_mappings:
            return {}

        def reading_name_for(mapping: dict[str, Any]) -> str | None:
            point_id = str(mapping.get("bms_point_id") or "")
            parameter_name = str(mapping.get("parameter_name") or "").strip()
            upper_point = point_id.upper()
            if "ROOMTEMP" in upper_point:
                return "room_temp"
            if "DAMPER" in upper_point:
                return "damper_position"
            if "RUN_STATE" in upper_point:
                return "equipment_online"
            if "FAN_SPEED" in upper_point:
                return "fan_speed"
            if "FILTER_DP" in upper_point:
                return "filter_dp"
            if "SUPPLY_AIR_TEMP" in upper_point:
                return "supply_air_temp"
            if "RETURN_AIR_TEMP" in upper_point:
                return "return_air_temp"

            if parameter_name and parameter_name not in {"unknown", "unknown_sensor"} and len(parameter_name) > 1:
                aliases = {
                    "room_temperature": "room_temp",
                    "zone_temperature": "zone_temp",
                    "fan_speed_hz": "fan_speed",
                    "fan_current": "fan_speed",
                    "outlet_water_temp_c": "outlet_water_temp",
                    "temperature_setpoint": "setpoint_temp",
                    "comp_current": "compressor_current_1",
                }
                return aliases.get(parameter_name, parameter_name)

            return None

        semaphore = asyncio.Semaphore(12)

        async def fetch_mapping(mapping: dict[str, Any]) -> tuple[dict[str, Any], Any | None]:
            point_id = mapping.get("bms_point_id")
            if not point_id:
                return mapping, None
            async with semaphore:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    try:
                        resp = await client.get(f"{base}/api/sites/{self.site_id}/points/{point_id}", headers=headers)
                        resp.raise_for_status()
                        data = resp.json()
                        value = self._extract_bridge_point_value(data)
                        if value is not None:
                            return mapping, value
                    except Exception:
                        pass

                    try:
                        resp = await client.get(
                            f"{base}/api/sites/{self.site_id}/trends/{point_id}",
                            headers=headers,
                            params={"limit": 1},
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        samples = data.get("samples") or []
                        value = self._extract_bridge_sample_value(samples[-1]) if samples else None
                        if value is not None:
                            return mapping, value
                    except Exception:
                        pass

            return mapping, None

        results = await asyncio.gather(
            *(fetch_mapping(mapping) for mapping in candidate_mappings), return_exceptions=True
        )
        states: dict[str, dict[str, Any]] = {}
        for result in results:
            if isinstance(result, Exception):
                continue
            mapping, value = result
            reading_name = reading_name_for(mapping)
            equipment_id = mapping.get("extracted_asset_id")
            if not equipment_id or not reading_name or value is None:
                continue
            try:
                if isinstance(value, bool):
                    numeric_value = 1.0 if value else 0.0
                elif isinstance(value, str) and value.lower() in {"online", "normal", "ok", "running"}:
                    numeric_value = 1.0
                elif isinstance(value, str) and value.lower() in {"offline", "fault", "failed", "stopped"}:
                    numeric_value = 0.0
                else:
                    numeric_value = float(value)
            except (TypeError, ValueError):
                continue

            equipment_type, _ = self._parse_equipment_code(str(equipment_id))
            state = states.setdefault(
                str(equipment_id),
                {"type": equipment_type.lower(), "sensor_readings": {}},
            )
            state["sensor_readings"][reading_name] = numeric_value

        return states

    async def _write_lighting_energy_from_states(self, states: dict[str, dict[str, Any]]) -> int:
        """Persist current DALI zone telemetry into lighting_energy."""
        dali_states = {
            equipment_id: state
            for equipment_id, state in states.items()
            if "-DALI-" in equipment_id and state.get("sensor_readings")
        }
        if not dali_states:
            return 0

        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            site_resp = client.table("sites").select("id").eq("code", self.site_id).limit(1).execute()
            if not site_resp.data:
                return 0
            site_uuid = site_resp.data[0]["id"]
            equipment_resp = (
                client.table("equipment")
                .select("code,zone_key")
                .eq("site_id", site_uuid)
                .in_("code", list(dali_states))
                .execute()
            )
            zone_by_equipment = {
                str(row.get("code")): str(row.get("zone_key") or "")
                for row in equipment_resp.data or []
                if row.get("code")
            }
            observed_at = datetime.now(UTC)
            rows = []
            for equipment_id, state in dali_states.items():
                payload = _lighting_energy_payload_from_state(
                    site_id=self.site_id,
                    equipment_id=equipment_id,
                    zone_id=zone_by_equipment.get(equipment_id),
                    readings=state.get("sensor_readings") or {},
                    observed_at=observed_at,
                )
                if payload:
                    rows.append(payload)

            if not rows:
                return 0
            client.table("lighting_energy").insert(rows).execute()
            logger.info("[SHADOW] Wrote %d DALI lighting_energy rows for %s", len(rows), self.site_id)
            return len(rows)
        except Exception as exc:
            logger.warning("[SHADOW] Failed to write DALI lighting_energy rows for %s: %s", self.site_id, exc)
            return 0

    @property
    def status(self) -> dict:
        """Return bridge connection status for API reporting.

        Connected if we have successfully polled at least once AND the last poll
        reported telemetry_fetched=True.
        """
        if self._poll_count == 0:
            return {"connected": False, "reason": "not_polled", "poll_count": 0, "last_poll": None}

        last = self._last_poll_result or {}
        errors = last.get("errors", [])
        real_errors = [e for e in errors if e]  # Filter empty strings from stale errors
        connected = last.get("telemetry_fetched", False) and not real_errors
        reason = None if connected else (real_errors[0] if real_errors else "poll_failed")

        return {
            "connected": connected,
            "reason": reason,
            "poll_count": self._poll_count,
            "last_poll": self._energy_last_poll.isoformat() if self._energy_last_poll else None,
            "ml_hours_ingested": last.get("ml_hours_ingested"),
            "bridge_data_source": "remote_bridge",
        }

    async def _poll_alarms(self, base: str, headers: dict[str, str]) -> int:
        """Fetch active alarms from bridge and upsert into the alerts table.

        BACnet alarms are a persistent queue: the bridge returns the complete set
        of currently-active alarms on every call. Each alarm retains its original
        event timestamp until explicitly cleared.

        This method:
          - Never filters by alarm age (persistent queue semantics)
          - Passes is_complete_snapshot=True so absent alarms are resolved
          - Sets poll_succeeded=False on any HTTP/network error (no state changes)
          - Feeds all alarms into the ML fault event buffer regardless of age
        """
        poll_succeeded = False
        alarms: list[dict[str, Any]] = []

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    f"{base}/api/sites/{self.site_id}/alarms",
                    headers=headers,
                    params={"active_only": True},
                )
                resp.raise_for_status()
                alarm_data = resp.json()

            alarms = alarm_data.get("alarms", [])
            poll_succeeded = True

        except httpx.HTTPStatusError as e:
            logger.warning("[SHADOW] Alarms poll HTTP %d: %s", e.response.status_code, e.response.text[:200])
        except Exception as e:
            logger.warning("[SHADOW] Alarms poll error: %s", e)

        if alarms:
            scoped_alarms = []
            scope_skipped = 0
            for alarm in alarms:
                reference_text = " ".join(
                    str(alarm.get(key) or "")
                    for key in (
                        "equipment_id",
                        "equipment_code",
                        "object_id",
                        "message_text",
                        "active_text",
                        "description",
                        "message",
                    )
                )
                if contains_site_002_out_of_scope_l3_reference(self.site_id, reference_text):
                    scope_skipped += 1
                    continue
                scoped_alarms.append(alarm)
            if scope_skipped:
                logger.warning(
                    "[SHADOW] Ignored %d alarm(s) for %s: Site 002 L3 is outside tenant scope",
                    scope_skipped,
                    self.site_id,
                )
            alarms = scoped_alarms

        # Feed all alarms into ML feeder regardless of poll outcome
        if alarms:
            try:
                from app.services.sentinel_data_sync import get_sentinel_data_sync

                sync = get_sentinel_data_sync(site_id=self.site_id)
                synthetic_skipped = 0
                for alarm in alarms:
                    message = alarm.get("message_text") or alarm.get("active_text") or alarm.get("description", "")
                    bridge_synthetic = _bridge_marks_synthetic_alarm(alarm)
                    is_synthetic = bridge_synthetic if bridge_synthetic is not None else _is_synthetic_alarm(message)
                    if is_synthetic:
                        synthetic_skipped += 1
                        continue
                    sync.ml_feeder.ingest_fault_event(alarm)
                if synthetic_skipped:
                    logger.warning(
                        "[SHADOW] Skipped %d synthetic alarm(s) from ML fault feeder",
                        synthetic_skipped,
                    )
            except Exception as e:
                logger.warning("[SHADOW] ML feeder alarm ingest failed: %s", e)

        # Upsert into alerts table with lifecycle tracking
        try:
            from app.services.adapter_health_monitor import AdapterHealthMonitor

            monitor = AdapterHealthMonitor()
            await monitor._write_bridge_alerts(
                self.site_id,
                alarms,
                is_complete_snapshot=poll_succeeded,
                poll_succeeded=poll_succeeded,
            )
        except Exception as e:
            logger.warning("[SHADOW] Failed to write bridge alarms to alerts table: %s", e)

        # Persist to equipment_fault_events for prediction generation
        if alarms and poll_succeeded:
            try:
                await self._persist_fault_events(alarms)
            except Exception as e:
                logger.warning("[SHADOW] Failed to persist fault events: %s", e)

        if poll_succeeded:
            logger.info("[SHADOW] %d alarms → upserted (complete snapshot)", len(alarms))
        else:
            logger.warning("[SHADOW] Alarm poll failed — zero state changes applied")

        return len(alarms) if poll_succeeded else 0

    async def _persist_fault_events(self, alarms: list[dict[str, Any]]) -> None:
        """Persist fault events to equipment_fault_events table for prediction generation.

        This makes fault data available to the prediction calculator so it can
        include alarm_frequency in prediction evidence.
        """

        from app.database.supabase_client import get_supabase_client

        supabase = get_supabase_client()

        # Resolve site UUID
        try:
            site_row = supabase.table("sites").select("id").eq("code", self.site_id).execute()
            if not site_row.data:
                return
            site_row.data[0]["id"]
        except Exception as e:
            logger.warning(f"[SHADOW] Could not resolve site UUID: {e}")
            return

        rows_to_insert = []
        for alarm in alarms:
            # Extract equipment code
            equip_code = alarm.get("equipment_id") or alarm.get("equipment_code") or ""
            obj_id = alarm.get("object_id") or ""

            # Try to parse equipment code from various fields
            if not equip_code and obj_id:
                # Parse from object_id like "S002-AHU-B1-001-supply_air_temp"
                parts = obj_id.split("-")
                if len(parts) >= 4 and parts[0].startswith("S"):
                    equip_code = "-".join(parts[:4])

            # Parse alarm timestamp
            alarm_time_str = alarm.get("timestamp") or alarm.get("time")
            recorded_at = datetime.now(UTC).isoformat()
            if alarm_time_str:
                try:
                    alarm_time = datetime.fromisoformat(alarm_time_str.replace("Z", "+00:00"))
                    recorded_at = alarm_time.isoformat()
                except (ValueError, TypeError):
                    pass

            # Extract alarm code/event type
            event_type = alarm.get("event_type") or alarm.get("alarm_class") or alarm.get("event_state", "UNKNOWN")
            alarm_code = alarm.get("code") or alarm.get("alarm_code") or event_type

            # Extract message
            message = alarm.get("active_text") or alarm.get("message_text") or alarm.get("description", "")
            if not message:
                message = alarm.get("message", "Fault detected")

            reference_text = " ".join([equip_code, obj_id, message])
            if contains_site_002_out_of_scope_l3_reference(self.site_id, reference_text):
                continue

            bridge_synthetic = _bridge_marks_synthetic_alarm(alarm)
            is_synthetic = bridge_synthetic if bridge_synthetic is not None else _is_synthetic_alarm(message)

            rows_to_insert.append(
                {
                    "site_id": self.site_id,
                    "equipment_code": equip_code or "UNKNOWN",
                    "alarm_code": alarm_code,
                    "event_type": event_type,
                    "severity": alarm.get("severity") or alarm.get("priority", "warning"),
                    "message_text": message[:500],  # Truncate to avoid overflow
                    "is_synthetic": is_synthetic,
                    "recorded_at": recorded_at,
                    "raw_payload": alarm,
                }
            )

        if not rows_to_insert:
            return

        try:
            # Deduplicate rows before upsert (bridge may return same alarm multiple times)
            seen = set()
            deduped = []
            for row in rows_to_insert:
                key = (row["site_id"], row["equipment_code"], row["alarm_code"], row["recorded_at"])
                if key not in seen:
                    seen.add(key)
                    deduped.append(row)
            supabase.table("equipment_fault_events").upsert(
                deduped, on_conflict="site_id,equipment_code,alarm_code,recorded_at"
            ).execute()
            logger.warning(f"[SHADOW] Persisted {len(deduped)} fault events to equipment_fault_events")
        except Exception as e:
            logger.warning(f"[SHADOW] Failed to insert fault events: {e}")

    def _upsert_log_source(self, equipment_state_count: int) -> None:
        """Create or update a log_sources entry reflecting bridge polling activity.

        This keeps the System Health monitoring page in sync with shadow mode operation,
        which bypasses the commissioning flow and doesn't write to log_sources directly.
        """
        try:
            from app.database.repositories.integration_repository import IntegrationRepository

            repo = IntegrationRepository()
            source_name = f"Shadow Bridge ({self.site_id})"

            existing = repo.get_log_source_by_name(source_name)
            now_iso = datetime.utcnow().isoformat()

            if existing:
                repo.update_log_source(
                    existing["id"],
                    {
                        "is_active": True,
                        "last_sync_at": now_iso,
                        "last_sync_status": "success",
                        "last_sync_records": equipment_state_count,
                    },
                )
            else:
                # Resolve site code (e.g. "site-002") to UUID for DB
                from app.database.repositories.site_repository import SiteRepository

                site_repo = SiteRepository()
                site_record = site_repo.client.table("sites").select("id").eq("code", self.site_id).execute()
                site_uuid = site_record.data[0]["id"] if site_record.data else self.site_id
                repo.create_log_source(
                    {
                        "site_id": site_uuid,
                        "name": source_name,
                        "source_type": "shadow_polling",
                        "connection_type": "api",
                        "is_active": True,
                        "sync_frequency_minutes": 5,
                        "last_sync_at": now_iso,
                        "last_sync_status": "success",
                        "last_sync_records": equipment_state_count,
                    }
                )
            logger.debug(f"[SHADOW] log_sources upserted: {source_name}")
        except Exception as e:
            logger.warning(f"[SHADOW] Failed to upsert log_sources: {e}")

    def _accumulate_energy(self, hvac_kw: float, lighting_kw: float, total_kw: float, now: datetime) -> None:
        """Accumulate energy from instantaneous power readings.

        Accumulates kWh based on time elapsed since last poll.
        Flushes to DB when day changes (new UTC date).
        """
        if self._energy_last_poll is None:
            self._energy_accum_start = now
            self._energy_last_poll = now
            return

        elapsed_seconds = (now - self._energy_last_poll).total_seconds()
        elapsed_hours = elapsed_seconds / 3600.0

        # Cap at 1 hour max between polls (avoid huge jumps after gaps)
        elapsed_hours = min(elapsed_hours, 1.0)

        self._energy_accumulator["hvac_kwh"] += hvac_kw * elapsed_hours
        self._energy_accumulator["lighting_kwh"] += lighting_kw * elapsed_hours
        self._energy_accumulator["other_kwh"] += (total_kw - hvac_kw - lighting_kw) * elapsed_hours
        self._energy_accumulator["total_kwh"] += total_kw * elapsed_hours
        self._energy_last_poll = now

        # Check if day changed (UTC midnight)
        current_date = now.date()
        accum_date = self._energy_accum_start.date() if self._energy_accum_start else None

        if accum_date and current_date > accum_date:
            # New day — flush yesterday's accumulated energy to DB
            self._flush_energy_to_db(accum_date)
            # Reset accumulator for new day
            self._energy_accumulator = {"hvac_kwh": 0.0, "lighting_kwh": 0.0, "other_kwh": 0.0, "total_kwh": 0.0}
            self._energy_accum_start = now

    _FCU_TELEMETRY_KEYS = ("setpoint", "fan_speed", "valve_position")

    def _load_fcu_telemetry(self, max_age_minutes: int = 30) -> dict[str, dict[str, float]]:
        """Latest per-FCU setpoint/fan_speed/valve_position from equipment operating_data.

        The bridge zone payload has no cooling_setpoint field, but each FCU's
        setpoint (and fan/valve state) reaches operating_data every poll cycle
        via the sentinel sync. Entries older than max_age_minutes are dropped
        per-key so a stalled writer degrades to "unknown" (tracker infers None)
        rather than feeding stale values into the inference.

        Returns {equipment_code: {key: value}} with only fresh keys present.
        """
        telemetry: dict[str, dict[str, float]] = {}
        try:
            from app.database.supabase_client import get_supabase_client

            rows = (
                get_supabase_client()
                .table("equipment")
                .select("code,operating_data")
                .like("code", f"{self._site_prefix}-FCU-%")
                .execute()
                .data
                or []
            )
            cutoff = datetime.now(tz=UTC) - timedelta(minutes=max_age_minutes)
            for row in rows:
                op = row.get("operating_data")
                if not isinstance(op, dict):
                    continue
                fresh: dict[str, float] = {}
                for key in self._FCU_TELEMETRY_KEYS:
                    entry = op.get(key)
                    if not isinstance(entry, dict):
                        continue
                    value = _safe_float(entry.get("value"))
                    if value is None:
                        continue
                    try:
                        ts = datetime.fromisoformat(str(entry.get("timestamp")).replace("Z", "+00:00"))
                    except (TypeError, ValueError):
                        continue
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=UTC)
                    if ts < cutoff:
                        continue
                    fresh[key] = value
                if fresh:
                    telemetry[str(row.get("code") or "").upper()] = fresh
        except Exception as e:
            logger.debug("[SHADOW] FCU telemetry load skipped: %s", e)
        return telemetry

    def _check_power_anomaly(self, total_kw: float, now: datetime) -> None:
        if total_kw <= 0:
            return
        self._total_kw_history.append(total_kw)
        if len(self._total_kw_history) < 3:
            return
        mean = sum(self._total_kw_history) / len(self._total_kw_history)
        deviation = abs(total_kw - mean) / mean
        if deviation > 0.25:
            logger.warning(
                "[DATA_QUALITY] total_kw anomaly at %s: %.1f kW deviates %.0f%% from %.1f kW rolling mean "
                "(window=%d readings) — possible BACnet unit/BMS meter collision",
                now.isoformat(),
                total_kw,
                deviation * 100,
                mean,
                len(self._total_kw_history),
            )
            throttle_hours = 1
            if (
                self._last_anomaly_alert_at is None
                or (now - self._last_anomaly_alert_at).total_seconds() > throttle_hours * 3600
            ):
                self._last_anomaly_alert_at = now
                try:
                    from app.database.supabase_client import get_supabase_client

                    sb = get_supabase_client()
                    sb.table("alerts").insert(
                        {
                            "site_id": self.site_id,
                            "title": "Power reading anomaly detected",
                            "message": (
                                f"total_kw={total_kw:.0f} deviates {deviation * 100:.0f}% from "
                                f"{mean:.0f} kW rolling mean — possible BACnet unit collision or meter scaling error"
                            ),
                            "severity": "warning",
                            "type": "data_quality",
                            "status": "active",
                            "source": "shadow_mode_polling",
                        }
                    ).execute()
                except Exception as exc:
                    logger.warning("[DATA_QUALITY] Failed to insert power anomaly alert: %s", exc)

    def _flush_energy_to_db(self, accum_date, force: bool = False) -> None:
        """Write accumulated energy to energy_consumption_history table."""
        from app.database.repositories.energy_consumption_repository import get_energy_consumption_repository

        total = self._energy_accumulator["total_kwh"]
        # Only write if meaningful (at least 0.01 kWh — avoids spurious zero writes)
        if not force and total < 0.01:
            return

        try:
            repo = get_energy_consumption_repository()
            repo.upsert(
                site_id=self.site_id,
                consumption_date=accum_date,
                hvac_kwh=round(self._energy_accumulator["hvac_kwh"], 3),
                lighting_kwh=round(self._energy_accumulator["lighting_kwh"], 3),
                other_kwh=round(self._energy_accumulator["other_kwh"], 3),
            )
            logger.info(
                f"[SHADOW] Energy flushed to DB: {accum_date} — "
                f"total={total:.2f} kWh (hvac={self._energy_accumulator['hvac_kwh']:.2f}, "
                f"lighting={self._energy_accumulator['lighting_kwh']:.2f})"
            )
        except Exception as e:
            logger.warning(f"[SHADOW] Energy flush failed: {e}")

    def _resolve_sensor(self, sensor_code: str) -> tuple[str | None, str | None]:
        """Resolve a sensor_code to (equipment_code, reading_name).

        Maps bridge sensor codes to SENTINEL equipment codes using the cached
        object catalog and zone→AHU mapping.

        Examples:
          "Zone-001-temp"     → "S{num}-FCU-001", "room_temp"
          "CH-1-ChwSupplyTemp" → "S{num}-CHILLER-B1-001", "chw_supuply_temp"
          "S{num}-AHU-B1-001-supply_air_temp" → "S{num}-AHU-B1-001", "supply_temp"
        """
        # Zone temperature: Zone-001-temp → S{num}-FCU-001
        prefix = self._site_prefix  # e.g. "S002"
        if sensor_code.startswith("Zone-") and "-temp" in sensor_code:
            parts = sensor_code.replace("-temp", "").split("-")
            if len(parts) == 2:
                zone_num = parts[1]
                return f"{prefix}-FCU-{zone_num}", "room_temp"
            return None, None

        # Chiller supply temp: CH-1-ChwSupplyTemp → S{num}-CHILLER-B1-001
        if "ChwSupplyTemp" in sensor_code:
            # "CH-1-ChwSupplyTemp" → rsplit gives ["CH-1", "ChwSupplyTemp"]
            chiller_id = sensor_code.rsplit("-", 1)[0]  # "CH-1"
            chiller_map = {
                "CH-1": f"{prefix}-CHILLER-B1-001",
                "CH-2": f"{prefix}-CHILLER-B1-002",
            }
            equip_code = chiller_map.get(chiller_id, f"{prefix}-CHILLER-B1-{chiller_id}")
            return equip_code, "chw_supply_temp"

        # AHU sensors: S{num}-AHU-B1-001-supply_air_temp
        if "AHU-" in sensor_code:
            parts = sensor_code.split("-")
            if len(parts) >= 5:
                site, typ, floor, seq, point = parts[0], parts[1], parts[2], parts[3], "-".join(parts[4:])
                equip_code = f"{site}-{typ}-{floor}-{seq}"
                reading_name = self._ahu_point_to_reading(point)
                return equip_code, reading_name

        # Weather: SITE{num}-WEATHER-outdoor_temperature
        if "WEATHER" in sensor_code and "outdoor_temp" in sensor_code.lower():
            return f"{prefix}-SITE-AGG", "outdoor_temp"
        if "WEATHER" in sensor_code and "humidity" in sensor_code.lower():
            return f"{prefix}-SITE-AGG", "outdoor_humidity"

        return None, None

    def _ahu_point_to_reading(self, point: str) -> str:
        """Map BACnet AHU point names to SENTINEL reading names."""
        mapping = {
            "supply_air_temp": "supply_temp",
            "fan_speed_pct": "fan_current",
            "return_air_temp": "return_temp",
            "filter_dp": "filter_dp",
            "damper_position": "damper_position",
        }
        return mapping.get(point, point)

    def _parse_equipment_code(self, code: str) -> tuple[str, str]:
        """Parse equipment code into (type, display_name).

        Code format: S002-{TYPE}-{rest} where TYPE is HVAC category
        e.g. S002-CHILLER-B1-001 → type=chiller, name=S002 Chiller B1-001
             S002-FCU-101         → type=fcu,    name=S002 FCU 101
             S002-MTR-B1-MAIN     → type=meter,  name=S002 Meter B1 Main
        """
        parts = code.split("-")
        raw_type = parts[1].upper() if len(parts) >= 2 else "UNKNOWN"

        # Normalise equipment type labels
        type_map = {
            "CHILLER": "chiller",
            "AHU": "ahu",
            "FCU": "fcu",
            "VAV": "vav",
            "SPLIT": "split",
            "CT": "cooling_tower",
            "CRAC": "crac",
            "DALI": "dali",
            "GEN": "generator",
            "TX": "transformer",
            "UPS": "ups",
            "ATS": "ats",
            "MSB": "msb",
            "MTR": "meter",
            "PFC": "pfc",
            "FDR": "feeder",
            "MV": "mv",
            "DB": "distribution_board",
            "BESS": "bess",
            "INV": "inverter",
            "PUMP": "pump",
            "FIRE": "fire",
            "ACC": "access_control",
            "CCTV": "cctv",
            "LUM": "luminaire",
            "ZONE": "zone",
            "UNKNOWN": "unknown",
        }
        eq_type = type_map.get(raw_type, "unknown")
        # Build human-readable name: "S002 Chiller B1-001"
        name_parts = code.split("-")
        if len(name_parts) >= 3:
            name = code.replace("-", " ", 1)  # "S002-CHILLER..." → "S002 CHILLER..."
            name = name.replace("-", " ", 1)  # "S002 CHILLER-B1..." → "S002 CHILLER B1..."
        else:
            name = code
        return eq_type, name

    def _classify_from_catalog(self, code: str) -> str:
        """Fallback classification using the loaded object catalog for codes without
        a recognizable type segment (e.g. S002-G-001, S002-R-042).

        Cross-references the BACnet object catalog to infer equipment type from
        point metadata (object types, point names, parent paths).
        """
        if not self._object_catalog:
            return "unknown"

        # Collect all catalog entries for this equipment code
        candidates = [o for o in self._object_catalog.values() if o.get("equipment_id") == code]
        if not candidates:
            return "unknown"

        point_types: set[str] = set()
        object_types: set[str] = set()
        point_names: list[str] = []
        descriptions: list[str] = []
        parent_paths: set[str] = set()

        for obj in candidates:
            point_types.add(obj.get("point_type", "").lower())
            ot = obj.get("object_type", "").lower()
            object_types.add(ot)
            point_names.append(obj.get("point_name", "").lower())
            descriptions.append(obj.get("description", "").lower())
            if obj.get("parent_path"):
                parent_paths.add(obj["parent_path"].lower())

        search_text = " ".join(point_names + descriptions)

        # ── Heuristic rules (ordered most to least specific) ────────────

        # Power / electrical metering
        if ("active_power" in search_text or "power" in search_text) and ("kw" in search_text or "kwh" in search_text):
            return "meter"

        # Temperature sensors in a zone context
        if "temp" in search_text or "temperature" in search_text:
            if "zone" in search_text or "space" in search_text:
                return "zone_sensor"
            if "return" in search_text or "supply" in search_text:
                return "ahu"
            return "zone_sensor"

        # Humidity sensors
        if "humidity" in search_text or "rh" in search_text.split():
            return "zone_sensor"

        # CO2 sensors
        if "co2" in search_text:
            return "zone_sensor"

        # Binary outputs / relays → likely lighting or contactor control
        if "binary_output" in object_types or "binary_value" in object_types:
            return "lighting_zone"

        # Presence / occupancy
        if "occupancy" in search_text or "presence" in search_text:
            return "zone_sensor"

        # Parent-path hints
        for path in parent_paths:
            if "/lighting/" in path or "/dali/" in path:
                return "lighting_zone"
            if "/hvac/" in path or "/ahu/" in path:
                return "ahu"

        # All points are analog_inputs with no specific keyword → generic sensor
        if object_types == {"analog_input"}:
            return "zone_sensor"

        return "unknown"

    def _equip_type_from_sensor(self, sensor_code: str) -> str:
        """Infer equipment type from sensor code string."""
        if "AHU" in sensor_code:
            return "ahu"
        if "CH-" in sensor_code:
            return "chiller"
        if "FCU" in sensor_code or "Zone-" in sensor_code:
            return "fcu"
        if "WEATHER" in sensor_code:
            return "ahu"
        return "unknown"

    async def _sync_equipment_status(self, base: str, headers: dict[str, str]) -> dict[str, Any]:
        """Sync equipment online/offline status from bridge /points endpoint.

        Updates the status field in Supabase equipment table for all onboarded
        equipment that appears in the bridge /points response. Equipment not in
        the bridge is marked offline. Bridge equipment not in DB is recorded for
        onboarding review; polling does not create active equipment.

        Returns:
            Dict with 'updated' count, 'missing_from_bridge' list, and 'created' count.
        """
        result = {"updated": 0, "missing_from_bridge": [], "created": 0}
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.get(
                    f"{base}/api/sites/{self.site_id}/points",
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()

            # /points returns {"equipment": [{"code": {"status": "online", ...}}, ...]}
            # The response is a list containing one dict with ALL equipment codes as keys.
            equip_list = data.get("equipment", [])
            if isinstance(equip_list, dict):
                equip_status_map = equip_list
            elif isinstance(equip_list, list) and len(equip_list) > 0:
                equip_status_map = equip_list[0] if isinstance(equip_list[0], dict) else {}
            else:
                equip_status_map = {}

            if not equip_status_map:
                return result

            # ── Extract equipment states from /points for ML pipeline ──
            # Bridge /points returns status + sensor readings per equipment code.
            vav_states: dict[str, dict[str, Any]] = {}
            dali_states: dict[str, dict[str, Any]] = {}
            meter_states: dict[str, dict[str, Any]] = {}
            for code, info in equip_status_map.items():
                if code.startswith(f"{self._site_prefix}-VAV-"):
                    # VAV: zone_temp, damper_position, airflow from bridge
                    vav_readings: dict[str, float] = {}
                    if (zt := info.get("temperature")) is not None:
                        vav_readings["zone_temp"] = float(zt)
                    if (dp := info.get("damper_position")) is not None:
                        vav_readings["damper_position"] = float(dp)
                    if (af := info.get("flow") or info.get("airflow")) is not None:
                        vav_readings["airflow_lps"] = float(af)
                    if (st := info.get("supply_temp") or info.get("supply_air_temp")) is not None:
                        vav_readings["supply_temp"] = float(st)
                    if vav_readings:
                        vav_states[code] = {
                            "type": "vav",
                            "sensor_readings": vav_readings,
                        }
                elif code.startswith(f"{self._site_prefix}-DALI-"):
                    # DALI controller: status + updated_at as sensor readings
                    dali_states[code] = {
                        "type": "dali",
                        "sensor_readings": {
                            "controller_status": 1.0 if info.get("status") in ("online", "normal", "ok") else 0.0,
                        },
                    }
                elif code.startswith(f"{self._site_prefix}-MTR-"):
                    # Power meter: active_power_kw (e.g. S002-MTR-B1-LIGHT)
                    readings: dict[str, float] = {}
                    if (ap := info.get("active_power_kw")) is not None:
                        readings["active_power_kw"] = float(ap)
                    if readings:
                        meter_states[code] = {
                            "type": "meter",
                            "sensor_readings": readings,
                        }

            result["vav_states"] = vav_states
            result["dali_states"] = dali_states
            result["meter_states"] = meter_states

            # Get all equipment from DB for this site
            from app.database.repositories.equipment_repository import EquipmentRepository
            from app.database.repositories.site_repository import SiteRepository

            site_repo = SiteRepository()
            site = site_repo.get_by_id(self.site_id)
            site_uuid = site.get("id") if site else None

            if not site_uuid:
                logger.warning(f"[SHADOW] Cannot sync equipment status — site {self.site_id} not found in DB")
                return result

            eq_repo = EquipmentRepository()
            all_equipment = eq_repo.get_all(site_id=site_uuid)

            # Build code sets and a truncated-to-full mapping.
            # Bridge returns truncated codes (up to 15 chars) that may cut mid-word
            # (e.g. "S002-MTR-B1-MAI" = DB "S002-MTR-B1-MAIN", "S002-MTR-R-SOL" = DB "S002-MTR-R-SOLAR").
            # We match by checking if the bridge code is a prefix of the DB code.
            # Also normalises naming differences: bridge uses underscores (DALI_L1_B),
            # DB uses S002- prefix + hyphens (S002-DALI-L1-B).
            db_full_codes = [eq.get("code") for eq in all_equipment]

            def _normalise(code: str) -> str:
                """Strip site prefix (e.g. S002-) and replace underscores with hyphens for matching."""
                c = code.replace("_", "-")
                if c.startswith(f"{self._site_prefix}-"):
                    c = c[len(self._site_prefix) + 1 :]
                return c

            def _letter_zone_to_numeric(code: str) -> str | None:
                """Convert old letter-based or mixed zone codes to numeric standard.

                L1-A → 101, L2-B → 202, L0-A → 001
                B1-XXX → B01, R-XXX → R01
                Returns None if the code doesn't match any known pattern.
                """
                import re

                # L-pattern: FCU-L1-A → FCU-101, DALI-L2-B → DALI-202
                m = re.match(r"^(.+)-L(\d)-([A-Z])$", code)
                if m:
                    prefix = m.group(1)
                    floor = int(m.group(2))
                    zone_num = ord(m.group(3)) - ord("A") + 1
                    if 1 <= zone_num <= 5:
                        zone_code = floor * 100 + zone_num
                        return f"{prefix}-{zone_code:03d}"

                # B1-pattern: CHILLER-B1-001 → CHILLER-B01, DALI-B1-CTRL → DALI-B01
                m = re.match(r"^(.+)-B1-", code)
                if m:
                    return f"{m.group(1)}-B01"

                # R-pattern: AHU-R-001 → AHU-R01, INV-R-001 → INV-R01
                m = re.match(r"^(.+)-R-\d{3}$", code)
                if m:
                    return f"{m.group(1)}-R01"

                return None

            db_norm_to_full: dict[str, str] = {}
            for dbc in db_full_codes:
                db_norm_to_full.setdefault(_normalise(dbc), dbc)

            # Build sets for membership tests
            db_full_set = set(db_full_codes)
            bridge_codes = set(equip_status_map.keys())
            bridge_lum_codes = {c for c in bridge_codes if "-LUM-" in c}
            # Map bridge codes → full DB codes.
            # Strategy: exact match first, then prefix match (bridge code is prefix of DB code).
            bridge_to_db: dict[str, str] = {}
            for bcode in bridge_codes:
                if bcode in db_full_set:
                    bridge_to_db[bcode] = bcode  # exact match
                else:
                    # Try normalised match: strip S002- and replace _ with -
                    bcode_norm = _normalise(bcode)
                    if bcode_norm in db_norm_to_full:
                        bridge_to_db[bcode] = db_norm_to_full[bcode_norm]
                        continue
                    # Try old format → new format: L1-A → 101 conversion
                    converted = _letter_zone_to_numeric(bcode_norm)
                    if converted and converted in db_norm_to_full:
                        bridge_to_db[bcode] = db_norm_to_full[converted]
                        continue
                    # Try prefix match: bridge code as prefix of DB code
                    matched = None
                    for db_code in db_full_codes:
                        if db_code.startswith(bcode) and (matched is None or len(db_code) < len(matched)):
                            matched = db_code
                    if matched:
                        bridge_to_db[bcode] = matched

            mapped_db_codes = set(bridge_to_db.values())

            def _remap_point_states(states: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
                remapped: dict[str, dict[str, Any]] = {}
                for bridge_code, state in states.items():
                    db_code = bridge_to_db.get(bridge_code) or self._normalize_to_db_code(bridge_code)
                    target = remapped.setdefault(
                        db_code,
                        {
                            "type": state.get("type"),
                            "sensor_readings": {},
                        },
                    )
                    target.setdefault("sensor_readings", {}).update(state.get("sensor_readings", {}))
                    if not target.get("type") and state.get("type"):
                        target["type"] = state.get("type")
                return remapped

            result["vav_states"] = _remap_point_states(vav_states)
            result["dali_states"] = _remap_point_states(dali_states)
            result["meter_states"] = _remap_point_states(meter_states)

            # Equipment in DB but not on bridge → mark offline
            missing = db_full_set - mapped_db_codes - bridge_lum_codes
            result["missing_from_bridge"] = sorted(missing)

            # Update each equipment found on bridge (using mapped DB codes)
            updated = 0
            for bcode, bridge_status_data in equip_status_map.items():
                if "-LUM-" in bcode and bcode not in bridge_to_db:
                    continue

                db_code = bridge_to_db.get(bcode)
                if not db_code:
                    continue

                bridge_status = bridge_status_data.get("status", "offline")
                db_status = _normalize_bridge_equipment_status(bridge_status)

                try:
                    eq_repo.update(db_code, {"status": db_status})
                    updated += 1
                except Exception as e:
                    logger.warning(f"[SHADOW] Failed to update {db_code} ({bcode}): {e}")

            # Mark equipment not present on bridge as offline
            for db_code in missing:
                try:
                    eq_repo.update(db_code, {"status": "offline"})
                    updated += 1
                except Exception as e:
                    logger.warning(f"[SHADOW] Failed to mark {db_code} offline: {e}")

            # Record bridge equipment that exists on the site but is not in
            # Supabase inventory. Onboarding, not polling, is responsible for
            # creating active equipment and zone links.
            bridge_all_codes = set(equip_status_map.keys())
            new_codes = bridge_all_codes - set(bridge_to_db.keys()) - bridge_lum_codes
            created = 0
            if new_codes:
                for bcode in sorted(new_codes):
                    bridge_status_data = equip_status_map.get(bcode, {})
                    # Skip luminaries
                    if "-LUM-" in bcode:
                        continue
                    # Normalize bridge code to canonical SENTINEL format
                    # B1-001 → B01, R-XXX → R01, L{N}-{LETTER} → {N*100+ZONE}
                    bcode_norm = _normalise(bcode)
                    conv = _letter_zone_to_numeric(bcode_norm)
                    canonical_code = f"{self._site_prefix}-{conv}" if conv else bcode
                    if is_site_002_out_of_scope_l3(self.site_id, canonical_code) or is_site_002_out_of_scope_l3(
                        self.site_id,
                        bcode,
                    ):
                        logger.warning(
                            "[SHADOW] Ignoring bridge equipment %s/%s for %s: Site 002 L3 is outside tenant scope",
                            bcode,
                            canonical_code,
                            self.site_id,
                        )
                        continue
                    blocker = self._equipment_zone_inventory_blocker(canonical_code)
                    derived_zone_id = (
                        blocker[0]
                        if blocker
                        else _bridge_zone_id_from_equipment_code(
                            self._site_prefix,
                            canonical_code,
                        )
                    )
                    reason = blocker[1] if blocker else "new_bridge_equipment"
                    # If canonical code already exists in DB, update it instead of creating duplicate
                    if canonical_code != bcode:
                        existing = eq_repo.get_by_id(canonical_code)
                        if existing:
                            bridge_status = bridge_status_data.get("status", "offline")
                            db_status = _normalize_bridge_equipment_status(bridge_status)
                            eq_repo.update(canonical_code, {"status": db_status})
                            continue
                    self._record_discovered_bridge_equipment(
                        bridge_code=bcode,
                        canonical_code=canonical_code,
                        bridge_status_data=bridge_status_data,
                        reason=reason,
                        derived_zone_id=derived_zone_id,
                    )

                if created > 0:
                    logger.info(f"[SHADOW] Auto-created {created} equipment from bridge")

            result["updated"] = updated
            result["created"] = created
            if updated > 0 or missing or created > 0:
                logger.info(
                    f"[SHADOW] Equipment status sync: {updated} updated, "
                    f"{len(missing)} missing from bridge, {created} created"
                )

        except Exception as e:
            logger.warning(
                "[SHADOW] Equipment status sync failed for %s (non-fatal): %s",
                self.site_id,
                e,
                exc_info=True,
            )

        return result


_shadow_polling_service: ShadowModePollingService | None = None


def get_shadow_mode_polling_service(site_id: str = "site-002") -> ShadowModePollingService:
    global _shadow_polling_service
    if _shadow_polling_service is None:
        _shadow_polling_service = ShadowModePollingService(site_id=site_id)
    return _shadow_polling_service

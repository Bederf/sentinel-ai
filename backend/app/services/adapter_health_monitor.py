"""Adapter Health Monitor — SLI Tier 1: Adapter Heartbeat.

Runs every 60s, calls get_status() on all registered DeviceAdapters
and ShadowModePollingService instances, writes to adapter_health table,
and emits alerts after 3 consecutive failures.

Wired into BackgroundSchedulerService via add_adapter_health_monitor_job().
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

from app.core.site_resolver import normalize_site_id

logger = logging.getLogger("adapter-health-monitor")

# Threshold for consecutive failures before alerting
_CONSECUTIVE_FAILURE_ALERT_THRESHOLD = 3

# How long to look back for consecutive-failure count
_FAILURE_LOOKBACK_HOURS = 1

# BACnet alarm states that represent a cleared/normal condition
_CLEARED_STATES: frozenset[str] = frozenset(
    {
        "NORMAL",
        "normal",
        "INACTIVE",
        "inactive",
        "CLEARED",
        "cleared",
        "CLOSE",
        "close",
        "OFFNORMAL_CLEARED",
    }
)


def build_source_dedupe_key(alarm: dict[str, Any]) -> str:
    """Build a stable BACnet identity key for UPSERT deduplication.

    Priority order:
    1. notification_class + object_identifier  — canonical BACnet alarm identity
    2. alarm id + event_id                     — bridge-assigned stable IDs
    3. equipment + code + type                 — fallback composite key
    """
    notif_class = alarm.get("notification_class") or alarm.get("notificationClass")
    # Bridge uses 'bacnet_object' (e.g. 'binaryInput,2033') — map to obj_id
    obj_id = (
        alarm.get("object_id") or alarm.get("objectIdentifier") or alarm.get("objectId") or alarm.get("bacnet_object")
    )
    if notif_class is not None and obj_id:
        return f"nc:{notif_class}|obj:{obj_id}"

    alarm_id = alarm.get("id") or alarm.get("alarm_id")
    event_id = alarm.get("event_id")
    if alarm_id and event_id:
        return f"id:{alarm_id}|ev:{event_id}"

    equipment = alarm.get("equipment_id") or alarm.get("equipment_code") or "UNKNOWN"
    code = alarm.get("code") or alarm.get("alarm_code") or "UNPARSEABLE"
    alarm_type = alarm.get("alarm_type") or alarm.get("event_type") or "UNCLASSIFIED"
    return f"eq:{equipment}|code:{code}|type:{alarm_type}"


def is_alarm_cleared(alarm: dict[str, Any]) -> bool:
    """Return True if this alarm represents a cleared/normal state."""
    to_state = alarm.get("to_state") or alarm.get("toState") or alarm.get("event_state")
    if to_state:
        return str(to_state).upper() in {"NORMAL", "INACTIVE", "CLEARED", "CLOSE", "OFFNORMAL_CLEARED"}
    return False


@dataclass
class AdapterHealthRecord:
    site_id: str  # internal format: 'site-002'
    adapter_name: str
    adapter_type: str  # 'shadow_bridge' | 'bacnet' | 'niagara' | 'obix' | 'dali'
    is_healthy: bool
    latency_ms: float | None
    consecutive_failures: int
    error_message: str | None
    metadata: dict[str, Any]


class AdapterHealthMonitor:
    """60-second interval health checks for all registered adapters per site."""

    def __init__(self):
        self._failure_cache: dict[str, int] = {}  # key: f"{site_id}:{adapter_name}"

    # ------------------------------------------------------------------
    # Public API (called by BackgroundSchedulerService)
    # ------------------------------------------------------------------

    async def run_health_cycle(self) -> dict[str, dict[str, AdapterHealthRecord]]:
        """Run one complete health check cycle across all registered adapters.

        Returns:
            {site_id: {adapter_name: AdapterHealthRecord}}
        """
        from app.config.settings import settings
        from app.services.device_abstraction import device_manager
        from app.services.shadow_mode_polling import get_shadow_mode_polling_service

        results: dict[str, dict[str, AdapterHealthRecord]] = {}

        # 1) ShadowModePollingService per configured site
        sites = self._get_monitored_sites(settings)
        for site_id in sites:
            results[site_id] = {}
            try:
                shadow = get_shadow_mode_polling_service(site_id)
                record = await self._check_shadow_bridge(site_id, shadow)
                results[site_id]["shadow_bridge"] = record
                await self._record_and_alert(site_id, "shadow_bridge", "shadow_bridge", record)
            except Exception as e:
                logger.exception(f"ShadowModePollingService check failed for {site_id}: {e}")

        # 2) DeviceManager adapters (BacnetBmsAdapter, NiagaraBACnetAdapter, etc.)
        try:
            # Ensure DeviceManager is initialized before reading adapters
            from app.services.ai_optimizer import ensure_device_manager_initialized

            await ensure_device_manager_initialized()
            adapters = getattr(device_manager, "_adapters", {})
            for name, adapter in adapters.items():
                site_id = self._site_id_from_adapter(adapter, name, settings)
                if site_id not in results:
                    results[site_id] = {}
                record = await self._check_device_adapter(site_id, name, adapter)
                adapter_type = self._infer_adapter_type(name, adapter)
                results[site_id][name] = record
                await self._record_and_alert(site_id, name, adapter_type, record)
        except Exception as e:
            logger.exception(f"DeviceManager adapter health check failed: {e}")

        return results

    # ------------------------------------------------------------------
    # Per-adapter checks
    # ------------------------------------------------------------------

    async def _check_shadow_bridge(self, site_id: str, shadow: Any) -> AdapterHealthRecord:
        """Check ShadowModePollingService bridge connectivity.

        Uses SIMBIOT's live health probe (actual HTTP request to bridge) rather
        than ShadowModePollingService.status, which only reflects whether poll()
        has ever been called — not whether the bridge is actually reachable now.
        """
        start = time.perf_counter()
        try:
            from app.services.simbiot_service import simbiot_service

            simbiot_status = await simbiot_service.get_site_status(site_id)
            latency_ms = (time.perf_counter() - start) * 1000

            connected = (
                simbiot_status.get("status") in ("connected", "ok") or simbiot_status.get("site_available") is True
            )
            is_healthy = connected
            error_message = None if is_healthy else f"bridge unreachable: {simbiot_status.get('status', 'unknown')}"
            metadata = {
                "site_available": simbiot_status.get("site_available"),
                "telemetry_fresh": simbiot_status.get("telemetry_fresh"),
                "last_telemetry_at": simbiot_status.get("last_telemetry_at"),
            }

            consecutive = await self._count_consecutive_failures(site_id, "shadow_bridge")

            return AdapterHealthRecord(
                site_id=site_id,
                adapter_name="shadow_bridge",
                adapter_type="shadow_bridge",
                is_healthy=is_healthy,
                latency_ms=latency_ms,
                consecutive_failures=consecutive,
                error_message=error_message,
                metadata=metadata,
            )
        except Exception as e:
            return AdapterHealthRecord(
                site_id=site_id,
                adapter_name="shadow_bridge",
                adapter_type="shadow_bridge",
                is_healthy=False,
                latency_ms=(time.perf_counter() - start) * 1000,
                consecutive_failures=await self._count_consecutive_failures(site_id, "shadow_bridge"),
                error_message=str(e)[:200],
                metadata={},
            )

    async def _check_device_adapter(self, site_id: str, adapter_name: str, adapter: Any) -> AdapterHealthRecord:
        """Check a DeviceAdapter via its get_status() method."""
        start = time.perf_counter()
        try:
            # NiagaraBACnetAdapter returns DeviceStatus enum; BacnetBmsAdapter returns BmsConnectionStatus
            status = await asyncio.wait_for(adapter.get_status(), timeout=5.0)
            latency_ms = (time.perf_counter() - start) * 1000

            # Normalize different adapter return types
            is_healthy = self._extract_healthy(status)
            error_message = self._extract_message(status)
            consecutive = await self._count_consecutive_failures(site_id, adapter_name)

            return AdapterHealthRecord(
                site_id=site_id,
                adapter_name=adapter_name,
                adapter_type=self._infer_adapter_type(adapter_name, adapter),
                is_healthy=is_healthy,
                latency_ms=latency_ms,
                consecutive_failures=consecutive,
                error_message=error_message,
                metadata={},
            )
        except TimeoutError:
            return AdapterHealthRecord(
                site_id=site_id,
                adapter_name=adapter_name,
                adapter_type=self._infer_adapter_type(adapter_name, adapter),
                is_healthy=False,
                latency_ms=(time.perf_counter() - start) * 1000,
                consecutive_failures=await self._count_consecutive_failures(site_id, adapter_name),
                error_message="health check timed out after 5s",
                metadata={},
            )
        except Exception as e:
            return AdapterHealthRecord(
                site_id=site_id,
                adapter_name=adapter_name,
                adapter_type=self._infer_adapter_type(adapter_name, adapter),
                is_healthy=False,
                latency_ms=(time.perf_counter() - start) * 1000,
                consecutive_failures=await self._count_consecutive_failures(site_id, adapter_name),
                error_message=str(e)[:200],
                metadata={},
            )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def _record_and_alert(
        self, site_id: str, adapter_name: str, adapter_type: str, record: AdapterHealthRecord
    ) -> None:
        """Write health record to Supabase and handle alert logic."""
        from app.database.supabase_client import get_supabase_client

        supabase = get_supabase_client()
        now = datetime.now(UTC)

        try:
            # Upsert current state
            uptime_1h = await self._calculate_uptime(site_id, adapter_name, hours=1)
            uptime_24h = await self._calculate_uptime(site_id, adapter_name, hours=24)

            supabase.table("adapter_health_current").upsert(
                {
                    "site_id": site_id,
                    "adapter_name": adapter_name,
                    "adapter_type": adapter_type,
                    "is_healthy": record.is_healthy,
                    "last_check": now.isoformat(),
                    "consecutive_failures": record.consecutive_failures,
                    "uptime_1h_percent": uptime_1h,
                    "uptime_24h_percent": uptime_24h,
                    "updated_at": now.isoformat(),
                }
            ).execute()

            # Insert history row (one per cycle)
            supabase.table("adapter_health").insert(
                {
                    "site_id": site_id,
                    "adapter_name": adapter_name,
                    "adapter_type": adapter_type,
                    "timestamp": now.isoformat(),
                    "is_healthy": record.is_healthy,
                    "latency_ms": record.latency_ms,
                    "consecutive_failures": record.consecutive_failures,
                    "error_message": record.error_message,
                    "metadata": record.metadata,
                }
            ).execute()

        except Exception as e:
            logger.error(f"Failed to persist adapter health for {adapter_name}@{site_id}: {e}", exc_info=True)
            try:
                supabase.table("adapter_health_current").upsert(
                    {
                        "site_id": site_id,
                        "adapter_name": adapter_name,
                        "adapter_type": adapter_type,
                        "is_healthy": False,
                        "last_check": now.isoformat(),
                        "consecutive_failures": record.consecutive_failures,
                        "error_message": f"persist_failed: {e!s}",
                        "updated_at": now.isoformat(),
                    }
                ).execute()
            except Exception as inner_e:
                logger.error(f"Failed to write fallback health record for {adapter_name}@{site_id}: {inner_e}")

        # Alert logic — fire on Nth consecutive failure
        if record.consecutive_failures == _CONSECUTIVE_FAILURE_ALERT_THRESHOLD:
            await self._emit_alert(site_id, adapter_name, adapter_type, record)

    async def _emit_alert(
        self, site_id: str, adapter_name: str, adapter_type: str, record: AdapterHealthRecord
    ) -> None:
        """Write failure alert to DB and log critically."""
        from app.database.supabase_client import get_supabase_client

        supabase = get_supabase_client()
        now = datetime.now(UTC)

        # Critical if it's the bridge or BACnet, warning otherwise
        severity = "critical" if adapter_type in ("shadow_bridge", "bacnet", "niagara") else "warning"
        message = (
            f"[{severity.upper()}] {adapter_name}@{site_id}: "
            f"{_CONSECUTIVE_FAILURE_ALERT_THRESHOLD} consecutive health check failures — "
            f"{record.error_message or 'unknown error'}"
        )

        logger.error(message)

        try:
            supabase.table("adapter_health_alerts").insert(
                {
                    "site_id": site_id,
                    "adapter_name": adapter_name,
                    "alert_type": "failure",
                    "severity": severity,
                    "message": message,
                    "created_at": now.isoformat(),
                }
            ).execute()
        except Exception as e:
            logger.error(f"Failed to write adapter health alert: {e}")

    # BACnet alarm type mapping for intelligent descriptions
    _BACNET_ALARM_TYPES: ClassVar[dict[str, str]] = {
        # Temperature-related
        "temp_hi": "High temperature detected",
        "temp_high": "High temperature detected",
        "temp_lo": "Low temperature detected",
        "temp_low": "Low temperature detected",
        "temp_crit": "Critical temperature threshold exceeded",
        "high_temp": "High temperature alarm",
        "low_temp": "Low temperature alarm",
        "freeze": "Freeze protection alarm",
        # Pressure-related
        "filter_dp": "Filter differential pressure high - check/replace filter",
        "filter_hi": "Filter clogged - maintenance required",
        "dp_hi": "High differential pressure",
        "pressure_hi": "High pressure alarm",
        "pressure_lo": "Low pressure alarm",
        # Fan/Vibration
        "fan_fail": "Fan failure detected",
        "vib_warn": "Elevated vibration - bearing wear suspected",
        "vib_crit": "Critical vibration - immediate inspection required",
        "belt_fail": "Drive belt failure or slippage",
        # Power/Electrical
        "power_loss": "Power loss or phase failure",
        "overcurrent": "Overcurrent condition",
        "undervoltage": "Undervoltage condition",
        "compressor_fail": "Compressor failure or high amp draw",
        # Flow/Level
        "flow_lo": "Low flow detected",
        "flow_fail": "Flow failure - pump or valve issue",
        "level_hi": "High level alarm",
        "level_lo": "Low level alarm",
        # General
        "fault": "Equipment fault condition active",
        "offline": "Equipment communication lost",
        "sensor_fail": "Sensor failure or out of range",
        "maintenance": "Maintenance reminder - service due",
    }

    def _generate_alarm_description(self, alarm: dict[str, Any]) -> tuple[str, str]:
        """Generate meaningful title and message from alarm data.

        Returns: (title, message) with intelligent fallbacks
        """
        # Extract fields
        code = alarm.get("code") or alarm.get("alarm_code") or ""
        raw_msg = alarm.get("message") or alarm.get("description") or alarm.get("alarm_text") or ""
        equipment_id = alarm.get("equipment_id") or alarm.get("equipment_code") or ""
        object_type = alarm.get("object_type") or ""
        point_name = alarm.get("point_name") or ""

        # If we have a good message already, use it
        if raw_msg and len(raw_msg) > 10 and "BACnet alarm" not in raw_msg:
            if code:
                return f"Equipment fault: {code}", raw_msg
            return "Equipment fault detected", raw_msg

        # Try to extract equipment type from equipment_id (e.g., S002-AHU-001)
        equipment_type = "Equipment"
        equipment_name = equipment_id
        if equipment_id and "-" in equipment_id:
            parts = equipment_id.split("-")
            if len(parts) >= 2:
                type_code = parts[1].upper()
                type_map = {
                    "AHU": "Air Handling Unit",
                    "FCU": "Fan Coil Unit",
                    "VAV": "VAV Box",
                    "CHILLER": "Chiller",
                    "CT": "Cooling Tower",
                    "PUMP": "Pump",
                    "BESS": "Battery",
                    "GEN": "Generator",
                    "UPS": "UPS",
                }
                equipment_type = type_map.get(type_code, type_code)
                equipment_name = f"{equipment_type} {parts[2]}" if len(parts) > 2 else equipment_id

        # Try to map alarm code to description
        description = None
        code_lower = code.lower().replace("-", "_").replace(" ", "_")

        # Direct mapping
        if code_lower in self._BACNET_ALARM_TYPES:
            description = self._BACNET_ALARM_TYPES[code_lower]
        else:
            # Try partial matching
            for key, desc in self._BACNET_ALARM_TYPES.items():
                if key in code_lower or code_lower in key:
                    description = desc
                    break

        # If still no description, try object_type or point_name
        if not description:
            combined = f"{object_type} {point_name}".lower()
            if "temp" in combined or "temperature" in combined:
                description = "Temperature out of normal range"
            elif "filter" in combined or "dp" in combined:
                description = "Filter maintenance may be required"
            elif "fan" in combined:
                description = "Fan performance issue detected"
            elif "pressure" in combined:
                description = "Pressure outside normal operating range"
            elif "flow" in combined:
                description = "Flow rate anomaly detected"
            else:
                description = "Equipment operating outside normal parameters"

        # Build title
        title = f"{equipment_type} alert: {code}" if code else f"{equipment_type} fault detected"

        # Build message
        if equipment_id:
            message = f"{equipment_name} ({equipment_id}): {description}. Review equipment status and perform maintenance if needed."
        else:
            message = f"{description}. Equipment ID unknown - check BMS for details."

        return title, message

    async def _write_bridge_alerts(
        self,
        site_id: str,
        alarms: list[dict[str, Any]],
        *,
        is_complete_snapshot: bool = False,
        poll_succeeded: bool = True,
    ) -> None:
        """Upsert bridge alarms with lifecycle tracking.

        Designed for BACnet's persistent alarm model: the bridge returns the same
        alarm on every poll until it clears, with its original event timestamp.

        - No age filter: alarms are valid regardless of how old the original event is.
        - UPSERT by (site_id, source, source_dedupe_key) — never blindly INSERT.
        - Snapshot resolution: when is_complete_snapshot=True, alarms absent from
          the current poll are transitioned to 'resolved'.
        - On poll failure: all writes are skipped entirely.
        - ML lifecycle events emitted only on transitions (opened/cleared/reopened).
        """
        if not poll_succeeded:
            logger.debug("[BRIDGE ALERTS] Poll failed — skipping all alert writes for %s", site_id)
            return

        from app.database.supabase_client import get_supabase_client

        supabase = get_supabase_client()
        now = datetime.now(UTC)
        source = "bacnet_bridge"

        # Resolve site UUID
        try:
            site_row = supabase.table("sites").select("id").eq("code", site_id).execute()
            if not site_row.data:
                logger.warning("[BRIDGE ALERTS] Site not found: %s", site_id)
                return
            site_uuid = site_row.data[0]["id"]
        except Exception as e:
            logger.warning("[BRIDGE ALERTS] Could not resolve site UUID for %s: %s", site_id, e)
            return

        # ── Fetch current active alarms for transition detection ─────────────
        try:
            existing_resp = (
                supabase.table("alerts")
                .select("source_dedupe_key, lifecycle_state, occurrence_count")
                .eq("site_id", site_uuid)
                .eq("source", source)
                .neq("status", "resolved")
                .execute()
            )
            existing_map: dict[str, dict[str, Any]] = {
                r["source_dedupe_key"]: r for r in (existing_resp.data or []) if r.get("source_dedupe_key")
            }
        except Exception as e:
            logger.warning("[BRIDGE ALERTS] Could not fetch existing alarms: %s", e)
            existing_map = {}

        # ── Phase 1: Upsert each active alarm ────────────────────────────────
        seen_dedupe_keys: set[str] = set()
        transitions: list[tuple[str, str, str]] = []  # (dedupe_key, old_state, new_state)
        upserted = 0

        for alarm in alarms or []:
            # Cleared-state alarms are handled by snapshot resolution, not upserted as active
            if is_alarm_cleared(alarm):
                continue

            dedupe_key = build_source_dedupe_key(alarm)

            # Skip alarms with no parseable identity
            alarm_code = alarm.get("code") or alarm.get("alarm_code") or ""
            notif_class = alarm.get("notification_class") or alarm.get("notificationClass")
            obj_id = (
                alarm.get("object_id")
                or alarm.get("objectIdentifier")
                or alarm.get("objectId")
                or alarm.get("bacnet_object")
            )
            has_bacnet_identity = notif_class is not None and obj_id
            if not alarm_code and not has_bacnet_identity:
                logger.warning("[BRIDGE ALERTS] Skipping unparseable alarm (no code, no BACnet identity): %s", alarm)
                continue

            # Per-poll dedup: bridge may send the same alarm twice in one response
            if dedupe_key in seen_dedupe_keys:
                continue
            seen_dedupe_keys.add(dedupe_key)

            # Parse original event timestamp (immutable — written only on first INSERT)
            alarm_time_str = alarm.get("timestamp") or alarm.get("time")
            event_at: str = now.isoformat()
            if alarm_time_str:
                try:
                    alarm_dt = datetime.fromisoformat(alarm_time_str.replace("Z", "+00:00"))
                    if alarm_dt.tzinfo is None:
                        alarm_dt = alarm_dt.replace(tzinfo=UTC)
                    event_at = alarm_dt.isoformat()
                except (ValueError, TypeError):
                    pass

            # Severity: string labels take priority, then BACnet numeric priority
            # (bridge sends priority as integer; higher = more critical on this bridge)
            # to_state=FAULT always → critical regardless of numeric priority.
            raw_sev = alarm.get("severity") or ""
            numeric_priority = alarm.get("priority") if isinstance(alarm.get("priority"), (int, float)) else None
            to_state_upper = str(alarm.get("to_state") or "").upper()
            if (
                str(raw_sev).lower() in ("critical", "high", "fault", "active")
                or to_state_upper == "FAULT"
                or (numeric_priority is not None and numeric_priority >= 75)
            ):
                severity = "critical"
            else:
                severity = "warning"

            # Equipment FK resolution (best-effort; NULL on miss)
            equipment_id: str | None = alarm.get("equipment_id") or alarm.get("equipment_code") or None
            resolved_equipment_type: str | None = None
            if equipment_id:
                try:
                    eq_row = (
                        supabase.table("equipment").select("id, type").eq("code", equipment_id).maybe_single().execute()
                    )
                    if eq_row.data:
                        equipment_id = eq_row.data["id"]
                        resolved_equipment_type = eq_row.data.get("type")
                except Exception:
                    equipment_id = None

            # Licensing gate — skip alerts for equipment types whose module is
            # not licensed for this site (Platform modules always allowed)
            if resolved_equipment_type and site_id:
                from app.models.module_registry import ModuleType
                from app.services.module_registry_service import module_registry
                from app.services.simbiot.connection_policy import infer_module_from_equipment_type

                mt = infer_module_from_equipment_type(resolved_equipment_type)
                if (
                    mt
                    and mt not in (ModuleType.KPI, ModuleType.ML, ModuleType.ASSETS)
                    and not module_registry.is_module_active(site_id, mt)
                ):
                    continue

            title, message = self._generate_alarm_description(alarm)

            existing_row = existing_map.get(dedupe_key)
            is_reopen = existing_row is not None and existing_row.get("lifecycle_state") == "resolved"
            if not existing_row:
                occurrence_count = 1
                lifecycle_state = "active"
            elif is_reopen:
                occurrence_count = (existing_row.get("occurrence_count") or 1) + 1
                lifecycle_state = "reopened"
            else:
                occurrence_count = existing_row.get("occurrence_count") or 1
                lifecycle_state = "active"

            upsert_payload: dict[str, Any] = {
                "site_id": site_uuid,
                "source": source,
                "source_dedupe_key": dedupe_key,
                "equipment_id": equipment_id,
                "type": "fault",
                "severity": severity,
                "status": "active",
                "title": title,
                "message": message,
                "last_seen_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "lifecycle_state": lifecycle_state,
                "occurrence_count": occurrence_count,
            }

            # event_at and first_seen_at only on first INSERT
            # (DB trigger protects them from being overwritten on subsequent UPSERTs)
            if not existing_row:
                upsert_payload["event_at"] = event_at
                upsert_payload["first_seen_at"] = now.isoformat()
                upsert_payload["created_at"] = now.isoformat()

            try:
                supabase.table("alerts").upsert(
                    upsert_payload,
                    on_conflict="site_id,source,source_dedupe_key",
                ).execute()
                upserted += 1
                if is_reopen:
                    transitions.append((dedupe_key, "resolved", "active"))
                elif not existing_row:
                    transitions.append((dedupe_key, "none", "active"))
            except Exception as e:
                logger.error("[BRIDGE ALERTS] Upsert failed for %s: %s", dedupe_key, e)

        if upserted:
            logger.info("[BRIDGE ALERTS] Upserted %d alarms for %s", upserted, site_id)

        # ── Phase 2: Snapshot-based resolution ───────────────────────────────
        # Only resolve when the bridge response is a complete snapshot of active alarms.
        # Partial polls must not resolve anything they don't mention.
        if is_complete_snapshot and existing_map:
            resolved_keys = set(existing_map.keys()) - seen_dedupe_keys
            if resolved_keys:
                try:
                    for key in resolved_keys:
                        supabase.table("alerts").update(
                            {
                                "status": "resolved",
                                "lifecycle_state": "resolved",
                                "resolved_at": now.isoformat(),
                                "last_seen_at": now.isoformat(),
                                "updated_at": now.isoformat(),
                            }
                        ).eq("site_id", site_uuid).eq("source", source).eq("source_dedupe_key", key).execute()
                        transitions.append((key, "active", "resolved"))
                    logger.info(
                        "[BRIDGE ALERTS] Resolved %d alarms absent from snapshot for %s",
                        len(resolved_keys),
                        site_id,
                    )
                except Exception as e:
                    logger.error("[BRIDGE ALERTS] Snapshot resolution failed: %s", e)

        # ── Phase 3: ML lifecycle event stubs ────────────────────────────────
        if transitions:
            await self._emit_alarm_lifecycle_events(site_id, transitions)

    async def _emit_alarm_lifecycle_events(
        self,
        site_id: str,
        transitions: list[tuple[str, str, str]],
    ) -> None:
        """Emit ML lifecycle events for alarm state transitions.

        Phase 224 will wire these into the ML fault classifier training pipeline.
        For now: structured log only.
        """
        for dedupe_key, old_state, new_state in transitions:
            logger.info(
                "[ALARM LIFECYCLE] %s → %s | key=%s | site=%s",
                old_state,
                new_state,
                dedupe_key,
                site_id,
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _count_consecutive_failures(self, site_id: str, adapter_name: str) -> int:
        """Count consecutive failures in the lookback window from DB."""
        from app.database.supabase_client import get_supabase_client

        cache_key = f"{site_id}:{adapter_name}"
        cached = self._failure_cache.get(cache_key)

        cutoff = datetime.now(UTC) - timedelta(hours=_FAILURE_LOOKBACK_HOURS)

        try:
            supabase = get_supabase_client()
            result = (
                supabase.table("adapter_health")
                .select("is_healthy")
                .eq("site_id", site_id)
                .eq("adapter_name", adapter_name)
                .gte("timestamp", cutoff.isoformat())
                .order("timestamp", desc=True)
                .limit(_CONSECUTIVE_FAILURE_ALERT_THRESHOLD + 1)
                .execute()
            )

            count = 0 if not result.data else sum(1 for r in result.data if not r["is_healthy"])

            self._failure_cache[cache_key] = count
            return count

        except Exception as e:
            logger.warning(f"Could not count consecutive failures from DB: {e}, using cache")
            return cached if cached is not None else 0

    async def _calculate_uptime(self, site_id: str, adapter_name: str, hours: int) -> float | None:
        """Calculate uptime % over the last N hours."""
        from app.database.supabase_client import get_supabase_client

        cutoff = datetime.now(UTC) - timedelta(hours=hours)

        try:
            supabase = get_supabase_client()
            result = (
                supabase.table("adapter_health")
                .select("is_healthy")
                .eq("site_id", site_id)
                .eq("adapter_name", adapter_name)
                .gte("timestamp", cutoff.isoformat())
                .execute()
            )

            if not result.data:
                return None

            healthy = sum(1 for r in result.data if r["is_healthy"])
            return round(100 * healthy / len(result.data), 2)

        except Exception as e:
            logger.warning(f"Could not calculate uptime for {adapter_name}@{site_id}: {e}")
            return None

    @staticmethod
    def _get_monitored_sites(settings: Any) -> list[str]:
        """Return list of site IDs that should be monitored.

        Reads enabled bridge adapters from site_adapter_config so that
        new sites (e.g. site-005) are automatically included without
        code changes.
        """
        sites: list[str] = []
        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            result = client.table("site_adapter_config").select("site_id").eq("enabled", True).execute()
            sites = list({row["site_id"] for row in (result.data or [])})
        except Exception:
            logger.warning("Could not query site_adapter_config, falling back to site-002")
            sites = ["site-002"]
            if getattr(settings, "ENABLE_SITE001_SOURCE", False):
                sites.append("site-001")
        return sorted(sites)

    @staticmethod
    def _site_id_from_adapter(adapter: Any, _name: str, _settings: Any) -> str:
        """Extract site_id from an adapter's config or name."""
        # Try to get from adapter config
        if hasattr(adapter, "_config") and adapter._config:
            config = adapter._config
            site_id = getattr(config, "site_id", None)
            if site_id:
                return normalize_site_id(site_id, to_supabase=False)
        # Fall back to site-002
        return "site-002"

    @staticmethod
    def _infer_adapter_type(adapter_name: str, adapter: Any | None = None) -> str:
        """Infer adapter type from name and class."""
        name_lower = adapter_name.lower()
        if "shadow" in name_lower or "bridge" in name_lower:
            return "shadow_bridge"
        if "niagara" in name_lower:
            return "niagara"
        if "bacnet" in name_lower:
            return "bacnet"
        if "obix" in name_lower:
            return "obix"
        if "dali" in name_lower or "lighting" in name_lower:
            return "dali"
        if "mri" in name_lower or "concept" in name_lower or "document" in name_lower:
            return "concept_mri"
        # Infer from class name
        if adapter is not None:
            class_name = adapter.__class__.__name__.lower()
            if "niagara" in class_name:
                return "niagara"
            if "bacnet" in class_name:
                return "bacnet"
            if "obix" in class_name:
                return "obix"
            if "dali" in class_name or "lighting" in class_name:
                return "dali"
        return "unknown"

    @staticmethod
    def _extract_healthy(status: Any) -> bool:
        """Normalize get_status() result to boolean."""
        if isinstance(status, bool):
            return status
        if hasattr(status, "connected"):
            return bool(status.connected)
        if hasattr(status, "status"):
            s = str(getattr(status, "status", "")).lower()
            return s in ("connected", "online", "healthy", "operational")
        if isinstance(status, dict):
            return bool(status.get("connected") or status.get("healthy"))
        return False

    @staticmethod
    def _extract_message(status: Any) -> str | None:
        """Extract error/status message from get_status() result."""
        if hasattr(status, "message"):
            return str(status.message) or None
        if hasattr(status, "reason"):
            return str(status.reason) or None
        if isinstance(status, dict):
            return status.get("message") or status.get("reason") or None
        return None

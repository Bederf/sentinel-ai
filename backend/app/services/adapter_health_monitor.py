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
from typing import Any

from app.core.site_resolver import normalize_site_id

logger = logging.getLogger("adapter-health-monitor")

# Threshold for consecutive failures before alerting
_CONSECUTIVE_FAILURE_ALERT_THRESHOLD = 3

# How long to look back for consecutive-failure count
_FAILURE_LOOKBACK_HOURS = 1


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
            logger.error(f"Failed to persist adapter health for {adapter_name}@{site_id}: {e}")

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
    _BACNET_ALARM_TYPES: dict[str, str] = {
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

    async def _write_bridge_alerts(self, site_id: str, alarms: list[dict[str, Any]]) -> None:
        """Write active bridge alarms to the alerts table for cockpit posture.

        Deduplicates by alarm code + source to avoid flooding on repeated polls.
        Only writes alarms from the last poll cycle that are still active.
        """
        import uuid

        from app.database.supabase_client import get_supabase_client

        if not alarms:
            return

        supabase = get_supabase_client()
        now = datetime.now(UTC)

        # Resolve site UUID
        try:
            site_row = supabase.table("sites").select("id").eq("code", site_id).execute()
            if not site_row.data:
                logger.warning(f"[BRIDGE ALERTS] Site not found: {site_id}")
                return
            site_uuid = site_row.data[0]["id"]
        except Exception as e:
            logger.warning(f"[BRIDGE ALERTS] Could not resolve site UUID for {site_id}: {e}")
            return

        # Build a dedupe key from each alarm: use code + message hash
        seen_keys: set[str] = set()
        rows_to_insert = []

        for alarm in alarms:
            # Extract fields for dedupe and classification
            alarm_code = alarm.get("code") or alarm.get("alarm_code") or ""
            source_equipment = alarm.get("equipment_id") or alarm.get("equipment_code") or "UNKNOWN_EQUIPMENT"
            alarm_type = alarm.get("alarm_type") or alarm.get("event_type") or "UNCLASSIFIED"

            # Generate intelligent title and message
            title, message = self._generate_alarm_description(alarm)

            # Dedupe key: source_equipment + code + alarm_type (NOT title/message which vary)
            # When code is empty, collapse all instances of this alarm class into one entry
            dedupe_key = f"{source_equipment}|{alarm_code or 'UNPARSEABLE'}|{alarm_type}"
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)

            # Severity mapping — log UNPARSEABLE alarms
            raw_severity = str(alarm.get("severity") or alarm.get("priority") or "medium").lower()
            alarm_timestamp = alarm.get("timestamp") or alarm.get("time") or "unknown"
            bacnet_object_id = alarm.get("object_id") or alarm.get("objectIdentifier") or "unknown"
            bacnet_object_type = alarm.get("object_type") or alarm.get("objectType") or "unknown"
            if not alarm_code:
                logger.warning(
                    "[BRIDGE ALERTS] Unparseable alarm: source=%s type=%s obj_id=%s obj_type=%s ts=%s raw=%s",
                    source_equipment,
                    alarm_type,
                    bacnet_object_id,
                    bacnet_object_type,
                    alarm_timestamp,
                    alarm,
                )
                # Skip storing empty-code alarms — they indicate a bridge/BMS parsing issue
                # The warning is already logged; do not flood the alerts table
                continue
            if raw_severity in ("critical", "high", "fault", "active"):
                severity = "critical"
            elif raw_severity in ("warning", "warn", "elevated"):
                severity = "warning"
            else:
                severity = "warning"

            # Equipment ID resolution
            equipment_id = alarm.get("equipment_id") or alarm.get("equipment_code") or None
            if equipment_id:
                try:
                    eq_row = supabase.table("equipment").select("id").eq("code", equipment_id).maybe_single().execute()
                    if eq_row.data:
                        equipment_id = eq_row.data["id"]
                except Exception:
                    equipment_id = None

            rows_to_insert.append(
                {
                    "id": str(uuid.uuid4()),
                    "site_id": site_uuid,
                    "equipment_id": equipment_id,
                    "type": "fault",
                    "severity": severity,
                    "status": "active",
                    "title": title,
                    "message": message,
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                }
            )

        if not rows_to_insert:
            return

        # Deduplicate: skip if an identical (type, equipment_id, message_hash) alert
        # already exists for this site, regardless of age.
        # This prevents fault-alert storms where the same COV condition fires every minute.
        try:
            existing = (
                supabase.table("alerts")
                .select("equipment_id, type, message")
                .eq("site_id", site_uuid)
                .eq("status", "active")
                .execute()
            )

            # Build dedupe key: (type, equipment_id, message_hash)
            # For null equipment_id, use title as fallback identifier
            def _alert_key(r: dict) -> str:
                eq_id = r.get("equipment_id") or r.get("title", "UNKNOWN")
                return f"{r.get('type', '')}:{eq_id}:{r.get('message', '')}"

            existing_keys = {_alert_key(r) for r in (existing.data or [])}
            # Filter: skip row if its (type, equipment_id, message) already has an active alert
            rows_to_insert = [
                r
                for r in rows_to_insert
                if f"{r.get('type', '')}:{r.get('equipment_id') or r.get('title', 'UNKNOWN')}:{r.get('message', '')}"
                not in existing_keys
            ]
        except Exception as e:
            logger.warning(f"[BRIDGE ALERTS] Dedup query failed, inserting anyway: {e}")

        if not rows_to_insert:
            return

        try:
            supabase.table("alerts").insert(rows_to_insert).execute()
            logger.info(f"[BRIDGE ALERTS] Wrote {len(rows_to_insert)} alerts for {site_id}")
        except Exception as e:
            logger.error(f"[BRIDGE ALERTS] Failed to insert alerts: {e}")

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
        """Return list of site IDs that should be monitored."""
        sites = ["site-002"]
        if getattr(settings, "ENABLE_SITE001_SOURCE", False):
            sites.append("site-001")
        return sites

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

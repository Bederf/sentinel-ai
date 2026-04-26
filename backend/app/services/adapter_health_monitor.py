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
        """Check ShadowModePollingService bridge connectivity."""
        start = time.perf_counter()
        try:
            status = shadow.status
            latency_ms = (time.perf_counter() - start) * 1000

            if isinstance(status, dict) and status.get("connected"):
                is_healthy = True
                error_message = None
                metadata = {
                    "poll_count": status.get("poll_count"),
                    "ml_hours_ingested": status.get("ml_hours_ingested"),
                    "bridge_data_source": status.get("bridge_data_source"),
                }
            else:
                is_healthy = False
                reason = status.get("reason", "unknown") if isinstance(status, dict) else "unknown"
                error_message = f"bridge disconnected: {reason}"
                metadata = {}

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
        sites = []
        # site-002 is always monitored when enabled
        if getattr(settings, "ENABLE_SITE002_SOURCE", False):
            sites.append("site-002")
        if getattr(settings, "ENABLE_SITE001_SOURCE", False):
            sites.append("site-001")
        # Always include site-002 if nothing configured (default active site)
        if not sites:
            sites.append("site-002")
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

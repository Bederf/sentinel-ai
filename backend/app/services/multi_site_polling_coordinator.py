"""Multi-site polling coordinator for Shadow Bridge telemetry.

Reads enabled adapter configurations from site_adapter_config, creates one
ShadowModePollingService per active site, and polls all of them sequentially.

This replaces the old single-site pattern where the APScheduler job hardcoded
site-002. New sites are automatically included when their bridge adapter is
enabled in the database — no code changes required.

Sites are excluded when:
  - site_adapter_config.enabled = false  (adapter disabled)
  - No bridge row exists for the site

Service instances are cached per site_id so that BACnet object catalogs,
energy accumulators, and FCU state trackers survive across poll cycles.
"""

from __future__ import annotations

import logging
from typing import Any

from app.database.supabase_client import get_supabase_client
from app.services.bridge_disconnect_notifier import check_and_alert, record_poll_result
from app.services.shadow_mode_polling import ShadowModePollingService, resolve_site_bridge_token

logger = logging.getLogger("sentinel.multi_site_polling")

# site_id → human-readable name (populated from sites table on first fetch)
_site_names: dict[str, str] = {}


class MultiSitePollingCoordinator:
    """Coordinates shadow-mode bridge polling across all enabled sites."""

    def __init__(self) -> None:
        # site_id → ShadowModePollingService (cached, preserves catalog + accumulator state)
        self._services: dict[str, Any] = {}

    def poll_all(self) -> dict[str, Any]:
        """Poll all sites that have an enabled bridge adapter.

        Called by APScheduler sync job. Dispatches each site's poll() to
        the main event loop via run_coroutine_threadsafe.

        Returns:
            {site_id: poll_result_dict} for every site attempted.
        """
        import asyncio

        results: dict[str, Any] = {}
        configs = self._fetch_enabled_bridge_configs()

        if not configs:
            logger.warning("[COORDINATOR] No enabled bridge configs found — nothing to poll")
            return results

        logger.info("[COORDINATOR] Polling %d site(s): %s", len(configs), list(configs))

        from app.services.background_scheduler import scheduler_service

        _main = scheduler_service._main_loop
        if not _main or not _main.is_running():
            logger.error("[COORDINATOR] Main event loop not available — cannot poll")
            return results

        for site_id, connection_config in configs.items():
            try:
                svc = self._get_or_create_service(site_id, connection_config)
                result = asyncio.run_coroutine_threadsafe(svc.poll(), _main).result(timeout=120)
                results[site_id] = result
                errors = result.get("errors", [])
                all_failed = bool(errors) and result.get("equipment_states", 0) == 0
                site_name = _site_names.get(site_id)
                record_poll_result(site_id, has_errors=all_failed, site_name=site_name)
                check_and_alert(site_id, site_name=site_name)
                if errors:
                    logger.warning("[COORDINATOR] %s poll errors: %s", site_id, errors)
                else:
                    logger.warning(
                        "[COORDINATOR] %s: %d states, ml_hours=%s",
                        site_id,
                        result.get("equipment_states", 0),
                        result.get("ml_hours_ingested", "?"),
                    )
            except Exception as exc:
                logger.error("[COORDINATOR] %s poll failed: %s", site_id, exc, exc_info=True)
                results[site_id] = {"errors": [str(exc)]}
                record_poll_result(site_id, has_errors=True, site_name=_site_names.get(site_id))
                check_and_alert(site_id, site_name=_site_names.get(site_id))

        return results

    def _get_or_create_service(self, site_id: str, connection_config: dict[str, Any]) -> Any:
        """Return cached ShadowModePollingService for site_id, creating if needed.

        Caching preserves object catalog, energy accumulators, and FCU tracker
        across poll cycles — identical to the old singleton pattern.

        Uses the module-level singleton for site-002 so system health probes
        that also reference get_shadow_mode_polling_service() see the same instance.
        """
        if site_id == "site-002":
            from app.services.shadow_mode_polling import get_shadow_mode_polling_service

            svc = get_shadow_mode_polling_service()
            svc._override_bridge_url = connection_config.get("base_url")
            svc._override_bridge_token = resolve_site_bridge_token(site_id, connection_config)
            if svc not in self._services.values():
                self._services[site_id] = svc
                logger.info("[COORDINATOR] Using singleton polling service for %s", site_id)
            return self._services.get(site_id) or svc

        if site_id not in self._services:
            self._services[site_id] = ShadowModePollingService(
                site_id=site_id,
                bridge_url=connection_config.get("base_url"),
                bridge_token=resolve_site_bridge_token(site_id, connection_config),
            )
            logger.info("[COORDINATOR] Created polling service for %s", site_id)

        return self._services[site_id]

    def get_service_status(self, site_id: str) -> dict | None:
        """Return connection status for a site from its cached polling service.

        Returns None if no polling service exists for this site (i.e. the
        coordinator has never polled it, or the bridge adapter is disabled).
        """
        svc = self._services.get(site_id)
        if svc is None:
            return None
        return svc.status

    def _fetch_enabled_bridge_configs(self) -> dict[str, dict[str, Any]]:
        """Return {site_id: connection_config} for all enabled bridge adapters.

        Reads directly from Supabase without going through SiteAdapterManager
        to keep this module free of circular imports.
        """
        try:
            client = get_supabase_client()
            rows = (
                client.table("site_adapter_config")
                .select("site_id, connection_config")
                .eq("protocol", "bridge")
                .eq("enabled", True)
                .execute()
            )
            configs = {
                row["site_id"]: row["connection_config"]
                for row in (rows.data or [])
                if row.get("connection_config", {}).get("base_url")
                and resolve_site_bridge_token(str(row.get("site_id") or ""), row.get("connection_config") or {})
            }
            # Cache human-readable site names for alert messages
            if configs:
                try:
                    site_rows = client.table("sites").select("code, name").in_("code", list(configs.keys())).execute()
                    for s in site_rows.data or []:
                        _site_names[s["code"]] = s.get("name") or s["code"]
                except Exception:
                    pass
            return configs
        except Exception as exc:
            logger.error("[COORDINATOR] Failed to fetch bridge configs: %s", exc)
            return {}


# Module-level singleton — mirrors the existing get_shadow_mode_polling_service pattern
_coordinator: MultiSitePollingCoordinator | None = None


def get_multi_site_polling_coordinator() -> MultiSitePollingCoordinator:
    global _coordinator
    if _coordinator is None:
        _coordinator = MultiSitePollingCoordinator()
    return _coordinator

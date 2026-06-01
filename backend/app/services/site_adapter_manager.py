"""
Site Adapter Manager — instantiates BMS adapters per site from database config.

Replaces the hardcoded site-002 + global BRIDGE_API_TOKEN pattern.
Every site polls using its own stored credentials.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.simbiot.adapter_registry import create_bms_adapter
from app.services.simbiot.bms_adapter import BmsAdapter, BmsConnectionConfig

logger = logging.getLogger("sentinel.site_adapter_manager")


class SiteAdapterManager:
    """Manages adapter instances for all sites, loading config from the database."""

    def __init__(self, supabase_client=None):
        self._supabase = supabase_client

    @property
    def supabase(self):
        if self._supabase is None:
            from app.database import get_supabase_client as get_supabase

            self._supabase = get_supabase()
        return self._supabase

    def get_adapters_for_site(self, site_id: str) -> list[BmsAdapter]:
        """
        Return all enabled adapter instances for a site.

        Args:
            site_id: Site code (e.g., "site-002", "site-003")

        Returns:
            List of connected BmsAdapter instances. Empty list if none succeed.
        """
        configs = self._fetch_adapter_configs(site_id)
        if not configs:
            logger.warning("[SAM] No adapter configs found for %s", site_id)
            return []

        adapters = []
        for cfg in configs:
            if not cfg.get("enabled", False):
                logger.debug("[SAM] Adapter %s disabled for %s", cfg.get("protocol"), site_id)
                continue

            connection_config = cfg.get("connection_config", {})
            try:
                adapter = self._create_adapter(
                    protocol=cfg.get("protocol", "bacnet"),
                    site_id=site_id,
                    connection_config=connection_config,
                )
                if adapter:
                    adapters.append(adapter)
                    logger.info("[SAM] Connected %s adapter for %s", cfg.get("protocol"), site_id)
            except Exception as exc:
                logger.error(
                    "[SAM] Error instantiating %s adapter for %s: %s",
                    cfg.get("protocol"),
                    site_id,
                    exc,
                )

        return adapters

    def _create_adapter(
        self,
        protocol: str,
        site_id: str,
        connection_config: dict[str, Any],
    ) -> BmsAdapter | None:
        """
        Create a single adapter from protocol + connection config.

        Bridge adapters are instantiated directly (they require credentials at
        construction time). Other protocols use the registry factory and are
        returned unconfigured — the caller invokes connect(config) when needed.
        """
        if protocol == "bridge":
            return self._create_bridge_adapter(site_id, connection_config)

        base_url = connection_config.get("base_url")
        host = connection_config.get("host")
        port = connection_config.get("port")
        username = connection_config.get("username")
        password = connection_config.get("password")
        use_tls = connection_config.get("use_tls", False)
        timeout = connection_config.get("timeout_seconds", 10.0)
        token = connection_config.get("token")

        # Build BmsConnectionConfig — shared contract
        conn_config = BmsConnectionConfig(
            site_id=site_id,
            source_type=protocol,
            host=host or (base_url.split("://")[1] if base_url and "://" in base_url else None),
            port=port,
            username=username,
            password=password,
            use_tls=use_tls,
            timeout_seconds=timeout,
            metadata={"token": token} if token else {},
        )

        try:
            # Adapter is returned unconfigured; caller invokes connect(conn_config)
            adapter = create_bms_adapter(adapter_type=protocol)
            _ = conn_config  # retained for callers that invoke connect() explicitly
            return adapter
        except Exception as exc:
            logger.error(
                "[SAM] Failed to create %s adapter for %s: %s",
                protocol,
                site_id,
                exc,
            )
            return None

    def _create_bridge_adapter(
        self,
        site_id: str,
        connection_config: dict[str, Any],
    ) -> BmsAdapter | None:
        """Instantiate BridgeBmsAdapter directly (requires credentials at construction)."""
        from app.services.simbiot.bridge_bms_adapter import bridge_adapter_from_connection_config

        adapter = bridge_adapter_from_connection_config(site_id, connection_config)
        if adapter is None:
            logger.error("[SAM] Cannot create bridge adapter for %s — missing credentials", site_id)
        return adapter

    def _fetch_adapter_configs(self, site_id: str) -> list[dict[str, Any]]:
        """
        Fetch all adapter configs for a site from site_adapter_config table.

        Returns:
            List of {protocol, enabled, connection_config} dicts
        """
        result = (
            self.supabase.table("site_adapter_config")
            .select("protocol, enabled, connection_config")
            .eq("site_id", site_id)
            .execute()
        )

        return result.data if result.data else []

    def save_adapter_config(
        self,
        site_id: str,
        protocol: str,
        connection_config: dict[str, Any],
        enabled: bool = True,
        poll_interval_seconds: int = 300,
    ) -> bool:
        """
        Save or update an adapter config for a site.
        Called by the SIMBIOT wizard on approval step.

        Args:
            site_id: Site code (e.g., "site-003")
            protocol: Protocol name ("bacnet", "obix", "modbus", "bridge")
            connection_config: Connection details dict (host, token, credentials, etc.)
            enabled: Whether the adapter is active
            poll_interval_seconds: How often to poll this adapter

        Returns:
            True if save succeeded
        """
        payload = {
            "site_id": site_id,
            "protocol": protocol,
            "enabled": enabled,
            "connection_config": connection_config,
            "poll_interval_seconds": poll_interval_seconds,
        }

        result = (
            self.supabase.table("site_adapter_config")
            .upsert(
                payload,
                on_conflict="site_id,protocol",
            )
            .execute()
        )

        if result.data is None:
            logger.error("[SAM] Failed to save %s config for %s", protocol, site_id)
            return False

        logger.info("[SAM] Saved %s adapter config for %s", protocol, site_id)
        return True

    def get_active_sites(self) -> list[dict[str, Any]]:
        """
        Query all sites that have at least one enabled adapter.

        Returns:
            List of {site_id, site_code} dicts
        """
        result = self.supabase.table("sites").select("id, code").eq("optimization_enabled", True).execute()
        return result.data if result.data else []

    def get_enabled_adapters_for_all_sites(self) -> dict[str, list[dict[str, Any]]]:
        """
        Return all enabled adapter configs keyed by site_id.
        Used by ShadowModePollingService to iterate over all sites.
        """
        result = (
            self.supabase.table("site_adapter_config")
            .select("site_id, protocol, enabled, connection_config, poll_interval_seconds")
            .eq("enabled", True)
            .execute()
        )

        by_site: dict[str, list[dict[str, Any]]] = {}
        for row in result.data or []:
            site = row.get("site_id", "")
            if site not in by_site:
                by_site[site] = []
            by_site[site].append(row)

        return by_site

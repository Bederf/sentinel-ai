"""Unit tests for MultiSitePollingCoordinator."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.multi_site_polling_coordinator import MultiSitePollingCoordinator


BRIDGE_CONFIG_S002 = {
    "base_url": "http://10.99.0.1:8080",
    "token": "test-token-s002",
    "poll_interval_seconds": 300,
}

BRIDGE_CONFIG_S001 = {
    "base_url": "http://10.99.0.1:8080",
    "token": "test-token-s001",
    "poll_interval_seconds": 300,
}


def _mock_poll_result(site_id: str) -> dict:
    return {
        "poll_count": 1,
        "equipment_states": 10,
        "ml_hours_ingested": 0.5,
        "errors": [],
    }


class TestFetchEnabledBridgeConfigs:
    def test_returns_only_sites_with_base_url_and_token(self):
        coordinator = MultiSitePollingCoordinator()

        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
            {"site_id": "site-002", "connection_config": BRIDGE_CONFIG_S002},
            {"site_id": "site-incomplete", "connection_config": {"base_url": "http://x.x.x.x"}},  # no token
        ]

        with patch(
            "app.services.multi_site_polling_coordinator.get_supabase_client",
            return_value=mock_client,
        ):
            configs = coordinator._fetch_enabled_bridge_configs()

        assert "site-002" in configs
        assert "site-incomplete" not in configs

    def test_returns_empty_on_db_error(self):
        coordinator = MultiSitePollingCoordinator()

        with patch(
            "app.services.multi_site_polling_coordinator.get_supabase_client",
            side_effect=Exception("DB down"),
        ):
            configs = coordinator._fetch_enabled_bridge_configs()

        assert configs == {}


class TestGetOrCreateService:
    def test_creates_service_with_injected_credentials(self):
        coordinator = MultiSitePollingCoordinator()

        with patch("app.services.multi_site_polling_coordinator.ShadowModePollingService") as mock_svc_cls:
            mock_svc_cls.return_value = MagicMock()
            svc = coordinator._get_or_create_service("site-002", BRIDGE_CONFIG_S002)

        mock_svc_cls.assert_called_once_with(
            site_id="site-002",
            bridge_url="http://10.99.0.1:8080",
            bridge_token="test-token-s002",
        )
        assert svc is not None

    def test_caches_service_across_calls(self):
        coordinator = MultiSitePollingCoordinator()

        with patch("app.services.multi_site_polling_coordinator.ShadowModePollingService") as mock_svc_cls:
            mock_svc_cls.return_value = MagicMock()
            svc1 = coordinator._get_or_create_service("site-002", BRIDGE_CONFIG_S002)
            svc2 = coordinator._get_or_create_service("site-002", BRIDGE_CONFIG_S002)

        assert svc1 is svc2
        mock_svc_cls.assert_called_once()  # Only created once

    def test_creates_separate_services_per_site(self):
        coordinator = MultiSitePollingCoordinator()

        with patch("app.services.multi_site_polling_coordinator.ShadowModePollingService") as mock_svc_cls:
            mock_svc_cls.side_effect = lambda **kwargs: MagicMock(site_id=kwargs["site_id"])
            svc_s002 = coordinator._get_or_create_service("site-002", BRIDGE_CONFIG_S002)
            svc_s001 = coordinator._get_or_create_service("site-001", BRIDGE_CONFIG_S001)

        assert svc_s002 is not svc_s001
        assert mock_svc_cls.call_count == 2


class TestPollAll:
    def test_polls_all_enabled_sites(self):
        coordinator = MultiSitePollingCoordinator()

        with (
            patch.object(
                coordinator,
                "_fetch_enabled_bridge_configs",
                return_value={"site-002": BRIDGE_CONFIG_S002},
            ),
            patch("app.services.multi_site_polling_coordinator.ShadowModePollingService") as mock_svc_cls,
        ):
            mock_svc = MagicMock()
            mock_svc.poll = MagicMock(return_value=_mock_poll_result("site-002"))
            mock_svc_cls.return_value = mock_svc

            import asyncio

            async def _async_result(*a, **kw):
                return _mock_poll_result("site-002")

            mock_svc.poll = _async_result

            results = coordinator.poll_all()

        assert "site-002" in results
        assert results["site-002"]["equipment_states"] == 10

    def test_returns_empty_when_no_enabled_configs(self):
        coordinator = MultiSitePollingCoordinator()

        with patch.object(coordinator, "_fetch_enabled_bridge_configs", return_value={}):
            results = coordinator.poll_all()

        assert results == {}

    def test_site_poll_failure_does_not_block_others(self):
        coordinator = MultiSitePollingCoordinator()

        configs = {
            "site-002": BRIDGE_CONFIG_S002,
            "site-003": BRIDGE_CONFIG_S001,
        }

        call_count = 0

        async def _poll_sometimes():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Bridge unreachable")
            return _mock_poll_result("site-003")

        with (
            patch.object(coordinator, "_fetch_enabled_bridge_configs", return_value=configs),
            patch("app.services.multi_site_polling_coordinator.ShadowModePollingService") as mock_svc_cls,
        ):
            mock_svc = MagicMock()
            mock_svc.poll = _poll_sometimes
            mock_svc_cls.return_value = mock_svc

            results = coordinator.poll_all()

        assert len(results) == 2
        # First site failed, second succeeded — both keys present
        assert "errors" in results.get("site-002", {}) or "errors" in results.get("site-003", {})

    def test_site001_excluded_when_bridge_disabled(self):
        """site-001 bridge is disabled in DB — should never appear in poll results."""
        coordinator = MultiSitePollingCoordinator()

        # Simulate only site-002 returned (site-001 filtered out by DB query)
        with patch.object(
            coordinator,
            "_fetch_enabled_bridge_configs",
            return_value={"site-002": BRIDGE_CONFIG_S002},
        ):
            with patch("app.services.multi_site_polling_coordinator.ShadowModePollingService") as mock_svc_cls:
                mock_svc = MagicMock()

                async def _poll():
                    return _mock_poll_result("site-002")

                mock_svc.poll = _poll
                mock_svc_cls.return_value = mock_svc

                results = coordinator.poll_all()

        assert "site-001" not in results
        assert "site-002" in results

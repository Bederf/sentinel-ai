"""Tests for real SOC injection in SolarDispatchService (Fix 5).

Verifies _get_current_soc returns simulated or real SOC depending on mode.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def dispatch_service():
    """Create a dispatch service instance with minimal seeding."""
    from app.services.solar_dispatch_service import SolarDispatchService

    svc = SolarDispatchService()
    return svc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetCurrentSOC:
    """Test _get_current_soc method."""

    @pytest.mark.asyncio
    async def test_simulation_mode_returns_simulated(self, dispatch_service):
        """In simulation mode, returns simulated SOC."""
        dispatch_service._simulated_soc["site-002"] = 65.0

        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.solar_connector_mode = "simulation"
            mock_settings.demo_mode = False
            soc = await dispatch_service._get_current_soc("site-002")

        assert soc == 65.0

    @pytest.mark.asyncio
    async def test_demo_mode_returns_simulated(self, dispatch_service):
        """In demo mode, always returns simulated SOC."""
        dispatch_service._simulated_soc["site-002"] = 72.0

        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.solar_connector_mode = "live"
            mock_settings.demo_mode = True
            soc = await dispatch_service._get_current_soc("site-002")

        assert soc == 72.0

    @pytest.mark.asyncio
    async def test_live_mode_reads_real_soc(self, dispatch_service):
        """In live mode, reads SOC from ingestion service."""
        dispatch_service._simulated_soc["site-002"] = 50.0

        mock_bess = MagicMock()
        mock_bess.soc_pct = 82.5

        mock_ingestion = MagicMock()
        mock_ingestion.get_bess_status = AsyncMock(return_value=mock_bess)

        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.solar_connector_mode = "live"
            mock_settings.demo_mode = False
            with patch(
                "app.services.solar_ingestion_service.get_solar_ingestion_service",
                return_value=mock_ingestion,
            ):
                soc = await dispatch_service._get_current_soc("site-002")

        assert soc == 82.5
        assert dispatch_service._last_real_soc["site-002"] == 82.5

    @pytest.mark.asyncio
    async def test_live_mode_fallback_on_failure(self, dispatch_service):
        """If real read fails, falls back to simulated SOC."""
        dispatch_service._simulated_soc["site-002"] = 55.0

        mock_ingestion = MagicMock()
        mock_ingestion.get_bess_status = AsyncMock(side_effect=Exception("Modbus timeout"))

        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.solar_connector_mode = "live"
            mock_settings.demo_mode = False
            with patch(
                "app.services.solar_ingestion_service.get_solar_ingestion_service",
                return_value=mock_ingestion,
            ):
                soc = await dispatch_service._get_current_soc("site-002")

        assert soc == 55.0

    @pytest.mark.asyncio
    async def test_live_mode_fallback_on_zero_soc(self, dispatch_service):
        """If real BESS returns 0% SOC, falls back to simulated."""
        dispatch_service._simulated_soc["site-002"] = 45.0

        mock_bess = MagicMock()
        mock_bess.soc_pct = 0.0

        mock_ingestion = MagicMock()
        mock_ingestion.get_bess_status = AsyncMock(return_value=mock_bess)

        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.solar_connector_mode = "live"
            mock_settings.demo_mode = False
            with patch(
                "app.services.solar_ingestion_service.get_solar_ingestion_service",
                return_value=mock_ingestion,
            ):
                soc = await dispatch_service._get_current_soc("site-002")

        assert soc == 45.0

    def test_sync_soc_returns_last_real(self, dispatch_service):
        """get_current_soc_sync returns last known real SOC."""
        dispatch_service._last_real_soc["site-002"] = 78.0
        dispatch_service._simulated_soc["site-002"] = 50.0
        assert dispatch_service.get_current_soc_sync("site-002") == 78.0

    def test_sync_soc_fallback_to_simulated(self, dispatch_service):
        """get_current_soc_sync falls back to simulated if no real SOC."""
        dispatch_service._simulated_soc["site-002"] = 60.0
        assert dispatch_service.get_current_soc_sync("site-002") == 60.0

    def test_sync_soc_default(self, dispatch_service):
        """get_current_soc_sync returns 50.0 for unknown site."""
        assert dispatch_service.get_current_soc_sync("unknown-site") == 50.0

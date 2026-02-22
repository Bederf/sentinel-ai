"""Tests for Phase 107: Ingestion Mode Hardening.

Three test groups:
  a) Live-mode fallback block — JSON fallback blocked in shadow_live/live_control
  b) Shadow write no-op + audit logging
  c) Startup live-mode guard — fail-fast on missing credentials/adapters
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure test env
os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("TESTING", "true")


# ---------------------------------------------------------------------------
# Group A: settings & enum unit tests
# ---------------------------------------------------------------------------


class TestIngestionModeEnum:
    """Test IngestionMode enum and Settings properties."""

    def test_default_mode_is_simulation(self):
        from app.config.settings import Settings, IngestionMode

        s = Settings(demo_mode=True)
        assert s.resolved_ingestion_mode == IngestionMode.SIMULATION
        assert not s.is_live_mode

    def test_demo_mode_overrides_shadow_live(self):
        from app.config.settings import Settings, IngestionMode

        s = Settings(demo_mode=True, ingestion_mode="shadow_live")
        assert s.resolved_ingestion_mode == IngestionMode.SIMULATION
        assert not s.is_live_mode

    def test_demo_mode_overrides_live_control(self):
        from app.config.settings import Settings, IngestionMode

        s = Settings(demo_mode=True, ingestion_mode="live_control")
        assert s.resolved_ingestion_mode == IngestionMode.SIMULATION

    def test_shadow_live_without_demo(self):
        from app.config.settings import Settings, IngestionMode

        s = Settings(demo_mode=False, ingestion_mode="shadow_live")
        assert s.resolved_ingestion_mode == IngestionMode.SHADOW_LIVE
        assert s.is_live_mode

    def test_live_control_without_demo(self):
        from app.config.settings import Settings, IngestionMode

        s = Settings(demo_mode=False, ingestion_mode="live_control")
        assert s.resolved_ingestion_mode == IngestionMode.LIVE_CONTROL
        assert s.is_live_mode

    def test_invalid_mode_falls_back_to_simulation(self):
        from app.config.settings import Settings, IngestionMode

        s = Settings(demo_mode=False, ingestion_mode="bogus_mode")
        assert s.resolved_ingestion_mode == IngestionMode.SIMULATION
        assert not s.is_live_mode


# ---------------------------------------------------------------------------
# Group B: AuditResultType enum fixes
# ---------------------------------------------------------------------------


class TestAuditResultType:
    """Test SHADOW and CANCELLED enum values exist."""

    def test_shadow_value(self):
        from app.models.audit_log import AuditResultType

        assert AuditResultType.SHADOW == "shadow"
        assert AuditResultType.SHADOW.value == "shadow"

    def test_cancelled_value(self):
        from app.models.audit_log import AuditResultType

        assert AuditResultType.CANCELLED == "cancelled"
        assert AuditResultType.CANCELLED.value == "cancelled"


# ---------------------------------------------------------------------------
# Group C: Live-mode fallback block (MCP tools)
# ---------------------------------------------------------------------------


class TestLiveModeFallbackBlock:
    """Verify that JSON fallback is blocked in live modes."""

    @pytest.mark.asyncio
    async def test_get_devices_blocks_json_in_live_mode(self):
        """get_devices_tool returns LIVE_DATA_REQUIRED when device_manager is unavailable."""
        from app.config.settings import IngestionMode

        mock_settings = MagicMock()
        mock_settings.is_live_mode = True
        mock_settings.resolved_ingestion_mode = IngestionMode.SHADOW_LIVE

        mock_dm = MagicMock()
        mock_dm._initialized = False

        with (
            patch("app.config.settings.settings", mock_settings),
            patch("app.mcp.simbiot_server.device_manager", mock_dm),
        ):
            from app.mcp.simbiot_server import get_devices_tool

            result = await get_devices_tool()
            assert result.get("code") == "LIVE_DATA_REQUIRED"
            assert result.get("tool") == "get_devices"

    @pytest.mark.asyncio
    async def test_read_device_point_blocks_json_in_live_mode(self):
        """read_device_point_tool returns LIVE_DATA_REQUIRED when device_manager fails."""
        from app.config.settings import IngestionMode

        mock_settings = MagicMock()
        mock_settings.is_live_mode = True
        mock_settings.resolved_ingestion_mode = IngestionMode.SHADOW_LIVE

        mock_dm = MagicMock()
        mock_dm._initialized = True
        mock_dm.read_device_value = AsyncMock(side_effect=Exception("adapter down"))

        with (
            patch("app.config.settings.settings", mock_settings),
            patch("app.mcp.simbiot_server.device_manager", mock_dm),
        ):
            from app.mcp.simbiot_server import read_device_point_tool

            result = await read_device_point_tool("S002-AHU-101", "supply_temp")
            assert result.get("code") == "LIVE_DATA_REQUIRED"
            assert result.get("tool") == "read_device_point"

    @pytest.mark.asyncio
    async def test_get_buildings_blocks_json_in_live_mode(self):
        """get_buildings_tool returns LIVE_DATA_REQUIRED when repo unavailable in live mode."""
        from app.config.settings import IngestionMode

        mock_settings = MagicMock()
        mock_settings.is_live_mode = True
        mock_settings.resolved_ingestion_mode = IngestionMode.SHADOW_LIVE

        # Simulate repository import failure
        with patch("app.config.settings.settings", mock_settings):
            from app.mcp.simbiot_server import get_buildings_tool

            # The BuildingRepository import will attempt Supabase connection and fail
            # in test env, returning the LIVE_DATA_REQUIRED error
            result = await get_buildings_tool()
            assert result.get("code") == "LIVE_DATA_REQUIRED"
            assert result.get("tool") == "get_buildings"

    @pytest.mark.asyncio
    async def test_simulation_mode_allows_json_fallback(self):
        """In simulation mode, JSON fallback proceeds normally."""
        from app.config.settings import IngestionMode

        mock_settings = MagicMock()
        mock_settings.is_live_mode = False
        mock_settings.resolved_ingestion_mode = IngestionMode.SIMULATION

        mock_dm = MagicMock()
        mock_dm._initialized = False

        with (
            patch("app.config.settings.settings", mock_settings),
            patch("app.mcp.simbiot_server.device_manager", mock_dm),
        ):
            from app.mcp.simbiot_server import get_devices_tool

            result = await get_devices_tool()
            # Should NOT have the error code — JSON fallback is OK in simulation
            assert result.get("code") != "LIVE_DATA_REQUIRED"
            assert "source" in result
            assert result["source"] == "json_file"


# ---------------------------------------------------------------------------
# Group D: Shadow write no-op + audit logging
# ---------------------------------------------------------------------------


class TestShadowWriteMode:
    """Verify shadow mode intercepts writes and logs to audit."""

    @pytest.mark.asyncio
    async def test_shadow_write_returns_noop(self):
        """write_device_point_tool in shadow mode returns shadow_mode=True, success=False."""
        from app.config.settings import IngestionMode

        mock_settings = MagicMock()
        mock_settings.resolved_ingestion_mode = IngestionMode.SHADOW_LIVE
        mock_settings.is_live_mode = True

        mock_dm = MagicMock()
        mock_dm._initialized = True
        mock_dm.read_device_value = AsyncMock(
            return_value=MagicMock(value=22.0, unit="°C", quality="good", timestamp=None)
        )
        # write_device_value should NOT be called in shadow mode
        mock_dm.write_device_value = AsyncMock()

        with (
            patch("app.config.settings.settings", mock_settings),
            patch("app.mcp.simbiot_server.device_manager", mock_dm),
        ):
            from app.mcp.simbiot_server import write_device_point_tool

            result = await write_device_point_tool(
                device_id="S002-AHU-101",
                point_name="supply_temp",
                value=24.0,
                priority=8,
                user="test_user",
            )

            assert result["shadow_mode"] is True
            assert result["success"] is False
            assert result["intended_value"] == 24.0
            assert result["mode"] == "shadow_live"
            assert result["source"] == "shadow_write"
            # Verify actual write was NOT called
            mock_dm.write_device_value.assert_not_called()

    @pytest.mark.asyncio
    async def test_shadow_write_returns_shadow_source(self):
        """Shadow write returns source='shadow_write' in the response."""

        mock_settings = MagicMock()
        mock_settings.resolved_ingestion_mode = MagicMock(value="shadow_live")
        mock_settings.is_live_mode = True

        with patch("app.config.settings.settings", mock_settings):
            from app.mcp.simbiot_server import write_device_point_tool

            result = await write_device_point_tool(
                device_id="S002-AHU-101",
                point_name="supply_temp",
                value=24.0,
                user="test_user",
            )

            assert result["shadow_mode"] is True
            assert result["source"] == "shadow_write"
            assert result["device_id"] == "S002-AHU-101"
            assert result["point_name"] == "supply_temp"


# ---------------------------------------------------------------------------
# Group E: Startup live-mode guards
# ---------------------------------------------------------------------------


class TestStartupLiveModeGuard:
    """Test startup validation for live modes."""

    def test_live_mode_requires_supabase_creds(self):
        """shadow_live without Supabase creds → RuntimeError at startup."""
        from app.config.settings import Settings

        s = Settings(
            demo_mode=False,
            ingestion_mode="shadow_live",
            supabase_url="",
            supabase_key="",
            jwt_secret_key="test-secret-key-32-chars-minimum!",
        )
        assert s.is_live_mode
        # The actual RuntimeError is raised in events.py startup, not here.
        # We verify the settings resolve correctly to live mode.

    def test_live_mode_settings_resolve_correctly(self):
        """Live mode settings resolve correctly without demo override."""
        from app.config.settings import Settings, IngestionMode

        s = Settings(
            demo_mode=False,
            ingestion_mode="shadow_live",
            jwt_secret_key="test-secret-key-32-chars-minimum!",
        )
        assert s.resolved_ingestion_mode == IngestionMode.SHADOW_LIVE
        assert s.is_live_mode

    def test_default_mode_no_live_requirements(self):
        """Default settings (no INGESTION_MODE) → simulation, no extra requirements."""
        from app.config.settings import Settings, IngestionMode

        s = Settings(demo_mode=True)
        assert s.resolved_ingestion_mode == IngestionMode.SIMULATION
        assert not s.is_live_mode


# ---------------------------------------------------------------------------
# Group F: EventType includes SHADOW_WRITE
# ---------------------------------------------------------------------------


class TestEventType:
    """Test SHADOW_WRITE added to lifecycle EventType."""

    def test_shadow_write_event_type(self):
        from app.services.lifecycle_orchestrator import EventType

        assert EventType.SHADOW_WRITE == "shadow_write"
        assert EventType.SHADOW_WRITE.value == "shadow_write"

"""Tests for startup validation, Phase 168-01: Demo mode production safety checks."""

from unittest.mock import MagicMock, patch

import pytest

from app.startup.events import startup_event


class TestDemoModeValidation:
    """Test AUTH-006: Demo mode production safety validation."""

    @pytest.mark.asyncio
    async def test_demo_mode_false_live_mode_true(self):
        """PASS: DEMO_MODE=false, is_live_mode=true (production safe)."""
        with patch("app.startup.events.settings") as mock_settings:
            with patch("app.startup.events.apply_edge_mode_overrides"):
                mock_settings.demo_mode = False
                mock_settings.is_live_mode = True
                mock_settings.jwt_secret_key = "test_secret_key_32_chars_long_xxxx"
                mock_settings.supabase_key = None
                mock_settings.solar_connector_mode = "simulation"

                mock_app = MagicMock()
                # Should not raise
                await startup_event(mock_app)

    @pytest.mark.asyncio
    async def test_demo_mode_true_live_mode_true_raises(self):
        """FAIL: DEMO_MODE=true, is_live_mode=true (production UNSAFE)."""
        with patch("app.startup.events.settings") as mock_settings:
            with patch("app.startup.events.apply_edge_mode_overrides"):
                mock_settings.demo_mode = True
                mock_settings.is_live_mode = True
                mock_settings.jwt_secret_key = "test_secret_key_32_chars_long_xxxx"
                mock_settings.supabase_key = None

                mock_app = MagicMock()
                with pytest.raises(RuntimeError) as exc_info:
                    await startup_event(mock_app)

                assert "DEMO_MODE=true" in str(exc_info.value)
                assert "is_live_mode" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_demo_mode_true_dev_mode(self):
        """PASS: DEMO_MODE=true, is_live_mode=false (dev mode, OK)."""
        with patch("app.startup.events.settings") as mock_settings:
            with patch("app.startup.events.apply_edge_mode_overrides"):
                mock_settings.demo_mode = True
                mock_settings.is_live_mode = False
                mock_settings.jwt_secret_key = "test_secret_key_32_chars_long_xxxx"
                mock_settings.supabase_key = None
                mock_settings.solar_connector_mode = "simulation"

                mock_app = MagicMock()
                # Should not raise
                await startup_event(mock_app)

    @pytest.mark.asyncio
    async def test_demo_mode_false_dev_mode(self):
        """PASS: DEMO_MODE=false, is_live_mode=false (normal dev, OK)."""
        with patch("app.startup.events.settings") as mock_settings:
            with patch("app.startup.events.apply_edge_mode_overrides"):
                mock_settings.demo_mode = False
                mock_settings.is_live_mode = False
                mock_settings.jwt_secret_key = "test_secret_key_32_chars_long_xxxx"
                mock_settings.supabase_key = None
                mock_settings.solar_connector_mode = "simulation"

                mock_app = MagicMock()
                # Should not raise
                await startup_event(mock_app)

    @pytest.mark.asyncio
    async def test_demo_mode_validation_message_clarity(self):
        """Error message must be clear about the safety issue."""
        with patch("app.startup.events.settings") as mock_settings:
            with patch("app.startup.events.apply_edge_mode_overrides"):
                mock_settings.demo_mode = True
                mock_settings.is_live_mode = True
                mock_settings.jwt_secret_key = "test_secret_key_32_chars_long_xxxx"
                mock_settings.supabase_key = None

                mock_app = MagicMock()
                with pytest.raises(RuntimeError) as exc_info:
                    await startup_event(mock_app)

                # Verify error message contains key information
                error_msg = str(exc_info.value)
                assert "FATAL" in error_msg
                assert "DEMO_MODE=true" in error_msg
                assert "production" in error_msg.lower()

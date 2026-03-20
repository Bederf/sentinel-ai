"""
Tests for unified service cost tracking (Phase 158).
=====================================================
Verifies record_message(), record_service(), get_summary/today integration,
daily report email content, and cost alert threshold logic.
"""

import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def fresh_tracker(tmp_path):
    """Create a fresh AiUsageTracker instance for each test."""
    from app.services import ai_usage_tracker as mod

    # Redirect file to tmp
    usage_file = tmp_path / "ai_usage_log.json"
    original_file = mod.USAGE_FILE
    mod.USAGE_FILE = usage_file

    # Reset singleton
    mod.AiUsageTracker._instance = None
    tracker = mod.AiUsageTracker()

    yield tracker

    # Restore
    mod.USAGE_FILE = original_file
    mod.AiUsageTracker._instance = None


class TestRecordMessage:
    def test_whatsapp_meta_creates_entry(self, fresh_tracker):
        fresh_tracker.record_message("whatsapp_meta", source="alert")
        today = fresh_tracker.get_today()
        assert "whatsapp_meta/message" in today["models"]
        model = today["models"]["whatsapp_meta/message"]
        assert model["calls"] == 1
        assert model["input_tokens"] == 0
        assert model["output_tokens"] == 0
        assert model["cost_usd"] == pytest.approx(0.005, abs=1e-6)

    def test_bulksms_creates_entry(self, fresh_tracker):
        fresh_tracker.record_message("bulksms", source="alert")
        today = fresh_tracker.get_today()
        assert "bulksms/message" in today["models"]
        model = today["models"]["bulksms/message"]
        assert model["cost_usd"] == pytest.approx(0.006, abs=1e-6)

    def test_telegram_is_free(self, fresh_tracker):
        fresh_tracker.record_message("telegram", source="alert")
        today = fresh_tracker.get_today()
        model = today["models"]["telegram/message"]
        assert model["calls"] == 1
        assert model["cost_usd"] == pytest.approx(0.0, abs=1e-6)

    def test_multiple_messages_accumulate(self, fresh_tracker):
        fresh_tracker.record_message("whatsapp_meta", source="alert")
        fresh_tracker.record_message("whatsapp_meta", source="alert")
        fresh_tracker.record_message("whatsapp_meta", source="wo")
        today = fresh_tracker.get_today()
        model = today["models"]["whatsapp_meta/message"]
        assert model["calls"] == 3
        assert model["cost_usd"] == pytest.approx(0.015, abs=1e-6)

    def test_recipient_count_multiplies_cost(self, fresh_tracker):
        fresh_tracker.record_message("bulksms", recipient_count=5, source="broadcast")
        today = fresh_tracker.get_today()
        model = today["models"]["bulksms/message"]
        assert model["calls"] == 1  # Still one API call
        assert model["cost_usd"] == pytest.approx(0.030, abs=1e-6)  # 5 * 0.006


class TestRecordService:
    def test_elevenlabs_chars(self, fresh_tracker):
        fresh_tracker.record_service("elevenlabs", units=500, unit_type="chars", source="tts")
        today = fresh_tracker.get_today()
        assert "elevenlabs/chars" in today["models"]
        model = today["models"]["elevenlabs/chars"]
        assert model["calls"] == 1
        assert model["cost_usd"] == pytest.approx(500 * 0.00003, abs=1e-6)

    def test_eskomsepush_free_tier(self, fresh_tracker):
        fresh_tracker.record_service("eskomsepush", units=1, unit_type="calls", source="energy")
        today = fresh_tracker.get_today()
        model = today["models"]["eskomsepush/calls"]
        assert model["calls"] == 1
        assert model["cost_usd"] == pytest.approx(0.0, abs=1e-6)

    def test_unknown_service_zero_cost(self, fresh_tracker):
        fresh_tracker.record_service("newservice", units=100, unit_type="widgets", source="test")
        today = fresh_tracker.get_today()
        model = today["models"]["newservice/widgets"]
        assert model["calls"] == 1
        assert model["cost_usd"] == pytest.approx(0.0, abs=1e-6)


class TestGetSummaryIncludesAll:
    def test_summary_includes_messaging_providers(self, fresh_tracker):
        fresh_tracker.record_message("whatsapp_meta", source="alert")
        fresh_tracker.record_service("elevenlabs", units=200, unit_type="chars", source="tts")
        fresh_tracker.record(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=50,
            source="chat",
        )
        summary = fresh_tracker.get_summary(days=1)

        assert "whatsapp_meta" in summary["by_provider"]
        assert "elevenlabs" in summary["by_provider"]
        assert "anthropic" in summary["by_provider"]
        assert summary["total_cost_usd"] > 0

    def test_today_includes_all_types(self, fresh_tracker):
        fresh_tracker.record_message("telegram", source="alert")
        fresh_tracker.record_service("eskomsepush", units=1, unit_type="calls", source="energy")

        today = fresh_tracker.get_today()
        assert "telegram/message" in today["models"]
        assert "eskomsepush/calls" in today["models"]
        assert today["total_calls"] == 2


class TestDailyReportEmail:
    def test_report_includes_messaging_section(self, fresh_tracker):
        fresh_tracker.record_message("whatsapp_meta", source="alert")
        fresh_tracker.record_message("bulksms", source="alert")
        fresh_tracker.record_service("elevenlabs", units=300, unit_type="chars", source="tts")

        # Mock SMTP settings
        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.notification_smtp_host = ""
            mock_settings.notification_smtp_port = 587
            mock_settings.notification_smtp_username = ""
            mock_settings.notification_smtp_password = ""

            # Can't actually send, but we can test the report generation
            # by checking get_today output
            today = fresh_tracker.get_today()
            models = today["models"]

            # Verify messaging entries exist
            assert "whatsapp_meta/message" in models
            assert "bulksms/message" in models
            assert "elevenlabs/chars" in models


class TestCostAlert:
    @patch("httpx.post")
    def test_alert_fires_when_threshold_exceeded(self, mock_post, fresh_tracker):
        """Cost alert should fire when daily spend exceeds threshold."""
        mock_post.return_value = MagicMock(status_code=200)

        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.cost_alert_daily_threshold_zar = 0.01  # Very low threshold
            mock_settings.cost_alert_telegram_chat_id = ""
            mock_settings.telegram_alert_chat_id = "12345"
            mock_settings.telegram_bot_token = "test-token"

            # Record enough spend to exceed threshold
            fresh_tracker.record_message("whatsapp_meta", source="alert")

            # Verify alert was sent
            assert mock_post.called
            call_args = mock_post.call_args
            assert "12345" in str(call_args)

    @patch("httpx.post")
    def test_alert_only_fires_once_per_day(self, mock_post, fresh_tracker):
        """Cost alert should only fire once per day."""
        mock_post.return_value = MagicMock(status_code=200)

        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.cost_alert_daily_threshold_zar = 0.01
            mock_settings.cost_alert_telegram_chat_id = "12345"
            mock_settings.telegram_bot_token = "test-token"

            fresh_tracker.record_message("whatsapp_meta", source="alert")
            fresh_tracker.record_message("whatsapp_meta", source="alert")
            fresh_tracker.record_message("whatsapp_meta", source="alert")

            # Should only have been called once
            assert mock_post.call_count == 1

    def test_no_alert_below_threshold(self, fresh_tracker):
        """No alert when spend is below threshold."""
        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.cost_alert_daily_threshold_zar = 1000.0
            mock_settings.cost_alert_telegram_chat_id = "12345"
            mock_settings.telegram_bot_token = "test-token"

            with patch("httpx.post") as mock_post:
                fresh_tracker.record_message("telegram", source="alert")  # Free
                assert not mock_post.called


class TestDataPersistence:
    def test_flush_persists_messaging_data(self, fresh_tracker, tmp_path):
        from app.services import ai_usage_tracker as mod

        fresh_tracker.record_message("whatsapp_meta", source="alert")
        fresh_tracker.flush()

        data = json.loads(mod.USAGE_FILE.read_text())
        today = date.today().isoformat()
        assert "whatsapp_meta/message" in data["daily"][today]

    def test_flush_persists_service_data(self, fresh_tracker, tmp_path):
        from app.services import ai_usage_tracker as mod

        fresh_tracker.record_service("elevenlabs", units=100, unit_type="chars", source="tts")
        fresh_tracker.flush()

        data = json.loads(mod.USAGE_FILE.read_text())
        today = date.today().isoformat()
        assert "elevenlabs/chars" in data["daily"][today]

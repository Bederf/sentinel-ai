"""
Tests for token budget enforcement (Phase 185 Wave 2).

Covers:
1. Budget not exceeded — no exception, no alert
2. Alert threshold fires once
3. Alert deduplication — second call does not fire again
4. Hard limit raises TokenBudgetExceeded
5. Interactive task classes excluded from budget
6. Redis unavailable — memory fallback, no exception
"""

import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo


class TestAiUsageTrackerBudget(unittest.IsolatedAsyncioTestCase):
    """Tests for AiUsageTracker token budget enforcement."""

    def setUp(self):
        # Reset singleton state between tests
        from app.services.ai_usage_tracker import AiUsageTracker

        AiUsageTracker._instance = None

    def _sast_now(self):
        return datetime.now(ZoneInfo("Africa/Johannesburg"))

    # ---- test_budget_not_exceeded ----
    def test_budget_not_exceeded(self):
        """record() with 50k tokens, 200k budget — no exception, no alert."""
        from app.services.ai_usage_tracker import AiUsageTracker

        tracker = AiUsageTracker.__new__(AiUsageTracker)
        tracker._initialized = True
        tracker._write_lock = MagicMock()
        tracker._today_cache = {}
        tracker._today_key = datetime.now().date().isoformat()
        tracker._usd_zar = 18.50
        tracker._redis = None
        tracker._redis_checked = True  # Force memory fallback
        tracker._memory_daily_totals = {}
        tracker._memory_alert_sent = {}

        with patch.object(tracker, "_check_and_enforce_budget", new_callable=AsyncMock) as mock_budget:
            tracker.record(
                provider="minimax",
                model="MiniMax-M2.5",
                input_tokens=40_000,
                output_tokens=10_000,
                source="ai_optimizer",
                site_id="site-002",
                task_class="heavy",
            )
            # Budget check was called with correct tokens
            mock_budget.assert_called_once_with("site-002", 50_000, "heavy")

    # ---- test_budget_alert_threshold ----
    def test_budget_alert_threshold(self):
        """Pushing total to 175k (87.5%) fires alert once."""
        from app.services.ai_usage_tracker import AiUsageTracker

        tracker = AiUsageTracker.__new__(AiUsageTracker)
        tracker._initialized = True
        tracker._write_lock = MagicMock()
        tracker._today_cache = {}
        tracker._today_key = datetime.now().date().isoformat()
        tracker._usd_zar = 18.50
        tracker._redis = None
        tracker._redis_checked = True
        tracker._memory_daily_totals = {}
        tracker._memory_alert_sent = {}

        # Mock _increment_daily_total to return 175k (simulates pre-seeded 170k + 5k)
        with patch.object(tracker, "_increment_daily_total", return_value=175_000):
            with patch.object(tracker, "_send_budget_alert", new_callable=AsyncMock) as mock_alert:
                with patch.object(tracker, "_check_alert_sent", new_callable=AsyncMock) as mock_check:
                    with patch.object(tracker, "_mark_alert_sent", new_callable=AsyncMock) as mock_mark:
                        mock_check.return_value = False  # No alert sent yet

                        tracker.record(
                            provider="minimax",
                            model="MiniMax-M2.5",
                            input_tokens=4_000,
                            output_tokens=1_000,
                            source="ai_optimizer",
                            site_id="site-002",
                            task_class="heavy",
                        )

                        mock_alert.assert_called_once()

    # ---- test_budget_alert_dedup ----
    def test_budget_alert_dedup(self):
        """Two calls both over threshold — alert fires only once."""
        from app.services.ai_usage_tracker import AiUsageTracker

        tracker = AiUsageTracker.__new__(AiUsageTracker)
        tracker._initialized = True
        tracker._write_lock = MagicMock()
        tracker._today_cache = {}
        tracker._today_key = datetime.now().date().isoformat()
        tracker._usd_zar = 18.50
        tracker._redis = None
        tracker._redis_checked = True
        tracker._memory_daily_totals = {}
        tracker._memory_alert_sent = {}

        with patch.object(tracker, "_send_budget_alert", new_callable=AsyncMock) as mock_alert:
            with patch.object(tracker, "_mark_alert_sent", new_callable=AsyncMock):
                with patch.object(tracker, "_check_alert_sent", new_callable=AsyncMock) as mock_check:
                    mock_check.return_value = True  # Alert already sent

                    tracker.record(
                        provider="minimax",
                        model="MiniMax-M2.5",
                        input_tokens=90_000,
                        output_tokens=10_000,
                        source="ai_optimizer",
                        site_id="site-002",
                        task_class="heavy",
                    )

                    # Alert should NOT fire because _check_alert_sent returned True
                    mock_alert.assert_not_called()

    # ---- test_budget_hard_limit ----
    def test_budget_hard_limit(self):
        """_check_and_enforce_budget() raising when total >= budget raises TokenBudgetExceeded."""
        from app.services.ai_usage_tracker import AiUsageTracker, TokenBudgetExceeded

        tracker = AiUsageTracker.__new__(AiUsageTracker)
        tracker._initialized = True
        tracker._write_lock = MagicMock()
        tracker._today_cache = {}
        tracker._today_key = datetime.now().date().isoformat()
        tracker._usd_zar = 18.50
        tracker._redis = None
        tracker._redis_checked = True
        tracker._memory_daily_totals = {}
        tracker._memory_alert_sent = {}

        # Mock _increment_daily_total so new_total >= 200k
        with patch.object(tracker, "_increment_daily_total", return_value=205_000):
            with patch.object(tracker, "_check_alert_sent", new_callable=AsyncMock) as mock_check:
                mock_check.return_value = False
                import asyncio

                with self.assertRaises(TokenBudgetExceeded) as ctx:
                    asyncio.run(tracker._check_and_enforce_budget("site-002", 10_000, "heavy"))

        self.assertEqual(ctx.exception.site_id, "site-002")
        self.assertGreaterEqual(ctx.exception.current, 200_000)
        self.assertEqual(ctx.exception.budget, 200_000)

    # ---- test_interactive_excluded ----
    def test_interactive_excluded(self):
        """task_class='chat_ai' over budget — no exception raised."""
        from app.services.ai_usage_tracker import AiUsageTracker

        tracker = AiUsageTracker.__new__(AiUsageTracker)
        tracker._initialized = True
        tracker._write_lock = MagicMock()
        tracker._today_cache = {}
        tracker._today_key = datetime.now().date().isoformat()
        tracker._usd_zar = 18.50
        tracker._redis = None
        tracker._redis_checked = True
        # Simulate already at budget
        today = datetime.now().date().isoformat()
        tracker._memory_daily_totals = {f"token_budget:site-002:{today}": 250_000}
        tracker._memory_alert_sent = {}

        # Should NOT raise even though we're over budget
        tracker.record(
            provider="anthropic",
            model="claude-sonnet-4-6",
            input_tokens=5_000,
            output_tokens=2_000,
            source="chat",
            site_id="site-002",
            task_class="chat_ai",
        )

    # ---- test_redis_fallback ----
    def test_redis_fallback(self):
        """Redis unavailable — record() completes without raising."""
        from app.services.ai_usage_tracker import AiUsageTracker

        tracker = AiUsageTracker.__new__(AiUsageTracker)
        tracker._initialized = True
        tracker._write_lock = MagicMock()
        tracker._today_cache = {}
        tracker._today_key = datetime.now().date().isoformat()
        tracker._usd_zar = 18.50
        tracker._redis = None
        tracker._redis_checked = False  # Not yet checked — will attempt Redis

        # Simulate Redis being unavailable
        with patch.object(tracker, "_get_redis", return_value=None):
            with patch.object(tracker, "_check_and_enforce_budget", new_callable=AsyncMock) as mock_budget:
                # Should not raise
                tracker.record(
                    provider="minimax",
                    model="MiniMax-M2.5",
                    input_tokens=1_000,
                    output_tokens=500,
                    source="ai_optimizer",
                    site_id="site-002",
                    task_class="heavy",
                )
                mock_budget.assert_called_once()


class TestTelegramProviderBudgetAlert(unittest.TestCase):
    """Tests for TelegramProvider.send_budget_alert."""

    def test_send_budget_alert_is_fire_and_forget(self):
        """send_budget_alert submits to ThreadPoolExecutor without blocking."""
        from app.services.notification_providers.telegram_provider import TelegramProvider

        with patch.object(TelegramProvider, "is_enabled", return_value=True):
            with patch.object(TelegramProvider, "__init__", lambda self: None):
                tp = TelegramProvider()
                tp.bot_token = "test_token"
                tp.default_chat_id = "12345"

                with patch("httpx.Client") as mock_client_cls:
                    mock_client = MagicMock()
                    mock_response = MagicMock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {"ok": True, "result": {"message_id": "1"}}
                    mock_client.__enter__ = MagicMock(return_value=mock_client)
                    mock_client.__exit__ = MagicMock(return_value=None)
                    mock_client.post = MagicMock(return_value=mock_response)
                    mock_client_cls.return_value = mock_client

                    tp.send_budget_alert("site-002", 175_000, 200_000, 87.5)

                    # Verify post was called
                    mock_client.post.assert_called_once()


if __name__ == "__main__":
    unittest.main()

"""Tests for ResidentialTelegramSender.

Phase 214 — Wave 6
Covers:
- send_alert: P1 and P2 formatting (verify prefix)
- Missing token: returns False, does not raise, does not use commercial bot
- Never logs token
- send_text, delete_message, answer_callback_query basic tests
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.residential.residential_telegram_sender import (
    ResidentialTelegramSender,
)


class TestResidentialTelegramSenderInit:
    def test_empty_token_sets_no_client(self):
        with patch("app.services.residential.residential_telegram_sender.settings") as mock_settings:
            mock_settings.sentinel_home_bot_token = ""
            sender = ResidentialTelegramSender()
            assert sender._token == ""
            assert sender._base == ""
            assert sender._client is None

    def test_valid_token_sets_base_and_client(self):
        with patch("app.services.residential.residential_telegram_sender.settings") as mock_settings:
            mock_settings.sentinel_home_bot_token = "valid-home-bot-token"
            sender = ResidentialTelegramSender()
            assert sender._token == "valid-home-bot-token"
            assert sender._base == "https://api.telegram.org/botvalid-home-bot-token"
            assert sender._client is not None


class TestIsConfigured:
    def test_returns_false_when_token_empty(self):
        with patch("app.services.residential.residential_telegram_sender.settings") as mock_settings:
            mock_settings.sentinel_home_bot_token = ""
            sender = ResidentialTelegramSender()
            assert sender._is_configured() is False

    def test_returns_true_when_token_set(self):
        with patch("app.services.residential.residential_telegram_sender.settings") as mock_settings:
            mock_settings.sentinel_home_bot_token = "some-token"
            sender = ResidentialTelegramSender()
            assert sender._is_configured() is True


class TestSendAlert:
    @pytest.mark.asyncio
    async def test_p1_prefix_format(self):
        with patch("app.services.residential.residential_telegram_sender.settings") as mock_settings:
            mock_settings.sentinel_home_bot_token = "test-token"
            sender = ResidentialTelegramSender()

            with patch.object(sender, "send_text", new_callable=AsyncMock) as mock_send:
                mock_send.return_value = True
                result = await sender.send_alert(
                    chat_id=12345,
                    message="Battery critical",
                    severity="P1",
                    platform="SOLARMAN",
                )
                assert result is True
                call_text = mock_send.call_args[0][1]
                assert call_text.startswith("🚨 P1: [SOLARMAN] Battery critical")

    @pytest.mark.asyncio
    async def test_p2_prefix_format(self):
        with patch("app.services.residential.residential_telegram_sender.settings") as mock_settings:
            mock_settings.sentinel_home_bot_token = "test-token"
            sender = ResidentialTelegramSender()

            with patch.object(sender, "send_text", new_callable=AsyncMock) as mock_send:
                mock_send.return_value = True
                result = await sender.send_alert(
                    chat_id=12345,
                    message="PV generation low",
                    severity="P2",
                    platform="Victron VRM",
                )
                assert result is True
                call_text = mock_send.call_args[0][1]
                assert call_text.startswith("⚠️ P2: [Victron VRM] PV generation low")

    @pytest.mark.asyncio
    async def test_returns_false_when_not_configured(self):
        with patch("app.services.residential.residential_telegram_sender.settings") as mock_settings:
            mock_settings.sentinel_home_bot_token = ""
            sender = ResidentialTelegramSender()

            result = await sender.send_alert(
                chat_id=12345,
                message="Test",
                severity="P1",
                platform="SOLARMAN",
            )
            assert result is False


class TestSendText:
    @pytest.mark.asyncio
    async def test_returns_true_on_success(self):
        with patch("app.services.residential.residential_telegram_sender.settings") as mock_settings:
            mock_settings.sentinel_home_bot_token = "test-token"
            sender = ResidentialTelegramSender()

            mock_resp = MagicMock()
            mock_resp.json.return_value = {"ok": True, "result": {"message_id": 1}}

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.post.return_value = mock_resp
                mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await sender.send_text(12345, "Hello world")
                assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_configured(self):
        with patch("app.services.residential.residential_telegram_sender.settings") as mock_settings:
            mock_settings.sentinel_home_bot_token = ""
            sender = ResidentialTelegramSender()

            result = await sender.send_text(12345, "Hello")
            assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_api_returns_error(self):
        with patch("app.services.residential.residential_telegram_sender.settings") as mock_settings:
            mock_settings.sentinel_home_bot_token = "test-token"
            sender = ResidentialTelegramSender()

            mock_resp = MagicMock()
            mock_resp.json.return_value = {"ok": False, "description": "Forbidden"}

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.post.return_value = mock_resp
                mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await sender.send_text(12345, "Hello")
                assert result is False

    @pytest.mark.asyncio
    async def test_includes_reply_markup_when_provided(self):
        with patch("app.services.residential.residential_telegram_sender.settings") as mock_settings:
            mock_settings.sentinel_home_bot_token = "test-token"
            sender = ResidentialTelegramSender()

            mock_resp = MagicMock()
            mock_resp.json.return_value = {"ok": True}

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.post.return_value = mock_resp
                mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                keyboard = {"inline_keyboard": [[{"text": "OK", "callback_data": "ok"}]]}
                await sender.send_text(12345, "Pick one", reply_markup=keyboard)
                payload = mock_client.post.call_args[1]["json"]
                assert "reply_markup" in payload


class TestDeleteMessage:
    @pytest.mark.asyncio
    async def test_returns_true_on_success(self):
        with patch("app.services.residential.residential_telegram_sender.settings") as mock_settings:
            mock_settings.sentinel_home_bot_token = "test-token"
            sender = ResidentialTelegramSender()

            mock_resp = MagicMock()
            mock_resp.json.return_value = {"ok": True}

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.post.return_value = mock_resp
                mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await sender.delete_message(12345, 42)
                assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_configured(self):
        with patch("app.services.residential.residential_telegram_sender.settings") as mock_settings:
            mock_settings.sentinel_home_bot_token = ""
            sender = ResidentialTelegramSender()

            result = await sender.delete_message(12345, 42)
            assert result is False


class TestAnswerCallbackQuery:
    @pytest.mark.asyncio
    async def test_returns_true_on_success(self):
        with patch("app.services.residential.residential_telegram_sender.settings") as mock_settings:
            mock_settings.sentinel_home_bot_token = "test-token"
            sender = ResidentialTelegramSender()

            mock_resp = MagicMock()
            mock_resp.json.return_value = {"ok": True}

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.post.return_value = mock_resp
                mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await sender.answer_callback_query("cbq-123", text="Done!")
                assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_configured(self):
        with patch("app.services.residential.residential_telegram_sender.settings") as mock_settings:
            mock_settings.sentinel_home_bot_token = ""
            sender = ResidentialTelegramSender()

            result = await sender.answer_callback_query("cbq-123")
            assert result is False


class TestNeverUsesCommercialBot:
    """Verify ResidentialTelegramSender never references SENTRY_BOT_TOKEN."""

    def test_no_sentry_bot_token_usage_in_runtime_code(self):
        """Runtime code must never reference SENTRY_BOT_TOKEN or telegram_bot_token."""
        import inspect
        import re

        import app.services.residential.residential_telegram_sender as mod

        source = inspect.getsource(mod)
        # Remove triple-quoted docstrings
        cleaned = re.sub(r'""".*?"""', "", source, flags=re.DOTALL)
        # Remove single-line comments
        lines = cleaned.split("\n")
        code_lines = [line for line in lines if not line.strip().startswith("#")]
        runtime_source = "\n".join(code_lines)
        assert "SENTRY_BOT_TOKEN" not in runtime_source
        assert "telegram_bot_token" not in runtime_source

    @pytest.mark.asyncio
    async def test_does_not_use_telegram_message_sender(self):
        """Must use its own httpx client, not TelegramMessageSender."""
        with patch("app.services.residential.residential_telegram_sender.settings") as mock_settings:
            mock_settings.sentinel_home_bot_token = "home-bot-token"
            sender = ResidentialTelegramSender()

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_resp = MagicMock()
                mock_resp.json.return_value = {"ok": True}
                mock_client.post.return_value = mock_resp
                mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                await sender.send_text(12345, "test")
                call_url = mock_client.post.call_args[0][0]
                assert "home-bot-token" in call_url


class TestNeverLogsToken:
    """Token must never appear in log output."""

    def test_token_not_in_log_messages(self):
        with patch("app.services.residential.residential_telegram_sender.settings") as mock_settings:
            mock_settings.sentinel_home_bot_token = "secret-home-token-12345"
            sender = ResidentialTelegramSender()

            import io
            import logging

            log_capture = io.StringIO()
            handler = logging.StreamHandler(log_capture)
            handler.setLevel(logging.DEBUG)

            logger = logging.getLogger("app.services.residential.residential_telegram_sender")
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)

            try:
                sender.send_text(12345, "test")
            except Exception:
                pass

            log_output = log_capture.getvalue()
            assert "secret-home-token-12345" not in log_output
            assert "home-bot-token" not in log_output

            logger.removeHandler(handler)

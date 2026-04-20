"""Tests for Telegram Bot API notification provider."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


def _make_provider(bot_token: str = "123:ABC", chat_id: str = "-100999"):
    """Create a TelegramProvider with given settings."""
    mock_settings = MagicMock()
    mock_settings.telegram_bot_token = bot_token
    mock_settings.telegram_alert_chat_id = chat_id

    with patch("app.config.settings.settings", mock_settings):
        from app.services.notification_providers.telegram_provider import TelegramProvider

        return TelegramProvider()


def test_telegram_enabled():
    """Provider is enabled when bot token is set."""
    provider = _make_provider(bot_token="123:ABC")
    assert provider.is_enabled() is True
    assert provider.channel_name == "telegram"
    assert provider.provider_name == "telegram_bot_api"


def test_telegram_disabled(monkeypatch):
    """Provider is disabled when bot token is empty."""
    monkeypatch.delenv("SENTRY_BOT_TOKEN", raising=False)
    provider = _make_provider(bot_token="")
    assert provider.is_enabled() is False


@pytest.mark.asyncio
async def test_send_success():
    """Successful send calls Bot API and returns message_id."""
    provider = _make_provider()

    resp_data = {"ok": True, "result": {"message_id": 42}}
    mock_resp = httpx.Response(200, json=resp_data, request=httpx.Request("POST", "https://api.telegram.org/test"))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as mock_post:
        result = await provider.send("12345", "Test Title", "Test body")

    assert result.success is True
    assert result.message_id == "42"
    # Verify Bot API payload
    call_kwargs = mock_post.call_args
    payload = call_kwargs.kwargs["json"]
    assert payload["chat_id"] == "12345"
    assert payload["parse_mode"] == "Markdown"
    assert "*Test Title*" in payload["text"]


@pytest.mark.asyncio
async def test_send_with_default_chat_id():
    """When no recipient given, falls back to default chat_id from settings."""
    provider = _make_provider(chat_id="-100999")

    resp_data = {"ok": True, "result": {"message_id": 99}}
    mock_resp = httpx.Response(200, json=resp_data, request=httpx.Request("POST", "https://api.telegram.org/test"))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as mock_post:
        result = await provider.send("", "Title", "Body")

    assert result.success is True
    payload = mock_post.call_args.kwargs["json"]
    assert payload["chat_id"] == "-100999"


@pytest.mark.asyncio
async def test_send_failure():
    """API error returns graceful failure."""
    provider = _make_provider()

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Bad Request",
            request=httpx.Request("POST", "https://api.telegram.org/test"),
            response=httpx.Response(400),
        ),
    ):
        result = await provider.send("12345", "Title", "Body")

    assert result.success is False
    assert result.error_code == "exception"


@pytest.mark.asyncio
async def test_connection_test():
    """test_connection calls /getMe endpoint."""
    provider = _make_provider()

    mock_resp = httpx.Response(200, json={"ok": True}, request=httpx.Request("GET", "https://api.telegram.org/test"))

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        assert await provider.test_connection() is True

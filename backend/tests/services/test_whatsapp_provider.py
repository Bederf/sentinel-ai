"""Tests for WhatsApp notification provider delegation to WhatsAppService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_whatsapp_singleton():
    """Reset the WhatsAppService singleton between tests."""
    import app.integrations.whatsapp_service as ws

    ws._whatsapp_service = None
    yield
    ws._whatsapp_service = None


def _make_provider(enabled: bool = True, provider_name: str = "twilio"):
    """Create a WhatsAppProvider with a mocked WhatsAppService."""
    mock_service = MagicMock()
    mock_service.enabled = enabled
    mock_service.provider = provider_name
    mock_service.send_text_message = AsyncMock()

    with patch("app.integrations.whatsapp_service.get_whatsapp_service", return_value=mock_service):
        from app.services.notification_providers.whatsapp_provider import WhatsAppProvider

        provider = WhatsAppProvider()
    return provider, mock_service


def test_provider_twilio_enabled():
    """Provider reports enabled when WhatsAppService (Twilio) is enabled."""
    provider, _ = _make_provider(enabled=True, provider_name="twilio")
    assert provider.is_enabled() is True
    assert provider.provider_name == "twilio"
    assert provider.channel_name == "whatsapp"


def test_provider_meta_enabled():
    """Provider reports enabled when WhatsAppService (Meta) is enabled."""
    provider, _ = _make_provider(enabled=True, provider_name="meta")
    assert provider.is_enabled() is True
    assert provider.provider_name == "meta"


def test_provider_disabled():
    """Provider reports disabled when WhatsAppService is not configured."""
    provider, _ = _make_provider(enabled=False)
    assert provider.is_enabled() is False


@pytest.mark.asyncio
async def test_send_success():
    """Successful send delegates to WhatsAppService and returns success."""
    provider, mock_service = _make_provider()
    mock_service.send_text_message.return_value = {"success": True, "message_id": "SM123"}

    result = await provider.send("+27721234567", "Test Title", "Test body")

    assert result.success is True
    assert result.message_id == "SM123"
    mock_service.send_text_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_failure():
    """Failed send returns error from WhatsAppService."""
    provider, mock_service = _make_provider()
    mock_service.send_text_message.return_value = {"success": False, "error": "Rate limit exceeded"}

    result = await provider.send("+27721234567", "Title", "Body")

    assert result.success is False
    assert result.error_code == "send_failed"
    assert "Rate limit" in result.error_message


@pytest.mark.asyncio
async def test_send_exception():
    """Exception during send is caught and returned as error."""
    provider, mock_service = _make_provider()
    mock_service.send_text_message.side_effect = RuntimeError("Connection reset")

    result = await provider.send("+27721234567", "Title", "Body")

    assert result.success is False
    assert result.error_code == "exception"
    assert "Connection reset" in result.error_message


@pytest.mark.asyncio
async def test_message_formatting():
    """Message sent to WhatsAppService includes bold title and body."""
    provider, mock_service = _make_provider()
    mock_service.send_text_message.return_value = {"success": True, "message_id": "SM456"}

    await provider.send("+27721234567", "Alert Title", "Some body text")

    call_args = mock_service.send_text_message.call_args
    message = call_args.args[1]  # second positional arg is message
    assert message == "*Alert Title*\n\nSome body text"


def test_auto_detect_twilio(monkeypatch):
    """Auto-detect Twilio when TWILIO_ACCOUNT_SID is set and WHATSAPP_PROVIDER is not."""
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACtest")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
    monkeypatch.setenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    monkeypatch.delenv("WHATSAPP_PROVIDER", raising=False)

    from app.integrations.whatsapp_service import get_whatsapp_service

    svc = get_whatsapp_service()
    assert svc.provider == "twilio"

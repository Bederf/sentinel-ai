"""Tests for focus_room_notifier — n8n → NotificationService.broadcast_alert replacement."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.models.notification import AlertLevel


@pytest.mark.asyncio
async def test_send_focus_overstay_alert_whatsapp_via_notification_service():
    """WhatsApp is sent via notification_service.broadcast_alert with correct params."""
    from app.services.focus_room_notifier import send_focus_overstay_alert

    mock_broadcast = AsyncMock(
        return_value={"success": True, "recipients_notified": 1, "errors": []}
    )

    with patch("app.services.focus_room_notifier.notification_service") as mock_ns:
        mock_ns.broadcast_alert = mock_broadcast
        with patch("app.services.focus_room_notifier.alert_notifier") as mock_tg:
            mock_tg.send_alert_sync.return_value = False  # Telegram fails — WhatsApp carries
            with patch("app.services.focus_room_notifier.settings") as mock_settings:
                mock_settings.twilio_whatsapp_to = "whatsapp:+27721234567"
                mock_settings.telegram_alert_chat_id = "-100999"

                result = await send_focus_overstay_alert(
                    site_id="site-002",
                    room_code="S002-FOCUS-01",
                    max_allowed_minutes=60,
                    cooldown_minutes=15,
                )

    assert result["whatsapp_sent"] is True
    assert result["whatsapp_result"]["success"] is True
    assert result["whatsapp_result"]["recipients_notified"] == 1

    # Verify broadcast_alert was called with correct args
    call_kwargs = mock_broadcast.call_args.kwargs
    assert "Focus Room Overstay Alert" in call_kwargs["title"]
    assert "S002-FOCUS-01" in call_kwargs["body"]
    assert call_kwargs["alert_level"] == AlertLevel.WARNING
    assert call_kwargs["notification_type"] == "focus_room_overstay"


@pytest.mark.asyncio
async def test_send_focus_overstay_alert_no_whatsapp_number():
    """When twilio_whatsapp_to is empty, whatsapp_result is error 'whatsapp_not_configured'."""
    from app.services.focus_room_notifier import send_focus_overstay_alert

    with patch("app.services.focus_room_notifier.alert_notifier") as mock_tg:
        mock_tg.send_alert_sync.return_value = False
        with patch("app.services.focus_room_notifier.settings") as mock_settings:
            mock_settings.twilio_whatsapp_to = ""
            mock_settings.telegram_alert_chat_id = "-100999"

            result = await send_focus_overstay_alert(
                site_id="site-002",
                room_code="S002-FOCUS-02",
                max_allowed_minutes=60,
                cooldown_minutes=15,
            )

    assert result["whatsapp_sent"] is False
    assert result["whatsapp_result"]["success"] is False
    assert result["whatsapp_result"]["error"] == "whatsapp_not_configured"


@pytest.mark.asyncio
async def test_send_focus_overstay_alert_notification_service_failure():
    """When broadcast_alert raises, whatsapp_result contains the exception message."""
    from app.services.focus_room_notifier import send_focus_overstay_alert

    with patch("app.services.focus_room_notifier.alert_notifier") as mock_tg:
        mock_tg.send_alert_sync.return_value = False
        with patch("app.services.focus_room_notifier.settings") as mock_settings:
            mock_settings.twilio_whatsapp_to = "whatsapp:+27721234567"
            mock_settings.telegram_alert_chat_id = "-100999"

            with patch("app.services.focus_room_notifier.notification_service") as mock_ns:
                mock_ns.broadcast_alert = AsyncMock(
                    side_effect=RuntimeError("WhatsApp provider unavailable")
                )

                result = await send_focus_overstay_alert(
                    site_id="site-002",
                    room_code="S002-FOCUS-03",
                    max_allowed_minutes=60,
                    cooldown_minutes=15,
                )

    assert result["whatsapp_sent"] is False
    assert result["whatsapp_result"]["success"] is False
    assert "WhatsApp provider unavailable" in result["whatsapp_result"]["error"]
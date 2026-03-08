"""Tests for NotificationService.broadcast_alert — unified plant/sentry dispatch."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.models.notification import AlertLevel, ChannelType
from app.services.notification_providers.base_provider import NotificationResult


def _mock_provider(enabled: bool = True, success: bool = True):
    """Create a mock notification provider."""
    p = MagicMock()
    p.is_enabled.return_value = enabled
    p.send = AsyncMock(
        return_value=NotificationResult(
            success=success,
            message_id="msg-123" if success else None,
            error_code=None if success else "send_failed",
            error_message=None if success else "Failed",
        )
    )
    return p


@pytest.fixture
def notification_service():
    """Create a NotificationService with mocked providers and repo."""
    with patch("app.services.notification_service.NotificationRepository") as MockRepo:
        mock_repo = MockRepo.return_value
        mock_repo.get_alert_subscribers = AsyncMock(return_value=[])
        mock_repo.get_notification_preferences = AsyncMock(return_value=None)
        mock_repo.get_notification_channels = AsyncMock(return_value=[])
        mock_repo.create_delivery_log = AsyncMock(side_effect=lambda log: log)

        from app.services.notification_service import NotificationService

        svc = NotificationService()
        svc.notification_repo = mock_repo
        yield svc


@pytest.mark.asyncio
async def test_broadcast_to_subscribers(notification_service):
    """When technician DB has subscribers, routes through notify_technician."""
    tech_id = UUID("00000000-0000-0000-0000-000000000010")
    notification_service.notification_repo.get_alert_subscribers.return_value = [tech_id]

    # Mock notify_technician to return success
    notification_service.notify_technician = AsyncMock(
        return_value={
            "success": True,
            "channels_sent": [ChannelType.TELEGRAM],
            "channels_failed": [],
            "errors": {},
        }
    )

    result = await notification_service.broadcast_alert("Test Alert", "Body text")

    assert result["success"] is True
    assert result["recipients_notified"] == 1
    notification_service.notify_technician.assert_awaited_once_with(
        technician_id=tech_id,
        title="Test Alert",
        body="Body text",
        alert_level=AlertLevel.CRITICAL,
        notification_type="plant_alert",
    )


@pytest.mark.asyncio
async def test_broadcast_fallback_direct(notification_service):
    """When no subscribers, sends directly via enabled providers to default recipients."""
    telegram_provider = _mock_provider(enabled=True, success=True)
    whatsapp_provider = _mock_provider(enabled=False)
    sms_provider = _mock_provider(enabled=False)

    notification_service.providers = {
        ChannelType.TELEGRAM: telegram_provider,
        ChannelType.WHATSAPP: whatsapp_provider,
        ChannelType.SMS: sms_provider,
    }

    with patch("app.config.settings.settings") as mock_settings:
        mock_settings.telegram_alert_chat_id = "-100999"
        mock_settings.twilio_whatsapp_to = ""

        result = await notification_service.broadcast_alert("Alert", "Body")

    assert result["success"] is True
    assert result["recipients_notified"] == 1
    telegram_provider.send.assert_awaited_once_with("-100999", "Alert", "Body")


@pytest.mark.asyncio
async def test_broadcast_mixed_channels(notification_service):
    """Both Telegram and WhatsApp enabled — both receive the alert."""
    telegram_provider = _mock_provider(enabled=True, success=True)
    whatsapp_provider = _mock_provider(enabled=True, success=True)
    sms_provider = _mock_provider(enabled=False)

    notification_service.providers = {
        ChannelType.TELEGRAM: telegram_provider,
        ChannelType.WHATSAPP: whatsapp_provider,
        ChannelType.SMS: sms_provider,
    }

    with patch("app.config.settings.settings") as mock_settings:
        mock_settings.telegram_alert_chat_id = "-100999"
        mock_settings.twilio_whatsapp_to = "whatsapp:+27721234567"

        result = await notification_service.broadcast_alert("Alert", "Body")

    assert result["success"] is True
    assert result["recipients_notified"] == 2
    telegram_provider.send.assert_awaited_once()
    whatsapp_provider.send.assert_awaited_once_with("+27721234567", "Alert", "Body")


@pytest.mark.asyncio
async def test_broadcast_no_channels_configured(notification_service):
    """When no providers enabled and no subscribers, returns failure gracefully."""
    notification_service.providers = {
        ChannelType.TELEGRAM: _mock_provider(enabled=False),
        ChannelType.WHATSAPP: _mock_provider(enabled=False),
        ChannelType.SMS: _mock_provider(enabled=False),
    }

    result = await notification_service.broadcast_alert("Alert", "Body")

    assert result["success"] is False
    assert result["recipients_notified"] == 0


@pytest.mark.asyncio
async def test_plant_alert_through_broadcast():
    """End-to-end: alarm object -> format -> broadcast_alert."""
    from app.plant.models import AlarmSeverity, DesigoBuildingAlarm
    from app.plant.plant_notifier import send_plant_alert

    alarm = DesigoBuildingAlarm(
        id="test-001",
        site_id="FLN02",
        building="Block A",
        raw_subject="FLN02: Chiller Fail",
        raw_body="body",
        equipment_description="Chiller-01",
        alarm_type="Fail",
        status="Fault",
        severity=AlarmSeverity.CRITICAL,
        equipment_category="hvac",
        received_at=datetime(2026, 3, 7, 10, 0),
    )

    mock_broadcast = AsyncMock(return_value={"success": True, "recipients_notified": 1, "errors": []})

    with patch("app.services.notification_service.notification_service") as mock_svc:
        mock_svc.broadcast_alert = mock_broadcast
        result = await send_plant_alert(alarm)

    assert result is True
    call_kwargs = mock_broadcast.call_args.kwargs
    assert "Plant Alert" in call_kwargs["title"]
    assert "Chiller-01" in call_kwargs["body"]
    assert call_kwargs["alert_level"] == AlertLevel.CRITICAL

"""Tests for app.plant.whatsapp_notifier — formatting and delivery."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.plant.models import AlarmSeverity, DesigoBuildingAlarm
from app.plant.whatsapp_notifier import format_plant_alert, send_plant_alert

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_alarm(**overrides) -> DesigoBuildingAlarm:
    defaults = {
        "id": "notif-001",
        "site_id": "FLN02",
        "building": "Block A",
        "raw_subject": "FLN02: Fire Damper Fail",
        "raw_body": "body text",
        "equipment_description": "Fire Damper B2-FD-01",
        "alarm_type": "Fail Status",
        "status": "Fault",
        "severity": AlarmSeverity.CRITICAL,
        "equipment_category": "fire_safety",
        "received_at": datetime(2026, 3, 7, 10, 30, tzinfo=UTC),
    }
    defaults.update(overrides)
    return DesigoBuildingAlarm(**defaults)


def _mock_settings(**overrides):
    """Return a mock settings object with sensible defaults."""
    defaults = {
        "twilio_account_sid": "",
        "twilio_auth_token": "",
        "twilio_whatsapp_from": "",
        "twilio_whatsapp_to": "",
        "whatsapp_webhook_url": "",
        "whatsapp_group_id": "",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _twilio_settings():
    return _mock_settings(
        twilio_account_sid="ACtest123",
        twilio_auth_token="token456",
        twilio_whatsapp_from="whatsapp:+14155238886",
        twilio_whatsapp_to="whatsapp:+27721234567",
    )


def _webhook_settings():
    return _mock_settings(
        whatsapp_webhook_url="http://test/webhook",
        whatsapp_group_id="group-1",
    )


# ---------------------------------------------------------------------------
# Formatting tests
# ---------------------------------------------------------------------------


def test_format_very_critical():
    """VERY_CRITICAL alarm has double red circle and URGENT label."""
    alarm = _make_alarm(severity=AlarmSeverity.VERY_CRITICAL)
    msg = format_plant_alert(alarm)
    assert "\U0001f534\U0001f534" in msg
    assert "URGENT" in msg
    assert "Immediate response required" in msg


def test_format_critical():
    """CRITICAL alarm has single red circle and Action required."""
    alarm = _make_alarm(severity=AlarmSeverity.CRITICAL)
    msg = format_plant_alert(alarm)
    assert "\U0001f534" in msg
    assert "Action required" in msg
    assert "\U0001f534\U0001f534" not in msg


def test_format_non_critical():
    """NON_CRITICAL alarm has yellow circle and For attention."""
    alarm = _make_alarm(severity=AlarmSeverity.NON_CRITICAL)
    msg = format_plant_alert(alarm)
    assert "\U0001f7e1" in msg
    assert "For attention" in msg


def test_format_cleared():
    """CLEARED alarm has green checkmark and Fault resolved."""
    alarm = _make_alarm(severity=AlarmSeverity.CLEARED, status="Normal")
    msg = format_plant_alert(alarm)
    assert "\u2705" in msg
    assert "Fault resolved" in msg


# ---------------------------------------------------------------------------
# Twilio delivery tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_via_twilio_success():
    """Twilio POST returns 201 with message SID."""
    alarm = _make_alarm()
    twilio_resp = httpx.Response(
        201,
        json={"sid": "SM123", "status": "queued"},
        request=httpx.Request("POST", "https://api.twilio.com/test"),
    )

    with (
        patch("app.plant.whatsapp_notifier._get_settings", return_value=_twilio_settings()),
        patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=twilio_resp),
    ):
        result = await send_plant_alert(alarm)
        assert result is True


@pytest.mark.asyncio
async def test_send_via_twilio_posts_correct_data():
    """Twilio call uses Basic Auth and correct form data."""
    alarm = _make_alarm()
    settings = _twilio_settings()
    twilio_resp = httpx.Response(
        201,
        json={"sid": "SM123", "status": "queued"},
        request=httpx.Request("POST", "https://api.twilio.com/test"),
    )

    with (
        patch("app.plant.whatsapp_notifier._get_settings", return_value=settings),
        patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=twilio_resp) as mock_post,
    ):
        await send_plant_alert(alarm)
        call_kwargs = mock_post.call_args
        # Verify auth tuple
        assert call_kwargs.kwargs["auth"] == ("ACtest123", "token456")
        # Verify form data
        assert call_kwargs.kwargs["data"]["From"] == "whatsapp:+14155238886"
        assert call_kwargs.kwargs["data"]["To"] == "whatsapp:+27721234567"
        assert "Fire Damper" in call_kwargs.kwargs["data"]["Body"]


# ---------------------------------------------------------------------------
# Webhook fallback delivery tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_via_webhook_fallback():
    """When Twilio not configured, falls back to webhook."""
    alarm = _make_alarm()
    ok_resp = httpx.Response(200, request=httpx.Request("POST", "http://test"))

    with (
        patch("app.plant.whatsapp_notifier._get_settings", return_value=_webhook_settings()),
        patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=ok_resp) as mock_post,
    ):
        result = await send_plant_alert(alarm)
        assert result is True
        # Webhook uses json payload, not form data
        call_kwargs = mock_post.call_args
        assert "json" in call_kwargs.kwargs


# ---------------------------------------------------------------------------
# Retry logic tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_failure_retry():
    """On first failure, retries once; second attempt succeeds."""
    alarm = _make_alarm(severity=AlarmSeverity.CRITICAL)
    ok_resp = httpx.Response(
        201,
        json={"sid": "SM123", "status": "queued"},
        request=httpx.Request("POST", "https://api.twilio.com/test"),
    )

    call_count = 0

    async def _side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.HTTPError("connection failed")
        return ok_resp

    with (
        patch("app.plant.whatsapp_notifier._get_settings", return_value=_twilio_settings()),
        patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=_side_effect),
    ):
        result = await send_plant_alert(alarm)
        assert result is True
        assert call_count == 2


@pytest.mark.asyncio
async def test_send_non_critical_no_retry():
    """NON_CRITICAL alarms do NOT retry on failure."""
    alarm = _make_alarm(severity=AlarmSeverity.NON_CRITICAL)

    call_count = 0

    async def _side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise httpx.HTTPError("connection failed")

    with (
        patch("app.plant.whatsapp_notifier._get_settings", return_value=_twilio_settings()),
        patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=_side_effect),
    ):
        result = await send_plant_alert(alarm)
        assert result is False
        assert call_count == 1


@pytest.mark.asyncio
async def test_send_no_config_returns_false():
    """When neither Twilio nor webhook is configured, returns False."""
    alarm = _make_alarm()

    with patch("app.plant.whatsapp_notifier._get_settings", return_value=_mock_settings()):
        result = await send_plant_alert(alarm)
        assert result is False

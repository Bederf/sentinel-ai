"""Tests for app.plant.whatsapp_notifier — formatting and delivery."""

from __future__ import annotations

from datetime import UTC, datetime
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
    # Should NOT have double red circle (very_critical)
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
# Delivery tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_success():
    """Successful POST returns True."""
    alarm = _make_alarm()
    mock_response = httpx.Response(200, request=httpx.Request("POST", "http://test"))

    with (
        patch("app.plant.whatsapp_notifier.WHATSAPP_WEBHOOK_URL", "http://test/webhook"),
        patch("app.plant.whatsapp_notifier.WHATSAPP_GROUP_ID", "group-1"),
        patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response),
    ):
        result = await send_plant_alert(alarm)
        assert result is True


@pytest.mark.asyncio
async def test_send_failure_retry():
    """On first failure, retries once; second attempt succeeds."""
    alarm = _make_alarm(severity=AlarmSeverity.CRITICAL)
    fail_resp = httpx.Response(500, request=httpx.Request("POST", "http://test"))
    ok_resp = httpx.Response(200, request=httpx.Request("POST", "http://test"))

    call_count = 0

    async def _side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.HTTPStatusError("err", request=httpx.Request("POST", "http://test"), response=fail_resp)
        return ok_resp

    with (
        patch("app.plant.whatsapp_notifier.WHATSAPP_WEBHOOK_URL", "http://test/webhook"),
        patch("app.plant.whatsapp_notifier.WHATSAPP_GROUP_ID", "group-1"),
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
        patch("app.plant.whatsapp_notifier.WHATSAPP_WEBHOOK_URL", "http://test/webhook"),
        patch("app.plant.whatsapp_notifier.WHATSAPP_GROUP_ID", "group-1"),
        patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=_side_effect),
    ):
        result = await send_plant_alert(alarm)
        assert result is False
        assert call_count == 1  # No retry for non_critical

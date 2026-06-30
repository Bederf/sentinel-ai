from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.sentry import residential_alerts_service as svc


def test_parse_unknown_key_rejects_arbitrary_json():
    with pytest.raises(ValueError, match="Unknown setting"):
        svc._parse_updates('{"runaway_enabled": false}')


def test_parse_cost_on_with_limit_sets_both_fields():
    updates, message = svc._parse_updates("cost on R80")
    assert updates == {"cost_limit_enabled": True, "cost_limit_zar": 80.0}
    assert "R80" in message


def test_parse_runaway_hours_validates_range():
    with pytest.raises(ValueError, match="between 1 and 24"):
        svc._parse_updates("runaway_hours 30")


def test_parse_overnight_window_validates_format():
    updates, _ = svc._parse_updates("overnight_window 23:00-05:00")
    assert updates == {"overnight_window": ["23:00", "05:00"]}

    with pytest.raises(ValueError, match="Invalid overnight window"):
        svc._parse_updates("overnight_window 25:00-05:00")


@pytest.mark.asyncio
async def test_handle_alerts_no_site_prompts_connect():
    with patch.object(svc, "_load_site", return_value=None):
        with patch.object(svc._sender, "send_text", AsyncMock(return_value=True)) as send:
            message = await svc.handle_alerts_command(123, "")

    assert message == "No active connection. Send /connect first."
    send.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_alerts_updates_known_setting_only():
    site = {"site_id": "res-123", "alert_config": {}}
    with patch.object(svc, "_load_site", return_value=site):
        with patch.object(svc, "_save_config") as save:
            with patch.object(svc._sender, "send_text", AsyncMock(return_value=True)):
                message = await svc.handle_alerts_command(123, "runaway off")

    save.assert_called_once_with("res-123", {"runaway_enabled": False})
    assert "disabled" in message


@pytest.mark.asyncio
async def test_handle_alerts_status_mentions_kw_rating_default():
    site = {"site_id": "res-123", "alert_config": {}}
    with patch.object(svc, "_load_site", return_value=site):
        with patch.object(svc._sender, "send_text", AsyncMock(return_value=True)):
            message = await svc.handle_alerts_command(123, "")

    assert "Appliance rating: 1.5kW" in message
    assert "/alerts kw_rating 2.5" in message

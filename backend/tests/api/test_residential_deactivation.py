from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import app.api.residential_onboarding as mod


def _supabase_with_active_site(site_id: str = "site-test") -> MagicMock:
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "uuid-001", "is_active": True, "eskom_area_code": "sandton-2"}
    ]
    sb.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{}]
    return sb


# ── Happy path ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deactivate_happy_path():
    sb = _supabase_with_active_site()
    with (
        patch("app.api.residential_onboarding.get_supabase_client", return_value=sb),
        patch("app.api.residential_onboarding.remove_residential_polling_job"),
        patch("app.api.residential_onboarding.get_mqtt_provisioner"),
        patch("app.api.residential_onboarding.mqtt", None),  # skip real MQTT
    ):
        result = await mod.deactivate_residential_site("site-test")

    assert result["status"] == "deactivated"
    assert result["site_id"] == "site-test"
    assert "deactivated_at" in result


@pytest.mark.asyncio
async def test_deactivate_idempotent_on_inactive_site():
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "uuid-001", "is_active": False}
    ]
    with patch("app.api.residential_onboarding.get_supabase_client", return_value=sb):
        result = await mod.deactivate_residential_site("site-test")

    assert result["status"] == "already_inactive"


@pytest.mark.asyncio
async def test_deactivate_raises_404_for_unknown_site():
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    with (
        patch("app.api.residential_onboarding.get_supabase_client", return_value=sb),
        pytest.raises(HTTPException) as exc_info,
    ):
        await mod.deactivate_residential_site("site-unknown")
    assert exc_info.value.status_code == 404


# ── Teardown sequence ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deactivate_calls_remove_polling_job():
    sb = _supabase_with_active_site()
    mock_remove = MagicMock()
    with (
        patch("app.api.residential_onboarding.get_supabase_client", return_value=sb),
        patch("app.api.residential_onboarding.remove_residential_polling_job", mock_remove),
        patch("app.api.residential_onboarding.get_mqtt_provisioner"),
        patch("app.api.residential_onboarding.mqtt", None),
    ):
        await mod.deactivate_residential_site("site-test")

    mock_remove.assert_called_once_with("site-test")


@pytest.mark.asyncio
async def test_deactivate_calls_revoke_site():
    sb = _supabase_with_active_site()
    mock_provisioner = MagicMock()
    with (
        patch("app.api.residential_onboarding.get_supabase_client", return_value=sb),
        patch("app.api.residential_onboarding.remove_residential_polling_job"),
        patch("app.api.residential_onboarding.get_mqtt_provisioner", return_value=mock_provisioner),
        patch("app.api.residential_onboarding.mqtt", None),
    ):
        await mod.deactivate_residential_site("site-test")

    mock_provisioner.revoke_site.assert_called_once_with("site-test")


@pytest.mark.asyncio
async def test_deactivate_marks_db_inactive():
    sb = _supabase_with_active_site()
    with (
        patch("app.api.residential_onboarding.get_supabase_client", return_value=sb),
        patch("app.api.residential_onboarding.remove_residential_polling_job"),
        patch("app.api.residential_onboarding.get_mqtt_provisioner"),
        patch("app.api.residential_onboarding.mqtt", None),
    ):
        await mod.deactivate_residential_site("site-test")

    # Verify update was called with is_active=False
    update_calls = sb.table.return_value.update.call_args_list
    assert any(
        call.args and call.args[0].get("is_active") is False
        for call in update_calls
    )


# ── Resilience ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deactivate_continues_if_polling_job_missing():
    """remove_residential_polling_job raises — teardown should continue."""
    sb = _supabase_with_active_site()
    with (
        patch("app.api.residential_onboarding.get_supabase_client", return_value=sb),
        patch("app.api.residential_onboarding.remove_residential_polling_job", side_effect=Exception("job not found")),
        patch("app.api.residential_onboarding.get_mqtt_provisioner"),
        patch("app.api.residential_onboarding.mqtt", None),
    ):
        result = await mod.deactivate_residential_site("site-test")

    assert result["status"] == "deactivated"


@pytest.mark.asyncio
async def test_deactivate_continues_if_acl_revocation_fails():
    """ACL revocation failure logs ERROR but still marks site inactive."""
    sb = _supabase_with_active_site()
    mock_prov = MagicMock()
    mock_prov.revoke_site.side_effect = Exception("mosquitto unreachable")
    with (
        patch("app.api.residential_onboarding.get_supabase_client", return_value=sb),
        patch("app.api.residential_onboarding.remove_residential_polling_job"),
        patch("app.api.residential_onboarding.get_mqtt_provisioner", return_value=mock_prov),
        patch("app.api.residential_onboarding.mqtt", None),
    ):
        result = await mod.deactivate_residential_site("site-test")

    assert result["status"] == "deactivated"
    update_calls = sb.table.return_value.update.call_args_list
    assert any(
        call.args and call.args[0].get("is_active") is False
        for call in update_calls
    )

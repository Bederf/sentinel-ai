from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.api.residential_onboarding import deactivate_residential_site


@patch("app.api.residential_onboarding.get_mqtt_provisioner")
@patch("app.api.residential_onboarding.get_supabase_client")
def test_deactivate_vps_revokes_credentials(mock_sb, mock_prov):
    # Arrange supabase row for HA VPS site
    mock_sb.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "uuid", "is_active": True, "platform": "home_assistant", "ha_deployment_type": "vps"}]
    )
    mock_sb.return_value.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"ok": True}]
    )
    mock_prov.return_value.revoke_vps_client = MagicMock()
    mock_prov.return_value.revoke_site = MagicMock()

    # Act
    # Note: calling function directly bypasses auth deps
    result = (
        __import__("asyncio")
        .get_event_loop()
        .run_until_complete(__import__("anyio").to_thread.run_sync(lambda: deactivate_residential_site("res-123")))
    )

    # Assert
    assert result["status"] in ("deactivated", "already_inactive")
    mock_prov.return_value.revoke_vps_client.assert_called_once()

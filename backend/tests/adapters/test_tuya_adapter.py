from __future__ import annotations

from datetime import datetime, timedelta
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.residential.tuya import TuyaCloudAdapter


def _make_adapter(extra: dict | None = None) -> TuyaCloudAdapter:
    cfg = {
        "site_id": "res-123",
        "tuya_uid": "tuya-user-1",
        "email": "home@example.com",
        "password": "secret",
        **(extra or {}),
    }
    return TuyaCloudAdapter(site_config=cfg, client_id="cid", client_secret="sec", api_region="eu")


def _mock_token_response() -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"result": {"access_token": "tok-123", "expire_time": 7200, "uid": "tuya-user-1"}}
    return resp


def _mock_sync_client(resp: MagicMock) -> MagicMock:
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.get.return_value = resp
    return client


def _patch_async_client(resp: MagicMock):
    mock_cls = MagicMock()
    instance = AsyncMock()
    instance.request = AsyncMock(return_value=resp)
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=instance)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
    return patch("app.adapters.residential.tuya.httpx.AsyncClient", mock_cls), instance


@pytest.mark.asyncio
async def test_authenticate_gets_access_token_without_logging_credentials():
    adapter = _make_adapter()
    token_resp = _mock_token_response()
    sync_client = _mock_sync_client(token_resp)

    with patch("app.adapters.residential.tuya.httpx.Client", return_value=sync_client):
        with patch.object(adapter, "_persist_site_config"):
            ok = await adapter.authenticate()

    assert ok is True
    assert adapter._access_token == "tok-123"
    args, kwargs = sync_client.get.call_args
    assert args[0].endswith("/v1.0/token")
    assert kwargs["params"] == {"grant_type": "1"}
    body = kwargs
    assert "secret" not in str(body)


@pytest.mark.asyncio
async def test_discover_devices_filters_aircons():
    adapter = _make_adapter({"tuya_access_token": "tok-123", "tuya_token_expire_at": time.time() + 60})
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "result": [
            {"id": "aircon-1", "name": "Bedroom AC", "category": "kt"},
            {"id": "plug-1", "name": "Smart Plug", "category": "cz"},
        ]
    }
    patcher, instance = _patch_async_client(resp)

    with patcher:
        manifests = await adapter.discover_devices()

    assert [m.device_id for m in manifests] == ["aircon-1"]
    assert manifests[0].device_type == "aircon"
    assert "/v2.0/cloud/thing/device" in instance.request.call_args.args[1]


@pytest.mark.asyncio
async def test_get_realtime_maps_status_and_runtime_minutes():
    last_on = (datetime.utcnow() - timedelta(hours=2)).isoformat()
    adapter = _make_adapter(
        {
            "tuya_access_token": "tok-123",
            "tuya_token_expire_at": time.time() + 60,
            "appliance_state": {"aircon-1": {"last_on_at": last_on}},
        }
    )
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "result": [
            {"code": "switch", "value": True},
            {"code": "temp_set", "value": 22},
            {"code": "temp_current", "value": 24},
            {"code": "mode", "value": "cool"},
        ]
    }
    patcher, _ = _patch_async_client(resp)

    with patcher:
        snap = await adapter.get_realtime("aircon-1")

    assert snap.source_system == "tuya"
    assert snap.appliance_power_state == "on"
    assert snap.appliance_target_temp_c == 22
    assert snap.appliance_current_temp_c == 24
    assert snap.appliance_mode == "cool"
    assert 119 <= snap.appliance_runtime_minutes <= 121


def test_tuya_adapter_does_not_expose_command_endpoint():
    import inspect

    from app.adapters.residential import tuya

    source = inspect.getsource(tuya.TuyaCloudAdapter)
    assert "/commands" not in source

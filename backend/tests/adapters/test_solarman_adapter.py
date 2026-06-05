from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.residential.solarman import SolarmanAdapter

_SITE_CONFIG = {"email": "test@example.com", "password": "secret", "site_id": "site-test"}
_APP_ID = "test-app-id"
_APP_SECRET = "test-app-secret"


def _make_adapter() -> SolarmanAdapter:
    return SolarmanAdapter(site_config=_SITE_CONFIG, app_id=_APP_ID, app_secret=_APP_SECRET)


def _mock_token_response(uid: int = 6681) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"access_token": "tok-abc123", "uid": uid}
    return resp


def _mock_sync_client(token_resp: MagicMock):
    client_instance = MagicMock()
    client_instance.__enter__ = MagicMock(return_value=client_instance)
    client_instance.__exit__ = MagicMock(return_value=False)
    client_instance.post.return_value = token_resp
    return client_instance


# ── Token management ─────────────────────────────────────────────────────────


def test_get_token_calls_refresh_once():
    adapter = _make_adapter()
    token_resp = _mock_token_response()
    sync_client = _mock_sync_client(token_resp)

    with patch("app.adapters.residential.solarman.httpx.Client", return_value=sync_client):
        tok1 = adapter._get_token()
        tok2 = adapter._get_token()

    assert tok1 == "tok-abc123"
    assert tok1 == tok2
    assert sync_client.post.call_count == 1


def test_refresh_token_uses_sha256_password():
    adapter = _make_adapter()
    token_resp = _mock_token_response()
    sync_client = _mock_sync_client(token_resp)

    with patch("app.adapters.residential.solarman.httpx.Client", return_value=sync_client):
        adapter._refresh_token()

    call_kwargs = sync_client.post.call_args
    body = call_kwargs.kwargs["json"] if call_kwargs.kwargs else call_kwargs[1]["json"]
    import hashlib

    expected_hash = hashlib.sha256(b"secret").hexdigest()
    assert body["password"] == expected_hash
    assert "secret" not in body["password"]


def test_refresh_token_extracts_uid():
    adapter = _make_adapter()
    token_resp = _mock_token_response(uid=6681)
    sync_client = _mock_sync_client(token_resp)

    with patch("app.adapters.residential.solarman.httpx.Client", return_value=sync_client):
        adapter._refresh_token()

    assert adapter._user_id == 6681


def test_token_refresh_on_401():
    adapter = _make_adapter()
    adapter._access_token = "old-token"
    adapter._token_needs_refresh = False

    token_resp = _mock_token_response()
    sync_client = _mock_sync_client(token_resp)

    async_resp_401 = MagicMock()
    async_resp_401.status_code = 401

    async_resp_ok = MagicMock()
    async_resp_ok.status_code = 200
    async_resp_ok.raise_for_status = MagicMock()
    async_resp_ok.json.return_value = {"dataList": []}

    with patch("app.adapters.residential.solarman.httpx.Client", return_value=sync_client):
        adapter._access_token = "tok-abc123"
        adapter._token_needs_refresh = False
        assert adapter._get_token() == "tok-abc123"


# ── authenticate ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_authenticate_success():
    adapter = _make_adapter()
    token_resp = _mock_token_response()
    sync_client = _mock_sync_client(token_resp)

    with patch("app.adapters.residential.solarman.httpx.Client", return_value=sync_client):
        result = await adapter.authenticate()

    assert result is True
    assert adapter._access_token == "tok-abc123"


@pytest.mark.asyncio
async def test_authenticate_failure_returns_false():
    adapter = _make_adapter()
    sync_client = MagicMock()
    sync_client.__enter__ = MagicMock(return_value=sync_client)
    sync_client.__exit__ = MagicMock(return_value=False)
    sync_client.post.side_effect = Exception("Connection refused")

    with patch("app.adapters.residential.solarman.httpx.Client", return_value=sync_client):
        result = await adapter.authenticate()

    assert result is False


# ── discover_devices ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_discover_devices_returns_manifests():
    adapter = _make_adapter()
    adapter._access_token = "tok-abc123"
    adapter._token_needs_refresh = False

    adapter._user_id = 6681

    plant_resp = MagicMock()
    plant_resp.status_code = 200
    plant_resp.raise_for_status = MagicMock()
    plant_resp.json.return_value = {
        "stationList": [
            {"id": 111, "name": "My Home"},
            {"id": 222, "name": "Garage"},
        ]
    }

    with patch("app.adapters.residential.solarman.httpx.AsyncClient") as mock_cls:
        instance = AsyncMock()
        instance.request = AsyncMock(return_value=plant_resp)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=instance)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        manifests = await adapter.discover_devices()

    call_body = instance.request.call_args.kwargs["json"]
    assert call_body["userId"] == 6681

    assert len(manifests) == 2
    assert manifests[0].device_id == "111"
    assert manifests[0].source_system == "solarman"
    assert "pv" in manifests[0].capabilities


# ── get_realtime ──────────────────────────────────────────────────────────────


def _patch_async_client(resp: MagicMock):
    """Helper: patch httpx.AsyncClient to return a mock response."""
    from unittest.mock import patch as _patch

    mock_cls = MagicMock()
    instance = AsyncMock()
    instance.request = AsyncMock(return_value=resp)
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=instance)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
    return _patch("app.adapters.residential.solarman.httpx.AsyncClient", mock_cls)


@pytest.mark.asyncio
async def test_get_realtime_normalises_fields():
    adapter = _make_adapter()
    adapter._access_token = "tok-abc123"
    adapter._token_needs_refresh = False

    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "dataList": [
            {"key": "generationPower", "value": "2500.0"},
            {"key": "batterySoc", "value": "75.5"},
            {"key": "batteryPower", "value": "-300.0"},
            {"key": "purchasePower", "value": "0.0"},
            {"key": "usePower", "value": "2200.0"},
            {"key": "gridVoltage", "value": "230.0"},
        ]
    }

    with _patch_async_client(resp):
        snap = await adapter.get_realtime("dev-001")

    assert snap.pv_power_w == 2500.0
    assert snap.battery_soc_pct == 75.5
    assert snap.battery_power_w == -300.0
    assert snap.grid_power_w == 0.0
    assert snap.load_power_w == 2200.0
    assert snap.grid_voltage_v == 230.0
    assert snap.source_system == "solarman"


@pytest.mark.asyncio
async def test_get_realtime_missing_fields_are_none():
    adapter = _make_adapter()
    adapter._access_token = "tok-abc123"
    adapter._token_needs_refresh = False

    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"dataList": []}

    with _patch_async_client(resp):
        snap = await adapter.get_realtime("dev-001")

    assert snap.pv_power_w is None
    assert snap.battery_soc_pct is None

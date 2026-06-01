from __future__ import annotations

import threading
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.residential.victron_vrm import VictronVRMAdapter, _derive_load

_SITE_CONFIG = {
    "username": "user@example.com",
    "password": "secret",
    "site_id": "site-test",
}


def _make_adapter(extra: dict | None = None) -> VictronVRMAdapter:
    cfg = {**_SITE_CONFIG, **(extra or {})}
    return VictronVRMAdapter(site_config=cfg)


def _mock_login_response() -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"token": "tok-xyz", "idUser": 42}
    return resp


def _mock_sync_client(login_resp: MagicMock) -> MagicMock:
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.post.return_value = login_resp
    return client


def _patch_async_client(resp: MagicMock):
    mock_cls = MagicMock()
    instance = AsyncMock()
    instance.request = AsyncMock(return_value=resp)
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=instance)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
    return patch("app.adapters.residential.victron_vrm.httpx.AsyncClient", mock_cls)


# ── _derive_load ──────────────────────────────────────────────────────────────


def test_derive_load_all_none_returns_none():
    assert _derive_load(None, None, None) is None


def test_derive_load_all_zero():
    assert _derive_load(0.0, 0.0, 0.0) == 0.0


def test_derive_load_positive_pv_no_grid_no_battery():
    # 2000W PV, 0W grid, 0W battery → 2000W load
    assert _derive_load(2000.0, 0.0, 0.0) == 2000.0


def test_derive_load_partial_none_treated_as_zero():
    # PV=2000, grid=None, battery=None → 2000.0
    assert _derive_load(2000.0, None, None) == 2000.0


def test_derive_load_charging_battery():
    # PV=3000, grid=0, battery=500 (charging) → load=2500
    assert _derive_load(3000.0, 0.0, 500.0) == 2500.0


def test_derive_load_discharging_battery():
    # PV=0, grid=0, battery=-1000 (discharging) → load=1000
    assert _derive_load(0.0, 0.0, -1000.0) == 1000.0


# ── Token management ──────────────────────────────────────────────────────────


def test_refresh_token_stores_token_and_id_user():
    adapter = _make_adapter()
    login_resp = _mock_login_response()
    sync_client = _mock_sync_client(login_resp)

    with patch("app.adapters.residential.victron_vrm.httpx.Client", return_value=sync_client):
        adapter._refresh_token()

    assert adapter._token == "tok-xyz"
    assert adapter._id_user == 42
    assert adapter._token_needs_refresh is False


def test_get_token_calls_refresh_once():
    adapter = _make_adapter()
    login_resp = _mock_login_response()
    sync_client = _mock_sync_client(login_resp)

    with patch("app.adapters.residential.victron_vrm.httpx.Client", return_value=sync_client):
        tok1 = adapter._get_token()
        tok2 = adapter._get_token()

    assert tok1 == "tok-xyz"
    assert tok1 == tok2
    assert sync_client.post.call_count == 1


def test_token_refresh_on_401():
    """On 401, _token_needs_refresh flag triggers re-auth exactly once."""
    adapter = _make_adapter()
    adapter._token = "old-tok"
    adapter._id_user = 42
    adapter._token_needs_refresh = False

    login_resp = _mock_login_response()
    sync_client = _mock_sync_client(login_resp)

    with patch("app.adapters.residential.victron_vrm.httpx.Client", return_value=sync_client):
        with adapter._token_lock:
            adapter._token_needs_refresh = True
        tok = adapter._get_token()

    assert tok == "tok-xyz"
    assert sync_client.post.call_count == 1


def test_concurrent_refresh_no_double_auth():
    """Lock prevents double refresh: if token already refreshed when lock acquired, reuse it."""
    adapter = _make_adapter()
    adapter._token = None
    adapter._token_needs_refresh = True

    refresh_count = 0

    def _fake_refresh(self_inner=None):
        nonlocal refresh_count
        refresh_count += 1
        adapter._token = "new-tok"
        adapter._id_user = 99
        adapter._token_needs_refresh = False

    with patch.object(adapter, "_refresh_token", side_effect=_fake_refresh):
        results = []

        def _worker():
            results.append(adapter._get_token())

        threads = [threading.Thread(target=_worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    # Lock ensures refresh runs once; all threads get the same token
    assert refresh_count == 1
    assert all(r == "new-tok" for r in results)


def test_id_user_cached_from_site_config():
    """If id_user already in site_config, skip fetching it on _get_id_user."""
    adapter = _make_adapter(extra={"id_user": 77})
    assert adapter._id_user == 77


# ── authenticate ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_authenticate_success():
    adapter = _make_adapter()
    login_resp = _mock_login_response()
    sync_client = _mock_sync_client(login_resp)

    with patch("app.adapters.residential.victron_vrm.httpx.Client", return_value=sync_client):
        ok = await adapter.authenticate()

    assert ok is True
    assert adapter._token == "tok-xyz"
    assert adapter._id_user == 42


@pytest.mark.asyncio
async def test_authenticate_failure_returns_false():
    adapter = _make_adapter()
    sync_client = MagicMock()
    sync_client.__enter__ = MagicMock(return_value=sync_client)
    sync_client.__exit__ = MagicMock(return_value=False)
    sync_client.post.side_effect = Exception("Connection refused")

    with patch("app.adapters.residential.victron_vrm.httpx.Client", return_value=sync_client):
        ok = await adapter.authenticate()

    assert ok is False


# ── discover_devices ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_discover_devices_returns_manifests():
    adapter = _make_adapter()
    adapter._token = "tok-xyz"
    adapter._id_user = 42
    adapter._token_needs_refresh = False

    installations_resp = MagicMock()
    installations_resp.status_code = 200
    installations_resp.raise_for_status = MagicMock()
    installations_resp.json.return_value = {
        "records": [
            {"idSite": 1001, "name": "Home Solar", "hasBattery": True, "hasGenerator": False},
            {"idSite": 1002, "name": "Cabin", "hasBattery": False, "hasGenerator": False},
        ]
    }

    with _patch_async_client(installations_resp):
        manifests = await adapter.discover_devices()

    assert len(manifests) == 2
    assert manifests[0].device_id == "1001"
    assert manifests[0].source_system == "victron"
    assert "battery" in manifests[0].capabilities
    assert "battery" not in manifests[1].capabilities


@pytest.mark.asyncio
async def test_discover_devices_skips_missing_idsite():
    adapter = _make_adapter()
    adapter._token = "tok-xyz"
    adapter._id_user = 42
    adapter._token_needs_refresh = False

    installations_resp = MagicMock()
    installations_resp.status_code = 200
    installations_resp.raise_for_status = MagicMock()
    installations_resp.json.return_value = {
        "records": [
            {"idSite": 1001, "name": "Home Solar"},
            {"name": "No ID Site"},  # missing idSite
        ]
    }

    with _patch_async_client(installations_resp):
        manifests = await adapter.discover_devices()

    assert len(manifests) == 1
    assert manifests[0].device_id == "1001"


# ── get_realtime ──────────────────────────────────────────────────────────────


def _make_widget_resp(records: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"success": 1, "records": records}
    return resp


@pytest.mark.asyncio
async def test_get_realtime_normalises_all_fields():
    adapter = _make_adapter()
    adapter._token = "tok-xyz"
    adapter._id_user = 42
    adapter._token_needs_refresh = False

    battery_records = {
        "Soc": {"value": 75.0},
        "P": {"value": -200.0},
        "Soh": {"value": 88.0},
    }
    solar_records = {"Ppv": {"value": 3000.0}}
    grid_records = {"Power": {"value": 500.0}, "VoltageL1": {"value": 231.0}}

    call_count = 0

    async def _fake_request(method, path, **kwargs):
        nonlocal call_count
        call_count += 1
        if "BatteryMonitor" in path:
            return {"success": 1, "records": battery_records}
        if "SolarChargerSummary" in path:
            return {"success": 1, "records": solar_records}
        if "GridMeter" in path:
            return {"success": 1, "records": grid_records}
        return {}

    with patch.object(adapter, "_request", side_effect=_fake_request):
        snap = await adapter.get_realtime("1001")

    assert snap.pv_power_w == 3000.0
    assert snap.battery_soc_pct == 75.0
    assert snap.battery_power_w == -200.0
    assert snap.grid_power_w == 500.0
    assert snap.grid_voltage_v == 231.0
    assert snap.battery_soh_pct == 88.0
    assert snap.source_system == "victron"
    # load = PV + grid - battery_charging_draw = 3000 + 500 - (-200) = ... wait
    # battery_power_w = -200 means discharging (negative = output to loads)
    # load = pv + grid - battery_power_w = 3000 + 500 - (-200) = 3700
    assert snap.load_power_w == 3700.0


@pytest.mark.asyncio
async def test_get_realtime_battery_soh_none_when_unavailable():
    adapter = _make_adapter()
    adapter._token = "tok-xyz"
    adapter._id_user = 42
    adapter._token_needs_refresh = False

    battery_records = {"Soc": {"value": 80.0}, "P": {"value": 0.0}}  # no Soh key
    solar_records = {"Ppv": {"value": 1000.0}}
    grid_records = {}

    async def _fake_request(method, path, **kwargs):
        if "BatteryMonitor" in path:
            return {"success": 1, "records": battery_records}
        if "SolarChargerSummary" in path:
            return {"success": 1, "records": solar_records}
        return {"success": 1, "records": grid_records}

    with patch.object(adapter, "_request", side_effect=_fake_request):
        snap = await adapter.get_realtime("1001")

    assert snap.battery_soh_pct is None


@pytest.mark.asyncio
async def test_get_realtime_partial_widgets_unavailable():
    """Widget failures are swallowed — corresponding fields become None."""
    adapter = _make_adapter()
    adapter._token = "tok-xyz"
    adapter._id_user = 42
    adapter._token_needs_refresh = False

    async def _fake_request(method, path, **kwargs):
        if "SolarChargerSummary" in path:
            raise RuntimeError("widget unavailable")
        if "GridMeter" in path:
            raise RuntimeError("widget unavailable")
        return {"success": 1, "records": {"Soc": {"value": 60.0}, "P": {"value": 100.0}}}

    with patch.object(adapter, "_request", side_effect=_fake_request):
        snap = await adapter.get_realtime("1001")

    assert snap.pv_power_w is None
    assert snap.grid_power_w is None
    assert snap.battery_soc_pct == 60.0
    # load: pv=None, grid=None, battery=100 → (0+0-100) = -100 (not None since battery is present)
    assert snap.load_power_w == -100.0


@pytest.mark.asyncio
async def test_get_realtime_all_widgets_unavailable_load_is_none():
    """If all widgets fail, load_power_w is None (all inputs None)."""
    adapter = _make_adapter()
    adapter._token = "tok-xyz"
    adapter._id_user = 42
    adapter._token_needs_refresh = False

    async def _fake_request(method, path, **kwargs):
        raise RuntimeError("all widgets down")

    with patch.object(adapter, "_request", side_effect=_fake_request):
        snap = await adapter.get_realtime("1001")

    assert snap.pv_power_w is None
    assert snap.grid_power_w is None
    assert snap.battery_power_w is None
    assert snap.load_power_w is None


# ── get_historical ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_historical_returns_snapshots():
    adapter = _make_adapter()
    adapter._token = "tok-xyz"
    adapter._id_user = 42
    adapter._token_needs_refresh = False

    stats_resp = MagicMock()
    stats_resp.status_code = 200
    stats_resp.raise_for_status = MagicMock()
    stats_resp.json.return_value = {
        "records": {
            "Ppv": [
                {"timestamp": 1700000000, "value": 2500.0},
                {"timestamp": 1700003600, "value": 3100.0},
            ],
            "batteryMonitorState": [
                {"timestamp": 1700000000, "value": 70.0},
                {"timestamp": 1700003600, "value": 75.0},
            ],
            "gridPower": [
                {"timestamp": 1700000000, "value": 200.0},
                {"timestamp": 1700003600, "value": 0.0},
            ],
        }
    }

    with _patch_async_client(stats_resp):
        snaps = await adapter.get_historical(
            "1001",
            start=datetime.utcfromtimestamp(1700000000),
            end=datetime.utcfromtimestamp(1700007200),
        )

    assert len(snaps) == 2
    assert snaps[0].pv_power_w == 2500.0
    assert snaps[0].battery_soc_pct == 70.0
    assert snaps[0].grid_power_w == 200.0
    assert snaps[0].source_system == "victron"
    assert snaps[0].load_power_w == 2500.0 + 200.0  # battery_power=None → 0


# ── get_alarms ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_alarms_normalises_severity():
    adapter = _make_adapter()
    adapter._token = "tok-xyz"
    adapter._id_user = 42
    adapter._token_needs_refresh = False

    alarms_resp = MagicMock()
    alarms_resp.status_code = 200
    alarms_resp.raise_for_status = MagicMock()
    alarms_resp.json.return_value = {
        "alarms": [
            {"idAlarm": 10, "description": "Low battery", "severity": "critical", "started": 1700000000, "ended": None},
            {
                "idAlarm": 20,
                "description": "Grid lost",
                "severity": "warning",
                "started": 1700001000,
                "ended": 1700002000,
            },
        ]
    }

    with _patch_async_client(alarms_resp):
        alarms = await adapter.get_alarms("1001")

    assert len(alarms) == 2
    assert alarms[0].severity == "critical"
    assert alarms[0].is_active is True
    assert alarms[1].severity == "warning"
    assert alarms[1].is_active is False


@pytest.mark.asyncio
async def test_get_alarms_empty():
    adapter = _make_adapter()
    adapter._token = "tok-xyz"
    adapter._id_user = 42
    adapter._token_needs_refresh = False

    alarms_resp = MagicMock()
    alarms_resp.status_code = 200
    alarms_resp.raise_for_status = MagicMock()
    alarms_resp.json.return_value = {"alarms": []}

    with _patch_async_client(alarms_resp):
        alarms = await adapter.get_alarms("1001")

    assert alarms == []

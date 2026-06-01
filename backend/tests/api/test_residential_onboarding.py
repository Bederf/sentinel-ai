from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.api.residential_onboarding as mod
from app.api.residential_onboarding import OnboardRequest

# ── HTTP client fixture (GET /platforms only — no async-patch issues) ─────────


@pytest.fixture()
def http_client():
    from fastapi import APIRouter, FastAPI

    app = FastAPI()
    r = APIRouter(prefix="/api/residential")

    @r.get("/platforms")
    async def _platforms():
        return await mod.get_platforms()

    app.include_router(r)
    return TestClient(app)


# ── Direct-call helper (avoids TestClient async-patch boundary issue) ─────────


def _req(**overrides) -> OnboardRequest:
    base = {
        "site_id": "site-test",
        "platform": "solarman",
        "deployment_tier": "cloud_only",
        "site_config": {"email": "test@example.com", "password": "s3cr3t", "site_id": "site-test"},
        "eskom_area_code": "KZN-2-16",
        "tariff_type": "prepaid",
        "polling_interval_seconds": 300,
    }
    base.update(overrides)
    return OnboardRequest(**base)


# ── GET /api/residential/platforms ───────────────────────────────────────────


def test_get_platforms_returns_list(http_client):
    resp = http_client.get("/api/residential/platforms")
    assert resp.status_code == 200
    data = resp.json()
    assert "platforms" in data
    ids = [p["id"] for p in data["platforms"]]
    assert "solarman" in ids
    assert "victron" in ids


def test_get_platforms_includes_auth_fields(http_client):
    resp = http_client.get("/api/residential/platforms")
    platforms = {p["id"]: p for p in resp.json()["platforms"]}
    solarman = platforms["solarman"]
    assert len(solarman["auth_fields"]) > 0
    field_keys = [f["key"] for f in solarman["auth_fields"]]
    assert "email" in field_keys
    assert "password" in field_keys


# ── POST /api/residential/onboard — happy path ────────────────────────────────


@pytest.fixture()
def mock_solarman_adapter():
    from app.adapters.residential.schemas import DeviceManifest

    adapter = MagicMock()
    adapter.authenticate = AsyncMock(return_value=True)
    adapter.discover_devices = AsyncMock(
        return_value=[
            DeviceManifest(
                device_id="dev-001",
                device_name="Home Inverter",
                device_type="inverter",
                source_system="solarman",
                capabilities=["pv", "grid", "load"],
            )
        ]
    )
    return adapter


@pytest.mark.asyncio
async def test_onboard_happy_path(mock_solarman_adapter):
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{"id": "res-site-uuid-001"}]

    with (
        patch("app.api.residential_onboarding.build_adapter", return_value=mock_solarman_adapter),
        patch("app.api.residential_onboarding.get_supabase_client", return_value=mock_supabase),
        patch("app.api.residential_onboarding.get_mqtt_provisioner"),
        patch("app.api.residential_onboarding.add_residential_polling_job"),
    ):
        result = await mod.onboard_residential_site(_req())

    assert result["status"] == "onboarded"
    assert result["devices_discovered"] == 1
    assert result["site_id"] == "site-test"
    assert result["platform"] == "solarman"


@pytest.mark.asyncio
async def test_onboard_creates_device_records(mock_solarman_adapter):
    inserted_tables: list[str] = []

    mock_supabase = MagicMock()

    def _table(name: str):
        inserted_tables.append(name)
        tbl = MagicMock()
        tbl.insert.return_value.execute.return_value.data = [{"id": "uuid-001"}]
        return tbl

    mock_supabase.table.side_effect = _table

    with (
        patch("app.api.residential_onboarding.build_adapter", return_value=mock_solarman_adapter),
        patch("app.api.residential_onboarding.get_supabase_client", return_value=mock_supabase),
        patch("app.api.residential_onboarding.get_mqtt_provisioner"),
        patch("app.api.residential_onboarding.add_residential_polling_job"),
    ):
        await mod.onboard_residential_site(_req())

    assert "residential_sites" in inserted_tables
    assert "residential_devices" in inserted_tables


# ── POST /api/residential/onboard — error paths ───────────────────────────────


@pytest.mark.asyncio
async def test_onboard_unsupported_platform_returns_400():
    with pytest.raises(HTTPException) as exc_info:
        await mod.onboard_residential_site(_req(platform="unknown_platform"))
    assert exc_info.value.status_code == 400
    assert "Unsupported platform" in exc_info.value.detail


@pytest.mark.asyncio
async def test_onboard_auth_failure_returns_401():
    adapter = MagicMock()
    adapter.authenticate = AsyncMock(return_value=False)

    with (
        patch("app.api.residential_onboarding.build_adapter", return_value=adapter),
        pytest.raises(HTTPException) as exc_info,
    ):
        await mod.onboard_residential_site(_req())

    assert exc_info.value.status_code == 401
    assert "authentication failed" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_onboard_auth_timeout_returns_504():
    adapter = MagicMock()
    adapter.authenticate = AsyncMock(return_value=True)

    with (
        patch("app.api.residential_onboarding.build_adapter", return_value=adapter),
        patch("app.api.residential_onboarding.asyncio.wait_for", side_effect=asyncio.TimeoutError),
        pytest.raises(HTTPException) as exc_info,
    ):
        await mod.onboard_residential_site(_req())

    assert exc_info.value.status_code == 504
    assert "timed out" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_onboard_discovery_timeout_returns_504(mock_solarman_adapter):
    call_count = 0

    async def _wait_for(coro, timeout):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return True
        raise TimeoutError

    with (
        patch("app.api.residential_onboarding.build_adapter", return_value=mock_solarman_adapter),
        patch("app.api.residential_onboarding.asyncio.wait_for", side_effect=_wait_for),
        pytest.raises(HTTPException) as exc_info,
    ):
        await mod.onboard_residential_site(_req())

    assert exc_info.value.status_code == 504


# ── Victron onboarding happy path ─────────────────────────────────────────────


@pytest.fixture()
def mock_victron_adapter():
    from app.adapters.residential.schemas import DeviceManifest

    adapter = MagicMock()
    adapter.authenticate = AsyncMock(return_value=True)
    adapter.discover_devices = AsyncMock(
        return_value=[
            DeviceManifest(
                device_id="12345",
                device_name="Victron Multiplus-II",
                device_type="inverter",
                source_system="victron",
                capabilities=["pv", "battery", "grid", "load"],
            )
        ]
    )
    return adapter


@pytest.mark.asyncio
async def test_onboard_victron_happy_path(mock_victron_adapter):
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{"id": "res-site-uuid-002"}]

    victron_req = _req(
        platform="victron",
        site_config={"username": "user@example.com", "password": "s3cr3t", "site_id": "site-test"},
    )

    with (
        patch("app.api.residential_onboarding.build_adapter", return_value=mock_victron_adapter),
        patch("app.api.residential_onboarding.get_supabase_client", return_value=mock_supabase),
        patch("app.api.residential_onboarding.get_mqtt_provisioner"),
        patch("app.api.residential_onboarding.add_residential_polling_job"),
    ):
        result = await mod.onboard_residential_site(victron_req)

    assert result["status"] == "onboarded"
    assert result["platform"] == "victron"
    assert result["devices_discovered"] == 1


@pytest.mark.asyncio
async def test_onboard_victron_credentials_encrypted(mock_victron_adapter):
    """site_config stored in DB must be encrypted (not plaintext)."""
    stored_config: list[str] = []

    mock_supabase = MagicMock()

    original_insert = MagicMock()
    original_insert.execute.return_value.data = [{"id": "uuid-vic"}]

    def _table_side_effect(name: str):
        tbl = MagicMock()
        if name == "residential_sites":

            def _store_config(row, **kwargs):
                stored_config.append(row.get("site_config", ""))
                return original_insert

            tbl.insert = _store_config
            tbl.upsert = _store_config  # Phase 213: changed insert→upsert
        else:
            tbl.insert.return_value.execute.return_value.data = []
        return tbl

    mock_supabase.table.side_effect = _table_side_effect

    victron_req = _req(
        platform="victron",
        site_config={"username": "user@example.com", "password": "top_secret_pass", "site_id": "site-test"},
    )

    with (
        patch("app.api.residential_onboarding.build_adapter", return_value=mock_victron_adapter),
        patch("app.api.residential_onboarding.get_supabase_client", return_value=mock_supabase),
        patch("app.api.residential_onboarding.get_mqtt_provisioner"),
        patch("app.api.residential_onboarding.add_residential_polling_job"),
    ):
        await mod.onboard_residential_site(victron_req)

    assert stored_config, "No site_config was stored"
    assert "top_secret_pass" not in stored_config[0], "Password stored unencrypted"


# ── GET /platforms — victron entry ────────────────────────────────────────────


def test_get_platforms_includes_victron(http_client):
    resp = http_client.get("/api/residential/platforms")
    platforms = {p["id"]: p for p in resp.json()["platforms"]}
    assert "victron" in platforms
    victron = platforms["victron"]
    field_keys = [f["key"] for f in victron["auth_fields"]]
    assert "username" in field_keys
    assert "password" in field_keys


# ── Credential safety ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_onboard_credentials_not_in_logs(mock_solarman_adapter, caplog):
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{"id": "uuid-001"}]

    with (
        patch("app.api.residential_onboarding.build_adapter", return_value=mock_solarman_adapter),
        patch("app.api.residential_onboarding.get_supabase_client", return_value=mock_supabase),
        patch("app.api.residential_onboarding.get_mqtt_provisioner"),
        patch("app.api.residential_onboarding.add_residential_polling_job"),
        caplog.at_level("DEBUG"),
    ):
        await mod.onboard_residential_site(_req())

    for record in caplog.records:
        assert "s3cr3t" not in record.message, "Password leaked into logs"


# ── chat_id field ──────────────────────────────────────────────────────────────


def test_onboard_request_chat_id_optional():
    # Without chat_id
    req = OnboardRequest(
        site_id="res-12345",
        platform="solarman",
        deployment_tier="cloud_only",
        site_config={"email": "a@b.com", "password": "pw"},
    )
    assert req.chat_id is None
    # With chat_id
    req2 = OnboardRequest(
        site_id="res-12345",
        platform="solarman",
        deployment_tier="cloud_only",
        site_config={"email": "a@b.com", "password": "pw"},
        chat_id=12345,
    )
    assert req2.chat_id == 12345

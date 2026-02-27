"""Tests for call-log reporter location memory endpoints."""

import pytest

from app.config.settings import settings


@pytest.fixture
def preserve_sentry_auth_settings():
    """Preserve mutable Sentry auth settings patched in these tests."""
    original_secret = settings.sentry_webhook_secret
    original_api_key = settings.sentry_bot_api_key
    original_demo_mode = settings.demo_mode
    original_ingestion_mode = settings.ingestion_mode
    try:
        yield
    finally:
        settings.sentry_webhook_secret = original_secret
        settings.sentry_bot_api_key = original_api_key
        settings.demo_mode = original_demo_mode
        settings.ingestion_mode = original_ingestion_mode


@pytest.fixture
def sentry_headers(preserve_sentry_auth_settings):
    """Configure deterministic Sentry headers for /api/sentry/* tests."""
    settings.demo_mode = False
    settings.ingestion_mode = "live_control"
    settings.sentry_webhook_secret = "test-secret"
    settings.sentry_bot_api_key = "test-sentry-api-key"
    return {
        "X-Sentry-Secret": "test-secret",
        "X-Sentry-API-Key": "test-sentry-api-key",
    }


@pytest.fixture
def isolate_location_memory_file(tmp_path, monkeypatch):
    """Use a temp JSON store for reporter location memory fallback."""
    from app.database.repositories import reporter_location_repository as repo_mod

    test_file = tmp_path / "reporter_location_memory.json"
    test_file.write_text("[]\n")
    monkeypatch.setattr(repo_mod, "JSON_PATH", test_file)
    return test_file


@pytest.mark.asyncio
async def test_call_log_persists_reporter_location_memory(
    client, monkeypatch, sentry_headers, isolate_location_memory_file
):
    """Successful call-log should save reporter phone/desk memory for next intake."""

    async def _fake_create_work_order(self, wo_data):
        return {
            "id": "wo-test-id",
            "code": "WO-2026-9001",
            "title": wo_data.get("title"),
        }

    monkeypatch.setattr(
        "app.database.repositories.work_order_repository.WorkOrderRepository.create_work_order",
        _fake_create_work_order,
        raising=False,
    )

    payload = {
        "site_id": "site-002",
        "zone_id": "Zone-208",
        "floor": "L2",
        "desk_id": "208",
        "location_text": "",
        "category": "Plumbing",
        "sub_category": "Leaking tap",
        "specialty": "plumbing",
        "priority": "medium",
        "title": "Plumbing: Leaking tap",
        "description": "Reported via mobile. Dripping tap near desk 208.",
        "reported_by": "Jane",
        "reporter_telegram_id": "12345678",
        "reporter_phone": "+27 72 123 4567",
        "channel": "whatsapp",
        "original_message": "dripping tap near my desk",
    }

    create_resp = await client.post("/api/sentry/call-log", json=payload, headers=sentry_headers)
    assert create_resp.status_code == 200, create_resp.text
    create_data = create_resp.json()
    assert create_data["success"] is True
    assert create_data["location_memory_saved"] is True

    lookup_resp = await client.get(
        "/api/sentry/call-log/location-memory",
        params={"reporter_phone": "+27721234567"},
        headers=sentry_headers,
    )
    assert lookup_resp.status_code == 200, lookup_resp.text
    lookup_data = lookup_resp.json()
    assert lookup_data["success"] is True
    assert lookup_data["found"] is True
    assert lookup_data["desk_id"] == "208"
    assert lookup_data["site_id"] == "site-002"
    assert lookup_data["floor"] == "L2"


@pytest.mark.asyncio
async def test_call_log_location_memory_lookup_by_telegram_id(client, sentry_headers, isolate_location_memory_file):
    """Lookup should resolve memory using reporter_telegram_id when phone not provided."""
    from app.database.repositories.reporter_location_repository import get_reporter_location_repository

    repo = get_reporter_location_repository()
    saved = repo.upsert(
        {
            "reporter_telegram_id": "998877",
            "reporter_name": "Alex",
            "site_id": "site-002",
            "zone_id": "Zone-120",
            "floor": "L1",
            "desk_id": "120",
            "location_text": "Desk 120, L1, Zone-120",
            "channel": "telegram",
        }
    )
    assert saved is not None

    resp = await client.get(
        "/api/sentry/call-log/location-memory",
        params={"reporter_telegram_id": "998877"},
        headers=sentry_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["found"] is True
    assert data["desk_id"] == "120"
    assert data["reporter_telegram_id"] == "998877"


@pytest.mark.asyncio
async def test_call_log_location_memory_not_found_and_validation(client, sentry_headers, isolate_location_memory_file):
    """Lookup returns found=false for unknown reporter and 400 for missing identifiers."""
    not_found = await client.get(
        "/api/sentry/call-log/location-memory",
        params={"reporter_phone": "+27720000000"},
        headers=sentry_headers,
    )
    assert not_found.status_code == 200
    assert not_found.json()["found"] is False

    bad = await client.get("/api/sentry/call-log/location-memory", headers=sentry_headers)
    assert bad.status_code == 400
    assert "reporter_phone or reporter_telegram_id" in bad.json()["detail"]

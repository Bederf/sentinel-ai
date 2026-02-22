"""Auth-mode tests for Sentry webhook security behavior."""

import pytest

from app.config.settings import settings


@pytest.fixture
def preserve_settings_state():
    """Preserve mutable settings fields that are patched during auth-mode tests."""
    original_demo_mode = settings.demo_mode
    original_ingestion_mode = settings.ingestion_mode
    original_secret = settings.sentry_webhook_secret
    original_sentry_api_key = settings.sentry_bot_api_key
    try:
        yield
    finally:
        settings.demo_mode = original_demo_mode
        settings.ingestion_mode = original_ingestion_mode
        settings.sentry_webhook_secret = original_secret
        settings.sentry_bot_api_key = original_sentry_api_key


@pytest.fixture
def mock_service_record_list(monkeypatch):
    """Avoid DB access in webhook endpoints that list pending service records."""

    async def _fake_list(self, filters=None):  # noqa: ARG001
        return []

    monkeypatch.setattr("app.api.sentry_webhooks.ServiceRecordRepository.list", _fake_list, raising=False)


def _api_key_headers() -> dict[str, str]:
    return {"X-Sentry-API-Key": settings.sentry_bot_api_key}


@pytest.mark.asyncio
async def test_pending_work_orders_public_in_simulation_without_secret(
    client,
    monkeypatch,
    preserve_settings_state,
    mock_service_record_list,
):
    """Simulation mode keeps /work-order/pending public when no secret is configured."""
    settings.demo_mode = False
    settings.ingestion_mode = "simulation"
    settings.sentry_webhook_secret = ""
    settings.sentry_bot_api_key = "test-sentry-api-key"
    monkeypatch.delenv("SENTRY_WEBHOOK_SECRET", raising=False)

    resp = await client.get("/api/sentry/work-order/pending", headers=_api_key_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["pending_count"] == 0


@pytest.mark.asyncio
async def test_live_mode_missing_secret_fails_closed(
    client,
    monkeypatch,
    preserve_settings_state,
):
    """Live modes fail closed when SENTRY_WEBHOOK_SECRET is missing."""
    settings.demo_mode = False
    settings.ingestion_mode = "shadow_live"
    settings.sentry_webhook_secret = ""
    settings.sentry_bot_api_key = "test-sentry-api-key"
    monkeypatch.delenv("SENTRY_WEBHOOK_SECRET", raising=False)

    resp = await client.post("/api/sentry/process-pending-notifications", headers=_api_key_headers())
    assert resp.status_code == 503
    assert "misconfigured" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_live_mode_invalid_secret_returns_403(
    client,
    preserve_settings_state,
):
    """Live mode rejects invalid webhook secrets."""
    settings.demo_mode = False
    settings.ingestion_mode = "live_control"
    settings.sentry_webhook_secret = "expected-secret"
    settings.sentry_bot_api_key = "test-sentry-api-key"

    resp = await client.post(
        "/api/sentry/process-pending-notifications",
        headers={**_api_key_headers(), "X-Sentry-Secret": "wrong-secret"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_live_mode_valid_secret_allows_request(
    client,
    preserve_settings_state,
    mock_service_record_list,
):
    """Live mode accepts correct webhook secret."""
    settings.demo_mode = False
    settings.ingestion_mode = "live_control"
    settings.sentry_webhook_secret = "correct-secret"
    settings.sentry_bot_api_key = "test-sentry-api-key"

    resp = await client.post(
        "/api/sentry/process-pending-notifications",
        headers={**_api_key_headers(), "X-Sentry-Secret": "correct-secret"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["processed"] == 0

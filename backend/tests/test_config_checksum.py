import logging
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from app.config.settings import Settings
from app.startup import events as startup_events
from app.utils.ai_provenance import get_ml_provenance, provenance_headers


def _make_settings(**overrides) -> Settings:
    base = {
        "_env_file": None,
        "jwt_secret_key": "test-secret-key-minimum-32-chars-long",
        "supabase_service_role_key": "service-role-key",
    }
    base.update(overrides)
    return Settings(**base)


def test_config_checksum_stable_for_secret_rotation():
    original = _make_settings(
        anthropic_api_key="anthropic-key-a",
        notification_smtp_password="smtp-password-a",
        sentry_webhook_secret="webhook-a",
    )
    rotated = _make_settings(
        anthropic_api_key="anthropic-key-b",
        notification_smtp_password="smtp-password-b",
        sentry_webhook_secret="webhook-b",
    )

    assert original.config_checksum == rotated.config_checksum


def test_config_checksum_changes_when_effective_config_changes():
    original = _make_settings(environment="development")
    updated = _make_settings(environment="production")

    assert original.config_checksum != updated.config_checksum


def test_provenance_headers_include_app_version_and_config_checksum():
    provenance = get_ml_provenance("inspection-analyzer-v1")
    headers = provenance_headers(provenance)

    assert headers["X-App-Version"] == provenance.app_version
    assert headers["X-Config-Checksum"] == provenance.config_checksum
    assert len(headers["X-Config-Checksum"]) == 64


@pytest.mark.asyncio
async def test_startup_logs_runtime_config_checksum(monkeypatch, caplog):
    async def _noop_devices_startup():
        return None

    monkeypatch.setenv("TESTING", "true")
    monkeypatch.setattr("app.api.devices.startup_event", _noop_devices_startup)
    monkeypatch.setattr(
        startup_events,
        "settings",
        SimpleNamespace(
            demo_mode=False,
            jwt_secret_key="test-secret-key-minimum-32-chars-long",
            supabase_key="",
            solar_connector_mode="simulation",
            modbus_bess_ip="",
            aegis_bess_writer_enabled=False,
            edge_mode=False,
            parasite_tier3_enabled=False,
            environment="test",
            parasite_enabled=False,
            app_version="99.1",
            config_checksum="abc123checksum",
            sentry_webhook_secret="",
            is_live_mode=False,
        ),
    )

    with caplog.at_level(logging.INFO, logger="sentinel.startup"):
        await startup_events.startup_event(FastAPI())

    assert "config_checksum=abc123checksum" in caplog.text
    assert "version=99.1" in caplog.text

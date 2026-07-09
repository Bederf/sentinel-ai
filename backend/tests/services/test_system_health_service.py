from datetime import UTC, datetime

import pytest

from app.config.settings import settings
from app.services.system_health_service import SystemHealthService


async def _health(score: int, status: str = "healthy", note: str = "ok"):
    return {"score": score, "status": status, "note": note}


@pytest.mark.asyncio
async def test_overall_health_score_is_normalized_and_critical_alerts_degrade_status(monkeypatch):
    service = object.__new__(SystemHealthService)

    monkeypatch.setattr(service, "_check_supabase", lambda: _health(95))
    monkeypatch.setattr(service, "_check_redis", lambda: _health(95))
    monkeypatch.setattr(service, "_check_event_bus", lambda: _health(95))
    monkeypatch.setattr(service, "_check_n8n", lambda: _health(40, "degraded", "down"))
    monkeypatch.setattr(service, "_check_servicenow", lambda: _health(50, "degraded", "missing credentials"))
    monkeypatch.setattr(service, "_check_notifications", lambda: _health(90))
    monkeypatch.setattr(service, "_check_device_manager", lambda: _health(90))
    monkeypatch.setattr(service, "_check_lighting", lambda: _health(90))
    monkeypatch.setattr(service, "_check_supervisor", lambda: _health(90))
    monkeypatch.setattr(service, "_check_field_network", lambda: _health(90))
    monkeypatch.setattr(service, "_check_obix", lambda: _health(0, "critical", "not authenticated"))
    monkeypatch.setattr(service, "_get_active_alerts", lambda *, limit: [{"severity": "critical"}])

    snapshot = await service.get_current_health()

    assert snapshot["overall_score"] == 81
    assert snapshot["overall_status"] == "degraded"
    assert len(snapshot["active_alerts"]) == 1


class _FakeResp:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, data):
        self._data = data

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def like(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        return _FakeResp(self._data)


class _FakeClient:
    def __init__(self, rows_by_table):
        self._rows_by_table = rows_by_table

    def table(self, name):
        return _FakeQuery(self._rows_by_table.get(name, []))


def test_bridge_runtime_status_uses_persisted_adapter_health():
    service = object.__new__(SystemHealthService)
    service.client = _FakeClient(
        {
            "adapter_health": [
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "is_healthy": True,
                    "metadata": {"last_telemetry_at": "2026-07-02T12:24:40Z"},
                }
            ]
        }
    )

    status = service._get_bridge_runtime_status("site-002")

    assert status["connected"] is True
    assert "Supervisor bridge connected" in status["note"]


@pytest.mark.asyncio
async def test_servicenow_missing_credentials_is_neutral(monkeypatch):
    service = object.__new__(SystemHealthService)

    class _ServiceNow:
        is_configured = False

    monkeypatch.setattr("app.services.servicenow_service.get_servicenow_service", lambda: _ServiceNow())

    result = await service._check_servicenow()

    assert result == {
        "score": 100,
        "status": "not_configured",
        "note": "Credentials not configured",
    }


@pytest.mark.asyncio
async def test_supervisor_without_site_code_is_neutral(monkeypatch):
    service = object.__new__(SystemHealthService)
    monkeypatch.setattr("app.services.system_health_service.get_primary_site_code", lambda: None)

    result = await service._check_supervisor()

    assert result == {
        "score": 100,
        "status": "not_configured",
        "note": "No primary site configured",
    }


@pytest.mark.asyncio
async def test_field_network_without_direct_adapter_is_neutral(monkeypatch):
    service = object.__new__(SystemHealthService)
    service.client = _FakeClient({"site_adapter_config": [{"protocol": "bridge"}]})
    monkeypatch.setattr("app.services.system_health_service.get_primary_site_code", lambda: "site-002")

    result = await service._check_field_network()

    assert result == {
        "score": 100,
        "status": "not_configured",
        "note": "No direct field-network adapter configured for site-002",
    }


@pytest.mark.asyncio
async def test_obix_without_site_adapter_or_settings_is_neutral(monkeypatch):
    service = object.__new__(SystemHealthService)
    service.client = _FakeClient({"site_adapter_config": [{"protocol": "bridge"}]})
    monkeypatch.setattr("app.services.system_health_service.get_primary_site_code", lambda: "site-002")
    monkeypatch.setattr(settings, "niagara_obix_host", "")
    monkeypatch.setattr(settings, "niagara_obix_username", "")
    monkeypatch.setattr(settings, "niagara_obix_password", "")

    result = await service._check_obix()

    assert result == {
        "score": 100,
        "status": "not_configured",
        "note": "No oBIX adapter configured for site-002",
    }


@pytest.mark.asyncio
async def test_n8n_disabled_is_neutral_not_degraded(monkeypatch):
    service = object.__new__(SystemHealthService)
    monkeypatch.setattr(settings, "n8n_enabled", False)

    result = await service._check_n8n()

    assert result == {
        "score": 100,
        "status": "not_configured",
        "note": "Disabled in config",
    }

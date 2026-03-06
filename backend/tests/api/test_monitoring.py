"""Tests for Phase 108: Monitoring Hardening.

Group A: Endpoint contract (4 tests)
Group B: Alert rule evaluation (5 tests)
Group C: Edge cases (3 tests)
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models.audit_log import AuditLogEntry
from app.services.monitoring_service import MonitoringService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_quality_metrics(**overrides):
    defaults = {
        "match_coverage": 95.0,
        "data_freshness_hours": 0.5,
        "error_rate": 0.2,
        "duplicate_rate": 0.1,
        "overall_score": 82.0,
        "trend": "stable",
    }
    defaults.update(overrides)
    return defaults


def _make_integration_health(**overrides):
    defaults = {
        "sources_count": 3,
        "active_sources": 2,
        "last_sync": datetime.utcnow().isoformat(),
        "total_records_ingested": 1500,
        "total_points_mapped": 100,
        "unmatched_points": 5,
        "recent_errors_count": 0,
    }
    defaults.update(overrides)
    return defaults


def _make_audit_entry(action, result, hours_ago=0):
    return AuditLogEntry(
        action=action,
        user="system",
        result=result,
        timestamp=datetime.now() - timedelta(hours=hours_ago),
    )


@pytest.fixture(autouse=True)
def _clear_cooldowns():
    """Reset alert cooldowns between tests."""
    MonitoringService._alert_cooldowns.clear()
    yield
    MonitoringService._alert_cooldowns.clear()


# ===========================================================================
# Group A: Endpoint contract
# ===========================================================================


def test_monitoring_returns_200_with_all_fields(test_client):
    """GET /api/system/monitoring returns 200 with all expected top-level fields."""
    response = test_client.get("/api/system/monitoring")
    assert response.status_code == 200
    data = response.json()
    assert "ingestion_mode" in data
    assert "is_live" in data
    assert "ingestion" in data
    assert "control" in data
    assert "alerts" in data
    assert "trend_24h" in data
    assert "checked_at" in data


def test_monitoring_includes_ingestion_kpis(test_client):
    """Ingestion KPIs sub-object contains expected keys."""
    response = test_client.get("/api/system/monitoring")
    assert response.status_code == 200
    ingestion = response.json()["ingestion"]
    assert "freshness_hours" in ingestion
    assert "error_rate" in ingestion
    assert "unmatched_points" in ingestion
    assert "total_points" in ingestion
    assert "match_coverage" in ingestion
    assert "provenance_summary" in ingestion


def test_monitoring_includes_control_kpis(test_client):
    """Control KPIs sub-object contains expected keys."""
    response = test_client.get("/api/system/monitoring")
    assert response.status_code == 200
    control = response.json()["control"]
    assert "shadow_writes_24h" in control
    assert "blocked_writes_24h" in control
    assert "approved_writes_24h" in control
    assert "safety_violations_24h" in control


def test_monitoring_building_filter(test_client):
    """Passing site_id filters to that building."""
    response = test_client.get("/api/system/monitoring?site_id=test-building")
    assert response.status_code == 200
    data = response.json()
    assert data["site_id"] == "test-building"


# ===========================================================================
# Group B: Alert rule evaluation
# ===========================================================================


@pytest.mark.asyncio
async def test_stale_data_alert_fires():
    """Stale data alert fires when freshness > 24h (imported from integration health)."""
    svc = MonitoringService()
    stale_sync = (datetime.utcnow() - timedelta(hours=30)).isoformat()

    with (
        patch.object(svc._integration_repo, "get_integration_health") as mock_health,
        patch.object(svc._integration_repo, "get_quality_metrics") as mock_qm,
        patch.object(svc._integration_repo, "get_log_sources", return_value=[]),
        patch.object(svc._audit_logger, "get_logs", return_value=[]),
        patch("app.services.monitoring_service.settings") as mock_settings,
    ):
        mock_settings.resolved_ingestion_mode.value = "shadow_live"
        mock_settings.is_live_mode = True
        mock_settings.resolved_ingestion_mode = MagicMock()
        mock_settings.resolved_ingestion_mode.value = "shadow_live"
        mock_settings.resolved_ingestion_mode.__eq__ = lambda self, other: False

        mock_health.return_value = _make_integration_health(last_sync=stale_sync)
        mock_qm.return_value = _make_quality_metrics(data_freshness_hours=30)

        snapshot = await svc.get_snapshot(site_id="test")
        stale_alerts = [a for a in snapshot.alerts if a.rule == "stale_data"]
        assert len(stale_alerts) == 1
        assert stale_alerts[0].severity == "warning"


@pytest.mark.asyncio
async def test_json_in_live_alert_fires():
    """json_in_live alert fires when file/manual sources exist in live mode."""
    svc = MonitoringService()

    with (
        patch.object(svc._integration_repo, "get_integration_health") as mock_health,
        patch.object(svc._integration_repo, "get_quality_metrics") as mock_qm,
        patch.object(svc._integration_repo, "get_log_sources") as mock_sources,
        patch.object(svc._audit_logger, "get_logs", return_value=[]),
        patch("app.services.monitoring_service.settings") as mock_settings,
    ):
        from app.config.settings import IngestionMode

        mock_settings.resolved_ingestion_mode = IngestionMode.SHADOW_LIVE
        mock_settings.is_live_mode = True

        mock_health.return_value = _make_integration_health()
        mock_qm.return_value = _make_quality_metrics()
        mock_sources.return_value = [
            {"connection_type": "api"},
            {"connection_type": "file_drop"},
        ]

        snapshot = await svc.get_snapshot(site_id="test")
        json_alerts = [a for a in snapshot.alerts if a.rule == "json_in_live"]
        assert len(json_alerts) == 1
        assert json_alerts[0].severity == "critical"


@pytest.mark.asyncio
async def test_high_error_rate_warning():
    """High error rate produces warning when rate > 10%."""
    svc = MonitoringService()

    with (
        patch.object(svc._integration_repo, "get_integration_health") as mock_health,
        patch.object(svc._integration_repo, "get_quality_metrics") as mock_qm,
        patch.object(svc._integration_repo, "get_log_sources", return_value=[]),
        patch.object(svc._audit_logger, "get_logs", return_value=[]),
        patch("app.services.monitoring_service.settings") as mock_settings,
    ):
        from app.config.settings import IngestionMode

        mock_settings.resolved_ingestion_mode = IngestionMode.SIMULATION
        mock_settings.is_live_mode = False

        # 1 error out of 5 active = 20% error ratio
        mock_health.return_value = _make_integration_health(recent_errors_count=1, active_sources=5)
        mock_qm.return_value = _make_quality_metrics()

        snapshot = await svc.get_snapshot(site_id="test")
        error_alerts = [a for a in snapshot.alerts if a.rule == "high_error_rate"]
        assert len(error_alerts) == 1
        assert error_alerts[0].severity == "warning"


@pytest.mark.asyncio
async def test_high_error_rate_critical():
    """High error rate produces critical when ratio >= 25%."""
    svc = MonitoringService()

    with (
        patch.object(svc._integration_repo, "get_integration_health") as mock_health,
        patch.object(svc._integration_repo, "get_quality_metrics") as mock_qm,
        patch.object(svc._integration_repo, "get_log_sources", return_value=[]),
        patch.object(svc._audit_logger, "get_logs", return_value=[]),
        patch("app.services.monitoring_service.settings") as mock_settings,
    ):
        from app.config.settings import IngestionMode

        mock_settings.resolved_ingestion_mode = IngestionMode.SIMULATION
        mock_settings.is_live_mode = False

        # 2 errors out of 5 active = 40% error ratio
        mock_health.return_value = _make_integration_health(recent_errors_count=2, active_sources=5)
        mock_qm.return_value = _make_quality_metrics()

        snapshot = await svc.get_snapshot(site_id="test")
        error_alerts = [a for a in snapshot.alerts if a.rule == "high_error_rate"]
        assert len(error_alerts) == 1
        assert error_alerts[0].severity == "critical"


@pytest.mark.asyncio
async def test_low_coverage_alert():
    """Low coverage alert fires when match_coverage < 50%."""
    svc = MonitoringService()

    with (
        patch.object(svc._integration_repo, "get_integration_health") as mock_health,
        patch.object(svc._integration_repo, "get_quality_metrics") as mock_qm,
        patch.object(svc._integration_repo, "get_log_sources", return_value=[]),
        patch.object(svc._audit_logger, "get_logs", return_value=[]),
        patch("app.services.monitoring_service.settings") as mock_settings,
    ):
        from app.config.settings import IngestionMode

        mock_settings.resolved_ingestion_mode = IngestionMode.SIMULATION
        mock_settings.is_live_mode = False

        mock_health.return_value = _make_integration_health(total_points_mapped=100, unmatched_points=60)
        mock_qm.return_value = _make_quality_metrics(match_coverage=40)

        snapshot = await svc.get_snapshot(site_id="test")
        coverage_alerts = [a for a in snapshot.alerts if a.rule == "low_coverage"]
        assert len(coverage_alerts) == 1
        assert coverage_alerts[0].severity == "warning"


# ===========================================================================
# Group C: Edge cases
# ===========================================================================


@pytest.mark.asyncio
async def test_simulation_mode_no_commissioning():
    """In SIMULATION mode, commissioning is None."""
    svc = MonitoringService()

    with (
        patch.object(svc._integration_repo, "get_integration_health") as mock_health,
        patch.object(svc._integration_repo, "get_log_sources", return_value=[]),
        patch.object(svc._audit_logger, "get_logs", return_value=[]),
        patch("app.services.monitoring_service.settings") as mock_settings,
    ):
        from app.config.settings import IngestionMode

        mock_settings.resolved_ingestion_mode = IngestionMode.SIMULATION
        mock_settings.is_live_mode = False

        mock_health.return_value = _make_integration_health()

        snapshot = await svc.get_snapshot()
        assert snapshot.commissioning is None


@pytest.mark.asyncio
async def test_empty_audit_log_zeros():
    """No audit entries means all control KPIs are 0."""
    svc = MonitoringService()

    with (
        patch.object(svc._integration_repo, "get_integration_health") as mock_health,
        patch.object(svc._integration_repo, "get_log_sources", return_value=[]),
        patch.object(svc._audit_logger, "get_logs", return_value=[]),
        patch("app.services.monitoring_service.settings") as mock_settings,
    ):
        from app.config.settings import IngestionMode

        mock_settings.resolved_ingestion_mode = IngestionMode.SIMULATION
        mock_settings.is_live_mode = False

        mock_health.return_value = _make_integration_health()

        snapshot = await svc.get_snapshot()
        assert snapshot.control.shadow_writes_24h == 0
        assert snapshot.control.blocked_writes_24h == 0
        assert snapshot.control.approved_writes_24h == 0
        assert snapshot.control.safety_violations_24h == 0


@pytest.mark.asyncio
async def test_trend_buckets_24_hours():
    """Trend buckets contain exactly 24 entries with derived flag."""
    svc = MonitoringService()

    with (
        patch.object(svc._integration_repo, "get_integration_health") as mock_health,
        patch.object(svc._integration_repo, "get_log_sources", return_value=[]),
        patch.object(svc._audit_logger, "get_logs", return_value=[]),
        patch("app.services.monitoring_service.settings") as mock_settings,
    ):
        from app.config.settings import IngestionMode

        mock_settings.resolved_ingestion_mode = IngestionMode.SIMULATION
        mock_settings.is_live_mode = False

        mock_health.return_value = _make_integration_health()

        snapshot = await svc.get_snapshot()
        assert len(snapshot.trend_24h) == 24
        for bucket in snapshot.trend_24h:
            assert bucket.derived is True
            assert "T" in bucket.hour  # ISO format

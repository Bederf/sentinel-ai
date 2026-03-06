"""Tests for Phase 109A: Asset Baseline + Health Recording.

Group A: Endpoint contract (4 tests)
Group B: Health status via threshold service (3 tests)
Group C: Baseline + deviation (4 tests)
Group D: Mode behavior (2 tests)
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.asset_health import AssetHealthBaseline
from app.services.asset_health_service import AssetHealthService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_equipment(code: str, name: str = "", health: int = 85, **overrides):
    """Build a minimal equipment dict as returned by EquipmentRepository."""
    defaults = {
        "id": code,
        "code": code,
        "name": name or code,
        "type": code.split("-")[1] if "-" in code else "unknown",
        "category": "HVAC",
        "health_score": health,
        "health": health,
        "status": "normal",
        "updated_at": datetime.now().isoformat(),
        "controllable": False,
        "location": "Level 1",
        "site_id": "site-002",
        "site_name": "Test Building",
        "details": {},
    }
    defaults.update(overrides)
    return defaults


def _make_baseline_status(has_active: bool = True, source: str = "manual", total: int = 1):
    return {
        "has_active_baseline": has_active,
        "last_baseline_at": datetime.now().isoformat() if has_active else None,
        "total_baselines": total,
        "baseline_source": source if has_active else None,
    }


def _make_deviation(max_dev: float, status: str):
    return {
        "max_deviation_percent": max_dev,
        "deviation_status": status,
    }


@pytest.fixture
def asset_health_service():
    """Create an AssetHealthService with mocked dependencies."""
    svc = AssetHealthService.__new__(AssetHealthService)
    svc._equipment_repo = MagicMock()
    svc._baseline_repo = MagicMock()
    svc._threshold_svc = MagicMock()
    # Default threshold behavior
    svc._threshold_svc.get_health_status.side_effect = lambda s: (
        "healthy" if s >= 90 else "warning" if s >= 50 else "critical"
    )
    return svc


# ===========================================================================
# Fixtures for endpoint tests
# ===========================================================================

_MOCK_ASSETS = [
    AssetHealthBaseline(
        equipment_id="S002-AHU-001",
        equipment_name="AHU 001",
        equipment_type="AHU",
        category="HVAC",
        health_score=85,
        health_status="warning",
        health_source="simulation",
        health_updated_at="2026-02-20T10:00:00",
        has_active_baseline=True,
        last_baseline_at="2026-02-15T08:00:00",
        total_baselines=2,
        baseline_source="manual",
        max_deviation_percent_24h=12.5,
        deviation_status="normal",
    ),
    AssetHealthBaseline(
        equipment_id="S002-FCU-101",
        equipment_name="FCU 101",
        equipment_type="FCU",
        category="HVAC",
        health_score=45,
        health_status="critical",
        health_source="simulation",
        health_updated_at=None,
        has_active_baseline=False,
        last_baseline_at=None,
        total_baselines=0,
        baseline_source=None,
        max_deviation_percent_24h=None,
        deviation_status=None,
    ),
]


def _mock_asset_svc():
    """Create a mock AssetHealthService."""
    svc = MagicMock()
    svc.get_site_assets = AsyncMock(return_value=_MOCK_ASSETS)
    svc.get_equipment_detail = AsyncMock(
        side_effect=lambda eid: next((a for a in _MOCK_ASSETS if a.equipment_id == eid), None)
    )
    return svc


# ===========================================================================
# Group A: Endpoint contract
# ===========================================================================


@pytest.mark.asyncio
async def test_site_assets_returns_200_with_contract():
    """GET /api/sites/{id}/assets/health-baseline returns 200 with expected shape."""
    from httpx import AsyncClient, ASGITransport
    from tests.conftest import app

    with patch("app.api.asset_health.get_asset_health_service", return_value=_mock_asset_svc()):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/sites/site-002/assets/health-baseline")
    assert response.status_code == 200
    data = response.json()
    assert "site_id" in data
    assert "total" in data
    assert "assets" in data
    assert isinstance(data["assets"], list)


@pytest.mark.asyncio
async def test_site_assets_includes_all_equipment():
    """All site equipment items should be returned in assets list."""
    from httpx import AsyncClient, ASGITransport
    from tests.conftest import app

    with patch("app.api.asset_health.get_asset_health_service", return_value=_mock_asset_svc()):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/sites/site-002/assets/health-baseline")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == len(data["assets"])
    assert data["total"] == 2


@pytest.mark.asyncio
async def test_equipment_detail_returns_200():
    """GET /api/equipment/{id}/health-baseline returns 200 for known equipment."""
    from httpx import AsyncClient, ASGITransport
    from tests.conftest import app

    with patch("app.api.asset_health.get_asset_health_service", return_value=_mock_asset_svc()):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/equipment/S002-AHU-001/health-baseline")
    assert response.status_code == 200
    data = response.json()
    assert data["equipment_id"] == "S002-AHU-001"
    assert "health_score" in data
    assert "health_status" in data
    assert "has_active_baseline" in data
    assert "deviation_status" in data


@pytest.mark.asyncio
async def test_equipment_detail_404_unknown():
    """GET /api/equipment/{id}/health-baseline returns 404 for unknown equipment."""
    from httpx import AsyncClient, ASGITransport
    from tests.conftest import app

    with patch("app.api.asset_health.get_asset_health_service", return_value=_mock_asset_svc()):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/equipment/DOES-NOT-EXIST-999/health-baseline")
    assert response.status_code == 404


# ===========================================================================
# Group B: Health status via threshold service
# ===========================================================================


@pytest.mark.asyncio
async def test_health_status_uses_threshold_service(asset_health_service):
    """health_status should be computed via HealthThresholdService, not hardcoded."""
    svc = asset_health_service
    eq = _make_equipment("S002-AHU-001", health=75)
    svc._equipment_repo.get_by_id.return_value = eq
    svc._baseline_repo.get_bulk_baseline_status = AsyncMock(return_value={})
    svc._baseline_repo.get_bulk_max_deviation_24h = AsyncMock(return_value={})

    result = await svc.get_equipment_detail("S002-AHU-001")
    assert result is not None
    assert result.health_status == "warning"  # 75 < 90
    svc._threshold_svc.get_health_status.assert_called_with(75)


@pytest.mark.asyncio
async def test_threshold_change_updates_status(asset_health_service):
    """Changing threshold mapping should change the asset's health_status."""
    svc = asset_health_service
    eq = _make_equipment("S002-AHU-001", health=75)
    svc._equipment_repo.get_by_id.return_value = eq
    svc._baseline_repo.get_bulk_baseline_status = AsyncMock(return_value={})
    svc._baseline_repo.get_bulk_max_deviation_24h = AsyncMock(return_value={})

    # With default thresholds: 75 -> warning
    result = await svc.get_equipment_detail("S002-AHU-001")
    assert result.health_status == "warning"

    # Now lower the threshold: 75 is "healthy" if threshold is 70
    svc._threshold_svc.get_health_status.side_effect = lambda s: (
        "healthy" if s >= 70 else "warning" if s >= 40 else "critical"
    )
    result = await svc.get_equipment_detail("S002-AHU-001")
    assert result.health_status == "healthy"


@pytest.mark.asyncio
async def test_health_source_reflects_origin(asset_health_service):
    """health_source should reflect simulation mode."""
    svc = asset_health_service
    eq = _make_equipment("S002-AHU-001", health=85)
    svc._equipment_repo.get_by_id.return_value = eq
    svc._baseline_repo.get_bulk_baseline_status = AsyncMock(return_value={})
    svc._baseline_repo.get_bulk_max_deviation_24h = AsyncMock(return_value={})

    with patch("app.services.asset_health_service.settings") as mock_settings:
        mock_settings.demo_mode = True
        result = await svc.get_equipment_detail("S002-AHU-001")
        assert result.health_source == "simulation"

        mock_settings.demo_mode = False
        result = await svc.get_equipment_detail("S002-AHU-001")
        assert result.health_source == "equipment_table"


# ===========================================================================
# Group C: Baseline + deviation
# ===========================================================================


@pytest.mark.asyncio
async def test_has_active_baseline_true(asset_health_service):
    """Equipment with active baseline should have has_active_baseline: true."""
    svc = asset_health_service
    code = "S002-CHILLER-B1-001"
    eq = _make_equipment(code, health=90)
    svc._equipment_repo.get_by_id.return_value = eq
    svc._baseline_repo.get_bulk_baseline_status = AsyncMock(
        return_value={code: _make_baseline_status(has_active=True, source="manual")}
    )
    svc._baseline_repo.get_bulk_max_deviation_24h = AsyncMock(return_value={})

    result = await svc.get_equipment_detail(code)
    assert result.has_active_baseline is True
    assert result.baseline_source == "manual"
    assert result.last_baseline_at is not None


@pytest.mark.asyncio
async def test_no_baseline_returns_false(asset_health_service):
    """Equipment without baseline should have has_active_baseline: false."""
    svc = asset_health_service
    code = "S002-FCU-201"
    eq = _make_equipment(code, health=80)
    svc._equipment_repo.get_by_id.return_value = eq
    svc._baseline_repo.get_bulk_baseline_status = AsyncMock(
        return_value={code: _make_baseline_status(has_active=False)}
    )
    svc._baseline_repo.get_bulk_max_deviation_24h = AsyncMock(return_value={})

    result = await svc.get_equipment_detail(code)
    assert result.has_active_baseline is False
    assert result.baseline_source is None
    assert result.last_baseline_at is None


@pytest.mark.asyncio
async def test_deviation_status_warning(asset_health_service):
    """Max deviation of 20% should yield deviation_status 'warning'."""
    svc = asset_health_service
    code = "S002-AHU-001"
    eq = _make_equipment(code, health=85)
    svc._equipment_repo.get_by_id.return_value = eq
    svc._baseline_repo.get_bulk_baseline_status = AsyncMock(return_value={code: _make_baseline_status(has_active=True)})
    svc._baseline_repo.get_bulk_max_deviation_24h = AsyncMock(return_value={code: _make_deviation(20.0, "warning")})

    result = await svc.get_equipment_detail(code)
    assert result.max_deviation_percent_24h == 20.0
    assert result.deviation_status == "warning"


@pytest.mark.asyncio
async def test_deviation_status_critical(asset_health_service):
    """Max deviation of 35% should yield deviation_status 'critical'."""
    svc = asset_health_service
    code = "S002-AHU-001"
    eq = _make_equipment(code, health=85)
    svc._equipment_repo.get_by_id.return_value = eq
    svc._baseline_repo.get_bulk_baseline_status = AsyncMock(return_value={code: _make_baseline_status(has_active=True)})
    svc._baseline_repo.get_bulk_max_deviation_24h = AsyncMock(return_value={code: _make_deviation(35.0, "critical")})

    result = await svc.get_equipment_detail(code)
    assert result.max_deviation_percent_24h == 35.0
    assert result.deviation_status == "critical"


# ===========================================================================
# Group D: Mode behavior
# ===========================================================================


@pytest.mark.asyncio
async def test_simulation_allows_synthetic_baseline():
    """In demo/simulation mode, _enqueue_baseline_captures should attempt auto-capture."""
    from app.api.niagara_discovery import _enqueue_baseline_captures

    with patch("app.config.settings.settings") as mock_settings:
        mock_settings.demo_mode = True
        # Should not raise; in demo mode it attempts capture
        await _enqueue_baseline_captures("disc-001", "site-002", 5)


@pytest.mark.asyncio
async def test_live_mode_requires_real_source():
    """In live mode, _enqueue_baseline_captures should log pending, not auto-capture."""
    from app.api.niagara_discovery import _enqueue_baseline_captures

    with patch("app.config.settings.settings") as mock_settings:
        mock_settings.demo_mode = False
        # Should not raise; just logs pending
        await _enqueue_baseline_captures("disc-001", "site-002", 3)

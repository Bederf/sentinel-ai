"""Tests for Phase 109B-02: Health Rating API Endpoints.

Group A: GET /api/equipment/{id}/health-rating (5 tests)
Group B: GET /api/equipment/{id}/health-rating/history (4 tests)
Group C: GET /api/sites/{site_id}/assets/health-summary (5 tests)
Group D: POST /api/health-assessment/recompute (3 tests)
Group E: Separation + invariant tests (2 tests)

Total: 19 tests
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.asset_health import AssetHealthBaseline
from app.models.health_rating import (
    HealthComponentBreakdown,
    HealthDataQualityResult,
    HealthRating,
    RecomputeResult,
)
from app.services.health_threshold_service import DEFAULT_THRESHOLDS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_health_rating(
    equipment_id: str = "S002-AHU-001",
    health_score: float = 82.5,
    health_status: str = "warning",
    confidence: str = "high",
    assessment_state: str = "normal",
    snapshot_at: str = "2026-02-20T10:00:00Z",
) -> HealthRating:
    """Build a HealthRating instance for test assertions."""
    return HealthRating(
        equipment_id=equipment_id,
        health_score=health_score,
        health_status=health_status,
        confidence=confidence,
        assessment_state=assessment_state,
        components=HealthComponentBreakdown(
            baseline_alignment_score=70.0,
            service_compliance_score=90.0,
            runtime_age_score=85.0,
            fault_burden_score=92.0,
            trend_momentum_score=80.0,
        ),
        data_quality=HealthDataQualityResult(
            freshness_minutes=15.0,
            snapshot_count_24h=12,
            valid_point_ratio=0.98,
            baseline_age_days=5,
            gates_passed=4,
            gates_total=4,
            confidence=confidence,
            assessment_state=assessment_state,
        ),
        formula_version="v1",
        snapshot_at=snapshot_at,
    )


def _make_mock_equipment(code: str = "S002-AHU-001", health: int = 85):
    """Build a minimal equipment dict."""
    return {
        "id": code,
        "code": code,
        "name": f"Test {code}",
        "type": code.split("-")[1] if "-" in code else "unknown",
        "category": "HVAC",
        "health_score": health,
        "health": health,
        "updated_at": datetime.now().isoformat(),
        "site_id": "test-building",
    }


def _make_asset_health_baseline(
    code: str = "S002-AHU-001",
    health_score: int = 85,
    health_status: str = "warning",
    has_baseline: bool = True,
):
    """Build an AssetHealthBaseline for site summary tests."""
    return AssetHealthBaseline(
        equipment_id=code,
        equipment_name=f"Test {code}",
        equipment_type=code.split("-")[1] if "-" in code else "unknown",
        category="HVAC",
        health_score=health_score,
        health_status=health_status,
        health_source="simulation",
        health_updated_at="2026-02-20T10:00:00",
        has_active_baseline=has_baseline,
        last_baseline_at="2026-02-15T08:00:00" if has_baseline else None,
        total_baselines=1 if has_baseline else 0,
        baseline_source="manual" if has_baseline else None,
        max_deviation_percent_24h=12.5 if has_baseline else None,
        deviation_status="normal" if has_baseline else None,
    )


def _mock_threshold_service(return_status=None):
    """Create a mock HealthThresholdService.

    When return_status is a string, always returns that status.
    When return_status is None, uses real threshold logic based on score.
    """
    svc = MagicMock()
    svc.get_thresholds.return_value = DEFAULT_THRESHOLDS.copy()

    if return_status is not None:
        svc.get_health_status.return_value = return_status
    else:

        def _real_status(score):
            if score >= DEFAULT_THRESHOLDS["healthy"]:
                return "healthy"
            elif score < DEFAULT_THRESHOLDS["critical"]:
                return "critical"
            else:
                return "warning"

        svc.get_health_status.side_effect = _real_status

    return svc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_snapshot_service():
    """Create a mock HealthSnapshotService."""
    svc = MagicMock()
    svc.get_latest = AsyncMock(return_value=_make_health_rating())
    svc.get_history = AsyncMock(return_value=[])
    svc.get_daily_rollups = AsyncMock(return_value=[])
    svc.store_snapshot = AsyncMock(return_value="snap-123")
    svc.recompute = AsyncMock(
        return_value=RecomputeResult(
            scope="single",
            equipment_processed=1,
            equipment_failed=0,
            duration_ms=42,
        )
    )
    return svc


@pytest.fixture
def mock_equipment_repo():
    """Create a mock EquipmentRepository."""
    repo = MagicMock()
    repo.get_by_id.return_value = _make_mock_equipment()
    return repo


@pytest.fixture
def mock_calculator():
    """Create a mock HealthRatingCalculator."""
    calc = MagicMock()
    calc.compute_rating = AsyncMock(return_value=_make_health_rating())
    return calc


# ===========================================================================
# Group A: GET /api/equipment/{id}/health-rating (5 tests)
# ===========================================================================


@pytest.mark.asyncio
async def test_health_rating_returns_200_with_all_fields(
    mock_snapshot_service,
    mock_equipment_repo,
):
    """GET /api/equipment/{id}/health-rating returns 200 with all expected fields."""
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    mock_threshold = _mock_threshold_service(return_status="warning")

    with (
        patch(
            "app.api.health_rating._get_snapshot_service",
            return_value=mock_snapshot_service,
        ),
        patch(
            "app.api.health_rating._get_equipment_repo",
            return_value=mock_equipment_repo,
        ),
        patch(
            "app.api.health_rating.get_health_threshold_service",
            return_value=mock_threshold,
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/equipment/S002-AHU-001/health-rating")

    assert response.status_code == 200
    data = response.json()
    assert "equipment_id" in data
    assert "health_score" in data
    assert "health_status" in data
    assert "confidence" in data
    assert "assessment_state" in data
    assert "components" in data
    assert "data_quality" in data
    assert "formula_version" in data
    assert "snapshot_at" in data


@pytest.mark.asyncio
async def test_health_rating_returns_404_unknown(mock_snapshot_service):
    """GET /api/equipment/{id}/health-rating returns 404 for unknown equipment."""
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    mock_repo = MagicMock()
    mock_repo.get_by_id.return_value = None

    with (
        patch(
            "app.api.health_rating._get_snapshot_service",
            return_value=mock_snapshot_service,
        ),
        patch(
            "app.api.health_rating._get_equipment_repo",
            return_value=mock_repo,
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/equipment/DOES-NOT-EXIST/health-rating")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_health_rating_status_matches_threshold_service(
    mock_equipment_repo,
):
    """Health rating status must match HealthThresholdService for the given score."""
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    for score, expected_status in [(95.0, "healthy"), (40.0, "critical")]:
        rating = _make_health_rating(health_score=score, health_status=expected_status)
        mock_svc = MagicMock()
        mock_svc.get_latest = AsyncMock(return_value=rating)

        mock_threshold = _mock_threshold_service(return_status=expected_status)

        with (
            patch(
                "app.api.health_rating._get_snapshot_service",
                return_value=mock_svc,
            ),
            patch(
                "app.api.health_rating._get_equipment_repo",
                return_value=mock_equipment_repo,
            ),
            patch(
                "app.api.health_rating.get_health_threshold_service",
                return_value=mock_threshold,
            ),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/equipment/S002-AHU-001/health-rating")

        assert response.status_code == 200
        data = response.json()
        assert data["health_status"] == expected_status


@pytest.mark.asyncio
async def test_health_rating_includes_component_breakdown(
    mock_snapshot_service,
    mock_equipment_repo,
):
    """Response must include all 5 component scores."""
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    mock_threshold = _mock_threshold_service(return_status="warning")

    with (
        patch(
            "app.api.health_rating._get_snapshot_service",
            return_value=mock_snapshot_service,
        ),
        patch(
            "app.api.health_rating._get_equipment_repo",
            return_value=mock_equipment_repo,
        ),
        patch(
            "app.api.health_rating.get_health_threshold_service",
            return_value=mock_threshold,
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/equipment/S002-AHU-001/health-rating")

    assert response.status_code == 200
    components = response.json()["components"]
    assert "baseline_alignment_score" in components
    assert "service_compliance_score" in components
    assert "runtime_age_score" in components
    assert "fault_burden_score" in components
    assert "trend_momentum_score" in components


@pytest.mark.asyncio
async def test_health_rating_includes_data_quality(
    mock_snapshot_service,
    mock_equipment_repo,
):
    """Response must include data quality fields: confidence, assessment_state."""
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    mock_threshold = _mock_threshold_service(return_status="warning")

    with (
        patch(
            "app.api.health_rating._get_snapshot_service",
            return_value=mock_snapshot_service,
        ),
        patch(
            "app.api.health_rating._get_equipment_repo",
            return_value=mock_equipment_repo,
        ),
        patch(
            "app.api.health_rating.get_health_threshold_service",
            return_value=mock_threshold,
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/equipment/S002-AHU-001/health-rating")

    assert response.status_code == 200
    data = response.json()
    assert data["confidence"] in ("high", "medium", "low")
    assert data["assessment_state"] in ("normal", "degraded_data", "insufficient_data")
    dq = data["data_quality"]
    assert "freshness_minutes" in dq
    assert "gates_passed" in dq
    assert "gates_total" in dq


# ===========================================================================
# Group B: GET /api/equipment/{id}/health-rating/history (4 tests)
# ===========================================================================


@pytest.mark.asyncio
async def test_history_returns_200_sorted_newest_first():
    """History snapshots must be sorted newest-first."""
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    snapshots = [
        _make_health_rating(snapshot_at="2026-02-18T10:00:00Z"),
        _make_health_rating(snapshot_at="2026-02-20T10:00:00Z"),
        _make_health_rating(snapshot_at="2026-02-19T10:00:00Z"),
    ]
    snapshots.sort(key=lambda s: s.snapshot_at, reverse=True)

    mock_svc = MagicMock()
    mock_svc.get_history = AsyncMock(return_value=snapshots)
    mock_svc.get_daily_rollups = AsyncMock(return_value=[])

    with patch(
        "app.api.health_rating._get_snapshot_service",
        return_value=mock_svc,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/equipment/S002-AHU-001/health-rating/history",
                params={"range": "7d"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["equipment_id"] == "S002-AHU-001"
    assert data["range_days"] == 7
    timestamps = [s["snapshot_at"] for s in data["snapshots"]]
    assert timestamps == sorted(timestamps, reverse=True), "Snapshots must be newest-first"


@pytest.mark.asyncio
async def test_history_respects_range_filter():
    """Service should be called with the correct range_days for 7d, 30d, 90d."""
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    for range_str, expected_days in [("7d", 7), ("30d", 30), ("90d", 90)]:
        mock_svc = MagicMock()
        mock_svc.get_history = AsyncMock(return_value=[])
        mock_svc.get_daily_rollups = AsyncMock(return_value=[])

        with patch(
            "app.api.health_rating._get_snapshot_service",
            return_value=mock_svc,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    "/api/equipment/S002-AHU-001/health-rating/history",
                    params={"range": range_str},
                )

        assert response.status_code == 200
        assert response.json()["range_days"] == expected_days
        mock_svc.get_history.assert_called_once_with("S002-AHU-001", expected_days)


@pytest.mark.asyncio
async def test_history_empty_returns_200():
    """No snapshots should return 200 with empty lists, not 404."""
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    mock_svc = MagicMock()
    mock_svc.get_history = AsyncMock(return_value=[])
    mock_svc.get_daily_rollups = AsyncMock(return_value=[])

    with patch(
        "app.api.health_rating._get_snapshot_service",
        return_value=mock_svc,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/equipment/S002-AHU-001/health-rating/history",
                params={"range": "7d"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["snapshots"] == []
    assert data["daily_rollups"] == []


@pytest.mark.asyncio
async def test_history_invalid_range_returns_400():
    """Invalid range parameter should return 400."""
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/equipment/S002-AHU-001/health-rating/history",
            params={"range": "999d"},
        )

    assert response.status_code == 400
    assert "Invalid range" in response.json()["detail"]


# ===========================================================================
# Group C: GET /api/sites/{site_id}/assets/health-summary (5 tests)
# ===========================================================================


def _mock_asset_health_service():
    """Create a mock AssetHealthService for summary tests."""
    assets = [
        _make_asset_health_baseline("S002-AHU-001", 85, "warning", has_baseline=True),
        _make_asset_health_baseline("S002-CHILLER-B1-001", 45, "critical", has_baseline=False),
        _make_asset_health_baseline("S002-FCU-101", 95, "healthy", has_baseline=True),
    ]
    svc = MagicMock()
    svc.get_site_assets = AsyncMock(return_value=assets)
    return svc


@pytest.mark.asyncio
async def test_health_summary_returns_one_per_asset():
    """GET /api/sites/{id}/assets/health-summary returns one item per asset."""
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    mock_asset_svc = _mock_asset_health_service()
    mock_snap_svc = MagicMock()
    mock_snap_svc.get_latest = AsyncMock(return_value=None)
    mock_snap_svc.get_history = AsyncMock(return_value=[])

    mock_threshold = _mock_threshold_service(return_status=None)

    with (
        patch(
            "app.api.health_rating._get_asset_health_service",
            return_value=mock_asset_svc,
        ),
        patch(
            "app.api.health_rating._get_snapshot_service",
            return_value=mock_snap_svc,
        ),
        patch(
            "app.api.health_rating.get_health_threshold_service",
            return_value=mock_threshold,
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/sites/site-002/assets/health-summary")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["assets"]) == 3


@pytest.mark.asyncio
async def test_health_summary_includes_required_fields():
    """Each asset in summary must include all required contract fields."""
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    mock_asset_svc = _mock_asset_health_service()
    mock_snap_svc = MagicMock()
    mock_snap_svc.get_latest = AsyncMock(return_value=None)
    mock_snap_svc.get_history = AsyncMock(return_value=[])

    mock_threshold = _mock_threshold_service(return_status=None)

    with (
        patch(
            "app.api.health_rating._get_asset_health_service",
            return_value=mock_asset_svc,
        ),
        patch(
            "app.api.health_rating._get_snapshot_service",
            return_value=mock_snap_svc,
        ),
        patch(
            "app.api.health_rating.get_health_threshold_service",
            return_value=mock_threshold,
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/sites/site-002/assets/health-summary")

    assert response.status_code == 200
    data = response.json()
    for asset in data["assets"]:
        assert "health_score" in asset
        assert "health_status" in asset
        assert "confidence" in asset
        assert "trend_7d" in asset
        assert "trend_30d" in asset
        assert "has_active_baseline" in asset
        assert "last_baseline_at" in asset
        assert "max_deviation_percent_24h" in asset
        assert "deviation_status" in asset
        assert "assessment_state" in asset
        assert "health_updated_at" in asset
        assert "health_source" in asset


@pytest.mark.asyncio
async def test_health_summary_filter_critical():
    """?status=critical should filter to only critical assets."""
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    mock_asset_svc = _mock_asset_health_service()
    mock_snap_svc = MagicMock()
    mock_snap_svc.get_latest = AsyncMock(return_value=None)
    mock_snap_svc.get_history = AsyncMock(return_value=[])

    mock_threshold = _mock_threshold_service(return_status=None)

    with (
        patch(
            "app.api.health_rating._get_asset_health_service",
            return_value=mock_asset_svc,
        ),
        patch(
            "app.api.health_rating._get_snapshot_service",
            return_value=mock_snap_svc,
        ),
        patch(
            "app.api.health_rating.get_health_threshold_service",
            return_value=mock_threshold,
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/sites/site-002/assets/health-summary",
                params={"status": "critical"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    for asset in data["assets"]:
        assert asset["health_status"] == "critical"


@pytest.mark.asyncio
async def test_health_summary_filter_no_baseline():
    """?has_baseline=false should filter to assets without baselines."""
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    mock_asset_svc = _mock_asset_health_service()
    mock_snap_svc = MagicMock()
    mock_snap_svc.get_latest = AsyncMock(return_value=None)
    mock_snap_svc.get_history = AsyncMock(return_value=[])

    mock_threshold = _mock_threshold_service(return_status=None)

    with (
        patch(
            "app.api.health_rating._get_asset_health_service",
            return_value=mock_asset_svc,
        ),
        patch(
            "app.api.health_rating._get_snapshot_service",
            return_value=mock_snap_svc,
        ),
        patch(
            "app.api.health_rating.get_health_threshold_service",
            return_value=mock_threshold,
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/sites/site-002/assets/health-summary",
                params={"has_baseline": "false"},
            )

    assert response.status_code == 200
    data = response.json()
    for asset in data["assets"]:
        assert asset["has_active_baseline"] is False
    assert data["total"] == 1


@pytest.mark.asyncio
async def test_health_summary_filter_low_confidence():
    """?confidence=low should filter to assets with low data quality confidence."""
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    mock_asset_svc = _mock_asset_health_service()
    mock_snap_svc = MagicMock()
    low_conf_rating = _make_health_rating(confidence="low", assessment_state="degraded_data")
    mock_snap_svc.get_latest = AsyncMock(return_value=low_conf_rating)
    mock_snap_svc.get_history = AsyncMock(return_value=[])

    mock_threshold = _mock_threshold_service(return_status=None)

    with (
        patch(
            "app.api.health_rating._get_asset_health_service",
            return_value=mock_asset_svc,
        ),
        patch(
            "app.api.health_rating._get_snapshot_service",
            return_value=mock_snap_svc,
        ),
        patch(
            "app.api.health_rating.get_health_threshold_service",
            return_value=mock_threshold,
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/sites/site-002/assets/health-summary",
                params={"confidence": "low"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    for asset in data["assets"]:
        assert asset["confidence"] == "low"


# ===========================================================================
# Group D: POST /api/health-assessment/recompute (3 tests)
# ===========================================================================


@pytest.mark.asyncio
async def test_recompute_returns_202(mock_snapshot_service):
    """POST /api/health-assessment/recompute returns 202 Accepted."""
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    with patch(
        "app.api.health_rating._get_snapshot_service",
        return_value=mock_snapshot_service,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/health-assessment/recompute",
                json={"equipment_id": "S002-AHU-001", "scope": "single"},
            )

    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "completed"
    assert "result" in data


@pytest.mark.asyncio
async def test_recompute_requires_equipment_id_for_single():
    """scope=single without equipment_id should return 422."""
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/health-assessment/recompute",
            json={"scope": "single"},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_recompute_logs_audit(mock_snapshot_service):
    """Recompute should log an audit entry via AuditLogger.log_control_action."""
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    mock_audit_instance = MagicMock()

    with (
        patch(
            "app.api.health_rating._get_snapshot_service",
            return_value=mock_snapshot_service,
        ),
        patch(
            "app.services.audit_logger.AuditLogger",
            return_value=mock_audit_instance,
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/health-assessment/recompute",
                json={"equipment_id": "S002-AHU-001", "scope": "single"},
            )

    assert response.status_code == 202
    mock_audit_instance.log_control_action.assert_called_once()
    all_args_str = str(mock_audit_instance.log_control_action.call_args)
    assert "health_assessment_recompute" in all_args_str


# ===========================================================================
# Group E: Separation + invariant tests (2 tests)
# ===========================================================================


@pytest.mark.asyncio
async def test_health_endpoints_never_return_risk_probability(
    mock_snapshot_service,
    mock_equipment_repo,
):
    """Health rating response must NEVER contain risk probability fields."""
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    mock_threshold = _mock_threshold_service(return_status="warning")

    with (
        patch(
            "app.api.health_rating._get_snapshot_service",
            return_value=mock_snapshot_service,
        ),
        patch(
            "app.api.health_rating._get_equipment_repo",
            return_value=mock_equipment_repo,
        ),
        patch(
            "app.api.health_rating.get_health_threshold_service",
            return_value=mock_threshold,
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/equipment/S002-AHU-001/health-rating")

    assert response.status_code == 200
    data = response.json()

    forbidden_keys = {
        "risk_probability",
        "failure_probability",
        "risk_score",
        "risk_level",
        "predicted_failure",
    }

    def _check_no_risk(obj, path=""):
        if isinstance(obj, dict):
            for key, value in obj.items():
                assert key not in forbidden_keys, f"Risk field '{key}' found at {path}.{key} in health response"
                _check_no_risk(value, f"{path}.{key}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _check_no_risk(item, f"{path}[{i}]")

    _check_no_risk(data)


@pytest.mark.asyncio
async def test_health_status_invariant(mock_equipment_repo):
    """Status in response must always match what HealthThresholdService returns."""
    from httpx import ASGITransport, AsyncClient

    from tests.conftest import app

    test_cases = [
        (95.0, "healthy"),
        (75.0, "warning"),
        (40.0, "critical"),
    ]

    for score, expected_status in test_cases:
        rating = _make_health_rating(health_score=score, health_status=expected_status)
        mock_svc = MagicMock()
        mock_svc.get_latest = AsyncMock(return_value=rating)

        mock_threshold = _mock_threshold_service(return_status=expected_status)

        with (
            patch(
                "app.api.health_rating._get_snapshot_service",
                return_value=mock_svc,
            ),
            patch(
                "app.api.health_rating._get_equipment_repo",
                return_value=mock_equipment_repo,
            ),
            patch(
                "app.api.health_rating.get_health_threshold_service",
                return_value=mock_threshold,
            ),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/equipment/S002-AHU-001/health-rating")

        assert response.status_code == 200
        assert response.json()["health_status"] == expected_status, (
            f"For score {score}, expected status '{expected_status}' but got '{response.json()['health_status']}'"
        )

"""Tests for the commissioning scorecard (Phase 107b).

Groups:
A — Model tests
B — Gate logic
C — Truth check
D — Consecutive days
E — Promotion
F — API endpoints
"""

import os

os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("TESTING", "true")

import pytest  # noqa: E402
from datetime import datetime  # noqa: E402
from unittest.mock import patch, MagicMock, AsyncMock  # noqa: E402

from app.models.commissioning import (  # noqa: E402
    CommissioningGateId,
    CommissioningGate,
    TruthCheckEntry,
    CommissioningScorecard,
)
from app.models.integration import BuildingStatus  # noqa: E402
from app.services.commissioning_service import CommissioningService  # noqa: E402


# ==================== Helpers ====================


def _make_quality(
    match_coverage=97.0,
    data_freshness_hours=0.2,
    error_rate=0.3,
    duplicate_rate=0.1,
    overall_score=95.0,
    trend="stable",
):
    return {
        "match_coverage": match_coverage,
        "data_freshness_hours": data_freshness_hours,
        "error_rate": error_rate,
        "duplicate_rate": duplicate_rate,
        "overall_score": overall_score,
        "trend": trend,
    }


def _make_entry(within_tolerance=True, idx=0):
    return TruthCheckEntry(
        point_id=f"PT-{idx:03d}",
        point_name=f"Point {idx}",
        sentinel_value=22.0,
        native_bms_value=22.1 if within_tolerance else 50.0,
        tolerance=0.5,
        within_tolerance=within_tolerance,
        timestamp=datetime(2026, 2, 20, 10, 0),
    )


def _make_entries(total=20, agreeing=20):
    """Make a list of entries with a given number agreeing."""
    entries = []
    for i in range(total):
        entries.append(_make_entry(within_tolerance=i < agreeing, idx=i))
    return entries


# ==================== Group A: Model Tests ====================


class TestModels:
    def test_gate_id_enum_values(self):
        ids = [g.value for g in CommissioningGateId]
        assert "match_coverage" in ids
        assert "unmatched_points" in ids
        assert "data_freshness" in ids
        assert "error_rate" in ids
        assert "duplicate_rate" in ids
        assert "source_provenance" in ids
        assert "value_validity" in ids
        assert "timestamp_integrity" in ids
        assert len(ids) == 8

    def test_commissioning_gate_fields(self):
        gate = CommissioningGate(
            id=CommissioningGateId.MATCH_COVERAGE,
            name="Match Coverage",
            category="point_mapping",
            target=">= 95%",
            actual=96.0,
            passed=True,
            details="96% matched",
        )
        assert gate.id == CommissioningGateId.MATCH_COVERAGE
        assert gate.passed is True
        assert gate.actual == 96.0

    def test_site_status_new_values(self):
        assert BuildingStatus.SHADOW_LIVE == "shadow_live"
        assert BuildingStatus.LIVE_CONTROL == "live_control"
        # Existing values still there
        assert BuildingStatus.DRAFT == "draft"
        assert BuildingStatus.ACTIVE == "active"


# ==================== Group B: Gate Logic ====================


class TestGateLogic:
    """Test each gate's pass/fail boundary."""

    @pytest.fixture
    def svc(self):
        svc = CommissioningService()
        return svc

    def _mock_repo(self, svc, quality, sources=None):
        """Patch the repo methods on the service."""
        svc._repo = MagicMock()
        svc._repo.get_quality_metrics.return_value = quality
        svc._repo.get_log_sources.return_value = sources or [
            {"id": "src-1", "sync_frequency_minutes": 15, "is_active": True, "connection_type": "api"}
        ]
        # For value_validity / timestamp_integrity
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_in = MagicMock()
        mock_gte = MagicMock()
        mock_gt = MagicMock()
        mock_exec = MagicMock()
        mock_exec.data = []
        mock_exec.count = 0
        mock_table.select.return_value = mock_select
        mock_select.in_.return_value = mock_in
        mock_in.gte.return_value = mock_gte
        mock_in.gt.return_value = mock_gt
        mock_gte.execute.return_value = mock_exec
        mock_gt.execute.return_value = mock_exec
        svc._repo.client.table.return_value = mock_table

    @pytest.mark.asyncio
    async def test_match_coverage_pass_at_95(self, svc):
        self._mock_repo(svc, _make_quality(match_coverage=95.0))
        scorecard = await svc.run_scorecard("bld-1")
        gate = next(g for g in scorecard.gates if g.id == CommissioningGateId.MATCH_COVERAGE)
        assert gate.passed is True

    @pytest.mark.asyncio
    async def test_match_coverage_fail_at_94(self, svc):
        self._mock_repo(svc, _make_quality(match_coverage=94.0))
        scorecard = await svc.run_scorecard("bld-1")
        gate = next(g for g in scorecard.gates if g.id == CommissioningGateId.MATCH_COVERAGE)
        assert gate.passed is False

    @pytest.mark.asyncio
    async def test_unmatched_points_pass_at_4(self, svc):
        self._mock_repo(svc, _make_quality(match_coverage=96.0))  # unmatched = 4%
        scorecard = await svc.run_scorecard("bld-1")
        gate = next(g for g in scorecard.gates if g.id == CommissioningGateId.UNMATCHED_POINTS)
        assert gate.passed is True
        assert gate.actual == 4.0

    @pytest.mark.asyncio
    async def test_unmatched_points_fail_at_6(self, svc):
        self._mock_repo(svc, _make_quality(match_coverage=94.0))  # unmatched = 6%
        scorecard = await svc.run_scorecard("bld-1")
        gate = next(g for g in scorecard.gates if g.id == CommissioningGateId.UNMATCHED_POINTS)
        assert gate.passed is False

    @pytest.mark.asyncio
    async def test_data_freshness_pass(self, svc):
        # sync_freq=15min → target=0.5h; actual=0.2h < 0.5h → pass
        self._mock_repo(svc, _make_quality(data_freshness_hours=0.2))
        scorecard = await svc.run_scorecard("bld-1")
        gate = next(g for g in scorecard.gates if g.id == CommissioningGateId.DATA_FRESHNESS)
        assert gate.passed is True

    @pytest.mark.asyncio
    async def test_data_freshness_fail(self, svc):
        # sync_freq=15min → target=0.5h; actual=1.0h >= 0.5h → fail
        self._mock_repo(svc, _make_quality(data_freshness_hours=1.0))
        scorecard = await svc.run_scorecard("bld-1")
        gate = next(g for g in scorecard.gates if g.id == CommissioningGateId.DATA_FRESHNESS)
        assert gate.passed is False

    @pytest.mark.asyncio
    async def test_error_rate_pass_at_05(self, svc):
        self._mock_repo(svc, _make_quality(error_rate=0.5))
        scorecard = await svc.run_scorecard("bld-1")
        gate = next(g for g in scorecard.gates if g.id == CommissioningGateId.ERROR_RATE)
        assert gate.passed is True

    @pytest.mark.asyncio
    async def test_error_rate_fail_at_15(self, svc):
        self._mock_repo(svc, _make_quality(error_rate=1.5))
        scorecard = await svc.run_scorecard("bld-1")
        gate = next(g for g in scorecard.gates if g.id == CommissioningGateId.ERROR_RATE)
        assert gate.passed is False

    @pytest.mark.asyncio
    async def test_duplicate_rate_pass_at_03(self, svc):
        self._mock_repo(svc, _make_quality(duplicate_rate=0.3))
        scorecard = await svc.run_scorecard("bld-1")
        gate = next(g for g in scorecard.gates if g.id == CommissioningGateId.DUPLICATE_RATE)
        assert gate.passed is True

    @pytest.mark.asyncio
    async def test_duplicate_rate_fail_at_06(self, svc):
        self._mock_repo(svc, _make_quality(duplicate_rate=0.6))
        scorecard = await svc.run_scorecard("bld-1")
        gate = next(g for g in scorecard.gates if g.id == CommissioningGateId.DUPLICATE_RATE)
        assert gate.passed is False

    @pytest.mark.asyncio
    async def test_source_provenance_pass_no_json(self, svc):
        sources = [
            {"id": "s1", "sync_frequency_minutes": 15, "is_active": True, "connection_type": "api"},
            {"id": "s2", "sync_frequency_minutes": 15, "is_active": True, "connection_type": "database"},
        ]
        self._mock_repo(svc, _make_quality(), sources=sources)
        scorecard = await svc.run_scorecard("bld-1")
        gate = next(g for g in scorecard.gates if g.id == CommissioningGateId.SOURCE_PROVENANCE)
        assert gate.passed is True

    @pytest.mark.asyncio
    async def test_source_provenance_fail_with_file_drop(self, svc):
        sources = [
            {"id": "s1", "sync_frequency_minutes": 15, "is_active": True, "connection_type": "api"},
            {
                "id": "s2",
                "sync_frequency_minutes": 15,
                "is_active": True,
                "connection_type": "file_drop",
                "name": "Legacy CSV",
            },
        ]
        self._mock_repo(svc, _make_quality(), sources=sources)
        scorecard = await svc.run_scorecard("bld-1")
        gate = next(g for g in scorecard.gates if g.id == CommissioningGateId.SOURCE_PROVENANCE)
        assert gate.passed is False
        assert gate.actual == 1.0

    @pytest.mark.asyncio
    async def test_value_validity_pass(self, svc):
        self._mock_repo(svc, _make_quality())
        # Mock trends query to return mostly valid values
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_in = MagicMock()
        mock_gte = MagicMock()
        mock_exec = MagicMock()
        mock_exec.data = [{"value": 22.0} for _ in range(1000)]
        mock_table.select.return_value = mock_select
        mock_select.in_.return_value = mock_in
        mock_in.gte.return_value = mock_gte
        mock_gte.execute.return_value = mock_exec
        svc._repo.client.table.return_value = mock_table

        scorecard = await svc.run_scorecard("bld-1")
        gate = next(g for g in scorecard.gates if g.id == CommissioningGateId.VALUE_VALIDITY)
        assert gate.passed is True
        assert gate.actual < 0.5

    @pytest.mark.asyncio
    async def test_value_validity_fail(self, svc):
        self._mock_repo(svc, _make_quality())
        # Mock trends query with many null values
        rows = [{"value": 22.0} for _ in range(100)]
        rows.extend([{"value": None} for _ in range(10)])  # 10/110 ≈ 9% invalid
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_in = MagicMock()
        mock_gte = MagicMock()
        mock_exec = MagicMock()
        mock_exec.data = rows
        mock_table.select.return_value = mock_select
        mock_select.in_.return_value = mock_in
        mock_in.gte.return_value = mock_gte
        mock_gte.execute.return_value = mock_exec
        svc._repo.client.table.return_value = mock_table

        scorecard = await svc.run_scorecard("bld-1")
        gate = next(g for g in scorecard.gates if g.id == CommissioningGateId.VALUE_VALIDITY)
        assert gate.passed is False

    @pytest.mark.asyncio
    async def test_timestamp_integrity_pass(self, svc):
        self._mock_repo(svc, _make_quality())
        # Mock: total=10000, future=0
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_in_total = MagicMock()
        mock_in_future = MagicMock()
        mock_gte = MagicMock()
        mock_gt = MagicMock()
        total_exec = MagicMock()
        total_exec.count = 10000
        future_exec = MagicMock()
        future_exec.count = 0

        mock_table.select.return_value = mock_select
        mock_select.in_.side_effect = [mock_in_total, mock_in_future]
        mock_in_total.gte.return_value = mock_gte
        mock_in_future.gt.return_value = mock_gt
        mock_gte.execute.return_value = total_exec
        mock_gt.execute.return_value = future_exec
        svc._repo.client.table.return_value = mock_table

        scorecard = await svc.run_scorecard("bld-1")
        gate = next(g for g in scorecard.gates if g.id == CommissioningGateId.TIMESTAMP_INTEGRITY)
        assert gate.passed is True

    @pytest.mark.asyncio
    async def test_timestamp_integrity_fail(self, svc):
        self._mock_repo(svc, _make_quality())

        # Need to handle BOTH _check_value_validity and _check_timestamp_integrity
        # calls to client.table("ingested_trends"). Each call creates a new
        # chain. Use side_effect on table() to return different mock tables.

        # Table mock for value_validity call
        vv_table = MagicMock()
        vv_select = MagicMock()
        vv_in = MagicMock()
        vv_gte = MagicMock()
        vv_exec = MagicMock()
        vv_exec.data = [{"value": 22.0} for _ in range(100)]
        vv_table.select.return_value = vv_select
        vv_select.in_.return_value = vv_in
        vv_in.gte.return_value = vv_gte
        vv_gte.execute.return_value = vv_exec

        # Table mock for timestamp_integrity call (two sub-queries: total + future)
        ts_table = MagicMock()
        ts_select = MagicMock()
        ts_in_total = MagicMock()
        ts_in_future = MagicMock()
        ts_gte = MagicMock()
        ts_gt = MagicMock()
        total_exec = MagicMock()
        total_exec.count = 10000
        future_exec = MagicMock()
        future_exec.count = 20  # 0.2% invalid → valid=99.8% < 99.9%
        ts_table.select.return_value = ts_select
        ts_select.in_.side_effect = [ts_in_total, ts_in_future]
        ts_in_total.gte.return_value = ts_gte
        ts_in_future.gt.return_value = ts_gt
        ts_gte.execute.return_value = total_exec
        ts_gt.execute.return_value = future_exec

        svc._repo.client.table.side_effect = [vv_table, ts_table, ts_table]

        scorecard = await svc.run_scorecard("bld-1")
        gate = next(g for g in scorecard.gates if g.id == CommissioningGateId.TIMESTAMP_INTEGRITY)
        assert gate.passed is False


# ==================== Group C: Truth Check ====================


class TestTruthCheck:
    def test_all_20_agreeing_passes(self):
        svc = CommissioningService()
        entries = _make_entries(total=20, agreeing=20)
        result = svc.submit_truth_check("bld-1", entries)
        assert result.passed is True
        assert result.agreement_pct == 100.0
        assert result.total_points == 20

    def test_30_points_29_agree_fails(self):
        svc = CommissioningService()
        entries = _make_entries(total=30, agreeing=29)
        result = svc.submit_truth_check("bld-1", entries)
        assert result.passed is False
        assert result.agreement_pct == pytest.approx(96.67, abs=0.01)

    def test_less_than_20_raises(self):
        svc = CommissioningService()
        entries = _make_entries(total=19, agreeing=19)
        with pytest.raises(ValueError, match="requires >= 20"):
            svc.submit_truth_check("bld-1", entries)

    def test_exact_98_passes(self):
        svc = CommissioningService()
        # 50 points, 49 agreeing = 98% exactly
        entries = _make_entries(total=50, agreeing=49)
        result = svc.submit_truth_check("bld-1", entries)
        assert result.passed is True
        assert result.agreement_pct == 98.0


# ==================== Group D: Consecutive Days ====================


class TestConsecutiveDays:
    def test_no_history_returns_0(self):
        svc = CommissioningService()
        assert svc.get_consecutive_pass_days("bld-1") == 0

    def test_three_passing_days(self):
        svc = CommissioningService()
        svc._scorecard_history["bld-1"] = [
            {"date": "2026-02-18", "all_gates_passed": True, "checked_at": ""},
            {"date": "2026-02-19", "all_gates_passed": True, "checked_at": ""},
            {"date": "2026-02-20", "all_gates_passed": True, "checked_at": ""},
        ]
        assert svc.get_consecutive_pass_days("bld-1") == 3

    def test_pass_pass_fail_pass_returns_1(self):
        svc = CommissioningService()
        svc._scorecard_history["bld-1"] = [
            {"date": "2026-02-17", "all_gates_passed": True, "checked_at": ""},
            {"date": "2026-02-18", "all_gates_passed": True, "checked_at": ""},
            {"date": "2026-02-19", "all_gates_passed": False, "checked_at": ""},
            {"date": "2026-02-20", "all_gates_passed": True, "checked_at": ""},
        ]
        assert svc.get_consecutive_pass_days("bld-1") == 1

    def test_all_failing_returns_0(self):
        svc = CommissioningService()
        svc._scorecard_history["bld-1"] = [
            {"date": "2026-02-19", "all_gates_passed": False, "checked_at": ""},
            {"date": "2026-02-20", "all_gates_passed": False, "checked_at": ""},
        ]
        assert svc.get_consecutive_pass_days("bld-1") == 0


# ==================== Group E: Promotion ====================


def _mock_quality_gate_pass():
    """Return a patch context that makes the quality gate pre-check pass.

    The Phase 109 quality gate evaluator runs inside promote_to_live()
    before the scorecard check.  We mock it to return GateStatus.PASS so
    the scorecard-level promotion logic is exercised instead.
    """
    from app.services.quality_gate_policy import GateStatus

    mock_evaluator = MagicMock()
    mock_evaluator.collect_metrics = AsyncMock(return_value={})
    mock_result = MagicMock()
    mock_result.overall = GateStatus.PASS
    mock_result.failed_rules = []
    mock_evaluator.evaluate.return_value = mock_result
    mock_cls = MagicMock(return_value=mock_evaluator)
    return patch("app.services.quality_gate_evaluator.QualityGateEvaluator", mock_cls)


class TestPromotion:
    @pytest.fixture
    def svc(self):
        svc = CommissioningService()
        return svc

    def _setup_passing_svc(self, svc):
        """Set up a service where all gates pass and prerequisites are met."""
        svc._repo = MagicMock()
        svc._repo.get_quality_metrics.return_value = _make_quality()
        svc._repo.get_log_sources.return_value = [
            {"id": "s1", "sync_frequency_minutes": 15, "is_active": True, "connection_type": "api"}
        ]
        # Mock value_validity / timestamp_integrity to pass
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_in = MagicMock()
        mock_gte = MagicMock()
        mock_gt = MagicMock()
        valid_exec = MagicMock()
        valid_exec.data = [{"value": 22.0} for _ in range(100)]
        valid_exec.count = 10000
        future_exec = MagicMock()
        future_exec.count = 0
        mock_table.select.return_value = mock_select
        mock_select.in_.side_effect = lambda *a, **kw: mock_in
        mock_in.gte.return_value = mock_gte
        mock_in.gt.return_value = mock_gt
        mock_gte.execute.return_value = valid_exec
        mock_gt.execute.return_value = future_exec
        svc._repo.client.table.return_value = mock_table

        # Pre-populate 2 days of passing history
        svc._scorecard_history["bld-1"] = [
            {"date": "2026-02-18", "all_gates_passed": True, "checked_at": ""},
            {"date": "2026-02-19", "all_gates_passed": True, "checked_at": ""},
        ]

        # Submit a passing truth check
        entries = _make_entries(total=20, agreeing=20)
        svc.submit_truth_check("bld-1", entries)

    @pytest.mark.asyncio
    async def test_promotion_success(self, svc):
        self._setup_passing_svc(svc)
        from app.config.settings import IngestionMode

        mock_settings = MagicMock()
        mock_settings.resolved_ingestion_mode = IngestionMode.SHADOW_LIVE
        with (
            patch("app.services.commissioning_service.app_settings", mock_settings),
            _mock_quality_gate_pass(),
        ):
            result = await svc.promote_to_live("bld-1")
            assert result.success is True
            assert result.new_mode == "live_control"
            svc._repo.update_site_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_promotion_blocked_by_gate(self, svc):
        self._setup_passing_svc(svc)
        # Override match_coverage to fail
        svc._repo.get_quality_metrics.return_value = _make_quality(match_coverage=90.0)

        from app.config.settings import IngestionMode

        mock_settings = MagicMock()
        mock_settings.resolved_ingestion_mode = IngestionMode.SHADOW_LIVE
        with (
            patch("app.services.commissioning_service.app_settings", mock_settings),
            _mock_quality_gate_pass(),
        ):
            result = await svc.promote_to_live("bld-1")
            assert result.success is False
            assert any("match_coverage" in r for r in result.blocking_reasons)

    @pytest.mark.asyncio
    async def test_promotion_blocked_by_consecutive_days(self, svc):
        self._setup_passing_svc(svc)
        # Clear history -> 0 consecutive days (the run_scorecard call adds 1, but need >= 2)
        svc._scorecard_history["bld-1"] = []

        from app.config.settings import IngestionMode

        mock_settings = MagicMock()
        mock_settings.resolved_ingestion_mode = IngestionMode.SHADOW_LIVE
        with (
            patch("app.services.commissioning_service.app_settings", mock_settings),
            _mock_quality_gate_pass(),
        ):
            result = await svc.promote_to_live("bld-1")
            assert result.success is False
            assert any("consecutive_days" in r for r in result.blocking_reasons)

    @pytest.mark.asyncio
    async def test_promotion_blocked_no_truth_check(self, svc):
        self._setup_passing_svc(svc)
        # Remove truth check
        svc._truth_checks.clear()

        from app.config.settings import IngestionMode

        mock_settings = MagicMock()
        mock_settings.resolved_ingestion_mode = IngestionMode.SHADOW_LIVE
        with (
            patch("app.services.commissioning_service.app_settings", mock_settings),
            _mock_quality_gate_pass(),
        ):
            result = await svc.promote_to_live("bld-1")
            assert result.success is False
            assert "truth_check_missing" in result.blocking_reasons


# ==================== Group F: API Endpoints ====================


class TestAPIEndpoints:
    """Integration tests for the API endpoints."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app

        return TestClient(app)

    def test_scorecard_endpoint_returns_200(self, client):
        with patch("app.api.integration.commissioning_service") as mock_svc:
            mock_svc.run_scorecard = AsyncMock(
                return_value=CommissioningScorecard(
                    site_id="site-002",
                    ingestion_mode="simulation",
                    checked_at=datetime.utcnow(),
                    gates=[],
                    summary={"passed": 0, "failed": 0, "total": 0},
                    all_gates_passed=False,
                    consecutive_pass_days=0,
                    can_promote=False,
                    blocking_gates=[],
                )
            )
            resp = client.get("/api/integration/buildings/site-002/commissioning-scorecard")
            assert resp.status_code == 200
            data = resp.json()
            assert data["site_id"] == "site-002"

    def test_truth_check_rejects_too_few_entries(self, client):
        entries = [
            {
                "point_id": f"PT-{i}",
                "point_name": f"P{i}",
                "sentinel_value": 22.0,
                "native_bms_value": 22.1,
                "tolerance": 0.5,
                "within_tolerance": True,
                "timestamp": "2026-02-20T10:00:00",
            }
            for i in range(5)
        ]
        resp = client.post(
            "/api/integration/buildings/site-002/truth-check",
            json={"entries": entries},
        )
        # Pydantic validation should reject < 20 entries
        assert resp.status_code == 422

    def test_promote_rejects_non_shadow_live(self, client):
        # Default INGESTION_MODE is 'simulation', not 'shadow_live'
        resp = client.post("/api/integration/buildings/site-002/promote-to-live")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "simulation" in data["message"]

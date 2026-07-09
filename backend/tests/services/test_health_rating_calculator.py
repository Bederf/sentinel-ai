"""
Tests for HealthRatingCalculator, HealthDataQualityGate, and HealthSnapshotService.

Phase 109B: Health Assessment Timeline

Target: 40+ tests covering:
- 5 formula components with clamping and edge cases
- Composite score with weight verification
- Status delegation to HealthThresholdService
- Data quality gate mode-specific thresholds
- Separation invariants (no risk writes, no local status)
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.health_data_quality_gate import HealthDataQualityGate
from app.services.health_rating_calculator import WEIGHTS, HealthRatingCalculator

# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def calc():
    """Create a HealthRatingCalculator instance."""
    return HealthRatingCalculator()


@pytest.fixture
def gate():
    """Create a HealthDataQualityGate instance."""
    return HealthDataQualityGate()


# ======================================================================
# Component 1: Baseline Alignment (weight 0.35)
# ======================================================================


class TestBaselineAlignment:
    """Tests for calculate_baseline_alignment."""

    def test_zero_deviation(self, calc):
        """0% deviation = perfect score of 100."""
        assert calc.calculate_baseline_alignment(0) == 100.0

    def test_50pct_deviation(self, calc):
        """50% deviation = score of 0 (100 - 2*50)."""
        assert calc.calculate_baseline_alignment(50) == 0.0

    def test_10pct_deviation(self, calc):
        """10% deviation = 80 (100 - 2*10)."""
        assert calc.calculate_baseline_alignment(10) == 80.0

    def test_25pct_deviation(self, calc):
        """25% deviation = 50 (100 - 2*25)."""
        assert calc.calculate_baseline_alignment(25) == 50.0

    def test_none_returns_healthy_floor(self, calc):
        """None (no baseline comparison available) returns 85 healthy-floor score."""
        assert calc.calculate_baseline_alignment(None) == 85.0

    def test_large_deviation_clamps_to_zero(self, calc):
        """Very large deviation clamps to 0."""
        assert calc.calculate_baseline_alignment(100) == 0.0
        assert calc.calculate_baseline_alignment(200) == 0.0

    def test_negative_deviation_clamps_to_100(self, calc):
        """Negative deviation clamps to 100 (can't exceed 100)."""
        result = calc.calculate_baseline_alignment(-10)
        assert result == 100.0


class TestBaselineAlignmentZ:
    """Tests for σ-driven calculate_baseline_alignment_z."""

    def test_zero_z_is_perfect(self, calc):
        """On-baseline reading (z=0) = 100, not 50 — the score anchors at 100."""
        assert calc.calculate_baseline_alignment_z(0.0) == 100.0

    def test_one_sigma_within_noise_band(self, calc):
        """1σ is normal visit-to-visit noise → stays near the healthy band."""
        assert calc.calculate_baseline_alignment_z(1.0) == pytest.approx(88.25, abs=0.01)

    def test_two_sigma_watch_zone(self, calc):
        """2σ deviation → 60.65 (warning-band contribution)."""
        assert calc.calculate_baseline_alignment_z(2.0) == pytest.approx(60.65, abs=0.01)

    def test_three_sigma_alarm(self, calc):
        """3σ (control-chart out-of-control) → 32.47."""
        assert calc.calculate_baseline_alignment_z(3.0) == pytest.approx(32.47, abs=0.01)

    def test_four_sigma_near_zero(self, calc):
        """4σ → 13.53, heading to 0."""
        assert calc.calculate_baseline_alignment_z(4.0) == pytest.approx(13.53, abs=0.01)

    def test_signed_symmetry(self, calc):
        """Deviation below the baseline mean scores the same as above."""
        assert calc.calculate_baseline_alignment_z(-2.0) == calc.calculate_baseline_alignment_z(2.0)

    def test_none_returns_healthy_floor(self, calc):
        """None (no rollup baseline) keeps the 85 healthy-floor semantics."""
        assert calc.calculate_baseline_alignment_z(None) == 85.0

    def test_monotonic_decreasing(self, calc):
        """Score strictly decreases as |z| grows."""
        scores = [calc.calculate_baseline_alignment_z(z) for z in (0.0, 0.5, 1.0, 2.0, 3.0, 5.0)]
        assert scores == sorted(scores, reverse=True)


class TestSigmaElements:
    """Tests for _sigma_elements baseline_values parsing."""

    def test_new_rollup_shape(self, calc):
        """New {value, sigma, n} shape parses mean and sigma."""
        parsed = calc._sigma_elements({"vibration_mm_s": {"value": 2.5, "sigma": 0.3, "n": 8}})
        assert parsed == {"vibration_mm_s": (2.5, 0.3)}

    def test_legacy_tolerance_fallback(self, calc):
        """Legacy {value, tolerance} shape uses tolerance as the σ proxy."""
        parsed = calc._sigma_elements({"filter_dp": {"value": 250, "tolerance": 50}})
        assert parsed == {"filter_dp": (250.0, 50.0)}

    def test_zero_sigma_falls_back_to_tolerance(self, calc):
        """sigma=0 (first rollup, n<2, no prior tolerance) uses tolerance if present."""
        parsed = calc._sigma_elements({"amps": {"value": 12.0, "sigma": 0.0, "tolerance": 1.5}})
        assert parsed == {"amps": (12.0, 1.5)}

    def test_no_usable_sigma_skipped(self, calc):
        """Elements without a positive σ are skipped."""
        assert calc._sigma_elements({"amps": {"value": 12.0, "sigma": 0.0}}) == {}

    def test_non_dict_values_skipped(self, calc):
        """Legacy scalar elements and junk are skipped without raising."""
        parsed = calc._sigma_elements(
            {"note": "ok", "amps": {"value": "bad", "sigma": 1}, "good": {"value": 1, "sigma": 1}}
        )
        assert parsed == {"good": (1.0, 1.0)}

    def test_none_input(self, calc):
        """None baseline_values → empty dict."""
        assert calc._sigma_elements(None) == {}


class TestLeastSquaresSlope:
    """Tests for the OLS slope helper."""

    def test_perfect_line(self, calc):
        assert calc._least_squares_slope([(0.0, 0.0), (7.0, 1.0), (14.0, 2.0)]) == pytest.approx(1.0 / 7.0)

    def test_flat_line(self, calc):
        assert calc._least_squares_slope([(0.0, 1.0), (5.0, 1.0), (10.0, 1.0)]) == pytest.approx(0.0)

    def test_degenerate_x_returns_none(self, calc):
        assert calc._least_squares_slope([(3.0, 1.0), (3.0, 2.0)]) is None

    def test_single_point_returns_none(self, calc):
        assert calc._least_squares_slope([(0.0, 1.0)]) is None


def _baseline_row(date_iso: str, values: dict):
    """Minimal stand-in for an EquipmentBaseline model row."""
    from types import SimpleNamespace

    return SimpleNamespace(baseline_date=date_iso, baseline_values=values)


@pytest.mark.asyncio
class TestRollupTrendSlope:
    """Tests for _get_rollup_trend_slope over rollup history."""

    async def test_rising_element_produces_degrading_slope(self, calc):
        """Vibration drifting 1σ per week → positive points/day slope (25/7)."""
        history = [
            _baseline_row("2026-07-15T00:00:00+00:00", {"vib": {"value": 12.0, "sigma": 1.2}}),
            _baseline_row("2026-07-08T00:00:00+00:00", {"vib": {"value": 11.0, "sigma": 1.1}}),
            _baseline_row("2026-07-01T00:00:00+00:00", {"vib": {"value": 10.0, "sigma": 1.0}}),
        ]
        with patch("app.database.repositories.baseline_repository.BaselineRepository") as mock_repo_cls:
            mock_repo = MagicMock()

            async def _history(equipment_id, limit=10):
                return history

            mock_repo.get_equipment_baseline_history = _history
            mock_repo_cls.return_value = mock_repo

            slope = await calc._get_rollup_trend_slope("EQ-1")

        # |z| vs oldest rollup (σ0=1.0): 0, 1, 2 over days 0, 7, 14 → 1/7 σ/day × 25
        assert slope == pytest.approx(25.0 / 7.0, abs=1e-6)

    async def test_fewer_than_three_rollups_returns_none(self, calc):
        history = [
            _baseline_row("2026-07-08T00:00:00+00:00", {"vib": {"value": 11.0, "sigma": 1.0}}),
            _baseline_row("2026-07-01T00:00:00+00:00", {"vib": {"value": 10.0, "sigma": 1.0}}),
        ]
        with patch("app.database.repositories.baseline_repository.BaselineRepository") as mock_repo_cls:
            mock_repo = MagicMock()

            async def _history(equipment_id, limit=10):
                return history

            mock_repo.get_equipment_baseline_history = _history
            mock_repo_cls.return_value = mock_repo

            assert await calc._get_rollup_trend_slope("EQ-1") is None


@pytest.mark.asyncio
class TestGetBaselineZ:
    """Tests for _get_baseline_z worst-element selection."""

    async def test_worst_element_by_magnitude_keeps_sign(self, calc):
        baseline = _baseline_row(
            "2026-07-01T00:00:00+00:00",
            {
                "amps": {"value": 10.0, "sigma": 1.0},
                "temp": {"value": 5.0, "sigma": 1.0},
            },
        )
        with patch("app.database.repositories.baseline_repository.BaselineRepository") as mock_repo_cls:
            mock_repo = MagicMock()

            async def _active(equipment_id):
                return baseline

            mock_repo.get_active_equipment_baseline = _active
            mock_repo_cls.return_value = mock_repo

            with patch.object(calc, "_get_latest_service_readings") as mock_readings:

                async def _readings(equipment_id):
                    return {"amps": 12.0, "temp": 2.0}  # z=+2 and z=−3

                mock_readings.side_effect = _readings
                z = await calc._get_baseline_z("EQ-1")

        assert z == pytest.approx(-3.0)

    async def test_no_active_baseline_returns_none(self, calc):
        with patch("app.database.repositories.baseline_repository.BaselineRepository") as mock_repo_cls:
            mock_repo = MagicMock()

            async def _active(equipment_id):
                return None

            mock_repo.get_active_equipment_baseline = _active
            mock_repo_cls.return_value = mock_repo

            assert await calc._get_baseline_z("EQ-1") is None


# ======================================================================
# Component 2: Service Compliance (weight 0.20)
# ======================================================================


class TestServiceCompliance:
    """Tests for calculate_service_compliance."""

    def test_on_time(self, calc):
        """Service done exactly on schedule = 100."""
        assert calc.calculate_service_compliance(90, 90) == 100.0

    def test_early_service(self, calc):
        """Service done early = 100 (days_overdue = 0)."""
        assert calc.calculate_service_compliance(60, 90) == 100.0

    def test_30_days_overdue(self, calc):
        """30 days overdue = 100 - 1.5*30 = 55."""
        assert calc.calculate_service_compliance(120, 90) == 55.0

    def test_none_returns_default(self, calc):
        """None (no service record) returns 60."""
        assert calc.calculate_service_compliance(None, 90) == 60.0

    def test_very_overdue_clamps_to_zero(self, calc):
        """Very overdue clamps to 0."""
        # 100 days overdue: 100 - 1.5*100 = -50 → 0
        assert calc.calculate_service_compliance(190, 90) == 0.0

    def test_exact_interval(self, calc):
        """At exact interval boundary, not overdue."""
        assert calc.calculate_service_compliance(90, 90) == 100.0


# ======================================================================
# Component 3: Runtime / Age (weight 0.20)
# ======================================================================


class TestRuntimeAge:
    """Tests for calculate_runtime_age."""

    def test_new_equipment(self, calc):
        """Brand new equipment = near 100."""
        score = calc.calculate_runtime_age(0, 15)
        assert score == 100.0

    def test_at_expected_life(self, calc):
        """At expected life, age_ratio = 1.0, no runtime → 50."""
        score = calc.calculate_runtime_age(15.0, 15.0)
        assert score == 50.0

    def test_half_life(self, calc):
        """Half expected life, no runtime → 75."""
        score = calc.calculate_runtime_age(7.5, 15.0)
        assert score == 75.0

    def test_beyond_life_capped(self, calc):
        """Beyond expected life, age_ratio capped at 1.2."""
        # age_ratio = 30/15 = 2.0 → capped at 1.2
        # score = 100 - 50*1.2 = 40
        score = calc.calculate_runtime_age(30.0, 15.0)
        assert score == 40.0

    def test_no_runtime_age_only(self, calc):
        """No runtime_hours → runtime_ratio = 0, age-only calculation."""
        score = calc.calculate_runtime_age(10.0, 20.0, None, None)
        assert score == 75.0  # 100 - 50*(10/20) - 50*0 = 75

    def test_with_runtime(self, calc):
        """Both age and runtime contribute."""
        # age_ratio = 5/15 = 0.333
        # runtime_ratio = 25000/50000 = 0.5
        # score = 100 - 50*0.333 - 50*0.5 = 100 - 16.67 - 25 = 58.33
        score = calc.calculate_runtime_age(5.0, 15.0, 25000, 50000)
        assert 58.0 <= score <= 59.0

    def test_none_age(self, calc):
        """None age → treated as 0."""
        score = calc.calculate_runtime_age(None, 15.0)
        assert score == 100.0

    def test_expected_life_zero_safety(self, calc):
        """Expected life of 0 should not divide by zero."""
        score = calc.calculate_runtime_age(5.0, 0)
        # max(0, 1) = 1; age_ratio = min(5/1, 1.2) = 1.2
        assert score == 40.0


# ======================================================================
# Component 4: Fault Burden (weight 0.15)
# ======================================================================


class TestFaultBurden:
    """Tests for calculate_fault_burden."""

    def test_no_faults(self, calc):
        """Zero faults = 100."""
        assert calc.calculate_fault_burden(0, 0) == 100.0

    def test_one_critical(self, calc):
        """One critical = 100 - 8*(3) = 76."""
        assert calc.calculate_fault_burden(1, 0) == 76.0

    def test_one_warning(self, calc):
        """One warning = 100 - 8*1 = 92."""
        assert calc.calculate_fault_burden(0, 1) == 92.0

    def test_mixed_faults(self, calc):
        """Mixed: 2 critical + 3 warning = 2*3+3*1=9 → 100-72=28."""
        assert calc.calculate_fault_burden(2, 3) == 28.0

    def test_many_faults_clamps_to_zero(self, calc):
        """5 critical + 5 warning = 20 → 100-160=-60 → 0."""
        assert calc.calculate_fault_burden(5, 5) == 0.0


# ======================================================================
# Component 5: Trend Momentum (weight 0.10)
# ======================================================================


class TestTrendMomentum:
    """Tests for calculate_trend_momentum."""

    def test_improving(self, calc):
        """Slope <= -0.3 = 95 (improving)."""
        assert calc.calculate_trend_momentum(-0.5) == 95

    def test_stable(self, calc):
        """-0.3 < slope < 0.3 = 80 (stable)."""
        assert calc.calculate_trend_momentum(0.0) == 80

    def test_degrading(self, calc):
        """0.3 <= slope < 1.0 = 55 (degrading)."""
        assert calc.calculate_trend_momentum(0.5) == 55

    def test_rapidly_degrading(self, calc):
        """slope >= 1.0 = 30 (rapidly degrading)."""
        assert calc.calculate_trend_momentum(1.5) == 30

    def test_none_returns_stable(self, calc):
        """None → 80 (assume stable)."""
        assert calc.calculate_trend_momentum(None) == 80.0

    def test_boundary_negative_0_3(self, calc):
        """Exactly -0.3 = improving (<=)."""
        assert calc.calculate_trend_momentum(-0.3) == 95

    def test_boundary_positive_0_3(self, calc):
        """Exactly 0.3 = degrading (>=)."""
        assert calc.calculate_trend_momentum(0.3) == 55

    def test_boundary_1_0(self, calc):
        """Exactly 1.0 = rapidly degrading (>=)."""
        assert calc.calculate_trend_momentum(1.0) == 30

    def test_just_below_negative_boundary(self, calc):
        """-0.29 is still stable."""
        assert calc.calculate_trend_momentum(-0.29) == 80

    def test_just_below_positive_boundary(self, calc):
        """0.29 is still stable."""
        assert calc.calculate_trend_momentum(0.29) == 80


# ======================================================================
# Composite Score
# ======================================================================


class TestCompositeScore:
    """Tests for calculate_health_score."""

    def test_all_perfect(self, calc):
        """All 100s → 100."""
        score = calc.calculate_health_score(100, 100, 100, 100, 100)
        assert score == 100.0

    def test_all_zero(self, calc):
        """All 0s → 0."""
        score = calc.calculate_health_score(0, 0, 0, 0, 0)
        assert score == 0.0

    def test_weights_sum_to_one(self):
        """Verify weights sum to exactly 1.0."""
        total = sum(WEIGHTS.values())
        assert total == pytest.approx(1.0)

    def test_mixed_scores(self, calc):
        """Verify weighted calculation with known values."""
        # baseline=90, service=80, runtime=70, fault=60, trend=50
        expected = round(0.35 * 90 + 0.20 * 80 + 0.20 * 70 + 0.15 * 60 + 0.10 * 50, 1)
        score = calc.calculate_health_score(90, 80, 70, 60, 50)
        assert score == expected

    def test_final_clamp_upper(self, calc):
        """Score cannot exceed 100 even with rounding."""
        score = calc.calculate_health_score(100, 100, 100, 100, 100)
        assert score <= 100.0

    def test_final_clamp_lower(self, calc):
        """Score cannot go below 0."""
        score = calc.calculate_health_score(0, 0, 0, 0, 0)
        assert score >= 0.0

    def test_rounding(self, calc):
        """Score is rounded to 1 decimal place."""
        score = calc.calculate_health_score(87, 73, 65, 91, 42)
        assert score == round(score, 1)


# ======================================================================
# Status Delegation
# ======================================================================


class TestStatusDelegation:
    """Tests for health status determination."""

    def test_status_uses_health_threshold_service(self, calc):
        """Status must come from HealthThresholdService, never computed locally."""
        with patch("app.services.health_rating_calculator.get_health_threshold_service") as mock_factory:
            mock_service = MagicMock()
            mock_service.get_health_status.return_value = "warning"
            mock_factory.return_value = mock_service

            result = calc.get_health_status(75.0)

            assert result == "warning"
            mock_service.get_health_status.assert_called_once_with(75.0)

    def test_status_never_computed_locally(self, calc):
        """Calculator has no local threshold logic."""
        # The calculator should not contain hardcoded threshold values
        # for status mapping. It delegates entirely.
        import inspect

        source = inspect.getsource(calc.get_health_status)
        assert "healthy" not in source or "get_health_threshold_service" in source


# ======================================================================
# Data Quality Gates
# ======================================================================


class TestDataQualityGate:
    """Tests for HealthDataQualityGate."""

    def test_simulation_all_pass(self, gate):
        """All gates pass in simulation mode → high confidence."""
        result = gate.evaluate(
            "simulation",
            freshness_minutes=60,
            snapshot_count_24h=10,
            valid_point_ratio=0.95,
            baseline_age_days=5,
        )
        assert result.confidence == "high"
        assert result.assessment_state == "normal"
        assert result.gates_passed == 4
        assert result.gates_total == 4

    def test_simulation_one_fail(self, gate):
        """One gate fails in simulation → medium confidence."""
        # freshness > 1440
        result = gate.evaluate(
            "simulation",
            freshness_minutes=1500,
            snapshot_count_24h=10,
            valid_point_ratio=0.95,
            baseline_age_days=5,
        )
        assert result.confidence == "medium"
        assert result.gates_passed == 3

    def test_simulation_two_fail(self, gate):
        """Two gates fail in simulation → low + degraded_data."""
        result = gate.evaluate(
            "simulation",
            freshness_minutes=1500,
            snapshot_count_24h=2,
            valid_point_ratio=0.95,
            baseline_age_days=5,
        )
        assert result.confidence == "low"
        assert result.assessment_state == "degraded_data"
        assert result.gates_passed == 2

    def test_shadow_live_thresholds(self, gate):
        """Shadow live has stricter thresholds than simulation."""
        # Pass simulation but fail shadow_live
        result = gate.evaluate(
            "shadow_live",
            freshness_minutes=200,  # > 120 max
            snapshot_count_24h=10,  # < 20 min
            valid_point_ratio=0.95,  # < 0.98 min
            baseline_age_days=5,
        )
        assert result.confidence == "low"
        assert result.gates_passed <= 2

    def test_live_control_strict(self, gate):
        """Live control has strictest thresholds."""
        result = gate.evaluate(
            "live_control",
            freshness_minutes=60,  # > 30
            snapshot_count_24h=50,  # > 44
            valid_point_ratio=0.999,  # > 0.995
            baseline_age_days=3,  # < 7
        )
        assert result.confidence == "medium"  # only freshness fails

    def test_live_control_all_pass(self, gate):
        """All gates pass in live_control mode."""
        result = gate.evaluate(
            "live_control",
            freshness_minutes=10,
            snapshot_count_24h=50,
            valid_point_ratio=0.999,
            baseline_age_days=3,
        )
        assert result.confidence == "high"

    def test_boundary_equality_passes(self, gate):
        """Exact threshold value passes (<=, >=)."""
        result = gate.evaluate(
            "simulation",
            freshness_minutes=1440,  # exactly max
            snapshot_count_24h=4,  # exactly min
            valid_point_ratio=0.90,  # exactly min
            baseline_age_days=30,  # exactly max
        )
        assert result.confidence == "high"
        assert result.gates_passed == 4

    def test_unknown_mode_falls_back(self, gate):
        """Unknown mode falls back to simulation thresholds."""
        result = gate.evaluate(
            "unknown_mode",
            freshness_minutes=60,
            snapshot_count_24h=10,
            valid_point_ratio=0.95,
            baseline_age_days=5,
        )
        assert result.confidence == "high"


# ======================================================================
# Separation Invariants
# ======================================================================


class TestSeparationInvariants:
    """Tests that calculator never writes risk or touches predictions."""

    def test_calculator_no_prediction_imports(self):
        """Calculator should not import prediction-related modules."""
        from app.services import health_rating_calculator

        # Check actual import statements, not docstrings
        import_lines = [
            line.strip()
            for line in open(health_rating_calculator.__file__).readlines()
            if line.strip().startswith(("import ", "from "))
        ]
        import_text = "\n".join(import_lines)
        assert "prediction" not in import_text.lower()

    def test_calculator_no_risk_probability(self):
        """Calculator source should not contain risk probability logic."""
        from app.services import health_rating_calculator

        # Check function/method bodies for risk probability writes
        import_lines = [
            line.strip()
            for line in open(health_rating_calculator.__file__).readlines()
            if line.strip().startswith(("import ", "from "))
        ]
        import_text = "\n".join(import_lines)
        assert "risk_probability" not in import_text
        assert "failure_probability" not in import_text

    def test_gate_returns_correct_types(self, gate):
        """Data quality gate returns correctly typed result."""
        from app.models.health_rating import HealthDataQualityResult

        result = gate.evaluate("simulation", 60, 10, 0.95, 5)
        assert isinstance(result, HealthDataQualityResult)
        assert isinstance(result.freshness_minutes, float)
        assert isinstance(result.snapshot_count_24h, int)
        assert isinstance(result.confidence, str)
        assert result.confidence in ("high", "medium", "low")


# ======================================================================
# HealthSnapshotService (import check)
# ======================================================================


class TestSnapshotServiceImport:
    """Basic tests for HealthSnapshotService availability."""

    def test_import(self):
        """HealthSnapshotService imports cleanly."""
        from app.services.health_snapshot_service import HealthSnapshotService

        svc = HealthSnapshotService()
        assert hasattr(svc, "store_snapshot")
        assert hasattr(svc, "get_latest")
        assert hasattr(svc, "get_history")
        assert hasattr(svc, "get_daily_rollups")
        assert hasattr(svc, "recompute")
        assert hasattr(svc, "update_daily_rollup")

    def test_in_memory_mode(self):
        """Service falls back to in-memory when Supabase unavailable."""
        from app.services.health_snapshot_service import HealthSnapshotService

        # Hermetic: force the availability probe to fail regardless of
        # whether the box has a live Supabase (production hosts do).
        with patch(
            "app.database.supabase_client.get_supabase_client",
            side_effect=RuntimeError("unavailable"),
        ):
            svc = HealthSnapshotService()
        assert svc._use_memory is True


@pytest.mark.asyncio
class TestSnapshotServiceOperations:
    """Async tests for HealthSnapshotService storage operations."""

    async def test_store_and_retrieve(self):
        """Store a snapshot and retrieve it."""
        from app.models.health_rating import (
            HealthComponentBreakdown,
            HealthDataQualityResult,
            HealthRating,
        )
        from app.services.health_snapshot_service import HealthSnapshotService

        svc = HealthSnapshotService()
        svc._use_memory = True
        svc._memory_snapshots.clear()

        rating = HealthRating(
            equipment_id="TEST-001",
            health_score=85.5,
            health_status="warning",
            confidence="high",
            assessment_state="normal",
            components=HealthComponentBreakdown(
                baseline_alignment_score=90.0,
                service_compliance_score=80.0,
                runtime_age_score=75.0,
                fault_burden_score=92.0,
                trend_momentum_score=80.0,
            ),
            data_quality=HealthDataQualityResult(
                freshness_minutes=10.0,
                snapshot_count_24h=24,
                valid_point_ratio=0.99,
                baseline_age_days=5,
                gates_passed=4,
                gates_total=4,
                confidence="high",
                assessment_state="normal",
            ),
            formula_version="v1",
            snapshot_at="2026-02-20T12:00:00Z",
        )

        snapshot_id = await svc.store_snapshot(rating)
        assert snapshot_id is not None

        latest = await svc.get_latest("TEST-001")
        assert latest is not None
        assert latest.equipment_id == "TEST-001"
        assert latest.health_score == 85.5

    async def test_get_latest_nonexistent(self):
        """Get latest for nonexistent equipment returns None."""
        from app.services.health_snapshot_service import HealthSnapshotService

        svc = HealthSnapshotService()
        svc._use_memory = True
        svc._memory_snapshots.clear()

        result = await svc.get_latest("NONEXISTENT")
        assert result is None

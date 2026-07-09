"""Tests for Quality Gate Evaluator — Phase 109.

Tests evaluate(), apply_enforcement(), and enforcement mapping for
all mode x status combinations.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.quality_gate_evaluator import (
    _ENFORCEMENT_MAP,
    _SIMULATION_DEFAULTS,
    CONFIDENCE_CAP,
    QualityGateEvaluator,
)
from app.services.quality_gate_policy import (
    EnforcementAction,
    GateStatus,
    QualityGatePolicy,
    QualityGateResult,
    ReasonCode,
    RuleState,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def evaluator():
    """Create a QualityGateEvaluator with audit logging disabled."""
    e = QualityGateEvaluator()
    # Disable audit logging in tests
    e._audit_log = MagicMock()
    return e


@pytest.fixture
def all_pass_simulation_metrics():
    """Metrics that produce PASS for all 14 metrics in simulation mode."""
    return {
        "freshness_minutes": 60.0,
        "ingest_error_rate_pct_1h": 0.0,
        "match_coverage_pct": 100.0,
        "manual_source_pct": 0.0,
        "unmatched_points_pct": 0.0,
        "commissioning_all_gates_passed": 1.0,
        "truth_check_pass_rate_pct": 100.0,
        "consecutive_pass_days": 10.0,
        "mv_accuracy_7d_pct": 90.0,
        "comfort_violation_rate_7d_pct": 0.0,
        "rollback_rate_7d_pct": 0.0,
        "feedback_capture_rate_7d_pct": 100.0,
        "label_lag_p95_hours": 1.0,
        "drift_critical_alerts_24h": 0.0,
    }


@pytest.fixture
def all_pass_shadow_live_metrics():
    """Metrics that produce PASS for all 14 metrics in shadow_live mode."""
    return {
        "freshness_minutes": 60.0,
        "ingest_error_rate_pct_1h": 1.0,
        "match_coverage_pct": 95.0,
        "manual_source_pct": 0.0,
        "unmatched_points_pct": 5.0,
        "commissioning_all_gates_passed": 1.0,
        "truth_check_pass_rate_pct": 99.0,
        "consecutive_pass_days": 5.0,
        "mv_accuracy_7d_pct": 80.0,
        "comfort_violation_rate_7d_pct": 3.0,
        "rollback_rate_7d_pct": 2.0,
        "feedback_capture_rate_7d_pct": 95.0,
        "label_lag_p95_hours": 12.0,
        "drift_critical_alerts_24h": 0.0,
    }


@pytest.fixture
def all_pass_live_control_metrics():
    """Metrics that produce PASS for all 14 metrics in live_control mode."""
    return {
        "freshness_minutes": 5.0,
        "ingest_error_rate_pct_1h": 0.5,
        "match_coverage_pct": 99.0,
        "manual_source_pct": 0.0,
        "unmatched_points_pct": 1.0,
        "commissioning_all_gates_passed": 1.0,
        "truth_check_pass_rate_pct": 99.0,
        "consecutive_pass_days": 5.0,
        "mv_accuracy_7d_pct": 90.0,
        "comfort_violation_rate_7d_pct": 1.0,
        "rollback_rate_7d_pct": 1.0,
        "feedback_capture_rate_7d_pct": 98.0,
        "label_lag_p95_hours": 3.0,
        "drift_critical_alerts_24h": 0.0,
    }


# ---------------------------------------------------------------------------
# evaluate() tests
# ---------------------------------------------------------------------------


class TestEvaluate:
    """Tests for QualityGateEvaluator.evaluate()."""

    def test_all_pass_simulation(self, evaluator, all_pass_simulation_metrics):
        """All metrics passing in simulation mode -> GateStatus.PASS."""
        result = evaluator.evaluate("simulation", all_pass_simulation_metrics)
        assert result.overall == GateStatus.PASS
        assert result.enforcement == EnforcementAction.NORMAL
        assert result.failed_rules == []
        assert result.reason_codes == []

    def test_all_pass_shadow_live(self, evaluator, all_pass_shadow_live_metrics):
        """All metrics passing in shadow_live mode -> GateStatus.PASS."""
        result = evaluator.evaluate("shadow_live", all_pass_shadow_live_metrics)
        assert result.overall == GateStatus.PASS
        assert result.enforcement == EnforcementAction.NORMAL

    def test_all_pass_live_control(self, evaluator, all_pass_live_control_metrics):
        """All metrics passing in live_control mode -> GateStatus.PASS."""
        result = evaluator.evaluate("live_control", all_pass_live_control_metrics)
        assert result.overall == GateStatus.PASS
        assert result.enforcement == EnforcementAction.NORMAL

    def test_one_fail_simulation(self, evaluator, all_pass_simulation_metrics):
        """One failing metric in simulation -> FAIL + CAP_CONFIDENCE."""
        all_pass_simulation_metrics["freshness_minutes"] = 9999.0
        result = evaluator.evaluate("simulation", all_pass_simulation_metrics)
        assert result.overall == GateStatus.FAIL
        assert result.enforcement == EnforcementAction.CAP_CONFIDENCE
        assert "freshness_minutes" in result.failed_rules
        assert ReasonCode.DATA_FRESHNESS_FAIL in result.reason_codes

    def test_one_fail_shadow_live(self, evaluator, all_pass_shadow_live_metrics):
        """One failing metric in shadow_live -> FAIL + SUPPRESS_TIER3."""
        all_pass_shadow_live_metrics["match_coverage_pct"] = 50.0
        result = evaluator.evaluate("shadow_live", all_pass_shadow_live_metrics)
        assert result.overall == GateStatus.FAIL
        assert result.enforcement == EnforcementAction.SUPPRESS_TIER3
        assert "match_coverage_pct" in result.failed_rules

    def test_one_fail_live_control(self, evaluator, all_pass_live_control_metrics):
        """One failing metric in live_control -> FAIL + BLOCK_WRITES."""
        all_pass_live_control_metrics["ingest_error_rate_pct_1h"] = 10.0
        result = evaluator.evaluate("live_control", all_pass_live_control_metrics)
        assert result.overall == GateStatus.FAIL
        assert result.enforcement == EnforcementAction.BLOCK_WRITES

    def test_one_warn_simulation(self, evaluator, all_pass_simulation_metrics):
        """One warning metric in simulation -> WARN + NORMAL."""
        all_pass_simulation_metrics["freshness_minutes"] = 2000.0  # Between 1440 and 4320
        result = evaluator.evaluate("simulation", all_pass_simulation_metrics)
        assert result.overall == GateStatus.WARN
        assert result.enforcement == EnforcementAction.NORMAL
        assert "freshness_minutes" in result.warn_rules

    def test_one_warn_shadow_live(self, evaluator, all_pass_shadow_live_metrics):
        """One warning metric in shadow_live -> WARN + NORMAL."""
        all_pass_shadow_live_metrics["mv_accuracy_7d_pct"] = 70.0  # Between 65 and 75
        result = evaluator.evaluate("shadow_live", all_pass_shadow_live_metrics)
        assert result.overall == GateStatus.WARN
        assert result.enforcement == EnforcementAction.NORMAL

    def test_one_warn_live_control(self, evaluator, all_pass_live_control_metrics):
        """One warning metric in live_control -> WARN + SUPPRESS_TIER3."""
        all_pass_live_control_metrics["freshness_minutes"] = 30.0  # Between 15 and 60
        result = evaluator.evaluate("live_control", all_pass_live_control_metrics)
        assert result.overall == GateStatus.WARN
        assert result.enforcement == EnforcementAction.SUPPRESS_TIER3

    def test_mixed_warn_and_fail(self, evaluator, all_pass_simulation_metrics):
        """Mixed warn + fail -> overall FAIL (fail dominates)."""
        all_pass_simulation_metrics["freshness_minutes"] = 2000.0  # WARN
        all_pass_simulation_metrics["mv_accuracy_7d_pct"] = 10.0  # FAIL
        result = evaluator.evaluate("simulation", all_pass_simulation_metrics)
        assert result.overall == GateStatus.FAIL
        assert "mv_accuracy_7d_pct" in result.failed_rules
        assert "freshness_minutes" in result.warn_rules

    def test_na_metrics_excluded_from_gate(self, evaluator):
        """NA metrics don't affect overall gate status."""
        metrics = dict(_SIMULATION_DEFAULTS)
        # In simulation, manual_source_pct is NA -> any value is OK
        metrics["manual_source_pct"] = 100.0
        result = evaluator.evaluate("simulation", metrics)
        assert "manual_source_pct" not in result.failed_rules
        assert "manual_source_pct" not in result.warn_rules

    def test_runtime_none_metric_is_na_and_not_blocking(self, evaluator, all_pass_live_control_metrics):
        """A metric collector can mark an inapplicable live metric as runtime NA."""
        all_pass_live_control_metrics["mv_accuracy_7d_pct"] = None

        result = evaluator.evaluate("live_control", all_pass_live_control_metrics)

        mv_rule = next(r for r in result.rule_results if r.metric == "mv_accuracy_7d_pct")
        assert mv_rule.value is None
        assert mv_rule.state == RuleState.NA
        assert "mv_accuracy_7d_pct" not in result.failed_rules
        assert result.overall == GateStatus.PASS

    def test_rule_results_count(self, evaluator, all_pass_simulation_metrics):
        """All 14 metrics produce rule results."""
        result = evaluator.evaluate("simulation", all_pass_simulation_metrics)
        assert len(result.rule_results) == 14

    def test_reason_codes_only_from_failures(self, evaluator, all_pass_simulation_metrics):
        """Reason codes only come from failed metrics, not warnings."""
        all_pass_simulation_metrics["freshness_minutes"] = 2000.0  # WARN
        result = evaluator.evaluate("simulation", all_pass_simulation_metrics)
        assert result.reason_codes == []

    def test_mode_stored_in_result(self, evaluator, all_pass_simulation_metrics):
        """Result includes the mode used for evaluation."""
        result = evaluator.evaluate("simulation", all_pass_simulation_metrics)
        assert result.mode == "simulation"

    def test_evaluated_at_populated(self, evaluator, all_pass_simulation_metrics):
        """Result has an evaluated_at timestamp."""
        result = evaluator.evaluate("simulation", all_pass_simulation_metrics)
        assert result.evaluated_at != ""
        assert "T" in result.evaluated_at  # ISO format


# ---------------------------------------------------------------------------
# Enforcement mapping tests (9 combinations)
# ---------------------------------------------------------------------------


class TestEnforcementMapping:
    """Tests for mode x gate status -> enforcement action."""

    @pytest.mark.parametrize(
        "mode,gate_status,expected_enforcement",
        [
            ("simulation", GateStatus.PASS, EnforcementAction.NORMAL),
            ("simulation", GateStatus.WARN, EnforcementAction.NORMAL),
            ("simulation", GateStatus.FAIL, EnforcementAction.CAP_CONFIDENCE),
            ("shadow_live", GateStatus.PASS, EnforcementAction.NORMAL),
            ("shadow_live", GateStatus.WARN, EnforcementAction.NORMAL),
            ("shadow_live", GateStatus.FAIL, EnforcementAction.SUPPRESS_TIER3),
            ("live_control", GateStatus.PASS, EnforcementAction.NORMAL),
            ("live_control", GateStatus.WARN, EnforcementAction.SUPPRESS_TIER3),
            ("live_control", GateStatus.FAIL, EnforcementAction.BLOCK_WRITES),
        ],
    )
    def test_enforcement_map(self, mode, gate_status, expected_enforcement):
        """Verify each of the 9 mode x status enforcement mappings."""
        assert _ENFORCEMENT_MAP[(mode, gate_status)] == expected_enforcement


# ---------------------------------------------------------------------------
# apply_enforcement() tests
# ---------------------------------------------------------------------------


class TestApplyEnforcement:
    """Tests for QualityGateEvaluator.apply_enforcement()."""

    def _make_result(self, overall, enforcement, reason_codes=None):
        """Helper to build a minimal QualityGateResult."""
        return QualityGateResult(
            overall=overall,
            rule_results=[],
            failed_rules=[],
            warn_rules=[],
            enforcement=enforcement,
            reason_codes=reason_codes or [],
            mode="simulation",
        )

    def test_normal_no_modification(self, evaluator):
        """NORMAL enforcement doesn't modify recommendation values."""
        result = self._make_result(GateStatus.PASS, EnforcementAction.NORMAL)
        rec = {"confidence": 0.85, "action": "auto_execute"}
        modified = evaluator.apply_enforcement(result, rec)
        assert modified["confidence"] == 0.85
        assert modified["action"] == "auto_execute"
        assert modified["quality_gate_status"] == "pass"
        assert modified["enforcement_action"] == "normal"

    def test_cap_confidence(self, evaluator):
        """CAP_CONFIDENCE caps effective_confidence at 0.59."""
        result = self._make_result(GateStatus.FAIL, EnforcementAction.CAP_CONFIDENCE)
        rec = {"confidence": 0.85}
        modified = evaluator.apply_enforcement(result, rec)
        assert modified["effective_confidence"] == CONFIDENCE_CAP
        assert modified["quality_penalty"] == pytest.approx(0.26, abs=0.01)

    def test_cap_confidence_already_low(self, evaluator):
        """CAP_CONFIDENCE with confidence already below cap -> no change."""
        result = self._make_result(GateStatus.FAIL, EnforcementAction.CAP_CONFIDENCE)
        rec = {"confidence": 0.3}
        modified = evaluator.apply_enforcement(result, rec)
        assert modified["effective_confidence"] == 0.3
        assert modified["quality_penalty"] == 0.0

    def test_suppress_tier3(self, evaluator):
        """SUPPRESS_TIER3 converts auto_execute to pending_approval."""
        result = self._make_result(GateStatus.FAIL, EnforcementAction.SUPPRESS_TIER3)
        rec = {"action": "auto_execute"}
        modified = evaluator.apply_enforcement(result, rec)
        assert modified["max_action"] == "pending_approval"
        assert modified["action"] == "pending_approval"

    def test_suppress_tier3_non_auto(self, evaluator):
        """SUPPRESS_TIER3 with non-auto action sets max_action only."""
        result = self._make_result(GateStatus.WARN, EnforcementAction.SUPPRESS_TIER3)
        rec = {"action": "pending_approval"}
        modified = evaluator.apply_enforcement(result, rec)
        assert modified["max_action"] == "pending_approval"
        assert modified["action"] == "pending_approval"

    def test_block_writes(self, evaluator):
        """BLOCK_WRITES sets action=log_only and blocked=True."""
        result = self._make_result(
            GateStatus.FAIL,
            EnforcementAction.BLOCK_WRITES,
            reason_codes=[ReasonCode.DATA_FRESHNESS_FAIL, ReasonCode.MATCH_COVERAGE_FAIL],
        )
        rec = {"action": "auto_execute", "confidence": 0.95}
        modified = evaluator.apply_enforcement(result, rec)
        assert modified["action"] == "log_only"
        assert modified["blocked"] is True
        assert "data_freshness_fail" in modified["block_reasons"]
        assert "match_coverage_fail" in modified["block_reasons"]

    def test_always_adds_gate_status_fields(self, evaluator):
        """All enforcement actions add quality_gate_status and enforcement_action."""
        for enforcement in EnforcementAction:
            result = self._make_result(GateStatus.PASS, enforcement)
            rec = {}
            modified = evaluator.apply_enforcement(result, rec)
            assert "quality_gate_status" in modified
            assert "enforcement_action" in modified


# ---------------------------------------------------------------------------
# collect_metrics() tests
# ---------------------------------------------------------------------------


class TestCollectMetrics:
    """Tests for QualityGateEvaluator.collect_metrics()."""

    @pytest.mark.asyncio
    async def test_simulation_defaults_when_no_services(self, evaluator):
        """When all services fail, simulation defaults produce PASS values."""
        from app.config.settings import IngestionMode

        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.resolved_ingestion_mode = IngestionMode.SIMULATION
            metrics = await evaluator.collect_metrics("S002")
            # Verify all defaults are present
            assert len(metrics) == 14
            for key in _SIMULATION_DEFAULTS:
                assert key in metrics

    @pytest.mark.asyncio
    async def test_live_no_site_id_fail_closed(self, evaluator):
        """Live mode without site_id returns fail-closed defaults."""
        from app.config.settings import IngestionMode

        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.resolved_ingestion_mode = IngestionMode.LIVE_CONTROL
            metrics = await evaluator.collect_metrics(None)
            # Should return live defaults (all fail values)
            assert metrics["freshness_minutes"] == 9999.0
            assert metrics["match_coverage_pct"] == 0.0
            assert metrics["manual_source_pct"] == 100.0


# ===========================================================================
# Exhaustive boundary tests: 14 metrics x 3 modes (Task 3)
# ===========================================================================


class TestMetricBoundaries:
    """Parametrized boundary tests for all 14 metrics x 3 modes.

    For each metric/mode combo, tests:
    - Value at pass boundary -> PASS
    - Value just past pass boundary -> WARN (if warn exists) or FAIL
    - Value at warn boundary -> WARN (if exists)
    - Value just past warn/fail boundary -> FAIL
    - Value well within pass -> PASS
    - Value well beyond fail -> FAIL
    """

    # ------------------------------------------------------------------
    # SIMULATION mode boundaries
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "metric,value,expected",
        [
            # freshness_minutes: lower_is_better, pass=1440, warn=4320
            ("freshness_minutes", 0.0, RuleState.PASS),
            ("freshness_minutes", 1440.0, RuleState.PASS),  # at pass bound
            ("freshness_minutes", 1441.0, RuleState.WARN),  # just past pass
            ("freshness_minutes", 2880.0, RuleState.WARN),  # mid-warn
            ("freshness_minutes", 4320.0, RuleState.WARN),  # at warn bound
            ("freshness_minutes", 4321.0, RuleState.FAIL),  # just past warn
            ("freshness_minutes", 9999.0, RuleState.FAIL),  # well past
            # ingest_error_rate_pct_1h: lower_is_better, pass=15, warn=25
            ("ingest_error_rate_pct_1h", 0.0, RuleState.PASS),
            ("ingest_error_rate_pct_1h", 15.0, RuleState.PASS),
            ("ingest_error_rate_pct_1h", 15.1, RuleState.WARN),
            ("ingest_error_rate_pct_1h", 25.0, RuleState.WARN),
            ("ingest_error_rate_pct_1h", 25.1, RuleState.FAIL),
            ("ingest_error_rate_pct_1h", 100.0, RuleState.FAIL),
            # match_coverage_pct: higher_is_better, pass=60, warn=40
            ("match_coverage_pct", 100.0, RuleState.PASS),
            ("match_coverage_pct", 60.0, RuleState.PASS),  # at pass bound
            ("match_coverage_pct", 59.9, RuleState.WARN),  # just below pass
            ("match_coverage_pct", 40.0, RuleState.WARN),  # at warn bound
            ("match_coverage_pct", 39.9, RuleState.FAIL),  # just below warn
            ("match_coverage_pct", 0.0, RuleState.FAIL),
            # manual_source_pct: NA in simulation
            ("manual_source_pct", 0.0, RuleState.NA),
            ("manual_source_pct", 50.0, RuleState.NA),
            ("manual_source_pct", 100.0, RuleState.NA),
            # unmatched_points_pct: lower_is_better, pass=40, warn=60
            ("unmatched_points_pct", 0.0, RuleState.PASS),
            ("unmatched_points_pct", 40.0, RuleState.PASS),
            ("unmatched_points_pct", 40.1, RuleState.WARN),
            ("unmatched_points_pct", 60.0, RuleState.WARN),
            ("unmatched_points_pct", 60.1, RuleState.FAIL),
            ("unmatched_points_pct", 100.0, RuleState.FAIL),
            # commissioning_all_gates_passed: NA in simulation
            ("commissioning_all_gates_passed", 0.0, RuleState.NA),
            ("commissioning_all_gates_passed", 1.0, RuleState.NA),
            # truth_check_pass_rate_pct: NA in simulation
            ("truth_check_pass_rate_pct", 0.0, RuleState.NA),
            ("truth_check_pass_rate_pct", 100.0, RuleState.NA),
            # consecutive_pass_days: NA in simulation
            ("consecutive_pass_days", 0.0, RuleState.NA),
            ("consecutive_pass_days", 10.0, RuleState.NA),
            # mv_accuracy_7d_pct: higher_is_better, pass=50, warn=40
            ("mv_accuracy_7d_pct", 90.0, RuleState.PASS),
            ("mv_accuracy_7d_pct", 50.0, RuleState.PASS),
            ("mv_accuracy_7d_pct", 49.9, RuleState.WARN),
            ("mv_accuracy_7d_pct", 40.0, RuleState.WARN),
            ("mv_accuracy_7d_pct", 39.9, RuleState.FAIL),
            ("mv_accuracy_7d_pct", 0.0, RuleState.FAIL),
            # comfort_violation_rate_7d_pct: lower_is_better, pass=20, warn=35
            ("comfort_violation_rate_7d_pct", 0.0, RuleState.PASS),
            ("comfort_violation_rate_7d_pct", 20.0, RuleState.PASS),
            ("comfort_violation_rate_7d_pct", 20.1, RuleState.WARN),
            ("comfort_violation_rate_7d_pct", 35.0, RuleState.WARN),
            ("comfort_violation_rate_7d_pct", 35.1, RuleState.FAIL),
            # rollback_rate_7d_pct: lower_is_better, pass=15, warn=25
            ("rollback_rate_7d_pct", 0.0, RuleState.PASS),
            ("rollback_rate_7d_pct", 15.0, RuleState.PASS),
            ("rollback_rate_7d_pct", 15.1, RuleState.WARN),
            ("rollback_rate_7d_pct", 25.0, RuleState.WARN),
            ("rollback_rate_7d_pct", 25.1, RuleState.FAIL),
            # feedback_capture_rate_7d_pct: higher_is_better, pass=70, warn=50
            ("feedback_capture_rate_7d_pct", 100.0, RuleState.PASS),
            ("feedback_capture_rate_7d_pct", 70.0, RuleState.PASS),
            ("feedback_capture_rate_7d_pct", 69.9, RuleState.WARN),
            ("feedback_capture_rate_7d_pct", 50.0, RuleState.WARN),
            ("feedback_capture_rate_7d_pct", 49.9, RuleState.FAIL),
            # label_lag_p95_hours: lower_is_better, pass=72, warn=120
            ("label_lag_p95_hours", 1.0, RuleState.PASS),
            ("label_lag_p95_hours", 72.0, RuleState.PASS),
            ("label_lag_p95_hours", 72.1, RuleState.WARN),
            ("label_lag_p95_hours", 120.0, RuleState.WARN),
            ("label_lag_p95_hours", 120.1, RuleState.FAIL),
            # drift_critical_alerts_24h: lower_is_better, pass=2, no warn
            ("drift_critical_alerts_24h", 0.0, RuleState.PASS),
            ("drift_critical_alerts_24h", 2.0, RuleState.PASS),
            ("drift_critical_alerts_24h", 3.0, RuleState.FAIL),  # no warn band
            ("drift_critical_alerts_24h", 10.0, RuleState.FAIL),
        ],
        ids=lambda x: str(x),
    )
    def test_simulation_boundary(self, metric, value, expected):
        """Boundary test for simulation mode thresholds."""
        policy = QualityGatePolicy()
        threshold = policy.get_metric_threshold(metric, "simulation")
        assert threshold.evaluate(value) == expected

    # ------------------------------------------------------------------
    # SHADOW_LIVE mode boundaries
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "metric,value,expected",
        [
            # freshness_minutes: lower_is_better, pass=120, warn=360
            ("freshness_minutes", 0.0, RuleState.PASS),
            ("freshness_minutes", 120.0, RuleState.PASS),
            ("freshness_minutes", 121.0, RuleState.WARN),
            ("freshness_minutes", 360.0, RuleState.WARN),
            ("freshness_minutes", 361.0, RuleState.FAIL),
            # ingest_error_rate_pct_1h: lower_is_better, pass=3, warn=5
            ("ingest_error_rate_pct_1h", 0.0, RuleState.PASS),
            ("ingest_error_rate_pct_1h", 3.0, RuleState.PASS),
            ("ingest_error_rate_pct_1h", 3.1, RuleState.WARN),
            ("ingest_error_rate_pct_1h", 5.0, RuleState.WARN),
            ("ingest_error_rate_pct_1h", 5.1, RuleState.FAIL),
            # match_coverage_pct: higher_is_better, pass=90, warn=80
            ("match_coverage_pct", 95.0, RuleState.PASS),
            ("match_coverage_pct", 90.0, RuleState.PASS),
            ("match_coverage_pct", 89.9, RuleState.WARN),
            ("match_coverage_pct", 80.0, RuleState.WARN),
            ("match_coverage_pct", 79.9, RuleState.FAIL),
            # manual_source_pct: lower_is_better, pass=0, no warn (>0 = fail)
            ("manual_source_pct", 0.0, RuleState.PASS),
            ("manual_source_pct", 0.01, RuleState.FAIL),  # no warn
            ("manual_source_pct", 50.0, RuleState.FAIL),
            # unmatched_points_pct: lower_is_better, pass=10, warn=20
            ("unmatched_points_pct", 5.0, RuleState.PASS),
            ("unmatched_points_pct", 10.0, RuleState.PASS),
            ("unmatched_points_pct", 10.1, RuleState.WARN),
            ("unmatched_points_pct", 20.0, RuleState.WARN),
            ("unmatched_points_pct", 20.1, RuleState.FAIL),
            # commissioning_all_gates_passed: higher_is_better, pass=1, no warn
            ("commissioning_all_gates_passed", 1.0, RuleState.PASS),
            ("commissioning_all_gates_passed", 0.0, RuleState.FAIL),
            # truth_check_pass_rate_pct: higher_is_better, pass=98, warn=95
            ("truth_check_pass_rate_pct", 99.0, RuleState.PASS),
            ("truth_check_pass_rate_pct", 98.0, RuleState.PASS),
            ("truth_check_pass_rate_pct", 97.9, RuleState.WARN),
            ("truth_check_pass_rate_pct", 95.0, RuleState.WARN),
            ("truth_check_pass_rate_pct", 94.9, RuleState.FAIL),
            # consecutive_pass_days: higher_is_better, pass=2, warn=1
            ("consecutive_pass_days", 5.0, RuleState.PASS),
            ("consecutive_pass_days", 2.0, RuleState.PASS),
            ("consecutive_pass_days", 1.5, RuleState.WARN),
            ("consecutive_pass_days", 1.0, RuleState.WARN),
            ("consecutive_pass_days", 0.9, RuleState.FAIL),
            ("consecutive_pass_days", 0.0, RuleState.FAIL),
            # mv_accuracy_7d_pct: higher_is_better, pass=75, warn=65
            ("mv_accuracy_7d_pct", 80.0, RuleState.PASS),
            ("mv_accuracy_7d_pct", 75.0, RuleState.PASS),
            ("mv_accuracy_7d_pct", 74.9, RuleState.WARN),
            ("mv_accuracy_7d_pct", 65.0, RuleState.WARN),
            ("mv_accuracy_7d_pct", 64.9, RuleState.FAIL),
            # comfort_violation_rate_7d_pct: lower_is_better, pass=8, warn=12
            ("comfort_violation_rate_7d_pct", 5.0, RuleState.PASS),
            ("comfort_violation_rate_7d_pct", 8.0, RuleState.PASS),
            ("comfort_violation_rate_7d_pct", 8.1, RuleState.WARN),
            ("comfort_violation_rate_7d_pct", 12.0, RuleState.WARN),
            ("comfort_violation_rate_7d_pct", 12.1, RuleState.FAIL),
            # rollback_rate_7d_pct: lower_is_better, pass=5, warn=8
            ("rollback_rate_7d_pct", 3.0, RuleState.PASS),
            ("rollback_rate_7d_pct", 5.0, RuleState.PASS),
            ("rollback_rate_7d_pct", 5.1, RuleState.WARN),
            ("rollback_rate_7d_pct", 8.0, RuleState.WARN),
            ("rollback_rate_7d_pct", 8.1, RuleState.FAIL),
            # feedback_capture_rate_7d_pct: higher_is_better, pass=90, warn=80
            ("feedback_capture_rate_7d_pct", 95.0, RuleState.PASS),
            ("feedback_capture_rate_7d_pct", 90.0, RuleState.PASS),
            ("feedback_capture_rate_7d_pct", 89.9, RuleState.WARN),
            ("feedback_capture_rate_7d_pct", 80.0, RuleState.WARN),
            ("feedback_capture_rate_7d_pct", 79.9, RuleState.FAIL),
            # label_lag_p95_hours: lower_is_better, pass=24, warn=36
            ("label_lag_p95_hours", 12.0, RuleState.PASS),
            ("label_lag_p95_hours", 24.0, RuleState.PASS),
            ("label_lag_p95_hours", 24.1, RuleState.WARN),
            ("label_lag_p95_hours", 36.0, RuleState.WARN),
            ("label_lag_p95_hours", 36.1, RuleState.FAIL),
            # drift_critical_alerts_24h: lower_is_better, pass=0, warn=1
            ("drift_critical_alerts_24h", 0.0, RuleState.PASS),
            ("drift_critical_alerts_24h", 0.5, RuleState.WARN),
            ("drift_critical_alerts_24h", 1.0, RuleState.WARN),
            ("drift_critical_alerts_24h", 1.1, RuleState.FAIL),
            ("drift_critical_alerts_24h", 2.0, RuleState.FAIL),
        ],
        ids=lambda x: str(x),
    )
    def test_shadow_live_boundary(self, metric, value, expected):
        """Boundary test for shadow_live mode thresholds."""
        policy = QualityGatePolicy()
        threshold = policy.get_metric_threshold(metric, "shadow_live")
        assert threshold.evaluate(value) == expected

    # ------------------------------------------------------------------
    # LIVE_CONTROL mode boundaries
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "metric,value,expected",
        [
            # freshness_minutes: lower_is_better, pass=15, warn=60
            ("freshness_minutes", 5.0, RuleState.PASS),
            ("freshness_minutes", 15.0, RuleState.PASS),
            ("freshness_minutes", 15.1, RuleState.WARN),
            ("freshness_minutes", 60.0, RuleState.WARN),
            ("freshness_minutes", 60.1, RuleState.FAIL),
            # ingest_error_rate_pct_1h: lower_is_better, pass=1, warn=2
            ("ingest_error_rate_pct_1h", 0.0, RuleState.PASS),
            ("ingest_error_rate_pct_1h", 1.0, RuleState.PASS),
            ("ingest_error_rate_pct_1h", 1.1, RuleState.WARN),
            ("ingest_error_rate_pct_1h", 2.0, RuleState.WARN),
            ("ingest_error_rate_pct_1h", 2.1, RuleState.FAIL),
            # match_coverage_pct: higher_is_better, pass=98, warn=95
            ("match_coverage_pct", 99.0, RuleState.PASS),
            ("match_coverage_pct", 98.0, RuleState.PASS),
            ("match_coverage_pct", 97.9, RuleState.WARN),
            ("match_coverage_pct", 95.0, RuleState.WARN),
            ("match_coverage_pct", 94.9, RuleState.FAIL),
            # manual_source_pct: lower_is_better, pass=0, no warn
            ("manual_source_pct", 0.0, RuleState.PASS),
            ("manual_source_pct", 0.01, RuleState.FAIL),
            ("manual_source_pct", 100.0, RuleState.FAIL),
            # unmatched_points_pct: lower_is_better, pass=2, warn=5
            ("unmatched_points_pct", 1.0, RuleState.PASS),
            ("unmatched_points_pct", 2.0, RuleState.PASS),
            ("unmatched_points_pct", 2.1, RuleState.WARN),
            ("unmatched_points_pct", 5.0, RuleState.WARN),
            ("unmatched_points_pct", 5.1, RuleState.FAIL),
            # commissioning_all_gates_passed: higher_is_better, pass=1, no warn
            ("commissioning_all_gates_passed", 1.0, RuleState.PASS),
            ("commissioning_all_gates_passed", 0.0, RuleState.FAIL),
            # truth_check_pass_rate_pct: higher_is_better, pass=98, no warn
            ("truth_check_pass_rate_pct", 99.0, RuleState.PASS),
            ("truth_check_pass_rate_pct", 98.0, RuleState.PASS),
            ("truth_check_pass_rate_pct", 97.9, RuleState.FAIL),  # no warn
            # consecutive_pass_days: higher_is_better, pass=2, no warn
            ("consecutive_pass_days", 5.0, RuleState.PASS),
            ("consecutive_pass_days", 2.0, RuleState.PASS),
            ("consecutive_pass_days", 1.9, RuleState.FAIL),  # no warn
            ("consecutive_pass_days", 0.0, RuleState.FAIL),
            # mv_accuracy_7d_pct: higher_is_better, pass=85, warn=75
            ("mv_accuracy_7d_pct", 90.0, RuleState.PASS),
            ("mv_accuracy_7d_pct", 85.0, RuleState.PASS),
            ("mv_accuracy_7d_pct", 84.9, RuleState.WARN),
            ("mv_accuracy_7d_pct", 75.0, RuleState.WARN),
            ("mv_accuracy_7d_pct", 74.9, RuleState.FAIL),
            # comfort_violation_rate_7d_pct: lower_is_better, pass=3, warn=5
            ("comfort_violation_rate_7d_pct", 1.0, RuleState.PASS),
            ("comfort_violation_rate_7d_pct", 3.0, RuleState.PASS),
            ("comfort_violation_rate_7d_pct", 3.1, RuleState.WARN),
            ("comfort_violation_rate_7d_pct", 5.0, RuleState.WARN),
            ("comfort_violation_rate_7d_pct", 5.1, RuleState.FAIL),
            # rollback_rate_7d_pct: lower_is_better, pass=2, warn=4
            ("rollback_rate_7d_pct", 1.0, RuleState.PASS),
            ("rollback_rate_7d_pct", 2.0, RuleState.PASS),
            ("rollback_rate_7d_pct", 2.1, RuleState.WARN),
            ("rollback_rate_7d_pct", 4.0, RuleState.WARN),
            ("rollback_rate_7d_pct", 4.1, RuleState.FAIL),
            # feedback_capture_rate_7d_pct: higher_is_better, pass=97, warn=93
            ("feedback_capture_rate_7d_pct", 99.0, RuleState.PASS),
            ("feedback_capture_rate_7d_pct", 97.0, RuleState.PASS),
            ("feedback_capture_rate_7d_pct", 96.9, RuleState.WARN),
            ("feedback_capture_rate_7d_pct", 93.0, RuleState.WARN),
            ("feedback_capture_rate_7d_pct", 92.9, RuleState.FAIL),
            # label_lag_p95_hours: lower_is_better, pass=6, warn=12
            ("label_lag_p95_hours", 3.0, RuleState.PASS),
            ("label_lag_p95_hours", 6.0, RuleState.PASS),
            ("label_lag_p95_hours", 6.1, RuleState.WARN),
            ("label_lag_p95_hours", 12.0, RuleState.WARN),
            ("label_lag_p95_hours", 12.1, RuleState.FAIL),
            # drift_critical_alerts_24h: lower_is_better, pass=0, no warn
            ("drift_critical_alerts_24h", 0.0, RuleState.PASS),
            ("drift_critical_alerts_24h", 0.1, RuleState.FAIL),  # no warn
            ("drift_critical_alerts_24h", 1.0, RuleState.FAIL),
        ],
        ids=lambda x: str(x),
    )
    def test_live_control_boundary(self, metric, value, expected):
        """Boundary test for live_control mode thresholds."""
        policy = QualityGatePolicy()
        threshold = policy.get_metric_threshold(metric, "live_control")
        assert threshold.evaluate(value) == expected


# ===========================================================================
# Overall gate aggregation boundary tests
# ===========================================================================


class TestGateAggregation:
    """Tests for overall gate aggregation with mixed states."""

    @pytest.fixture
    def eval_with_no_audit(self):
        """Evaluator with audit disabled."""
        e = QualityGateEvaluator()
        e._audit_log = MagicMock()
        return e

    def test_all_pass_no_na_gives_pass(self, eval_with_no_audit):
        """When all non-NA metrics pass, overall is PASS."""
        metrics = dict(_SIMULATION_DEFAULTS)
        result = eval_with_no_audit.evaluate("simulation", metrics)
        assert result.overall == GateStatus.PASS

    def test_single_warn_gives_warn(self, eval_with_no_audit):
        """Single WARN with rest PASS -> WARN."""
        metrics = dict(_SIMULATION_DEFAULTS)
        metrics["freshness_minutes"] = 2000.0  # WARN in simulation
        result = eval_with_no_audit.evaluate("simulation", metrics)
        assert result.overall == GateStatus.WARN

    def test_single_fail_gives_fail(self, eval_with_no_audit):
        """Single FAIL with rest PASS -> FAIL."""
        metrics = dict(_SIMULATION_DEFAULTS)
        metrics["freshness_minutes"] = 9999.0  # FAIL in simulation
        result = eval_with_no_audit.evaluate("simulation", metrics)
        assert result.overall == GateStatus.FAIL

    def test_warn_plus_fail_gives_fail(self, eval_with_no_audit):
        """WARN + FAIL -> FAIL (fail dominates)."""
        metrics = dict(_SIMULATION_DEFAULTS)
        metrics["freshness_minutes"] = 2000.0  # WARN
        metrics["ingest_error_rate_pct_1h"] = 50.0  # FAIL
        result = eval_with_no_audit.evaluate("simulation", metrics)
        assert result.overall == GateStatus.FAIL

    def test_multiple_warns_gives_warn(self, eval_with_no_audit):
        """Multiple WARNs, no FAIL -> WARN."""
        metrics = dict(_SIMULATION_DEFAULTS)
        metrics["freshness_minutes"] = 2000.0  # WARN
        metrics["ingest_error_rate_pct_1h"] = 20.0  # WARN
        result = eval_with_no_audit.evaluate("simulation", metrics)
        assert result.overall == GateStatus.WARN

    def test_multiple_fails_gives_fail(self, eval_with_no_audit):
        """Multiple FAILs -> FAIL with multiple reason codes."""
        metrics = dict(_SIMULATION_DEFAULTS)
        metrics["freshness_minutes"] = 9999.0  # FAIL
        metrics["ingest_error_rate_pct_1h"] = 50.0  # FAIL
        metrics["mv_accuracy_7d_pct"] = 0.0  # FAIL
        result = eval_with_no_audit.evaluate("simulation", metrics)
        assert result.overall == GateStatus.FAIL
        assert len(result.failed_rules) == 3
        assert len(result.reason_codes) == 3


# ===========================================================================
# Reason code correctness tests
# ===========================================================================


class TestReasonCodes:
    """Tests that the correct reason codes are assigned per metric."""

    @pytest.fixture
    def eval_with_no_audit(self):
        e = QualityGateEvaluator()
        e._audit_log = MagicMock()
        return e

    @pytest.mark.parametrize(
        "metric,expected_code",
        [
            ("freshness_minutes", ReasonCode.DATA_FRESHNESS_FAIL),
            ("ingest_error_rate_pct_1h", ReasonCode.INGEST_ERROR_RATE_FAIL),
            ("match_coverage_pct", ReasonCode.MATCH_COVERAGE_FAIL),
            ("mv_accuracy_7d_pct", ReasonCode.MV_ACCURACY_FAIL),
            ("feedback_capture_rate_7d_pct", ReasonCode.FEEDBACK_COVERAGE_FAIL),
            ("drift_critical_alerts_24h", ReasonCode.DRIFT_CRITICAL_FAIL),
            ("unmatched_points_pct", ReasonCode.QUALITY_GATE_BLOCK),
            ("comfort_violation_rate_7d_pct", ReasonCode.QUALITY_GATE_BLOCK),
            ("rollback_rate_7d_pct", ReasonCode.QUALITY_GATE_BLOCK),
            ("label_lag_p95_hours", ReasonCode.QUALITY_GATE_BLOCK),
        ],
    )
    def test_reason_code_per_metric(self, eval_with_no_audit, metric, expected_code):
        """Each failing metric produces the correct reason code."""
        # Use shadow_live so most metrics have real thresholds (not NA)
        metrics = {
            "freshness_minutes": 60.0,
            "ingest_error_rate_pct_1h": 1.0,
            "match_coverage_pct": 95.0,
            "manual_source_pct": 0.0,
            "unmatched_points_pct": 5.0,
            "commissioning_all_gates_passed": 1.0,
            "truth_check_pass_rate_pct": 99.0,
            "consecutive_pass_days": 5.0,
            "mv_accuracy_7d_pct": 80.0,
            "comfort_violation_rate_7d_pct": 3.0,
            "rollback_rate_7d_pct": 2.0,
            "feedback_capture_rate_7d_pct": 95.0,
            "label_lag_p95_hours": 12.0,
            "drift_critical_alerts_24h": 0.0,
        }
        # Set the target metric to a failing value
        policy = QualityGatePolicy()
        threshold = policy.get_metric_threshold(metric, "shadow_live")
        if threshold.direction == "lower_is_better":
            metrics[metric] = 99999.0
        else:
            metrics[metric] = 0.0

        result = eval_with_no_audit.evaluate("shadow_live", metrics)
        assert expected_code in result.reason_codes

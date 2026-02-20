"""Tests for Quality Gate Evaluator — Phase 109.

Tests evaluate(), apply_enforcement(), and enforcement mapping for
all mode x status combinations.
"""

import pytest
from unittest.mock import MagicMock, patch

from app.services.quality_gate_policy import (
    EnforcementAction,
    GateStatus,
    QualityGateResult,
    ReasonCode,
)
from app.services.quality_gate_evaluator import (
    CONFIDENCE_CAP,
    QualityGateEvaluator,
    _ENFORCEMENT_MAP,
    _SIMULATION_DEFAULTS,
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

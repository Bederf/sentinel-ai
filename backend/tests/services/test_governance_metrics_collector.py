"""Tests for GovernanceMetricsCollector — Phase 160-01.

Verifies that governance metric recording methods work correctly
and that all 5 new metric families appear in the Prometheus registry.
"""

import pytest
from prometheus_client import generate_latest

from app.api.metrics import REGISTRY
from app.services.governance_metrics_collector import (
    governance_metrics,
    _normalise_route,
)


class TestGovernanceMetricsCollector:
    """Unit tests for GovernanceMetricsCollector methods."""

    def test_record_quality_gate_rule_increments_counter(self):
        """Calling record_quality_gate_rule increments the counter."""
        from app.api.metrics import sentinel_quality_gate_rule_evaluations_total

        # Get baseline
        before = sentinel_quality_gate_rule_evaluations_total.labels(
            rule_name="freshness_minutes", status="pass"
        )._value.get()

        governance_metrics.record_quality_gate_rule("freshness_minutes", "pass")

        after = sentinel_quality_gate_rule_evaluations_total.labels(
            rule_name="freshness_minutes", status="pass"
        )._value.get()
        assert after == before + 1

    def test_record_quality_gate_rule_invalid_status_defaults_to_fail(self):
        """Invalid status values are normalised to 'fail'."""
        from app.api.metrics import sentinel_quality_gate_rule_evaluations_total

        before = sentinel_quality_gate_rule_evaluations_total.labels(
            rule_name="test_rule_invalid", status="fail"
        )._value.get()

        governance_metrics.record_quality_gate_rule("test_rule_invalid", "bogus")

        after = sentinel_quality_gate_rule_evaluations_total.labels(
            rule_name="test_rule_invalid", status="fail"
        )._value.get()
        assert after == before + 1

    def test_record_drift_score_sets_gauge(self):
        """Calling record_drift_score sets the gauge to the given value."""
        from app.api.metrics import sentinel_model_drift_score

        governance_metrics.record_drift_score("model-001", "CHILLER", 0.7)

        value = sentinel_model_drift_score.labels(model_id="model-001", model_type="CHILLER")._value.get()
        assert value == pytest.approx(0.7, abs=0.001)

    def test_record_drift_score_clamps_value(self):
        """Drift score is clamped to 0.0-1.0 range."""
        from app.api.metrics import sentinel_model_drift_score

        governance_metrics.record_drift_score("model-clamp", "AHU", 1.5)
        value = sentinel_model_drift_score.labels(model_id="model-clamp", model_type="AHU")._value.get()
        assert value == pytest.approx(1.0)

        governance_metrics.record_drift_score("model-clamp-neg", "AHU", -0.3)
        value = sentinel_model_drift_score.labels(model_id="model-clamp-neg", model_type="AHU")._value.get()
        assert value == pytest.approx(0.0)

    def test_record_tool_error_increments_by_type(self):
        """Different error types produce distinct counter increments."""
        from app.api.metrics import sentinel_tool_call_errors_total

        for error_type in ["param_validation", "execution", "timeout", "permission", "module_inactive"]:
            before = sentinel_tool_call_errors_total.labels(tool_name="test_tool", error_type=error_type)._value.get()

            governance_metrics.record_tool_error("test_tool", error_type)

            after = sentinel_tool_call_errors_total.labels(tool_name="test_tool", error_type=error_type)._value.get()
            assert after == before + 1, f"Failed for error_type={error_type}"

    def test_record_approval_latency_observes_histogram(self):
        """Calling record_approval_latency increments the histogram count."""
        from app.api.metrics import sentinel_approval_latency_seconds

        # Observe a value
        governance_metrics.record_approval_latency("S002", "tier2", 45.0)

        # Verify the histogram has at least one sample
        # Access the internal sample count
        sample = sentinel_approval_latency_seconds.labels(site_id="S002", tier="tier2")
        # _sum is the sum of all observations
        assert sample._sum.get() >= 45.0

    def test_record_ai_usage_increments_tokens_and_cost(self):
        """Token and cost counters increment correctly."""
        from app.api.metrics import (
            sentinel_ai_tokens_by_route_total,
            sentinel_ai_cost_by_route_total,
        )

        before_tokens = sentinel_ai_tokens_by_route_total.labels(
            route="chat", site_id="S002", provider="anthropic"
        )._value.get()
        before_cost = sentinel_ai_cost_by_route_total.labels(route="chat", site_id="S002")._value.get()

        governance_metrics.record_ai_usage("chat", "S002", "anthropic", 1000, 0.05)

        after_tokens = sentinel_ai_tokens_by_route_total.labels(
            route="chat", site_id="S002", provider="anthropic"
        )._value.get()
        after_cost = sentinel_ai_cost_by_route_total.labels(route="chat", site_id="S002")._value.get()

        assert after_tokens == before_tokens + 1000
        assert after_cost == pytest.approx(before_cost + 0.05, abs=0.001)

    def test_metrics_best_effort_no_crash(self):
        """Methods handle bad inputs (None, empty, negative) without raising."""
        # None values
        governance_metrics.record_quality_gate_rule(None, None)
        governance_metrics.record_drift_score(None, None, None)
        governance_metrics.record_tool_error(None, None)
        governance_metrics.record_approval_latency(None, None, None)
        governance_metrics.record_approval_rejection(None, None)
        governance_metrics.record_ai_usage(None, None, None, None, None)

        # Empty strings
        governance_metrics.record_quality_gate_rule("", "")
        governance_metrics.record_drift_score("", "", 0.5)
        governance_metrics.record_tool_error("", "")

        # Negative values
        governance_metrics.record_drift_score("neg", "test", -1.0)
        governance_metrics.record_approval_latency("S002", "tier1", -10.0)
        governance_metrics.record_ai_usage("chat", "S002", "anthropic", -100, -0.5)

        # If we get here, no exceptions were raised
        assert True


class TestRouteNormalisation:
    """Test route normalisation logic."""

    def test_direct_mappings(self):
        assert _normalise_route("chat") == "chat"
        assert _normalise_route("chat_response") == "chat"
        assert _normalise_route("tool_call") == "tools"
        assert _normalise_route("tools") == "tools"
        assert _normalise_route("sentry") == "sentry"

    def test_prefix_mappings(self):
        assert _normalise_route("background_task") == "background"
        assert _normalise_route("background_ml") == "background"
        assert _normalise_route("optimization_run") == "optimization"

    def test_fallback_to_other(self):
        assert _normalise_route("unknown_source") == "other"
        assert _normalise_route("") == "other"
        assert _normalise_route(None) == "other"


class TestMetricsEndpointIntegration:
    """Integration tests verifying new metrics appear in Prometheus output."""

    def test_metrics_endpoint_contains_new_families(self):
        """All 5 new Phase 160 metric families appear in generate_latest output."""
        output = generate_latest(REGISTRY).decode("utf-8")

        expected_families = [
            "sentinel_quality_gate_rule_evaluations_total",
            "sentinel_model_drift_score",
            "sentinel_tool_call_errors_total",
            "sentinel_approval_latency_seconds",
            # sentinel_approval_rejection_rate removed — uses sentinel_approval_decisions_total
            "sentinel_ai_tokens_by_route_total",
            "sentinel_ai_cost_by_route_total",
        ]

        for metric_name in expected_families:
            assert f"# HELP {metric_name}" in output, f"Missing metric family in /metrics output: {metric_name}"

    def test_new_metrics_coexist_with_existing(self):
        """New metrics don't break existing metric definitions."""
        output = generate_latest(REGISTRY).decode("utf-8")

        # Existing metrics still present
        existing = [
            "sentinel_quality_gate_evaluations_total",
            "sentinel_recommendations_total",
            "sentinel_tool_calls_total",
            "sentinel_approval_decisions_total",
        ]
        for metric_name in existing:
            assert f"# HELP {metric_name}" in output, (
                f"Existing metric missing after Phase 160 additions: {metric_name}"
            )

"""Tests for /metrics Prometheus endpoint (Phases 125, 127)."""


class TestMetricsEndpoint:
    """Verify /metrics returns all expected metric families."""

    def test_metrics_returns_prometheus_format(self):
        """Endpoint returns text/plain with Prometheus exposition format."""
        from app.api.metrics import REGISTRY, generate_latest

        output = generate_latest(REGISTRY).decode("utf-8")
        assert "# HELP" in output
        assert "# TYPE" in output

    def test_all_governance_metrics_present(self):
        """All 8 original AI governance metrics are registered."""
        from app.api.metrics import REGISTRY, generate_latest

        output = generate_latest(REGISTRY).decode("utf-8")

        expected_metrics = [
            "sentinel_quality_gate_evaluations_total",
            "sentinel_quality_gate_enforcement",
            "sentinel_recommendations_total",
            "sentinel_approval_decisions_total",
            "sentinel_safety_violations_total",
            "sentinel_model_drift_alerts",
            "sentinel_rollback_total",
            "sentinel_info",
        ]

        for metric in expected_metrics:
            assert f"# HELP {metric}" in output, f"Missing metric: {metric}"

    def test_http_request_metrics_present(self):
        """Phase 127 HTTP request metrics are registered."""
        from app.api.metrics import REGISTRY, generate_latest

        output = generate_latest(REGISTRY).decode("utf-8")

        expected = [
            "sentinel_http_requests_total",
            "sentinel_http_request_duration_seconds",
            "sentinel_http_requests_in_progress",
        ]

        for metric in expected:
            assert f"# HELP {metric}" in output, f"Missing metric: {metric}"

    def test_tool_call_metrics_present(self):
        """Phase 127 tool call metrics are registered."""
        from app.api.metrics import REGISTRY, generate_latest

        output = generate_latest(REGISTRY).decode("utf-8")

        expected = [
            "sentinel_tool_calls_total",
            "sentinel_tool_call_duration_seconds",
        ]

        for metric in expected:
            assert f"# HELP {metric}" in output, f"Missing metric: {metric}"

    def test_database_cache_metrics_present(self):
        """Phase 125 database and cache metrics are registered."""
        from app.api.metrics import REGISTRY, generate_latest

        output = generate_latest(REGISTRY).decode("utf-8")

        expected = [
            "sentinel_db_query_duration_seconds",
            "sentinel_cache_operations_total",
            "sentinel_cache_hit_rate_percent",
        ]

        for metric in expected:
            assert f"# HELP {metric}" in output, f"Missing metric: {metric}"

    def test_total_metric_count(self):
        """At least 16 metric families registered (excludes _created auto-generated)."""
        from app.api.metrics import REGISTRY, generate_latest

        output = generate_latest(REGISTRY).decode("utf-8")
        # Filter out _created auto-generated metrics from prometheus_client
        families = [
            line for line in output.split("\n") if line.startswith("# HELP sentinel_") and "_created " not in line
        ]
        assert len(families) >= 16, f"Expected >=16 metric families, got {len(families)}: {families}"

    def test_ip_allowlist_blocks_external(self):
        """Metrics endpoint blocks non-local IPs."""
        from app.api.metrics import _is_allowed

        assert _is_allowed("127.0.0.1") is True
        assert _is_allowed("10.0.0.5") is True
        assert _is_allowed("192.168.1.1") is True
        assert _is_allowed("8.8.8.8") is False
        assert _is_allowed("203.0.113.1") is False

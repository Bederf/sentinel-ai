"""Tests for /metrics Prometheus endpoint (Phases 125, 127, 168-01).

Phase 168-01: Adds authentication tests for MONITORING-001 gap closure.
Gap 6 (MEDIUM): /metrics endpoint unauthenticated → add AuthLevel.AUTHENTICATED guard.
"""

import os

os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret-for-ci-at-least-32-chars")


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


class TestMetricsAuthenticationGateway:
    """Test Phase 168-01: Authentication gateway on /metrics endpoint.

    Gap 6 (MEDIUM): /metrics endpoint unauthenticated.
    Control: MONITORING-001 (Prometheus Metrics).
    """

    def test_metrics_endpoint_requires_auth(self):
        """GET /metrics without auth should return 401."""
        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app)
        response = client.get("/metrics")

        # Without credentials, should get 401
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"

    def test_metrics_endpoint_with_valid_auditor_token(self):
        """GET /metrics with valid AUDITOR token should return 200."""
        from fastapi.testclient import TestClient

        from app.main import app
        from app.middleware.auth_middleware import create_jwt_token
        from app.models.auth import SentinelRole

        client = TestClient(app)

        # Create a valid AUDITOR token
        token = create_jwt_token(
            user_id="test-auditor",
            email="auditor@example.com",
            role=SentinelRole.AUDITOR.value,
            full_name="Test Auditor",
        )

        response = client.get("/metrics", headers={"Authorization": f"Bearer {token}"})

        # With valid AUDITOR token, should return 200
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert "sentinel_" in response.text

    def test_metrics_endpoint_with_valid_admin_token(self):
        """GET /metrics with valid ADMIN token should return 200."""
        from fastapi.testclient import TestClient

        from app.main import app
        from app.middleware.auth_middleware import create_jwt_token
        from app.models.auth import SentinelRole

        client = TestClient(app)

        # Create a valid ADMIN token
        token = create_jwt_token(
            user_id="test-admin",
            email="admin@example.com",
            role=SentinelRole.ADMIN.value,
            full_name="Test Admin",
        )

        response = client.get("/metrics", headers={"Authorization": f"Bearer {token}"})

        # With valid ADMIN token, should return 200
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert "sentinel_" in response.text

    def test_metrics_endpoint_with_invalid_token(self):
        """GET /metrics with invalid token should return 401."""
        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app)

        response = client.get("/metrics", headers={"Authorization": "Bearer invalid.token.here"})

        # Invalid token should return 401
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"

    def test_metrics_endpoint_with_operator_token(self):
        """GET /metrics with OPERATOR token should return 200 (OPERATOR >= AUDITOR in auth)."""
        from fastapi.testclient import TestClient

        from app.main import app
        from app.middleware.auth_middleware import create_jwt_token
        from app.models.auth import SentinelRole

        client = TestClient(app)

        # Create a valid OPERATOR token
        token = create_jwt_token(
            user_id="test-operator",
            email="operator@example.com",
            role=SentinelRole.OPERATOR.value,
            full_name="Test Operator",
        )

        response = client.get("/metrics", headers={"Authorization": f"Bearer {token}"})

        # OPERATOR should have access (higher privilege than AUDITOR)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert "sentinel_" in response.text

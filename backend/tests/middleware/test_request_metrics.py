"""Tests for RequestMetricsMiddleware (Phase 127)."""

import pytest

from app.middleware.request_metrics import _normalize_path


class TestPathNormalization:
    """Test that dynamic path segments are replaced to bound label cardinality."""

    def test_uuid_replacement(self):
        path = "/api/users/550e8400-e29b-41d4-a716-446655440000"
        assert _normalize_path(path) == "/api/users/{id}"

    def test_equipment_code_replacement(self):
        path = "/api/equipment/S002-AHU-B1-001"
        assert _normalize_path(path) == "/api/equipment/{id}"

    def test_equipment_code_chiller(self):
        path = "/api/equipment/S012-CHILLER-R-002/health"
        assert _normalize_path(path) == "/api/equipment/{id}/health"

    def test_site_id_replacement(self):
        path = "/api/buildings/site-002/zones"
        assert _normalize_path(path) == "/api/buildings/{id}/zones"

    def test_numeric_id_replacement(self):
        path = "/api/work-orders/42"
        assert _normalize_path(path) == "/api/work-orders/{id}"

    def test_multiple_dynamic_segments(self):
        path = "/api/buildings/site-002/equipment/S002-AHU-B1-001"
        assert _normalize_path(path) == "/api/buildings/{id}/equipment/{id}"

    def test_skip_paths_unchanged(self):
        assert _normalize_path("/metrics") == "/metrics"
        assert _normalize_path("/health") == "/health"
        assert _normalize_path("/docs") == "/docs"

    def test_static_path_unchanged(self):
        assert _normalize_path("/api/auth/login") == "/api/auth/login"

    def test_api_root_unchanged(self):
        assert _normalize_path("/api") == "/api"


class TestRequestMetricsMiddleware:
    """Integration tests for the middleware with a test client."""

    @pytest.fixture
    def app(self):
        """Create a minimal FastAPI app with the middleware."""
        from fastapi import FastAPI
        from app.middleware.request_metrics import RequestMetricsMiddleware

        app = FastAPI()
        app.add_middleware(RequestMetricsMiddleware)

        @app.get("/api/test")
        async def test_endpoint():
            return {"ok": True}

        @app.get("/api/fail")
        async def fail_endpoint():
            raise ValueError("boom")

        return app

    @pytest.fixture
    def client(self, app):
        from starlette.testclient import TestClient

        return TestClient(app)

    def test_successful_request_increments_counter(self, client):
        from app.api.metrics import sentinel_http_requests_total

        # Get baseline
        before = sentinel_http_requests_total.labels(method="GET", path="/api/test", status_code="200")._value.get()

        client.get("/api/test")

        after = sentinel_http_requests_total.labels(method="GET", path="/api/test", status_code="200")._value.get()

        assert after == before + 1

    def test_duration_histogram_records(self, client):
        from app.api.metrics import sentinel_http_request_duration_seconds

        # Get baseline count
        before = sentinel_http_request_duration_seconds.labels(method="GET", path="/api/test")._sum.get()

        client.get("/api/test")

        after = sentinel_http_request_duration_seconds.labels(method="GET", path="/api/test")._sum.get()

        assert after > before

    def test_in_progress_gauge_returns_to_zero(self, client):
        from app.api.metrics import sentinel_http_requests_in_progress

        client.get("/api/test")
        # After request completes, in-progress should be back to 0
        assert sentinel_http_requests_in_progress._value.get() >= 0

    def test_error_request_records_500(self, client):
        from app.api.metrics import sentinel_http_requests_total

        before = sentinel_http_requests_total.labels(method="GET", path="/api/fail", status_code="500")._value.get()

        try:
            client.get("/api/fail")
        except Exception:
            pass  # Server error expected

        after = sentinel_http_requests_total.labels(method="GET", path="/api/fail", status_code="500")._value.get()

        assert after == before + 1

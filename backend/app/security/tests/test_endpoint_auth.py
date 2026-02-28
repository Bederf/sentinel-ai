"""
Tests for endpoint-level RBAC enforcement.

Validates that:
- RAG endpoints require authentication (were previously zero auth)
- Control endpoints require OPERATOR role (level 2)
- Settings PUT endpoints require ADMIN role (level 4)
- Chat endpoint requires AUDITOR role (level 1)
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.models.auth import AuthContext, SentinelRole


def _make_auth_ctx(
    role: SentinelRole = SentinelRole.AUDITOR,
    user_id: str = "test-user",
    email: str = "test@example.com",
) -> AuthContext:
    """Create an AuthContext for testing."""
    return AuthContext(
        user_id=user_id,
        role=role,
        auth_method="test",
        source_ip="127.0.0.1",
        email=email,
        scopes=[],
    )


# ---------------------------------------------------------------------------
# Helper: get the main app's TestClient in non-demo mode
# ---------------------------------------------------------------------------


def _get_test_client():
    """Import and return a TestClient for the main app."""
    # Import inside function to avoid circular imports at module level
    from app.main import app

    return TestClient(app)


# ---------------------------------------------------------------------------
# RAG endpoints require auth
# ---------------------------------------------------------------------------


class TestRagEndpointsRequireAuth:
    """All /api/rag/* endpoints return 401 without auth."""

    @patch("app.security.pipeline.settings")
    @patch("app.security.pipeline._authenticate_request")
    def test_rag_query_requires_auth(self, mock_auth, mock_settings):
        """POST /api/rag/query returns 401 without auth."""
        mock_settings.demo_mode = False
        mock_settings.environment = "development"
        mock_auth.return_value = None

        client = _get_test_client()
        response = client.post("/api/rag/query", json={"query": "test"})
        assert response.status_code == 401

    @patch("app.security.pipeline.settings")
    @patch("app.security.pipeline._authenticate_request")
    def test_rag_search_requires_auth(self, mock_auth, mock_settings):
        """GET /api/rag/search returns 401 without auth."""
        mock_settings.demo_mode = False
        mock_settings.environment = "development"
        mock_auth.return_value = None

        client = _get_test_client()
        response = client.get("/api/rag/search?query=test")
        assert response.status_code == 401

    @patch("app.security.pipeline.settings")
    @patch("app.security.pipeline._authenticate_request")
    def test_rag_search_knowledge_requires_auth(self, mock_auth, mock_settings):
        """GET /api/rag/search/knowledge returns 401 without auth."""
        mock_settings.demo_mode = False
        mock_settings.environment = "development"
        mock_auth.return_value = None

        client = _get_test_client()
        response = client.get("/api/rag/search/knowledge?query=test")
        assert response.status_code == 401

    @patch("app.security.pipeline.settings")
    @patch("app.security.pipeline._authenticate_request")
    def test_rag_documents_requires_auth(self, mock_auth, mock_settings):
        """GET /api/rag/documents returns 401 without auth."""
        mock_settings.demo_mode = False
        mock_settings.environment = "development"
        mock_auth.return_value = None

        client = _get_test_client()
        response = client.get("/api/rag/documents")
        assert response.status_code == 401

    @patch("app.security.pipeline.settings")
    @patch("app.security.pipeline._authenticate_request")
    def test_rag_add_document_requires_auth(self, mock_auth, mock_settings):
        """POST /api/rag/documents returns 401 without auth."""
        mock_settings.demo_mode = False
        mock_settings.environment = "development"
        mock_auth.return_value = None

        client = _get_test_client()
        response = client.post(
            "/api/rag/documents",
            json={
                "code": "DOC-001",
                "title": "Test",
                "document_type": "manual",
                "equipment_type": "chiller",
                "full_text": "test content",
            },
        )
        assert response.status_code == 401

    @patch("app.security.pipeline.settings")
    @patch("app.security.pipeline._authenticate_request")
    def test_rag_health_no_auth_required(self, mock_auth, mock_settings):
        """GET /api/rag/health does NOT require auth (health check)."""
        mock_settings.demo_mode = False
        mock_settings.environment = "development"
        mock_auth.return_value = None

        client = _get_test_client()
        response = client.get("/api/rag/health")
        # Health endpoint should NOT return 401 (it has no auth requirement)
        assert response.status_code != 401


# ---------------------------------------------------------------------------
# Control endpoints require OPERATOR
# ---------------------------------------------------------------------------


class TestControlEndpointsRequireOperator:
    """Control endpoints return 403 for AUDITOR role."""

    @patch("app.security.pipeline.settings")
    @patch("app.security.pipeline._authenticate_request")
    def test_device_control_blocked_for_auditor(self, mock_auth, mock_settings):
        """POST /devices/{id}/control returns 403 for AUDITOR."""
        mock_settings.demo_mode = False
        mock_settings.environment = "development"
        mock_auth.return_value = _make_auth_ctx(SentinelRole.AUDITOR)

        client = _get_test_client()
        response = client.post(
            "/api/devices/test-device/control",
            json={"point": "temperature_sp", "value": 22.5},
        )
        assert response.status_code == 403

    @patch("app.security.pipeline.settings")
    @patch("app.security.pipeline._authenticate_request")
    def test_device_scan_blocked_for_auditor(self, mock_auth, mock_settings):
        """POST /api/devices/{id}/scan returns 403 for AUDITOR."""
        mock_settings.demo_mode = False
        mock_settings.environment = "development"
        mock_auth.return_value = _make_auth_ctx(SentinelRole.AUDITOR)

        client = _get_test_client()
        response = client.post("/api/devices/test-device/scan")
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Settings PUT endpoints require ADMIN
# ---------------------------------------------------------------------------


class TestSettingsEndpointsRequireAdmin:
    """Settings PUT endpoints return 403 for non-ADMIN roles."""

    @patch("app.security.pipeline.settings")
    @patch("app.security.pipeline._authenticate_request")
    def test_settings_put_blocked_for_operator(self, mock_auth, mock_settings):
        """PUT /settings returns 403 for OPERATOR."""
        mock_settings.demo_mode = False
        mock_settings.environment = "development"
        mock_auth.return_value = _make_auth_ctx(SentinelRole.OPERATOR)

        client = _get_test_client()
        response = client.put("/api/settings", json={"healthThresholds": {"healthy": 90, "warning": 70, "critical": 0}})
        assert response.status_code == 403

    @patch("app.security.pipeline.settings")
    @patch("app.security.pipeline._authenticate_request")
    def test_settings_get_allowed_for_auditor(self, mock_auth, mock_settings):
        """GET /api/settings returns 200 for AUDITOR."""
        mock_settings.demo_mode = False
        mock_settings.environment = "development"
        mock_auth.return_value = _make_auth_ctx(SentinelRole.AUDITOR)

        client = _get_test_client()
        response = client.get("/api/settings")
        assert response.status_code == 200

    @patch("app.security.pipeline.settings")
    @patch("app.security.pipeline._authenticate_request")
    def test_settings_put_requires_auth(self, mock_auth, mock_settings):
        """PUT /api/settings returns 401 without auth."""
        mock_settings.demo_mode = False
        mock_settings.environment = "development"
        mock_auth.return_value = None

        client = _get_test_client()
        response = client.put("/api/settings", json={"healthThresholds": {"healthy": 90, "warning": 70, "critical": 0}})
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Chat endpoint requires AUDITOR
# ---------------------------------------------------------------------------


class TestChatEndpointRequiresAuth:
    """Chat endpoint requires authentication."""

    @patch("app.security.pipeline.settings")
    @patch("app.security.pipeline._authenticate_request")
    def test_chat_requires_auth(self, mock_auth, mock_settings):
        """POST /chat returns 401 without auth."""
        mock_settings.demo_mode = False
        mock_settings.environment = "development"
        mock_auth.return_value = None

        client = _get_test_client()
        response = client.post("/api/chat", json={"message": "Hello"})
        assert response.status_code == 401

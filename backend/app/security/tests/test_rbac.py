"""
Tests for RBAC dependencies (require_role, require_site_access).

Validates numeric level-based role checks and site-scoped authorization.
"""

import json
from unittest.mock import patch

from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from app.models.auth import AuthContext, SentinelRole
from app.security.constants import ROLE_LEVELS
from app.security.pipeline import (
    require_role,
    require_site_access,
    _get_user_role_level,
    _check_site_access,
    clear_site_access_cache,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


def _create_test_app_with_role(min_level: int) -> FastAPI:
    """Create a minimal FastAPI app with a role-gated endpoint."""
    app = FastAPI()

    @app.get("/protected")
    async def protected_endpoint(auth: AuthContext = Depends(require_role(min_level))):
        return {"user": auth.user_id, "role": auth.role.value}

    return app


def _create_test_app_with_site_access() -> FastAPI:
    """Create a minimal FastAPI app with a site-access-gated endpoint."""
    app = FastAPI()

    @app.get("/sites/{site_id}/data")
    async def site_endpoint(
        site_id: str,
        auth: AuthContext = Depends(require_site_access("site_id")),
    ):
        return {"user": auth.user_id, "site": site_id}

    return app


# ---------------------------------------------------------------------------
# Test _get_user_role_level
# ---------------------------------------------------------------------------


class TestGetUserRoleLevel:
    """Tests for _get_user_role_level helper."""

    def test_admin_level(self):
        ctx = _make_auth_ctx(SentinelRole.ADMIN)
        assert _get_user_role_level(ctx) == 4

    def test_operator_level(self):
        ctx = _make_auth_ctx(SentinelRole.OPERATOR)
        assert _get_user_role_level(ctx) == 2

    def test_auditor_level(self):
        ctx = _make_auth_ctx(SentinelRole.AUDITOR)
        assert _get_user_role_level(ctx) == 1

    def test_developer_level(self):
        ctx = _make_auth_ctx(SentinelRole.DEVELOPER)
        assert _get_user_role_level(ctx) == 3

    def test_bot_agent_level(self):
        ctx = _make_auth_ctx(SentinelRole.BOT_AGENT)
        assert _get_user_role_level(ctx) == 1

    def test_levels_match_constants(self):
        """Verify _get_user_role_level is consistent with ROLE_LEVELS dict."""
        for role in SentinelRole:
            ctx = _make_auth_ctx(role)
            expected = ROLE_LEVELS.get(role.value.lower(), 0)
            assert _get_user_role_level(ctx) == expected


# ---------------------------------------------------------------------------
# Test require_role
# ---------------------------------------------------------------------------


class TestRequireRole:
    """Tests for require_role dependency."""

    @patch("app.security.pipeline.settings")
    @patch("app.security.pipeline._authenticate_request")
    def test_require_role_blocks_insufficient(self, mock_auth, mock_settings):
        """AUDITOR (level 1) blocked from ADMIN-only endpoint (level 4)."""
        mock_settings.demo_mode = False
        mock_settings.environment = "development"
        mock_auth.return_value = _make_auth_ctx(SentinelRole.AUDITOR)

        app = _create_test_app_with_role(min_level=4)
        client = TestClient(app)
        response = client.get("/protected", headers={"Authorization": "Bearer test-token"})

        assert response.status_code == 403
        assert "Insufficient role level" in response.json()["detail"]

    @patch("app.security.pipeline.settings")
    @patch("app.security.pipeline._authenticate_request")
    def test_require_role_allows_sufficient(self, mock_auth, mock_settings):
        """ADMIN (level 4) can access ADMIN-level endpoint."""
        mock_settings.demo_mode = False
        mock_settings.environment = "development"
        mock_auth.return_value = _make_auth_ctx(SentinelRole.ADMIN)

        app = _create_test_app_with_role(min_level=4)
        client = TestClient(app)
        response = client.get("/protected", headers={"Authorization": "Bearer test-token"})

        assert response.status_code == 200
        assert response.json()["role"] == "admin"

    @patch("app.security.pipeline.settings")
    @patch("app.security.pipeline._authenticate_request")
    def test_require_role_allows_higher_than_min(self, mock_auth, mock_settings):
        """ADMIN (level 4) can access OPERATOR-level (level 2) endpoint."""
        mock_settings.demo_mode = False
        mock_settings.environment = "development"
        mock_auth.return_value = _make_auth_ctx(SentinelRole.ADMIN)

        app = _create_test_app_with_role(min_level=2)
        client = TestClient(app)
        response = client.get("/protected", headers={"Authorization": "Bearer test-token"})

        assert response.status_code == 200
        assert response.json()["role"] == "admin"

    @patch("app.security.pipeline.settings")
    @patch("app.security.pipeline._authenticate_request")
    def test_require_role_operator_blocked_from_admin(self, mock_auth, mock_settings):
        """OPERATOR (level 2) blocked from ADMIN-level (level 4) endpoint."""
        mock_settings.demo_mode = False
        mock_settings.environment = "development"
        mock_auth.return_value = _make_auth_ctx(SentinelRole.OPERATOR)

        app = _create_test_app_with_role(min_level=4)
        client = TestClient(app)
        response = client.get("/protected", headers={"Authorization": "Bearer test-token"})

        assert response.status_code == 403

    @patch("app.security.pipeline.settings")
    @patch("app.security.pipeline._authenticate_request")
    def test_require_role_returns_401_no_auth(self, mock_auth, mock_settings):
        """No credentials returns 401."""
        mock_settings.demo_mode = False
        mock_settings.environment = "development"
        mock_auth.return_value = None

        app = _create_test_app_with_role(min_level=1)
        client = TestClient(app)
        response = client.get("/protected")

        assert response.status_code == 401

    @patch("app.security.pipeline.settings")
    @patch("app.security.pipeline._authenticate_request")
    def test_require_role_exact_level_passes(self, mock_auth, mock_settings):
        """OPERATOR (level 2) passes operator-level (level 2) check."""
        mock_settings.demo_mode = False
        mock_settings.environment = "development"
        mock_auth.return_value = _make_auth_ctx(SentinelRole.OPERATOR)

        app = _create_test_app_with_role(min_level=2)
        client = TestClient(app)
        response = client.get("/protected", headers={"Authorization": "Bearer test-token"})

        assert response.status_code == 200
        assert response.json()["role"] == "operator"

    @patch("app.security.pipeline.settings")
    def test_demo_mode_no_longer_grants_auto_auth(self, mock_settings):
        """Demo mode no longer grants automatic auth — unauthenticated requests get 401."""
        mock_settings.demo_mode = True
        mock_settings.environment = "development"

        app = _create_test_app_with_role(min_level=2)
        client = TestClient(app)
        response = client.get("/protected")
        # Without a token, should get 401 even with demo_mode=True
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Test require_site_access
# ---------------------------------------------------------------------------


class TestRequireSiteAccess:
    """Tests for require_site_access dependency."""

    @patch("app.security.pipeline.settings")
    @patch("app.security.pipeline._authenticate_request")
    def test_site_access_admin_all_sites(self, mock_auth, mock_settings):
        """ADMIN can access any site."""
        mock_settings.demo_mode = False
        mock_settings.environment = "development"
        mock_auth.return_value = _make_auth_ctx(SentinelRole.ADMIN)

        app = _create_test_app_with_site_access()
        client = TestClient(app)
        response = client.get(
            "/sites/site-999/data",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        assert response.json()["site"] == "site-999"

    @patch("app.security.pipeline._check_site_access")
    @patch("app.security.pipeline.settings")
    @patch("app.security.pipeline._authenticate_request")
    def test_site_access_operator_only_authorized(self, mock_auth, mock_settings, mock_check):
        """OPERATOR denied for unauthorized site."""
        mock_settings.demo_mode = False
        mock_settings.environment = "development"
        mock_auth.return_value = _make_auth_ctx(SentinelRole.OPERATOR)
        mock_check.return_value = False

        app = _create_test_app_with_site_access()
        client = TestClient(app)
        response = client.get(
            "/sites/site-999/data",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 403
        assert "Not authorized for site" in response.json()["detail"]

    @patch("app.security.pipeline._check_site_access")
    @patch("app.security.pipeline.settings")
    @patch("app.security.pipeline._authenticate_request")
    def test_site_access_operator_authorized_site(self, mock_auth, mock_settings, mock_check):
        """OPERATOR allowed for authorized site."""
        mock_settings.demo_mode = False
        mock_settings.environment = "development"
        mock_auth.return_value = _make_auth_ctx(SentinelRole.OPERATOR)
        mock_check.return_value = True

        app = _create_test_app_with_site_access()
        client = TestClient(app)
        response = client.get(
            "/sites/site-002/data",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        assert response.json()["site"] == "site-002"

    @patch("app.security.pipeline.settings")
    @patch("app.security.pipeline._authenticate_request")
    def test_site_access_returns_401_no_auth(self, mock_auth, mock_settings):
        """No credentials returns 401."""
        mock_settings.demo_mode = False
        mock_settings.environment = "development"
        mock_auth.return_value = None

        app = _create_test_app_with_site_access()
        client = TestClient(app)
        response = client.get("/sites/site-002/data")

        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Test _check_site_access with JSON fallback
# ---------------------------------------------------------------------------


class TestCheckSiteAccessJsonFallback:
    """Tests for _check_site_access using JSON config fallback."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_site_access_cache()

    def test_json_config_grants_access(self, tmp_path):
        """User in JSON config gets access to listed site."""
        config_file = tmp_path / "site_access_config.json"
        config_file.write_text(
            json.dumps(
                {
                    "operator@example.com": ["site-002", "site-003"],
                }
            )
        )

        clear_site_access_cache()

        # Patch the module-level path and force Supabase to fail
        with patch("app.security.pipeline._SITE_ACCESS_CONFIG_PATH", config_file):
            with patch(
                "app.database.repositories.user_site_access_repository.get_user_site_access_repository",
                side_effect=Exception("No DB"),
            ):
                ctx = _make_auth_ctx(SentinelRole.OPERATOR, email="operator@example.com")
                assert _check_site_access(ctx, "site-002") is True

        clear_site_access_cache()

    def test_json_config_denies_unlisted_site(self, tmp_path):
        """User not in JSON config for site is denied."""
        config_file = tmp_path / "site_access_config.json"
        config_file.write_text(
            json.dumps(
                {
                    "operator@example.com": ["site-002"],
                }
            )
        )

        clear_site_access_cache()

        with patch("app.security.pipeline._SITE_ACCESS_CONFIG_PATH", config_file):
            with patch(
                "app.database.repositories.user_site_access_repository.get_user_site_access_repository",
                side_effect=Exception("No DB"),
            ):
                ctx = _make_auth_ctx(SentinelRole.OPERATOR, email="operator@example.com")
                assert _check_site_access(ctx, "site-999") is False

        clear_site_access_cache()

    def test_json_config_unknown_user_denied(self, tmp_path):
        """Unknown user gets no access."""
        config_file = tmp_path / "site_access_config.json"
        config_file.write_text(
            json.dumps(
                {
                    "operator@example.com": ["site-002"],
                }
            )
        )

        clear_site_access_cache()

        with patch("app.security.pipeline._SITE_ACCESS_CONFIG_PATH", config_file):
            with patch(
                "app.database.repositories.user_site_access_repository.get_user_site_access_repository",
                side_effect=Exception("No DB"),
            ):
                ctx = _make_auth_ctx(SentinelRole.OPERATOR, email="unknown@example.com")
                assert _check_site_access(ctx, "site-002") is False

        clear_site_access_cache()

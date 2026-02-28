"""
Tests for DEMO_MODE hardening (Phase 137-02).

Validates that DEMO_MODE grants OPERATOR role (level 2), never ADMIN (level 4),
and that security features remain active in demo mode.
"""

import pytest
from unittest.mock import MagicMock, patch

from app.models.auth import SentinelRole, ROLE_HIERARCHY, AuthLevel


class TestDemoModeGrantsOperator:
    """DEMO_MODE session should have OPERATOR role, not ADMIN."""

    @pytest.mark.asyncio
    async def test_require_auth_demo_mode_grants_operator(self):
        """require_auth() in demo mode creates context with OPERATOR role."""
        from app.middleware.auth_middleware import require_auth

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.url.path = "/api/test"
        mock_request.state = MagicMock()

        with patch("app.middleware.auth_middleware.settings") as mock_settings:
            mock_settings.demo_mode = True
            mock_settings.environment = "development"
            mock_settings.demo_allowed_origins = []
            mock_settings.cors_origins = []

            dependency = require_auth(AuthLevel.AUTHENTICATED)
            ctx = await dependency(mock_request)

            assert ctx.role == SentinelRole.OPERATOR
            assert ctx.role != SentinelRole.ADMIN
            assert ctx.auth_method == "demo_mode"

    @pytest.mark.asyncio
    async def test_require_role_demo_mode_caps_at_operator(self):
        """require_role() in demo mode caps role at OPERATOR even when ADMIN requested."""
        from app.middleware.auth_middleware import require_role

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.url.path = "/api/admin/test"
        mock_request.state = MagicMock()

        with patch("app.middleware.auth_middleware.settings") as mock_settings:
            mock_settings.demo_mode = True
            mock_settings.environment = "development"
            mock_settings.demo_allowed_origins = []
            mock_settings.cors_origins = []

            dependency = require_role(SentinelRole.ADMIN)
            ctx = await dependency(mock_request)

            # Even though ADMIN was requested, demo mode caps at OPERATOR
            assert ctx.role == SentinelRole.OPERATOR
            assert ROLE_HIERARCHY[ctx.role] <= ROLE_HIERARCHY[SentinelRole.OPERATOR]

    @pytest.mark.asyncio
    async def test_require_role_demo_mode_allows_lower_roles(self):
        """require_role() in demo mode grants requested role if at or below OPERATOR."""
        from app.middleware.auth_middleware import require_role

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.url.path = "/api/read/test"
        mock_request.state = MagicMock()

        with patch("app.middleware.auth_middleware.settings") as mock_settings:
            mock_settings.demo_mode = True
            mock_settings.environment = "development"
            mock_settings.demo_allowed_origins = []
            mock_settings.cors_origins = []

            dependency = require_role(SentinelRole.AUDITOR)
            ctx = await dependency(mock_request)

            # AUDITOR is below OPERATOR, so it should be granted as-is
            assert ctx.role == SentinelRole.AUDITOR


class TestDemoModeDoesNotBypassSecurity:
    """Audit logging and security features run even in DEMO_MODE."""

    @pytest.mark.asyncio
    async def test_demo_mode_sets_auth_on_request_state(self):
        """Demo mode still attaches auth context to request.state for audit."""
        from app.middleware.auth_middleware import require_auth

        class FakeState:
            auth = None

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.url.path = "/api/test"
        mock_request.state = FakeState()

        with patch("app.middleware.auth_middleware.settings") as mock_settings:
            mock_settings.demo_mode = True
            mock_settings.environment = "development"
            mock_settings.demo_allowed_origins = []
            mock_settings.cors_origins = []

            dependency = require_auth(AuthLevel.AUTHENTICATED)
            ctx = await dependency(mock_request)

            # Auth context is attached to request.state (required for audit middleware)
            assert mock_request.state.auth is not None
            assert mock_request.state.auth.user_id == "demo-user"
            assert ctx.user_id == "demo-user"
            assert ctx.source_ip is not None

    @pytest.mark.asyncio
    async def test_demo_mode_metadata_flags_demo(self):
        """Demo mode context includes demo_mode flag in metadata for audit trail."""
        from app.middleware.auth_middleware import require_auth

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.url.path = "/api/test"
        mock_request.state = MagicMock()

        with patch("app.middleware.auth_middleware.settings") as mock_settings:
            mock_settings.demo_mode = True
            mock_settings.environment = "development"
            mock_settings.demo_allowed_origins = []
            mock_settings.cors_origins = []

            dependency = require_auth(AuthLevel.AUTHENTICATED)
            ctx = await dependency(mock_request)

            assert ctx.metadata.get("demo_mode") is True


class TestDemoModeProductionGuard:
    """DEMO_MODE + ENVIRONMENT=production raises RuntimeError."""

    @pytest.mark.asyncio
    async def test_require_auth_blocks_demo_in_production(self):
        """require_auth() raises 503 when DEMO_MODE=true and ENVIRONMENT=production."""
        from fastapi import HTTPException
        from app.middleware.auth_middleware import require_auth

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.url.path = "/api/test"

        with patch("app.middleware.auth_middleware.settings") as mock_settings:
            mock_settings.demo_mode = True
            mock_settings.environment = "production"

            dependency = require_auth(AuthLevel.AUTHENTICATED)
            with pytest.raises(HTTPException) as exc_info:
                await dependency(mock_request)

            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_require_role_blocks_demo_in_production(self):
        """require_role() raises 503 when DEMO_MODE=true and ENVIRONMENT=production."""
        from fastapi import HTTPException
        from app.middleware.auth_middleware import require_role

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.url.path = "/api/test"

        with patch("app.middleware.auth_middleware.settings") as mock_settings:
            mock_settings.demo_mode = True
            mock_settings.environment = "production"

            dependency = require_role(SentinelRole.OPERATOR)
            with pytest.raises(HTTPException) as exc_info:
                await dependency(mock_request)

            assert exc_info.value.status_code == 503

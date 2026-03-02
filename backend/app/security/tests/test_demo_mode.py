"""
Tests verifying that DEMO_MODE no longer grants auth bypasses.

After the demo-auth removal, setting DEMO_MODE=true should have no effect
on authentication — all requests must carry valid JWT tokens.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException

from app.models.auth import SentinelRole, AuthLevel


class TestDemoModeNoBypass:
    """DEMO_MODE=true must NOT grant automatic auth context."""

    @pytest.mark.asyncio
    async def test_require_auth_rejects_unauthenticated_even_with_demo_mode(self):
        """require_auth() rejects requests without a valid token, even if demo_mode=True."""
        from app.middleware.auth_middleware import require_auth

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.query_params = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.url.path = "/api/test"
        mock_request.state = MagicMock(spec=[])

        with patch("app.middleware.auth_middleware.settings") as mock_settings:
            mock_settings.demo_mode = True
            mock_settings.environment = "development"

            with patch("app.middleware.auth_middleware._authenticate_request", new_callable=AsyncMock) as mock_auth:
                mock_auth.return_value = None  # No valid credentials

                dependency = require_auth(AuthLevel.AUTHENTICATED)
                with pytest.raises(HTTPException) as exc_info:
                    await dependency(mock_request)

                assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_require_role_rejects_unauthenticated_even_with_demo_mode(self):
        """require_role() rejects unauthenticated requests even if demo_mode=True."""
        from app.middleware.auth_middleware import require_role

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.query_params = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.url.path = "/api/admin/test"
        mock_request.state = MagicMock(spec=[])

        with patch("app.middleware.auth_middleware.settings") as mock_settings:
            mock_settings.demo_mode = True
            mock_settings.environment = "development"

            with patch("app.middleware.auth_middleware._authenticate_request", new_callable=AsyncMock) as mock_auth:
                mock_auth.return_value = None

                dependency = require_role(SentinelRole.OPERATOR)
                with pytest.raises(HTTPException) as exc_info:
                    await dependency(mock_request)

                assert exc_info.value.status_code == 401


class TestNoHardcodedDemoUsers:
    """Verify _DEMO_USERS dict no longer exists in auth.py."""

    def test_no_demo_users_dict_in_auth(self):
        """auth.py should not export _DEMO_USERS."""
        import app.api.auth as auth_module

        assert not hasattr(auth_module, "_DEMO_USERS"), "_DEMO_USERS still exists in auth.py"

    def test_no_demo_users_dict_in_remote_ops(self):
        """remote_ops.py should not export _DEMO_USERS."""
        import app.api.remote_ops as remote_ops_module

        assert not hasattr(remote_ops_module, "_DEMO_USERS"), "_DEMO_USERS still exists in remote_ops.py"

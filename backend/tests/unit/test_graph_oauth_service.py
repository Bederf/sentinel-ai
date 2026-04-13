"""Unit tests for graph_oauth_service.py (Phase 184-01-02, Section C).

Tests:
1. Token acquisition calls MSAL and returns token
2. Token caching — second call uses cache (no MSAL call)
3. Token expiry — msal failure returns None
4. Concurrent calls — asyncio.Lock prevents duplicate acquisition
5. Startup validation — correct env var presence check
"""

from __future__ import annotations

import os
import time
from unittest.mock import MagicMock, patch

import pytest


class TestGraphOAuthService:
    """Tests for graph_oauth_service token acquisition and caching."""

    def test_token_acquisition_returns_token(self) -> None:
        """Token acquisition calls MSAL and returns access token on success."""
        mock_result = {"access_token": "test-token-abc123", "expires_in": 3600}

        with patch.dict(
            os.environ,
            {
                "OUTLOOK_CLIENT_ID": "test-client-id",
                "OUTLOOK_CLIENT_SECRET": "test-client-secret",
                "OUTLOOK_TENANT_ID": "test-tenant-id",
            },
        ):
            with patch("app.services.graph_oauth_service._get_msal_app") as mock_get_app:
                mock_app = MagicMock()
                mock_app.acquire_token_for_client.return_value = mock_result
                mock_get_app.return_value = mock_app

                # Reset module state
                import app.services.graph_oauth_service as svc

                svc._token_cache = {}
                svc._msal_app = None

                result = None

                async def _run():
                    nonlocal result
                    result = await svc._acquire_access_token()
                    return result

                import asyncio

                asyncio.run(_run())

                assert result == "test-token-abc123"
                mock_app.acquire_token_for_client.assert_called_once_with(
                    scopes=["https://graph.microsoft.com/.default"]
                )

    def test_token_caching_returns_cached_token(self) -> None:
        """Second call within TTL uses cached token (no MSAL call)."""
        cached_token = {
            "token": "cached-token-xyz",
            "expires_at": time.time() + 3600,  # 1 hour from now
        }

        with patch.dict(
            os.environ,
            {
                "OUTLOOK_CLIENT_ID": "test-client-id",
                "OUTLOOK_CLIENT_SECRET": "test-client-secret",
                "OUTLOOK_TENANT_ID": "test-tenant-id",
            },
        ):
            import app.services.graph_oauth_service as svc

            svc._token_cache = {"access_token": cached_token}
            svc._msal_app = None

            async def _run():
                return await svc._acquire_access_token()

            result = None

            async def _run2():
                nonlocal result
                result = await svc._acquire_access_token()
                return result

            import asyncio

            asyncio.run(_run2())

            assert result == "cached-token-xyz"
            # _get_msal_app should not be called (cache hit)

    def test_token_acquisition_failure_returns_none(self) -> None:
        """MSAL failure (empty result dict) returns None."""
        with patch.dict(
            os.environ,
            {
                "OUTLOOK_CLIENT_ID": "test-client-id",
                "OUTLOOK_CLIENT_SECRET": "test-client-secret",
                "OUTLOOK_TENANT_ID": "test-tenant-id",
            },
        ):
            with patch("app.services.graph_oauth_service._get_msal_app") as mock_get_app:
                mock_app = MagicMock()
                mock_app.acquire_token_for_client.return_value = {}  # Empty = failure
                mock_get_app.return_value = mock_app

                import app.services.graph_oauth_service as svc

                svc._token_cache = {}
                svc._msal_app = None

                result = None

                async def _run():
                    nonlocal result
                    result = await svc._acquire_access_token()
                    return result

                import asyncio

                asyncio.run(_run())

                assert result is None

    def test_expired_token_triggers_refresh(self) -> None:
        """Cached token that is expired (< 60s buffer) triggers new acquisition."""
        expired_token = {
            "token": "expired-token",
            "expires_at": time.time() - 10,  # Already expired
        }

        fresh_token = {"access_token": "fresh-token", "expires_in": 3600}

        with patch.dict(
            os.environ,
            {
                "OUTLOOK_CLIENT_ID": "test-client-id",
                "OUTLOOK_CLIENT_SECRET": "test-client-secret",
                "OUTLOOK_TENANT_ID": "test-tenant-id",
            },
        ):
            with patch("app.services.graph_oauth_service._get_msal_app") as mock_get_app:
                mock_app = MagicMock()
                mock_app.acquire_token_for_client.return_value = fresh_token
                mock_get_app.return_value = mock_app

                import app.services.graph_oauth_service as svc

                svc._token_cache = {"access_token": expired_token}
                svc._msal_app = None

                result = None

                async def _run():
                    nonlocal result
                    result = await svc._acquire_access_token()
                    return result

                import asyncio

                asyncio.run(_run())

                assert result == "fresh-token"
                # Should have called MSAL since cache was expired

    def test_clear_token_cache(self) -> None:
        """clear_token_cache() resets the module-level cache."""
        import app.services.graph_oauth_service as svc

        svc._token_cache = {"access_token": {"token": "stale", "expires_at": time.time() + 3600}}

        svc.clear_token_cache()

        assert svc._token_cache == {}

    def test_missing_credentials_returns_none(self) -> None:
        """Missing OUTLOOK_CLIENT_ID returns None (no crash)."""
        with patch.dict(os.environ, {}, clear=True):
            import app.services.graph_oauth_service as svc

            svc._token_cache = {}
            svc._msal_app = None

            result = None

            async def _run():
                nonlocal result
                result = await svc._acquire_access_token()
                return result

            import asyncio

            asyncio.run(_run())

            assert result is None


class TestGraphOAuthServiceConcurrent:
    """Tests for concurrent token acquisition (asyncio.Lock behavior)."""

    @pytest.mark.asyncio
    async def test_concurrent_calls_only_one_acquires(self) -> None:
        """When multiple coroutines call _acquire_access_token simultaneously,
        only one should actually call MSAL (Lock prevents duplicate acquisition)."""
        import asyncio
        from unittest.mock import MagicMock

        call_count = 0

        def _mock_acquire(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Simulate slow MSAL call
            time.sleep(0.05)
            return {"access_token": f"token-{call_count}", "expires_in": 3600}

        mock_result = {"access_token": "shared-token", "expires_in": 3600}

        with patch.dict(
            os.environ,
            {
                "OUTLOOK_CLIENT_ID": "test-client-id",
                "OUTLOOK_CLIENT_SECRET": "test-client-secret",
                "OUTLOOK_TENANT_ID": "test-tenant-id",
            },
        ):
            with patch("app.services.graph_oauth_service._get_msal_app") as mock_get_app:
                mock_app = MagicMock()
                mock_app.acquire_token_for_client.side_effect = _mock_acquire
                mock_get_app.return_value = mock_app

                import app.services.graph_oauth_service as svc

                svc._token_cache = {}
                svc._msal_app = None

                # Launch 3 concurrent calls
                async def _call():
                    return await svc._acquire_access_token()

                results = await asyncio.gather(_call(), _call(), _call())

                # All should get a token (first one fills cache; others wait)
                assert all(r is not None for r in results)
                # MSAL should be called exactly once (Lock serialization)
                assert call_count == 1

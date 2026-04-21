"""Graph OAuth token acquisition service (Phase 184-01-02, Section C).

Implements asyncio.Lock double-checked locking for token caching to prevent
concurrent duplicate token acquisitions (BLOCKER-5 fix).

Credentials: OUTLOOK_CLIENT_ID, OUTLOOK_CLIENT_SECRET, OUTLOOK_TENANT_ID
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

logger = logging.getLogger(__name__)

# Module-level token cache: {access_token: {token: str, expires_at: float}}
_token_cache: dict = {}
_token_lock = asyncio.Lock()

# MSAL app — created once, reused across token acquisitions
_msal_app = None


def _get_msal_app():
    """Get or create MSAL ConfidentialClientApplication (lazy init)."""
    global _msal_app
    if _msal_app is None:
        import msal

        client_id = os.getenv("OUTLOOK_CLIENT_ID", "")
        client_credential = os.getenv("OUTLOOK_CLIENT_SECRET", "")
        tenant_id = os.getenv("OUTLOOK_TENANT_ID", "")
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        _msal_app = msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_credential,
            authority=authority,
        )
    return _msal_app


async def _acquire_access_token() -> str | None:
    """Acquire an access token from Azure AD using client credentials flow.

    Uses double-checked locking with asyncio.Lock to prevent concurrent
    duplicate token acquisitions when APScheduler drives parallel poll cycles.

    Returns:
        Access token string on success, None on failure.
    """
    # Fast path: return cached token if still valid (60s buffer)
    if (cached := _token_cache.get("access_token")) and cached["expires_at"] > time.time() + 60:
        return cached["token"]

    # Slow path: acquire lock and refresh if needed
    async with _token_lock:
        # Re-check after acquiring lock (another coroutine may have refreshed)
        if (cached := _token_cache.get("access_token")) and cached["expires_at"] > time.time() + 60:
            return cached["token"]

        # Attempt token acquisition
        try:
            app = _get_msal_app()
            result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        except Exception as exc:
            logger.warning("[GraphOAuth] Token acquisition error: %s", exc)
            return None

        if not result:
            logger.warning("[GraphOAuth] Token acquisition failed — check OUTLOOK_CLIENT credentials")
            return None

        _token_cache["access_token"] = {
            "token": result["access_token"],
            "expires_at": time.time() + result["expires_in"],
        }
        logger.debug(
            "[GraphOAuth] Token acquired, expires in %ds",
            result["expires_in"],
        )
        return result["access_token"]


def clear_token_cache() -> None:
    """Clear the cached token (e.g., on 401 error to force re-acquisition)."""
    global _token_cache
    _token_cache = {}
    logger.debug("[GraphOAuth] Token cache cleared")

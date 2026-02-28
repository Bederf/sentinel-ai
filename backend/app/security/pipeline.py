"""
Security Pipeline — RBAC & Site Authorization Dependencies.

Provides FastAPI dependency functions for role-based access control (RBAC)
and site-level authorization. These complement the existing auth_middleware.py
require_auth/require_role by adding:

    1. require_role(min_level) — Numeric level-based role check using ROLE_LEVELS
    2. require_site_access(site_id_param) — Site-scoped authorization

Usage:
    from app.security.pipeline import require_role, require_site_access

    @router.get("/api/admin/config")
    async def get_config(
        auth: AuthContext = Depends(require_role(4))  # ADMIN only
    ):
        ...

    @router.get("/api/sites/{site_id}/equipment")
    async def get_equipment(
        site_id: str,
        auth: AuthContext = Depends(require_site_access("site_id"))
    ):
        ...
"""

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Request, status

from app.config.settings import settings
from app.middleware.auth_middleware import _authenticate_request, _extract_ip_address
from app.models.auth import AuthContext, SentinelRole
from app.security.constants import ROLE_LEVELS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Site Access Configuration (JSON fallback when Supabase unavailable)
#
# File: backend/app/data/site_access_config.json
# Format: { "user_email": ["site-002", "site-003"], ... }
# ADMINs bypass this entirely.
# ---------------------------------------------------------------------------
_SITE_ACCESS_CONFIG_PATH = Path(__file__).parent.parent / "data" / "site_access_config.json"
_site_access_cache: Optional[dict] = None


def _load_site_access_config() -> dict:
    """Load site access configuration from JSON file.

    Returns:
        Dict mapping user email to list of authorized site codes.
    """
    global _site_access_cache
    if _site_access_cache is not None:
        return _site_access_cache

    if _SITE_ACCESS_CONFIG_PATH.exists():
        try:
            with open(_SITE_ACCESS_CONFIG_PATH) as f:
                _site_access_cache = json.load(f)
                return _site_access_cache
        except Exception as e:
            logger.warning(f"Failed to load site access config: {e}")

    _site_access_cache = {}
    return _site_access_cache


def clear_site_access_cache() -> None:
    """Clear the cached site access config (for testing)."""
    global _site_access_cache
    _site_access_cache = None


def _get_user_role_level(auth_ctx: AuthContext) -> int:
    """Get the numeric role level for an authenticated user.

    Uses ROLE_LEVELS from constants.py. Falls back to 0 for unknown roles.

    Args:
        auth_ctx: Authenticated user context.

    Returns:
        Numeric role level (higher = more privileged).
    """
    role_name = auth_ctx.role.value.lower()
    return ROLE_LEVELS.get(role_name, 0)


async def _get_auth_context(request: Request) -> AuthContext:
    """Get or create auth context from request, handling demo mode.

    Centralizes the auth extraction logic so both require_role and
    require_site_access share the same authentication flow.

    Args:
        request: FastAPI request object.

    Returns:
        AuthContext for the authenticated user.

    Raises:
        HTTPException 401 if no valid credentials.
    """
    # Check if auth already attached (e.g., by upstream middleware)
    existing = getattr(request.state, "auth", None)
    if existing is not None:
        return existing

    # Demo mode bypass
    if settings.demo_mode:
        if settings.environment == "production":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service misconfigured",
            )

        source_ip = _extract_ip_address(request)

        # Try real auth first
        auth_ctx = await _authenticate_request(request)
        if auth_ctx:
            request.state.auth = auth_ctx
            return auth_ctx

        # Demo fallback — ADMIN for full access in dev
        demo_ctx = AuthContext(
            user_id="demo-user",
            role=SentinelRole.ADMIN,
            auth_method="demo_mode",
            source_ip=source_ip,
            email="demo@sentinel.local",
            scopes=["admin:all"],
            metadata={"demo_mode": True},
        )
        request.state.auth = demo_ctx
        return demo_ctx

    # Production auth
    auth_ctx = await _authenticate_request(request)
    if auth_ctx is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    request.state.auth = auth_ctx
    return auth_ctx


# ---------------------------------------------------------------------------
# require_role — Numeric level-based RBAC dependency
# ---------------------------------------------------------------------------


def require_role(min_level: int):
    """FastAPI dependency requiring a minimum numeric role level.

    Uses ROLE_LEVELS from security constants:
        bot_agent=1, auditor=1, operator=2, developer=3, admin=4

    Args:
        min_level: Minimum role level required (1-4).

    Returns:
        FastAPI dependency that yields AuthContext if authorized.

    Raises:
        HTTPException 401 if not authenticated.
        HTTPException 403 if role level is below min_level.

    Usage:
        @router.post("/api/admin/settings")
        async def update_settings(
            auth: AuthContext = Depends(require_role(4))
        ):
            ...
    """

    async def _dependency(request: Request) -> AuthContext:
        auth_ctx = await _get_auth_context(request)
        user_level = _get_user_role_level(auth_ctx)

        if user_level < min_level:
            logger.warning(
                "RBAC denied: user=%s role=%s level=%d required=%d path=%s",
                auth_ctx.user_id,
                auth_ctx.role.value,
                user_level,
                min_level,
                request.url.path,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role level",
            )

        return auth_ctx

    return _dependency


# ---------------------------------------------------------------------------
# require_site_access — Site-scoped authorization dependency
# ---------------------------------------------------------------------------


def require_site_access(site_id_param: str = "site_id"):
    """FastAPI dependency requiring access to a specific site.

    ADMINs (level 4) can access all sites.
    Other roles are checked against:
      1. Supabase user_site_access table (if available)
      2. JSON config fallback (backend/app/data/site_access_config.json)

    The site_id is extracted from the path parameter named `site_id_param`.

    Args:
        site_id_param: Name of the path/query parameter containing the site ID.

    Returns:
        FastAPI dependency that yields AuthContext if authorized for the site.

    Raises:
        HTTPException 401 if not authenticated.
        HTTPException 403 if not authorized for the requested site.

    Usage:
        @router.get("/api/sites/{site_id}/equipment")
        async def get_equipment(
            site_id: str,
            auth: AuthContext = Depends(require_site_access("site_id"))
        ):
            ...
    """

    async def _dependency(request: Request) -> AuthContext:
        auth_ctx = await _get_auth_context(request)

        # Extract site_id from path params, query params, or header
        site_id = request.path_params.get(site_id_param)
        if not site_id:
            site_id = request.query_params.get(site_id_param)
        if not site_id:
            site_id = request.headers.get("X-Site-Id")

        if not site_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing site identifier (path param '{site_id_param}', query param, or X-Site-Id header)",
            )

        # ADMINs bypass site access checks
        user_level = _get_user_role_level(auth_ctx)
        if user_level >= ROLE_LEVELS.get("admin", 4):
            return auth_ctx

        # Check site access
        has_access = _check_site_access(auth_ctx, site_id)
        if not has_access:
            logger.warning(
                "Site access denied: user=%s role=%s site=%s path=%s",
                auth_ctx.user_id,
                auth_ctx.role.value,
                site_id,
                request.url.path,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Not authorized for site: {site_id}",
            )

        return auth_ctx

    return _dependency


def _check_site_access(auth_ctx: AuthContext, site_id: str) -> bool:
    """Check if a user has access to a specific site.

    Tries Supabase first, falls back to JSON config.

    Args:
        auth_ctx: Authenticated user context.
        site_id: Site code (e.g., "site-002").

    Returns:
        True if user has access.
    """
    # Try Supabase repository first
    try:
        from app.database.repositories.user_site_access_repository import (
            get_user_site_access_repository,
        )

        repo = get_user_site_access_repository()
        if auth_ctx.email:
            return repo.has_access_to_building_code(
                user_email=auth_ctx.email,
                user_role=auth_ctx.role,
                building_code=site_id,
            )
    except Exception as e:
        logger.debug(f"Supabase site access check failed, using JSON fallback: {e}")

    # JSON config fallback
    config = _load_site_access_config()
    if auth_ctx.email:
        authorized_sites = config.get(auth_ctx.email.lower(), [])
        return site_id in authorized_sites

    return False

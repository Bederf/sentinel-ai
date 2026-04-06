"""
Security Pipeline — RBAC, Site Authorization & Prompt Guard Dependencies.

Provides FastAPI dependency functions for role-based access control (RBAC),
site-level authorization, and prompt injection defence. These complement
the existing auth_middleware.py require_auth/require_role by adding:

    1. require_role(min_level) — Numeric level-based role check using ROLE_LEVELS
    2. require_site_access(site_id_param) — Site-scoped authorization
    3. prompt_guard(field, source) — Prompt injection scoring & rewrite
    4. validate_llm_routes(app) — Startup route integrity check

Usage:
    from app.security.pipeline import require_role, require_site_access, prompt_guard

    @router.post("/chat", tags=["llm_touching"])
    async def chat(
        request: Request,
        chat_request: ChatRequest,
        auth: AuthContext = Depends(require_role(1)),
        guarded_text: str = Depends(prompt_guard(field="message", source="direct")),
    ):
        # guarded_text is either original or rewritten
        ...
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status

from app.config.settings import settings
from app.middleware.auth_middleware import _authenticate_request, _extract_ip_address
from app.models.auth import AuthContext
from app.security.constants import ROLE_LEVELS, SITE_ID_PATTERN

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Site Access Configuration (JSON fallback when Supabase unavailable)
#
# File: backend/app/data/site_access_config.json
# Format: { "user_email": ["site-002", "site-003"], ... }
# ADMINs bypass this entirely.
# ---------------------------------------------------------------------------
_SITE_ACCESS_CONFIG_PATH = Path(__file__).parent.parent / "data" / "site_access_config.json"
_site_access_cache: dict | None = None


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
    """Get or create auth context from request, handling local profile mode.

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

    # Authenticate
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
            return repo.has_access_to_site_code(
                user_email=auth_ctx.email,
                user_role=auth_ctx.role,
                site_code=site_id,
            )
    except Exception as e:
        logger.debug(f"Supabase site access check failed, using JSON fallback: {e}")

    # JSON config fallback
    config = _load_site_access_config()
    if auth_ctx.email:
        authorized_sites = config.get(auth_ctx.email.lower(), [])
        return site_id in authorized_sites

    return False


# ---------------------------------------------------------------------------
# prompt_guard — Prompt injection scoring dependency
# ---------------------------------------------------------------------------


def prompt_guard(field: str = "message", source: str = "direct"):
    """FastAPI dependency that scores a request body field for injection risk.

    Reads the JSON request body, extracts the text from ``field``, runs
    :func:`score_prompt`, and:
      - **block** (score >= source threshold): raises HTTP 400 + audit event
      - **rewrite**: returns sanitised text
      - **allow**: returns original text

    Also validates ``site_id`` format (``SITE_ID_PATTERN``) if present.

    Args:
        field: Name of the JSON body field containing the text to guard.
        source: One of ``"direct"``, ``"indirect"``, ``"webhook"``.

    Returns:
        FastAPI dependency yielding the (possibly rewritten) text string.

    Usage::

        @router.post("/chat", tags=["llm_touching"])
        async def chat(
            guarded_text: str = Depends(prompt_guard("message", "direct")),
        ):
            ...
    """

    async def _dependency(request: Request) -> str:
        from app.security.prompt_guard import audit_snippet, score_prompt

        # --- Parse body once and cache on request.state ---
        body: dict = {}
        if not hasattr(request.state, "_parsed_body"):
            try:
                raw = await request.body()
                body = json.loads(raw) if raw else {}
                request.state._parsed_body = body
            except Exception:
                body = {}
                request.state._parsed_body = body
        else:
            body = request.state._parsed_body

        text = body.get(field, "")
        if isinstance(text, dict):
            # Some payloads nest the text (e.g., WhatsApp text.body)
            text = text.get("body", str(text))
        if not isinstance(text, str):
            text = str(text) if text else ""

        # --- site_id format validation (if present) ---
        site_id = body.get("site_id")
        if site_id and not SITE_ID_PATTERN.match(site_id):
            logger.warning(
                "prompt_guard: invalid site_id format: %s path=%s",
                site_id,
                request.url.path,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid site_id format. Expected: site-NNN",
            )

        # --- Score the prompt ---
        result = score_prompt(text, source)

        # --- Audit logging (hash, not raw text) ---
        text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
        snippet = audit_snippet(text)

        if result.action == "block":
            logger.warning(
                "prompt_guard BLOCKED: source=%s score=%.2f hash=%s snippet=%s path=%s reasons=%s",
                source,
                result.score,
                text_hash,
                snippet[:80],
                request.url.path,
                result.reasons[:3],
            )
            # Audit: PROMPT_GUARD_BLOCK (Phase 137-09)
            try:
                from app.security.audit_events import audit_prompt_guard_block

                _source_ip = _extract_ip_address(request)
                _user = getattr(getattr(request.state, "auth", None), "user_id", "unknown")
                audit_prompt_guard_block(text, result.score, source, user=_user, source_ip=_source_ip)
            except Exception:
                pass  # Audit failure must not block the security response
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "Prompt injection detected",
                    "code": "PROMPT_GUARD_BLOCK",
                },
            )

        if result.action == "rewrite":
            logger.info(
                "prompt_guard REWRITE: source=%s score=%.2f hash=%s path=%s",
                source,
                result.score,
                text_hash,
                request.url.path,
            )
            # Audit: PROMPT_GUARD_REWRITE (Phase 137-09)
            try:
                from app.security.audit_events import audit_prompt_guard_rewrite

                _source_ip = _extract_ip_address(request)
                _user = getattr(getattr(request.state, "auth", None), "user_id", "unknown")
                audit_prompt_guard_rewrite(text, result.score, source, user=_user, source_ip=_source_ip)
            except Exception:
                pass
            return result.rewritten_text or text

        return text

    return _dependency


# ---------------------------------------------------------------------------
# validate_llm_routes — Startup integrity check
# ---------------------------------------------------------------------------

# Expected dependency function names on every llm_touching route
_REQUIRED_DEPS = {"require_role", "prompt_guard"}


def validate_llm_routes(app: FastAPI) -> None:
    """Scan all routes tagged ``llm_touching`` and verify security deps.

    In production (``settings.environment == "production"``): raises
    ``RuntimeError`` for any route missing required dependencies.
    In local/dev: logs a CRITICAL warning.

    Call this during ``app.on_event("startup")`` or in a lifespan handler.
    """
    issues: list[str] = []

    for route in app.routes:
        tags = getattr(route, "tags", []) or []
        if "llm_touching" not in tags:
            continue

        path = getattr(route, "path", "unknown")
        dep_names: set[str] = set()

        # Walk the dependency tree
        for dep in getattr(route, "dependencies", []) or []:
            dep_func = getattr(dep, "dependency", None)
            if dep_func:
                name = getattr(dep_func, "__name__", "")
                # prompt_guard and require_role are closures named _dependency
                # so we check __qualname__ for the outer function name
                qualname = getattr(dep_func, "__qualname__", "")
                for req_dep in _REQUIRED_DEPS:
                    if req_dep in name or req_dep in qualname:
                        dep_names.add(req_dep)

        # Also check the endpoint's own Depends() params
        endpoint = getattr(route, "endpoint", None)
        if endpoint:
            import inspect

            sig = inspect.signature(endpoint)
            for param in sig.parameters.values():
                if param.default and hasattr(param.default, "dependency"):
                    dep_func = param.default.dependency
                    qualname = getattr(dep_func, "__qualname__", "")
                    for req_dep in _REQUIRED_DEPS:
                        if req_dep in qualname:
                            dep_names.add(req_dep)

        missing = _REQUIRED_DEPS - dep_names
        if missing:
            issues.append(f"  {path}: missing {missing}")

    if not issues:
        logger.info("validate_llm_routes: all llm_touching routes have required deps")
        return

    msg = "LLM route security gaps:\n" + "\n".join(issues)

    if getattr(settings, "environment", "development") == "production":
        raise RuntimeError(msg)
    else:
        logger.critical(msg)

"""
MCP SSE Authentication Helper.

Provides token-based authentication for MCP SSE endpoints.
Supports two credential sources (tried in order):
  1. JWT Bearer token (Authorization header) — real user identity
  2. MCP shared token (query param, X-MCP-Token header, or Bearer fallback)

Usage:
    from app.mcp.auth import require_mcp_auth

    @router.get("/api/mcp/sse")
    async def sse_endpoint(request: Request):
        auth_ctx = await require_mcp_auth(request)
        ...
"""

import logging
import secrets as secrets_mod

from fastapi import HTTPException, Request, status

from app.config.settings import settings
from app.middleware.auth_middleware import (
    _authenticate_request,
    _extract_bearer_token,
    _extract_ip_address,
    _extract_role_from_token,
    validate_jwt_token,
)
from app.models.auth import AuthContext, SentinelRole

logger = logging.getLogger(__name__)

_LOCALHOST_IPS = {"127.0.0.1", "::1", "localhost", "testclient", "unknown"}


def extract_mcp_token(request: Request, *, allow_query_param: bool = True) -> str | None:
    """Extract MCP auth token from request.

    Checks (in order):
      1. ``?token=`` query parameter (SSE connections) — skipped when
         ``allow_query_param=False`` (P5: production POST requests)
      2. ``X-MCP-Token`` header
      3. ``Authorization: Bearer`` header (only non-JWT values)

    Returns:
        Token string or None.
    """
    # 1. Query parameter (primary for SSE)
    if allow_query_param:
        token = request.query_params.get("token")
        if token:
            return token

    # 2. Dedicated header
    header_token = request.headers.get("X-MCP-Token")
    if header_token:
        return header_token

    # 3. Authorization: Bearer (skip JWT-like tokens with dots)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        bearer_value = auth_header[7:]
        # JWTs contain dots; MCP tokens do not
        if "." not in bearer_value and not bearer_value.startswith("sent_sk_"):
            return bearer_value

    return None


_mcp_token_first_seen: dict[str, float] = {}


def _validate_mcp_token(token: str) -> bool:
    """Validate token against configured MCP_AUTH_TOKEN with rotation and expiry.

    Supports:
    - Current token (``MCP_AUTH_TOKEN``)
    - Previous token during rotation grace period (``MCP_AUTH_TOKEN_PREVIOUS``)
    - Max age enforcement (``MCP_AUTH_TOKEN_MAX_AGE_HOURS``)
    """
    import time

    current = settings.mcp_auth_token
    previous = settings.mcp_auth_token_previous

    matched = False
    if current and secrets_mod.compare_digest(token, current):
        matched = True
    elif previous and secrets_mod.compare_digest(token, previous):
        matched = True
        logger.info("MCP auth via rotated (previous) token — rotate client to new token")

    if not matched:
        return False

    # Enforce max age: track when we first saw this token value
    max_age_hours = settings.mcp_auth_token_max_age_hours
    if max_age_hours > 0:
        now = time.monotonic()
        if token not in _mcp_token_first_seen:
            _mcp_token_first_seen[token] = now
        first_seen = _mcp_token_first_seen[token]
        age_hours = (now - first_seen) / 3600
        if age_hours > max_age_hours:
            logger.warning(
                "MCP token expired: age=%.1fh max=%dh — rotate MCP_AUTH_TOKEN",
                age_hours,
                max_age_hours,
            )
            return False

    return True


async def require_mcp_auth(request: Request) -> AuthContext:
    """Authenticate an MCP SSE request.

    Authentication strategy (tried in order):
      1. Standard JWT auth (gives real user identity)
      2. MCP shared token (gives service-level identity)

    Returns:
        AuthContext on success.

    Raises:
        HTTPException 401 on missing/invalid credentials.
        HTTPException 503 when MCP_AUTH_TOKEN not configured.
    """
    source_ip = _extract_ip_address(request)

    # 1. Try standard JWT auth first (real user identity)
    jwt_ctx = await _authenticate_request(request)
    if jwt_ctx:
        logger.debug(
            "MCP auth via JWT: user=%s role=%s ip=%s",
            jwt_ctx.user_id,
            jwt_ctx.role.value,
            source_ip,
        )
        return jwt_ctx

    # Non-production fallback: validate bearer JWT directly.
    # This keeps MCP SSE usable in test/dev where Supabase JWT secret may be unset.
    bearer_token = _extract_bearer_token(request)
    if bearer_token and settings.environment != "production":
        payload = validate_jwt_token(bearer_token, required_token_type="access")
        if payload:
            fallback_ctx = AuthContext(
                user_id=payload.get("sub", "unknown"),
                role=_extract_role_from_token(payload),
                auth_method="bearer_token",
                source_ip=source_ip,
                email=payload.get("email"),
                scopes=payload.get("scopes", []),
                metadata={"token_iss": payload.get("iss", ""), "mcp_fallback": True},
            )
            logger.debug(
                "MCP auth via JWT fallback: user=%s role=%s ip=%s",
                fallback_ctx.user_id,
                fallback_ctx.role.value,
                source_ip,
            )
            return fallback_ctx

    # 2. Try MCP shared token
    mcp_token = extract_mcp_token(request)
    if mcp_token:
        if _validate_mcp_token(mcp_token):
            auth_ctx = AuthContext(
                user_id="mcp-client",
                role=SentinelRole.OPERATOR,
                auth_method="mcp_token",
                source_ip=source_ip,
                email=None,
                scopes=["operator:all"],
                metadata={"auth_type": "mcp_shared_token"},
            )
            logger.debug("MCP auth via shared token: ip=%s", source_ip)
            return auth_ctx
        else:
            logger.warning(
                "MCP auth failure: invalid MCP token from ip=%s path=%s",
                source_ip,
                request.url.path,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid MCP authentication token",
            )

    # No valid credentials
    if not settings.mcp_auth_token:
        logger.error("MCP_AUTH_TOKEN not configured — MCP SSE endpoint unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MCP authentication not configured. Set MCP_AUTH_TOKEN environment variable.",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="MCP authentication required. Provide token via ?token= query param, "
        "X-MCP-Token header, or Authorization: Bearer header.",
    )

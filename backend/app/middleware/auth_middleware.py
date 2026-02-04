"""
Authentication Middleware for SENTINEL BMS Platform.

Handles Bearer token (Supabase JWT) and API key authentication.
Ported from AimTheLaw auth stack, adapted for BMS domain.

NOT registered globally - individual endpoints opt-in via require_auth() dependency.
Demo mode bypass preserved to avoid breaking existing demo flows.

FSR Domain: 4.7 - Logical Access Control

Usage:
    from app.middleware.auth_middleware import require_auth
    from app.models.auth import AuthLevel

    @router.get("/api/equipment")
    async def get_equipment(auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED))):
        # auth.user_id, auth.role, etc. available
        ...

    @router.post("/api/devices/{id}/control")
    async def control_device(auth: AuthContext = Depends(require_auth(AuthLevel.OPERATOR))):
        ...
"""

import hashlib
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, Request, status

from app.config.settings import settings
from app.models.auth import (
    AUTH_LEVEL_TO_MIN_ROLE,
    AuthContext,
    AuthLevel,
    SentinelRole,
    get_required_auth_level,
)

logger = logging.getLogger(__name__)

# =============================================================================
# API Key Store (in-memory for MVP, move to Supabase for production)
# =============================================================================

# Demo API keys for development/testing
# In production, these would be stored in Supabase with hashed keys
_API_KEY_STORE: Dict[str, Dict[str, Any]] = {}


def register_api_key(
    key_hash: str,
    owner: str,
    role: SentinelRole,
    scopes: Optional[List[str]] = None,
    description: str = "",
) -> None:
    """Register an API key in the in-memory store.

    Args:
        key_hash: SHA-256 hash of the API key
        owner: Human owner identifier
        role: Role assigned to this key
        scopes: API scopes granted
        description: Purpose of this key
    """
    _API_KEY_STORE[key_hash] = {
        "owner": owner,
        "role": role,
        "scopes": scopes or [],
        "description": description,
        "created_at": datetime.utcnow().isoformat(),
        "is_active": True,
    }


# =============================================================================
# Token Extraction and Validation
# =============================================================================


def _extract_bearer_token(request: Request) -> Optional[str]:
    """Extract Bearer token from Authorization header.

    Args:
        request: FastAPI request object

    Returns:
        Token string or None if not found
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        # Skip API keys (they start with sent_sk_)
        if token.startswith("sent_sk_"):
            return None
        return token
    return None


def _extract_api_key(request: Request) -> Optional[str]:
    """Extract API key from request headers.

    Checks both Authorization header (Bearer sent_sk_...) and X-API-Key header.

    Args:
        request: FastAPI request object

    Returns:
        API key string or None if not found
    """
    # Check Authorization header for API key
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer sent_sk_"):
        return auth_header[7:]

    # Check X-API-Key header
    api_key = request.headers.get("X-API-Key", "")
    if api_key.startswith("sent_sk_"):
        return api_key

    return None


def _extract_ip_address(request: Request) -> str:
    """Extract client IP from request with proxy support.

    Handles Cloudflare and standard proxy headers.

    Args:
        request: FastAPI request object

    Returns:
        Client IP address string
    """
    # Cloudflare-specific header
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()

    # Standard proxy headers
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # Fallback to direct client
    return request.client.host if request.client else "unknown"


async def _validate_supabase_token(token: str) -> Optional[Dict[str, Any]]:
    """Validate a Supabase JWT token.

    Attempts to decode and verify the token using Supabase's JWT secret
    or JWKS endpoint.

    Args:
        token: JWT token string

    Returns:
        Token payload dict or None if invalid
    """
    try:
        import jwt as pyjwt

        # Try decoding with Supabase JWT secret
        supabase_jwt_secret = settings.supabase_key
        if not supabase_jwt_secret:
            logger.debug("No Supabase key configured for JWT validation")
            return None

        # Decode without full verification for demo
        # In production, use JWKS endpoint for RS256 verification
        try:
            payload = pyjwt.decode(
                token,
                supabase_jwt_secret,
                algorithms=["HS256"],
                options={"verify_exp": True},
            )
            return payload
        except pyjwt.ExpiredSignatureError:
            logger.warning("Supabase token expired")
            return None
        except pyjwt.InvalidTokenError as e:
            logger.debug(f"Supabase token validation failed: {e}")
            return None

    except ImportError:
        logger.debug("PyJWT not installed, skipping Supabase token validation")
        return None
    except Exception as e:
        logger.error(f"Error validating Supabase token: {e}")
        return None


def _validate_api_key(api_key: str) -> Optional[Dict[str, Any]]:
    """Validate an API key against the key store.

    Args:
        api_key: Plaintext API key

    Returns:
        Key info dict or None if invalid
    """
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    key_info = _API_KEY_STORE.get(key_hash)

    if key_info and key_info.get("is_active", False):
        return {**key_info, "key_hash": key_hash}

    return None


def _extract_role_from_token(payload: Dict[str, Any]) -> SentinelRole:
    """Extract SENTINEL role from a JWT token payload.

    Checks multiple locations for role information.

    Args:
        payload: Decoded JWT payload

    Returns:
        SentinelRole (defaults to AUDITOR if no role found)
    """
    # Check direct role field
    role_str = payload.get("role")

    # Check user_metadata (Supabase pattern)
    if not role_str:
        user_metadata = payload.get("user_metadata", {})
        role_str = user_metadata.get("sentinel_role") or user_metadata.get("role")

    # Check app_metadata (Supabase pattern)
    if not role_str:
        app_metadata = payload.get("app_metadata", {})
        role_str = app_metadata.get("sentinel_role") or app_metadata.get("role")

    # Map to SentinelRole
    if role_str:
        try:
            return SentinelRole(role_str.lower())
        except ValueError:
            logger.warning(f"Unknown role '{role_str}', defaulting to AUDITOR")

    return SentinelRole.AUDITOR


# =============================================================================
# Authentication Dependencies (for FastAPI Depends())
# =============================================================================


async def _authenticate_request(request: Request) -> Optional[AuthContext]:
    """Attempt to authenticate a request using any available method.

    Tries Bearer token first, then API key.

    Args:
        request: FastAPI request object

    Returns:
        AuthContext if authenticated, None if no credentials provided
    """
    source_ip = _extract_ip_address(request)

    # Try Bearer token (Supabase JWT)
    token = _extract_bearer_token(request)
    if token:
        payload = await _validate_supabase_token(token)
        if payload:
            role = _extract_role_from_token(payload)
            auth_ctx = AuthContext(
                user_id=payload.get("sub", "unknown"),
                role=role,
                auth_method="bearer_token",
                source_ip=source_ip,
                email=payload.get("email"),
                scopes=payload.get("scopes", []),
                metadata={"token_iss": payload.get("iss", "")},
            )
            logger.debug(
                f"Auth success: user={auth_ctx.user_id} role={auth_ctx.role.value} "
                f"method=bearer_token ip={source_ip}"
            )
            return auth_ctx
        else:
            # Token provided but invalid
            logger.warning(
                f"Auth failure: invalid bearer token from ip={source_ip} "
                f"path={request.url.path}"
            )
            return None

    # Try API key
    api_key = _extract_api_key(request)
    if api_key:
        key_info = _validate_api_key(api_key)
        if key_info:
            auth_ctx = AuthContext(
                user_id=f"svc:{key_info['owner']}",
                role=key_info["role"],
                auth_method="api_key",
                source_ip=source_ip,
                scopes=key_info.get("scopes", []),
                api_key_id=key_info.get("key_hash", "")[:12],
                metadata={"description": key_info.get("description", "")},
            )
            logger.debug(
                f"Auth success: user={auth_ctx.user_id} role={auth_ctx.role.value} "
                f"method=api_key ip={source_ip}"
            )
            return auth_ctx
        else:
            logger.warning(
                f"Auth failure: invalid API key from ip={source_ip} "
                f"path={request.url.path}"
            )
            return None

    # No credentials provided
    return None


def require_auth(level: AuthLevel = AuthLevel.AUTHENTICATED):
    """FastAPI dependency that requires authentication at a specific level.

    In DEMO_MODE, creates a demo auth context instead of requiring real auth.
    This preserves existing demo functionality.

    Usage:
        @router.get("/api/equipment")
        async def get_equipment(
            auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED))
        ):
            ...

    Args:
        level: Required authentication level

    Returns:
        FastAPI dependency function
    """

    async def _dependency(request: Request) -> AuthContext:
        # DEMO_MODE bypass: allow all requests but log them
        if settings.demo_mode:
            source_ip = _extract_ip_address(request)

            # Still try to authenticate if credentials are provided
            auth_ctx = await _authenticate_request(request)
            if auth_ctx:
                request.state.auth = auth_ctx
                return auth_ctx

            # Create demo context
            demo_ctx = AuthContext(
                user_id="demo-user",
                role=SentinelRole.ADMIN,  # Demo gets full access
                auth_method="demo_mode",
                source_ip=source_ip,
                email="demo@sentinel.local",
                scopes=["admin:all"],
                metadata={"demo_mode": True},
            )
            request.state.auth = demo_ctx
            logger.debug(
                f"Demo mode auth: path={request.url.path} ip={source_ip}"
            )
            return demo_ctx

        # PUBLIC endpoints don't need auth
        if level == AuthLevel.PUBLIC:
            source_ip = _extract_ip_address(request)
            public_ctx = AuthContext(
                user_id="anonymous",
                role=SentinelRole.AUDITOR,
                auth_method="public",
                source_ip=source_ip,
            )
            request.state.auth = public_ctx
            return public_ctx

        # Authenticate the request
        auth_ctx = await _authenticate_request(request)

        if auth_ctx is None:
            logger.warning(
                f"Auth required but no valid credentials: "
                f"path={request.url.path} level={level.value} "
                f"ip={_extract_ip_address(request)}"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check authorization level
        if not auth_ctx.has_auth_level(level):
            logger.warning(
                f"Insufficient permissions: user={auth_ctx.user_id} "
                f"role={auth_ctx.role.value} required_level={level.value} "
                f"path={request.url.path} ip={auth_ctx.source_ip}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required level: {level.value}",
            )

        # Attach to request state
        request.state.auth = auth_ctx
        return auth_ctx

    return _dependency


def require_role(*roles: SentinelRole):
    """FastAPI dependency that requires specific roles.

    Ported from AimTheLaw's @require_roles() decorator,
    adapted as a FastAPI Depends() pattern for cleaner integration.

    Usage:
        @router.post("/api/admin/config")
        async def update_config(
            auth: AuthContext = Depends(require_role(SentinelRole.ADMIN))
        ):
            ...

        @router.get("/api/devices/{id}/control")
        async def control_device(
            auth: AuthContext = Depends(require_role(SentinelRole.OPERATOR, SentinelRole.ADMIN))
        ):
            ...

    Args:
        *roles: One or more allowed roles

    Returns:
        FastAPI dependency function
    """

    async def _dependency(request: Request) -> AuthContext:
        # DEMO_MODE bypass
        if settings.demo_mode:
            source_ip = _extract_ip_address(request)
            auth_ctx = await _authenticate_request(request)
            if auth_ctx:
                request.state.auth = auth_ctx
                return auth_ctx

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

        # Authenticate
        auth_ctx = await _authenticate_request(request)
        if auth_ctx is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check role
        if auth_ctx.role not in roles:
            # Also check hierarchy - higher roles inherit
            role_allowed = any(auth_ctx.has_role(r) for r in roles)
            if not role_allowed:
                logger.warning(
                    f"Role check failed: user={auth_ctx.user_id} "
                    f"role={auth_ctx.role.value} required={[r.value for r in roles]} "
                    f"path={request.url.path}"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied. Required roles: {', '.join(r.value for r in roles)}",
                )

        request.state.auth = auth_ctx
        return auth_ctx

    return _dependency


def get_current_auth(request: Request) -> Optional[AuthContext]:
    """Get the current auth context from request state.

    Utility function for code that needs auth info but doesn't
    require authentication (e.g., audit logging that works for
    both authenticated and unauthenticated requests).

    Args:
        request: FastAPI request object

    Returns:
        AuthContext if authenticated, None otherwise
    """
    return getattr(request.state, "auth", None)

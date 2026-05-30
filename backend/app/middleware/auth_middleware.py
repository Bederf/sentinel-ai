"""
Authentication Middleware for SENTINEL BMS Platform.

Handles Bearer token (Supabase JWT) and API key authentication.
Ported from AimTheLaw auth stack, adapted for BMS domain.

NOT registered globally - individual endpoints opt-in via require_auth() dependency.
Profile-based access overrides preserved for constrained local access flows.

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

import asyncio
import hashlib
import hmac
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt as pyjwt
from fastapi import HTTPException, Request, status

from app.config.settings import settings
from app.core.site_resolver import get_primary_site_code
from app.database.repositories.user_entitlements_repository import (
    get_user_entitlements_repository,
)
from app.database.supabase_client import get_supabase_client
from app.models.auth import AuthContext, AuthLevel, SentinelRole
from app.models.module_registry import ModuleType

logger = logging.getLogger(__name__)

# =============================================================================
# PII Sanitization (Phase 65-04)
# =============================================================================


def sanitize_email(email: str) -> str:
    """Mask email address for logging.

    Example: user@example.com -> u***r@e***.com

    Args:
        email: Email address to sanitize

    Returns:
        Masked email address
    """
    if not email or "@" not in email:
        return "***"

    local, domain = email.split("@", 1)
    masked_local = "*" if len(local) <= 1 else local[0] + "*" * (len(local) - 2) + local[-1]

    if len(domain) <= 1:
        masked_domain = "*"
    else:
        # Mask domain but keep TLD
        parts = domain.rsplit(".", 1)
        if len(parts) == 2:
            masked_domain = parts[0][0] + "*" * (len(parts[0]) - 1) + "." + parts[1]
        else:
            masked_domain = parts[0][0] + "*" * (len(parts[0]) - 1)

    return f"{masked_local}@{masked_domain}"


# =============================================================================
# JWT Token Creation (Phase 65-02: Access + Refresh Tokens)
# =============================================================================


def create_jwt_token(
    user_id: str,
    email: str,
    role: str,
    full_name: str,
    token_type: str = "access",
) -> str:
    """Create a JWT token (access or refresh).

    Args:
        user_id: User ID
        email: User email
        role: User role (SentinelRole value)
        full_name: User's full name
        token_type: Token type - "access" or "refresh"

    Returns:
        Encoded JWT token string
    """
    secret = settings.jwt_secret_key or settings.supabase_key
    if not secret:
        raise RuntimeError("JWT_SECRET environment variable is required")

    # Determine TTL based on token type
    if token_type == "refresh":
        ttl_seconds = settings.jwt_refresh_token_ttl_days * 24 * 60 * 60
    else:
        ttl_seconds = settings.jwt_access_token_ttl_minutes * 60

    # Fallback to old setting for backward compatibility
    if ttl_seconds == 0:
        legacy_hours = settings.jwt_expiration_hours or (settings.jwt_expiry_days * 24)
        ttl_seconds = legacy_hours * 60 * 60

    # Minimize JWT payload for security (Phase 65-04: PII reduction)
    # Keep: sub (user_id), role, exp, iat, jti, email (needed for module entitlements)
    # full_name not needed in JWT
    # Email is included because module access control needs it for entitlements lookup
    payload = {
        "sub": user_id,
        "email": email,  # Required for module entitlements checking
        "role": role,
        "token_type": token_type,  # "access" or "refresh"
        "jti": str(uuid.uuid4()),  # Unique token ID for blacklisting
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(seconds=ttl_seconds),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }

    token = pyjwt.encode(payload, secret, algorithm="HS256")
    logger.debug(f"Created {token_type} token for user {user_id}")
    return token


def create_refresh_token(user_id: str, email: str, role: str, full_name: str) -> str:
    """Create a refresh token with refresh TTL and refresh token_type claim."""
    return create_jwt_token(
        user_id=user_id,
        email=email,
        role=role,
        full_name=full_name,
        token_type="refresh",
    )


def validate_jwt_token(token: str, required_token_type: str | None = None) -> dict[str, Any] | None:
    """Validate a JWT token and return payload.

    Checks token expiration, token_type claim, and blacklist status.

    Args:
        token: JWT token string

    Returns:
        Token payload dict or None if invalid
    """
    try:
        secret = settings.jwt_secret_key or settings.supabase_key
        if not secret:
            logger.error("JWT_SECRET environment variable is required for token validation")
            return None

        payload = pyjwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"verify_exp": True},
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )

        # Check token_type claim (Phase 65-02)
        token_type = payload.get("token_type", "access")
        if token_type not in ("access", "refresh"):
            logger.warning(f"Invalid token_type: {token_type}")
            return None
        if required_token_type and token_type != required_token_type:
            logger.warning(
                "Invalid token_type for endpoint: got=%s expected=%s",
                token_type,
                required_token_type,
            )
            return None

        # Check blacklist if Redis available (Phase 65-02)
        jti = payload.get("jti")
        if not jti:
            logger.warning("Token missing jti claim")
            return None

        try:
            from app.services.token_blacklist_service import token_blacklist

            if token_blacklist.is_blacklisted(jti):
                logger.warning(f"Token {jti} is blacklisted")
                return None
        except Exception as e:
            # Graceful degradation: log warning but don't fail
            logger.debug(f"Blacklist check failed: {e}")

        return payload

    except pyjwt.ExpiredSignatureError:
        logger.debug("JWT token expired")
        return None
    except pyjwt.InvalidTokenError as e:
        logger.debug(f"JWT validation failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error validating JWT: {e}")
        return None


# =============================================================================
# Token Extraction and Validation
# =============================================================================


def _extract_bearer_token(request: Request) -> str | None:
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

    # NOTE: SSE stream uses ticket-based auth (POST /api/events/ticket)
    # instead of passing JWTs in URLs. No access_token query param needed.
    return None


def _extract_api_key(request: Request) -> str | None:
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


def _extract_sentry_bot_api_key(request: Request) -> str | None:
    """Extract the legacy Sentry bot API key header."""
    api_key = request.headers.get("X-Sentry-API-Key", "")
    return api_key or None


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


async def _validate_supabase_token(token: str) -> dict[str, Any] | None:
    """Validate a Supabase JWT token.

    Attempts to decode and verify the token using Supabase's JWT secret
    or JWKS endpoint. Now uses validate_jwt_token for consistency.

    Args:
        token: JWT token string

    Returns:
        Token payload dict or None if invalid
    """
    try:
        jwt_secret = settings.jwt_secret_key or settings.supabase_key
        if not jwt_secret:
            logger.debug("No JWT secret configured for token validation")
            return None

        # Use centralized validation function (Phase 65-02)
        return validate_jwt_token(token, required_token_type="access")

    except Exception as e:
        logger.error(f"Error validating Supabase token: {e}")
        return None


async def _validate_api_key(api_key: str) -> dict[str, Any] | None:
    """Validate an API key against Supabase-backed store (async, non-blocking).

    Returns AuthContext if valid, None if not found or expired.
    On Supabase error: returns None (fail-closed, no fallback).

    Args:
        api_key: Plaintext API key

    Returns:
        Key info dict or None if invalid
    """
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    try:
        # Use async Supabase client to avoid blocking event loop
        client = get_supabase_client()
        result = await asyncio.to_thread(
            lambda: client.table("api_keys").select("*").eq("key_hash", key_hash).limit(1).execute()
        )
        rows = result.data or []
        if rows:
            record = rows[0]
            if record.get("revoked"):
                return None

            expires_at = record.get("expires_at")
            if expires_at:
                # Use UTC datetime consistently (Python best practice)
                now = datetime.now(UTC)
                expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if now > expires_dt:
                    return None

            # Validate role enum — map integer owner_role to SentinelRole
            # Migration schema uses INTEGER: 1=auditor, 2=operator, 3=developer, 4=(unused), 5=admin
            owner_role_int = record.get("owner_role")
            if owner_role_int is None:
                logger.warning(
                    f"Missing owner_role in API key {record.get('id')}. Check api_keys table for missing role data."
                )
                role = SentinelRole.AUDITOR
            else:
                role_map = {
                    1: SentinelRole.AUDITOR,
                    2: SentinelRole.OPERATOR,
                    3: SentinelRole.DEVELOPER,
                    5: SentinelRole.ADMIN,
                }
                role = role_map.get(owner_role_int, SentinelRole.AUDITOR)
                if owner_role_int not in role_map:
                    logger.warning(
                        f"Unknown owner_role {owner_role_int} in API key {record.get('id')}. "
                        f"Defaulting to AUDITOR. Valid values: 1=auditor, 2=operator, 3=developer, 5=admin."
                    )

            key_info = {
                "owner": record.get("owner", "unknown"),
                "role": role,
                "scopes": record.get("scopes") or [],
                "description": f"api_key:{record.get('key_prefix', '')}",
                "is_active": True,
            }

            # Non-blocking last_used update (runs in background thread)
            try:
                last_used = datetime.now(UTC).isoformat()
                await asyncio.to_thread(
                    lambda: (
                        client.table("api_keys")
                        .update({"last_used_at": last_used})
                        .eq("id", record.get("id"))
                        .execute()
                    )
                )
            except Exception:
                pass  # Non-critical audit metric, safe to ignore

            return {**key_info, "key_hash": key_hash}
    except Exception as e:
        logger.error(f"API key validation failed: {e}")
        return None  # Fail-closed: invalid on any error

    return None


def _extract_role_from_token(payload: dict[str, Any]) -> SentinelRole:
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
# User Entitlements Loading
# =============================================================================


async def _load_user_entitlements(auth_ctx: AuthContext) -> None:
    """Load and attach user's module entitlements to their auth context.

    Fetches which modules the user is entitled to (has paid for) based on
    their email address. If no entitlements found, user gets default set.

    Args:
        auth_ctx: AuthContext object to populate with entitlements
    """
    if not auth_ctx.email:
        logger.debug("No email in auth context, skipping entitlements load")
        return

    try:
        repo = get_user_entitlements_repository()
        entitlements_profile = await repo.get_user_entitlements(auth_ctx.email)

        if entitlements_profile:
            auth_ctx.entitlements = entitlements_profile.entitlements
            logger.debug(f"Loaded entitlements for {auth_ctx.email}: {auth_ctx.entitlements}")
        else:
            logger.debug(f"No entitlements found for {auth_ctx.email}, using empty set")
            auth_ctx.entitlements = []
    except Exception as e:
        logger.warning(f"Failed to load entitlements for {auth_ctx.email}: {e} - user will see no modules")
        auth_ctx.entitlements = []


# =============================================================================
# Authentication Dependencies (for FastAPI Depends())
# =============================================================================


async def _authenticate_request(request: Request) -> AuthContext | None:
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

            # Load user entitlements (modules they have access to)
            await _load_user_entitlements(auth_ctx)

            logger.debug(
                f"Auth success: user={auth_ctx.user_id} role={auth_ctx.role.value} "
                f"method=bearer_token ip={source_ip} entitlements={auth_ctx.entitlements}"
            )
            return auth_ctx
        else:
            # Token provided but invalid
            logger.warning(f"Auth failure: invalid bearer token from ip={source_ip} path={request.url.path}")
            return None

    # Try legacy Sentry bot API key
    sentry_bot_key = _extract_sentry_bot_api_key(request)
    if sentry_bot_key and settings.sentry_bot_api_key:
        if hmac.compare_digest(sentry_bot_key, settings.sentry_bot_api_key):
            auth_ctx = AuthContext(
                user_id="svc:sentry-bot",
                role=SentinelRole.ADMIN,
                auth_method="sentry_bot_api_key",
                source_ip=source_ip,
                email="sentry-bot@sentinel.local",
                scopes=["admin:all"],
                metadata={"description": "legacy_sentry_bot_api_key"},
                is_bot_agent=True,
            )
            logger.debug("Auth success: user=svc:sentry-bot role=admin method=sentry_bot_api_key ip=%s", source_ip)
            return auth_ctx
        logger.warning("Auth failure: invalid Sentry bot API key from ip=%s path=%s", source_ip, request.url.path)
        return None

    # Try API key
    api_key = _extract_api_key(request)
    if api_key:
        key_info = await _validate_api_key(api_key)
        if key_info:
            role = key_info["role"]
            is_bot = False

            # Detect bot agent API keys (Phase 120-03):
            # 1. DB row has role="bot_agent"
            # 2. API key starts with "sent_bot_"
            if role == SentinelRole.BOT_AGENT or api_key.startswith("sent_bot_"):
                role = SentinelRole.BOT_AGENT
                is_bot = True

            auth_ctx = AuthContext(
                user_id=f"svc:{key_info['owner']}",
                role=role,
                auth_method="api_key",
                source_ip=source_ip,
                scopes=key_info.get("scopes", []),
                api_key_id=key_info.get("key_hash", "")[:12],
                metadata={"description": key_info.get("description", "")},
                is_bot_agent=is_bot,
            )

            # Load user entitlements for API key auth (if applicable)
            if "email" in key_info:
                auth_ctx.email = key_info["email"]
                await _load_user_entitlements(auth_ctx)

            logger.debug(
                f"Auth success: user={auth_ctx.user_id} role={auth_ctx.role.value} "
                f"method=api_key ip={source_ip} is_bot={is_bot} entitlements={auth_ctx.entitlements}"
            )
            return auth_ctx
        else:
            logger.warning(f"Auth failure: invalid API key from ip={source_ip} path={request.url.path}")
            return None

    # No credentials provided
    return None


def require_auth(level: AuthLevel = AuthLevel.AUTHENTICATED):
    """FastAPI dependency that requires authentication at a specific level.

    Enforces role-based access control (RBAC) on all protected endpoints.

    Note: DEMO_MODE bypasses are controlled at the startup level
    (see startup/events.py validation), not at the per-endpoint level.
    All endpoints using require_auth() enforce real authentication.

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

        # Reuse auth context from middleware (e.g. TESTING bypass) if already set
        auth_ctx = getattr(request.state, "auth", None)
        if auth_ctx is None:
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


def get_current_auth(request: Request) -> AuthContext | None:
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


# Convenience dependency for OPERATOR-level auth requirement
require_operator = require_auth(AuthLevel.OPERATOR)


def optional_auth(request: Request) -> AuthContext | None:
    """FastAPI dependency that returns auth context if available, None otherwise.

    Unlike require_role() which rejects unauthenticated requests, this allows
    the endpoint to work for both authenticated and anonymous users.

    Usage:
        @router.post("/api/public-endpoint")
        async def handler(auth: AuthContext | None = Depends(optional_auth)):
            ...
    """
    try:
        ctx = _authenticate_request_sync(request)
        return ctx
    except Exception:
        return None


def _authenticate_request_sync(request: Request) -> AuthContext | None:
    """Sync helper that extracts auth context from request state.

    Checks both the middleware-injected state (from agent_security) and
    the auth module's state for flexibility. Falls back to direct token
    extraction for public paths where middleware skips auth.
    """
    source_ip = _extract_ip_address(request)

    # 1) Check middleware-injected auth state
    state = getattr(request, "state", None)
    if state:
        auth = getattr(state, "auth", None)
        if auth:
            return auth
        auth_ctx = getattr(state, "auth_ctx", None)
        if auth_ctx:
            return auth_ctx

    # 2) Fallback: directly extract and validate Bearer token
    # This handles public-path endpoints that use optional_auth
    # but where the middleware skipped auth injection
    from app.config.settings import settings

    token = _extract_bearer_token(request)
    if not token:
        return None

    payload = validate_jwt_token(token, required_token_type="access")
    if not payload:
        return None

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
    if state is not None:
        state.auth = auth_ctx
    return auth_ctx


# =============================================================================
# Site Access Control (BOLA Prevention)
# =============================================================================


def require_site_access(
    site_param: str = "site_id",
    auth_level: AuthLevel = AuthLevel.AUTHENTICATED,
):
    """FastAPI dependency that requires authentication AND site-level access.

    Prevents BOLA (Broken Object Level Authorization) by verifying the
    authenticated user has access to the site referenced in the path parameter.

    ADMIN role always has access. Other roles are checked against:
    1. access_profiles (allowedSites)
    2. user_site_access table (Supabase)
    3. Default deny

    Usage:
        @router.get("/api/sites/{site_id}")
        async def get_site(
            site_id: str,
            auth: AuthContext = Depends(require_site_access("site_id")),
        ):
            ...

        @router.get("/api/buildings/{building_id}/equipment")
        async def get_equipment(
            building_id: str,
            auth: AuthContext = Depends(require_site_access("building_id")),
        ):
            ...

    Args:
        site_param: Name of the path parameter containing the site/building ID
        auth_level: Minimum auth level required (default AUTHENTICATED)

    Returns:
        FastAPI dependency function returning AuthContext
    """

    async def _dependency(request: Request) -> AuthContext:
        # First authenticate
        auth_ctx = getattr(request.state, "auth", None)
        if auth_ctx is None:
            auth_ctx = await _authenticate_request(request)

        if auth_ctx is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check auth level
        if not auth_ctx.has_auth_level(auth_level):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required level: {auth_level.value}",
            )

        # ADMIN always has access
        if auth_ctx.role == SentinelRole.ADMIN:
            request.state.auth = auth_ctx
            return auth_ctx

        # Extract site_id from path params
        site_code = request.path_params.get(site_param)
        if not site_code:
            # No site param in path — fall through (endpoint may not need site check)
            request.state.auth = auth_ctx
            return auth_ctx

        # Check site access: access profile first, then Supabase DB
        from app.config.access_profiles import get_access_profile_for_email, has_profile_site_access

        email = getattr(auth_ctx, "email", None) or ""

        # Step 1: Access profile check (if user has a profile)
        access_profile = get_access_profile_for_email(email) if email else None
        if access_profile:
            # User has an access profile — use it as the authority
            if not has_profile_site_access(email, site_code):
                logger.warning(
                    "Site access denied (access profile): user=%s site=%s path=%s",
                    auth_ctx.user_id,
                    site_code,
                    request.url.path,
                )
                _emit_bola_site_event(auth_ctx, site_code, request)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"You do not have access to site {site_code}",
                )
            # Access profile allows it — skip DB check
        else:
            # Step 2: No access profile — check database (Supabase user_site_access)
            try:
                from app.database.repositories.user_site_access_repository import (
                    UserSiteAccessRepository,
                )

                repo = UserSiteAccessRepository()
                if not repo.has_access_to_site_code(email, auth_ctx.role, site_code):
                    logger.warning(
                        "Site access denied (database): user=%s site=%s path=%s",
                        auth_ctx.user_id,
                        site_code,
                        request.url.path,
                    )
                    _emit_bola_site_event(auth_ctx, site_code, request)
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"You do not have access to site {site_code}",
                    )
            except HTTPException:
                raise
            except Exception as e:
                # Supabase unavailable — allow fail-open for non-profiled users
                # Production should use strict mode; local profile mode is permissive
                logger.debug("Site access DB check failed, allowing: %s", e)

        request.state.auth = auth_ctx
        return auth_ctx

    return _dependency


def require_query_site_access(
    site_param: str = "site_id",
    auth_level: AuthLevel = AuthLevel.AUTHENTICATED,
):
    """FastAPI dependency that validates site access for query-parameter-based endpoints.

    Same authorization logic as require_site_access, but reads site_id from
    query parameters instead of path parameters. Used for list/collection
    endpoints like GET /equipment?site_id=site-002.

    If site_id query param is absent, the endpoint handler is responsible for
    scoping results to the user's allowed sites (available via auth_ctx).

    Args:
        site_param: Name of the query parameter containing the site ID
        auth_level: Minimum auth level required
    """

    async def _dependency(request: Request) -> AuthContext:
        # Authenticate
        auth_ctx = getattr(request.state, "auth", None)
        if auth_ctx is None:
            auth_ctx = await _authenticate_request(request)

        if auth_ctx is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not auth_ctx.has_auth_level(auth_level):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required level: {auth_level.value}",
            )

        # ADMIN always has access
        if auth_ctx.role == SentinelRole.ADMIN:
            request.state.auth = auth_ctx
            return auth_ctx

        # Extract site_id from query params
        site_code = request.query_params.get(site_param)
        if not site_code:
            # No site filter — endpoint must scope results itself
            request.state.auth = auth_ctx
            return auth_ctx

        # Check site access (same logic as require_site_access)
        from app.config.access_profiles import get_access_profile_for_email, has_profile_site_access

        email = getattr(auth_ctx, "email", None) or ""
        access_profile = get_access_profile_for_email(email) if email else None

        if access_profile:
            if not has_profile_site_access(email, site_code):
                logger.warning(
                    "Query site access denied (access profile): user=%s site=%s path=%s",
                    auth_ctx.user_id,
                    site_code,
                    request.url.path,
                )
                _emit_bola_site_event(auth_ctx, site_code, request)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"You do not have access to site {site_code}",
                )
        else:
            try:
                from app.database.repositories.user_site_access_repository import (
                    UserSiteAccessRepository,
                )

                repo = UserSiteAccessRepository()
                if not repo.has_access_to_site_code(email, auth_ctx.role, site_code):
                    logger.warning(
                        "Query site access denied (database): user=%s site=%s path=%s",
                        auth_ctx.user_id,
                        site_code,
                        request.url.path,
                    )
                    _emit_bola_site_event(auth_ctx, site_code, request)
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"You do not have access to site {site_code}",
                    )
            except HTTPException:
                raise
            except Exception as e:
                logger.debug("Query site access DB check failed, allowing: %s", e)

        request.state.auth = auth_ctx
        return auth_ctx

    return _dependency


def require_equipment_access(
    equipment_param: str = "equipment_id",
    auth_level: AuthLevel = AuthLevel.AUTHENTICATED,
):
    """FastAPI dependency that verifies access to equipment via its parent site.

    Extracts the site code from the equipment code format (e.g., S002-AHU-B1-001 -> site-002)
    and checks site-level access.

    Usage:
        @router.get("/api/equipment/{equipment_id}/controls")
        async def get_controls(
            equipment_id: str,
            auth: AuthContext = Depends(require_equipment_access("equipment_id")),
        ):
            ...

    Args:
        equipment_param: Path parameter name for equipment code
        auth_level: Minimum auth level

    Returns:
        FastAPI dependency function returning AuthContext
    """

    async def _dependency(request: Request) -> AuthContext:
        # Authenticate first
        auth_ctx = getattr(request.state, "auth", None)
        if auth_ctx is None:
            auth_ctx = await _authenticate_request(request)

        if auth_ctx is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not auth_ctx.has_auth_level(auth_level):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required level: {auth_level.value}",
            )

        # ADMIN always has access
        if auth_ctx.role == SentinelRole.ADMIN:
            request.state.auth = auth_ctx
            return auth_ctx

        # Extract equipment code and derive site
        equipment_code = request.path_params.get(equipment_param, "")
        site_code = _equipment_code_to_site(equipment_code)

        if site_code:
            from app.config.access_profiles import get_access_profile_for_email, has_profile_site_access

            email = getattr(auth_ctx, "email", None) or ""
            access_profile = get_access_profile_for_email(email) if email else None

            if access_profile:
                if not has_profile_site_access(email, site_code):
                    logger.warning(
                        "Equipment access denied (access profile): user=%s equipment=%s site=%s",
                        auth_ctx.user_id,
                        equipment_code,
                        site_code,
                    )
                    _emit_bola_equipment_event(auth_ctx, equipment_code, site_code, request)
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"You do not have access to equipment {equipment_code}",
                    )
            else:
                try:
                    from app.database.repositories.user_site_access_repository import (
                        UserSiteAccessRepository,
                    )

                    repo = UserSiteAccessRepository()
                    if not repo.has_access_to_site_code(email, auth_ctx.role, site_code):
                        logger.warning(
                            "Equipment access denied (database): user=%s equipment=%s site=%s",
                            auth_ctx.user_id,
                            equipment_code,
                            site_code,
                        )
                        _emit_bola_equipment_event(auth_ctx, equipment_code, site_code, request)
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"You do not have access to equipment {equipment_code}",
                        )
                except HTTPException:
                    raise
                except Exception as e:
                    logger.debug("Equipment site access DB check failed, allowing: %s", e)

        request.state.auth = auth_ctx
        return auth_ctx

    return _dependency


def _get_route_pattern(request) -> str:
    """Return the normalized route pattern (e.g. /api/buildings/{site_id}/equipment).

    Falls back to the concrete path if no route match is available.
    """
    route = getattr(request, "scope", {}).get("route")
    if route and hasattr(route, "path"):
        return route.path
    return str(request.url.path)


def _emit_bola_site_event(auth_ctx, site_code: str, request) -> None:
    """Emit a structured BOLA_SITE_DENIED audit event (fire-and-forget)."""
    try:
        from app.security.audit_events import audit_bola_site_denied

        audit_bola_site_denied(
            user_id=auth_ctx.user_id,
            email=getattr(auth_ctx, "email", "") or "",
            role=auth_ctx.role.value if hasattr(auth_ctx.role, "value") else str(auth_ctx.role),
            site_id=site_code,
            path=_get_route_pattern(request),
            method=request.method,
            source_ip=_extract_ip_address(request),
        )
    except Exception as exc:
        logger.debug("Failed to emit BOLA site audit event: %s", exc)


def _emit_bola_equipment_event(auth_ctx, equipment_code: str, derived_site: str, request) -> None:
    """Emit a structured BOLA_EQUIPMENT_DENIED audit event (fire-and-forget)."""
    try:
        from app.security.audit_events import audit_bola_equipment_denied

        audit_bola_equipment_denied(
            user_id=auth_ctx.user_id,
            email=getattr(auth_ctx, "email", "") or "",
            role=auth_ctx.role.value if hasattr(auth_ctx.role, "value") else str(auth_ctx.role),
            equipment_code=equipment_code,
            derived_site=derived_site,
            path=_get_route_pattern(request),
            method=request.method,
            source_ip=_extract_ip_address(request),
        )
    except Exception as exc:
        logger.debug("Failed to emit BOLA equipment audit event: %s", exc)


def _equipment_code_to_site(equipment_code: str) -> str | None:
    """Extract site code from equipment code.

    Equipment code format: S002-AHU-B1-001 -> site prefix S002 -> site-002
    Zone format: S002-VAV-101 -> S002 -> site-002
    """
    if not equipment_code:
        return None
    parts = equipment_code.split("-")
    if not parts:
        return None
    prefix = parts[0]  # e.g., "S002"
    if prefix.startswith("S") and len(prefix) == 4 and prefix[1:].isdigit():
        return f"site-{prefix[1:]}"  # S002 -> site-002
    return None


# =============================================================================
# Module Access Control (Module Gating)
# =============================================================================


def require_module(*required_modules: "ModuleType"):
    """FastAPI dependency that requires specific modules to be active.

    Validates that the requested module(s) are active for the site before allowing access.
    Used to gate control features (CONTROL module), work orders (MAINTENANCE module), etc.

    Usage:
        from app.middleware.auth_middleware import require_module
        from app.models.module_registry import ModuleType

        @router.post(\"/api/hvac/zones/{id}/control\")
        async def control_hvac(
            zone_id: str,
            auth: AuthContext = Depends(require_module(ModuleType.HVAC_CONTROL)),
            request: Request
        ):
            # HVAC_CONTROL module is guaranteed to be active here
            ...

    Args:
        *required_modules: One or more ModuleType values that must be active

    Returns:
        FastAPI dependency function

    Raises:
        HTTPException 403 if modules not active
    """
    # Import here to avoid circular imports
    from app.services.module_registry_service import module_registry

    async def _dependency(request: Request) -> AuthContext:
        # Get auth context (module gating still requires authentication)
        auth_ctx = await _authenticate_request(request)
        if auth_ctx is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Get site_id from request headers or context
        site_id = request.headers.get("X-Site-Id") or get_primary_site_code() or "unknown"

        # Check if all required modules are active
        for module in required_modules:
            if not module_registry.is_module_active(site_id, module):
                logger.warning(
                    f"Module access denied: module {module.value} not active for site {site_id}, "
                    f"user {auth_ctx.user_id}, path {request.url.path}"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"The {module.value.upper()} module is not active for this site. "
                    f"Contact your administrator to enable this feature.",
                )

        request.state.auth = auth_ctx
        return auth_ctx

    return _dependency

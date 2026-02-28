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
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import uuid

import jwt as pyjwt
from fastapi import HTTPException, Request, status

from app.config.settings import settings
from app.database.supabase_client import get_supabase_client
from app.database.repositories.user_entitlements_repository import (
    get_user_entitlements_repository,
)
from app.models.auth import AuthContext, AuthLevel, SentinelRole, ROLE_HIERARCHY
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
    if len(local) <= 1:
        masked_local = "*"
    else:
        masked_local = local[0] + "*" * (len(local) - 2) + local[-1]

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
# API Key Store (in-memory for MVP, move to Supabase for production)
# =============================================================================

# Demo API keys for development/testing
# In production, these would be stored in Supabase with hashed keys
_API_KEY_STORE: Dict[str, Dict[str, Any]] = {}
_API_KEY_CACHE: Dict[str, Tuple[datetime, Dict[str, Any]]] = {}
_API_KEY_CACHE_TTL_SECONDS = 300


def _extract_allowed_demo_hosts() -> set[str]:
    """Build host allowlist for DEMO_MODE from configured origins."""
    hosts: set[str] = set()
    for configured_origin in (*settings.demo_allowed_origins, *settings.cors_origins):
        try:
            parsed = urlparse(configured_origin)
            if parsed.hostname:
                hosts.add(parsed.hostname.lower())
        except Exception:
            continue
    return hosts


def _is_demo_origin_allowed(request: Request) -> bool:
    """Return True when request origin/host matches configured demo-safe origins."""
    origin = (request.headers.get("origin") or "").strip()
    host_header = (request.headers.get("host") or "").strip()
    host_only = host_header.split(":", 1)[0].lower() if host_header else ""

    configured_origins = set(settings.demo_allowed_origins) | set(settings.cors_origins)
    if origin and origin in configured_origins:
        return True

    allowed_hosts = _extract_allowed_demo_hosts()
    return bool(host_only and host_only in allowed_hosts)


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
    secret = settings.jwt_secret_key or settings.supabase_key or "sentinel-demo-jwt-secret-change-in-production"

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


def validate_jwt_token(token: str, required_token_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Validate a JWT token and return payload.

    Checks token expiration, token_type claim, and blacklist status.

    Args:
        token: JWT token string

    Returns:
        Token payload dict or None if invalid
    """
    try:
        secret = settings.jwt_secret_key or settings.supabase_key or "sentinel-demo-jwt-secret-change-in-production"

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

    # NOTE: SSE stream uses ticket-based auth (POST /api/events/ticket)
    # instead of passing JWTs in URLs. No access_token query param needed.
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


def _validate_api_key(api_key: str) -> Optional[Dict[str, Any]]:
    """Validate an API key against database (with short in-memory cache).

    Args:
        api_key: Plaintext API key

    Returns:
        Key info dict or None if invalid
    """
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    now = datetime.utcnow()

    # 5-minute in-memory cache to reduce DB hits
    cached = _API_KEY_CACHE.get(key_hash)
    if cached:
        expires_at, cached_value = cached
        if now < expires_at:
            return {**cached_value, "key_hash": key_hash}
        _API_KEY_CACHE.pop(key_hash, None)

    # Primary source: database
    try:
        client = get_supabase_client()
        result = client.table("api_keys").select("*").eq("key_hash", key_hash).limit(1).execute()
        rows = result.data or []
        if rows:
            record = rows[0]
            if record.get("revoked"):
                return None

            expires_at = record.get("expires_at")
            if expires_at:
                expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if now.replace(tzinfo=expires_dt.tzinfo) > expires_dt:
                    return None

            role_value = str(record.get("role", "auditor")).lower()
            try:
                role = SentinelRole(role_value)
            except ValueError:
                role = SentinelRole.AUDITOR

            key_info = {
                "owner": record.get("owner", "unknown"),
                "role": role,
                "scopes": record.get("scopes") or [],
                "description": f"api_key:{record.get('key_prefix', '')}",
                "is_active": True,
            }
            _API_KEY_CACHE[key_hash] = (
                now + timedelta(seconds=_API_KEY_CACHE_TTL_SECONDS),
                key_info,
            )

            # Non-blocking last_used update
            try:
                client.table("api_keys").update({"last_used_at": now.isoformat()}).eq("id", record.get("id")).execute()
            except Exception:
                pass

            return {**key_info, "key_hash": key_hash}
    except Exception as e:
        logger.debug(f"DB API key validation failed, falling back to in-memory store: {e}")

    # Backward compatibility: fallback to legacy in-memory store
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

    # Try API key
    api_key = _extract_api_key(request)
    if api_key:
        key_info = _validate_api_key(api_key)
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
            # Block DEMO_MODE bypass in production environment
            if settings.environment == "production":
                logger.error(f"DEMO_MODE bypass attempted in production environment - path={request.url.path}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Service misconfigured",
                )

            source_ip = _extract_ip_address(request)

            # Restrict demo mode to localhost or explicitly allowed origins (C-4)
            _LOCALHOST_IPS = {"127.0.0.1", "::1", "localhost", "testclient", "unknown"}
            if source_ip not in _LOCALHOST_IPS:
                if not _is_demo_origin_allowed(request):
                    logger.warning(
                        f"DEMO_MODE access denied from non-local IP: "
                        f"ip={source_ip} origin={request.headers.get('origin')} "
                        f"host={request.headers.get('host')} path={request.url.path}"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Demo mode is only available from localhost",
                    )

            # Still try to authenticate if credentials are provided
            auth_ctx = await _authenticate_request(request)
            if auth_ctx:
                request.state.auth = auth_ctx
                return auth_ctx

            # Phase 120-03: Detect bot agents in demo mode via header or key prefix.
            # Bots get BOT_AGENT role instead of OPERATOR to prevent privilege escalation.
            _is_demo_bot = request.headers.get("X-Agent-Type", "").lower() == "bot" or (
                _extract_api_key(request) or ""
            ).startswith("sent_bot_")

            if _is_demo_bot:
                demo_ctx = AuthContext(
                    user_id="demo-bot",
                    role=SentinelRole.BOT_AGENT,
                    auth_method="demo_mode",
                    source_ip=source_ip,
                    email="bot@sentinel.local",
                    scopes=["bot_agent:all"],
                    metadata={"demo_mode": True},
                    is_bot_agent=True,
                )
            else:
                # Create demo context with ADMIN role so Supabase queries return all buildings
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
            logger.debug(f"Demo mode auth: path={request.url.path} ip={source_ip} is_bot={_is_demo_bot}")
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
            if settings.environment == "production":
                logger.error(f"DEMO_MODE role bypass attempted in production - path={request.url.path}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Service misconfigured",
                )

            source_ip = _extract_ip_address(request)

            # Restrict demo mode to localhost or configured allowed origins/hosts (C-4)
            _LOCALHOST_IPS = {"127.0.0.1", "::1", "localhost", "testclient", "unknown"}
            if source_ip not in _LOCALHOST_IPS and not _is_demo_origin_allowed(request):
                logger.warning(
                    f"DEMO_MODE role access denied from non-local IP: ip={source_ip} path={request.url.path}"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Demo mode is only available from localhost",
                )

            auth_ctx = await _authenticate_request(request)
            if auth_ctx:
                request.state.auth = auth_ctx
                return auth_ctx

            # Phase 120-03: Detect bot agents in demo mode via header or key prefix
            _is_demo_bot = request.headers.get("X-Agent-Type", "").lower() == "bot" or (
                _extract_api_key(request) or ""
            ).startswith("sent_bot_")

            if _is_demo_bot:
                demo_ctx = AuthContext(
                    user_id="demo-bot",
                    role=SentinelRole.BOT_AGENT,
                    auth_method="demo_mode",
                    source_ip=source_ip,
                    email="bot@sentinel.local",
                    scopes=["bot_agent:all"],
                    metadata={"demo_mode": True},
                    is_bot_agent=True,
                )
            else:
                # Create demo context - request the highest required role (avoids 30/min admin limit if possible)
                # If ADMIN is required, use ADMIN, otherwise use highest required role
                demo_role = max(roles, key=lambda r: ROLE_HIERARCHY.get(r, 0))
                demo_ctx = AuthContext(
                    user_id="demo-user",
                    role=demo_role,
                    auth_method="demo_mode",
                    source_ip=source_ip,
                    email="demo@sentinel.local",
                    scopes=[f"{demo_role.value}:all"],
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


# Convenience dependency for OPERATOR-level auth requirement
require_operator = require_auth(AuthLevel.OPERATOR)


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
        site_id = request.headers.get("X-Site-Id", "site-002")  # Default to site-002

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

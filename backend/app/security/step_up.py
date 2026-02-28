"""
Step-Up Authentication.

Requires re-authentication for sensitive operations:
    - Device control commands
    - Configuration changes
    - Recommendation approval/rejection

Issues short-lived step-up sessions (STEP_UP_VALIDITY_SECONDS)
that are validated alongside the primary JWT.

Server-side session store keyed by (user_id, device_id).
Device_id comes from X-Device-Id header or cookie.

Phase 137-04.
"""

import logging
import os
import time
from collections import defaultdict
from typing import Optional

import bcrypt
from fastapi import HTTPException, Request, status

from app.config.settings import settings
from app.middleware.auth_middleware import _authenticate_request, _extract_ip_address
from app.models.auth import AuthContext
from app.security.constants import STEP_UP_VALIDITY_SECONDS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Rate limit: max 5 attempts per 15 minutes per user
STEP_UP_MAX_ATTEMPTS = 5
STEP_UP_LOCKOUT_SECONDS = 15 * 60  # 15 minutes

# Admin PIN hash from environment
_ADMIN_PIN_HASH: str = os.environ.get("ADMIN_PIN_HASH", "")

# ---------------------------------------------------------------------------
# In-memory session store
#
# Key: (user_id, device_id)
# Value: expiry timestamp (epoch seconds)
# ---------------------------------------------------------------------------

_step_up_sessions: dict[tuple[str, str], float] = {}

# Rate limiting: user_id -> list of attempt timestamps
_step_up_attempts: dict[str, list[float]] = defaultdict(list)

# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------


def _cleanup_expired_sessions() -> None:
    """Remove expired sessions from the store. Called periodically."""
    now = time.time()
    expired_keys = [k for k, exp in _step_up_sessions.items() if exp <= now]
    for k in expired_keys:
        del _step_up_sessions[k]


def _check_rate_limit(user_id: str) -> None:
    """Check if user has exceeded step-up attempt rate limit.

    Raises:
        HTTPException 429 if rate limit exceeded.
    """
    now = time.time()
    cutoff = now - STEP_UP_LOCKOUT_SECONDS

    # Prune old entries
    recent = [t for t in _step_up_attempts[user_id] if t > cutoff]
    _step_up_attempts[user_id] = recent

    if len(recent) >= STEP_UP_MAX_ATTEMPTS:
        logger.warning(
            "Step-up rate limit exceeded: user=%s attempts=%d",
            user_id,
            len(recent),
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many step-up attempts. Try again in 15 minutes.",
        )


def _record_failed_attempt(user_id: str) -> None:
    """Record a failed step-up attempt for rate limiting."""
    _step_up_attempts[user_id].append(time.time())


def create_step_up_session(user_id: str, device_id: str, pin: str) -> bool:
    """Validate PIN and create a step-up session if valid.

    Args:
        user_id: Authenticated user ID.
        device_id: Device identifier from request header/cookie.
        pin: PIN to validate against ADMIN_PIN_HASH.

    Returns:
        True if session created, False if PIN invalid.

    Raises:
        HTTPException 429 if rate limit exceeded.
        HTTPException 503 if ADMIN_PIN_HASH not configured.
    """
    # Check rate limit
    _check_rate_limit(user_id)

    # Ensure PIN hash is configured
    pin_hash = _ADMIN_PIN_HASH
    if not pin_hash:
        logger.error("ADMIN_PIN_HASH environment variable is not configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Step-up authentication is not configured. Set ADMIN_PIN_HASH env var.",
        )

    # Validate PIN against bcrypt hash
    try:
        pin_bytes = pin.encode("utf-8")
        hash_bytes = pin_hash.encode("utf-8")

        if not bcrypt.checkpw(pin_bytes, hash_bytes):
            _record_failed_attempt(user_id)
            logger.warning(
                "Step-up PIN validation failed: user=%s device=%s",
                user_id,
                device_id,
            )
            # Audit: STEP_UP_FAILED (Phase 137-09)
            try:
                from app.security.audit_events import audit_step_up_failed

                audit_step_up_failed(user=user_id, device_id=device_id)
            except Exception:
                pass
            return False
    except ValueError as e:
        logger.error("Invalid ADMIN_PIN_HASH format: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Step-up authentication misconfigured.",
        )

    # Cleanup expired sessions before creating new one
    _cleanup_expired_sessions()

    # Create session
    expiry = time.time() + STEP_UP_VALIDITY_SECONDS
    _step_up_sessions[(user_id, device_id)] = expiry

    logger.info(
        "Step-up session created: user=%s device=%s ttl=%ds",
        user_id,
        device_id,
        STEP_UP_VALIDITY_SECONDS,
    )
    return True


def has_valid_step_up_session(user_id: str, device_id: str) -> bool:
    """Check if a valid step-up session exists for (user_id, device_id).

    Args:
        user_id: Authenticated user ID.
        device_id: Device identifier.

    Returns:
        True if valid session exists.
    """
    expiry = _step_up_sessions.get((user_id, device_id))
    if expiry is None:
        return False
    if time.time() > expiry:
        # Expired — clean up
        _step_up_sessions.pop((user_id, device_id), None)
        return False
    return True


def revoke_step_up_session(user_id: str, device_id: str) -> bool:
    """Explicitly revoke a step-up session.

    Args:
        user_id: Authenticated user ID.
        device_id: Device identifier.

    Returns:
        True if session was found and revoked.
    """
    return _step_up_sessions.pop((user_id, device_id), None) is not None


def _extract_device_id(request: Request) -> str:
    """Extract device_id from request header or cookie.

    Falls back to source IP if no device identifier provided.

    Args:
        request: FastAPI request.

    Returns:
        Device identifier string.
    """
    # Check header first
    device_id = request.headers.get("X-Device-Id", "")
    if device_id:
        return device_id

    # Check cookie
    device_id = request.cookies.get("device_id", "")
    if device_id:
        return device_id

    # Fallback to IP
    return _extract_ip_address(request)


# ---------------------------------------------------------------------------
# FastAPI dependency: require_step_up
# ---------------------------------------------------------------------------


def require_step_up():
    """FastAPI dependency that requires a valid step-up session.

    Must be used after require_auth — expects auth context on request.state.

    Returns 403 with detail "step_up_required" when no valid session exists.
    This allows the frontend to detect this specific case and show the PIN modal.

    Usage:
        @router.post("/api/device-controls/{code}/execute")
        async def execute_control(
            auth: AuthContext = Depends(require_auth(AuthLevel.OPERATOR)),
            _step_up: None = Depends(require_step_up()),
        ):
            ...
    """

    async def _dependency(request: Request) -> None:
        # Demo mode bypass: step-up is not enforced in demo mode
        if settings.demo_mode:
            return None

        # Get auth context from request state (set by require_auth upstream)
        auth_ctx: Optional[AuthContext] = getattr(request.state, "auth", None)

        if auth_ctx is None:
            # If no auth context, try to authenticate
            auth_ctx = await _authenticate_request(request)
            if auth_ctx is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                    headers={"WWW-Authenticate": "Bearer"},
                )

        user_id = auth_ctx.user_id
        device_id = _extract_device_id(request)

        if not has_valid_step_up_session(user_id, device_id):
            logger.info(
                "Step-up required: user=%s device=%s path=%s",
                user_id,
                device_id,
                request.url.path,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="step_up_required",
            )

        return None

    return _dependency


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _reset_sessions_for_testing() -> None:
    """Clear all step-up sessions and rate limits. For testing only."""
    _step_up_sessions.clear()
    _step_up_attempts.clear()


def _set_pin_hash_for_testing(pin_hash: str) -> None:
    """Override the PIN hash for testing. For testing only."""
    global _ADMIN_PIN_HASH
    _ADMIN_PIN_HASH = pin_hash

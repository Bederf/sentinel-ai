"""
Authentication API endpoints for SENTINEL BMS Platform.

Simple email-based authentication for demo purposes.
Users enter their email address and receive a JWT token for session management.

FSR Domain: 4.6 - Logical Access Control (MFA for privileged access)
FSR Domain: 4.7 - Logical Access Control
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config.settings import settings
from app.middleware.auth_middleware import create_jwt_token, validate_jwt_token, _extract_ip_address
from app.models.auth import (
    AUTH_LEVEL_TO_MIN_ROLE,
    AuthContext,
    AuthLevel,
    SentinelRole,
)
from app.services.mfa_service import get_mfa_service
from app.services.token_blacklist_service import token_blacklist

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# Default limiter (can be overridden via init_rate_limiter)
limiter = Limiter(key_func=get_remote_address)


def init_rate_limiter(shared_limiter):
    """Initialize the shared rate limiter from main.py.

    Called during app startup to inject the limiter dependency.

    Args:
        shared_limiter: Limiter instance from app.state.limiter
    """
    global limiter
    limiter = shared_limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# ---------------------------------------------------------------------------
# Brute-force protection (Phase 58-04 M-5)
# In-memory tracking: 5 failed attempts per email within 15 minutes = lockout
# ---------------------------------------------------------------------------
_login_attempts: dict[str, list[datetime]] = defaultdict(list)
_MAX_LOGIN_ATTEMPTS = 5
_LOCKOUT_MINUTES = 15


def _check_brute_force(identifier: str) -> None:
    """Raise 429 if too many recent failed login attempts for *identifier*."""
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=_LOCKOUT_MINUTES)
    # Prune old entries
    recent = [t for t in _login_attempts[identifier] if t > cutoff]
    _login_attempts[identifier] = recent
    if len(recent) >= _MAX_LOGIN_ATTEMPTS:
        logger.warning(f"Brute-force lockout triggered for {identifier}")
        raise HTTPException(
            status_code=429,
            detail=f"Too many login attempts. Try again in {_LOCKOUT_MINUTES} minutes.",
        )


def _record_failed_attempt(identifier: str) -> None:
    """Record a failed login attempt for *identifier*."""
    _login_attempts[identifier].append(datetime.utcnow())

# Demo users store - in production this would be in Supabase
# Email -> User mapping
_DEMO_USERS = {
    # Admin users
    "admin@sentinel.bms": {
        "user_id": "admin-001",
        "email": "admin@sentinel.bms",
        "full_name": "SENTINEL Administrator",
        "role": SentinelRole.ADMIN,
    },
    "bederf@gmail.com": {
        "user_id": "user-001",
        "email": "bederf@gmail.com",
        "full_name": "System Owner",
        "role": SentinelRole.ADMIN,
    },
    # Operator users (can control devices)
    "operator@sentinel.bms": {
        "user_id": "operator-001",
        "email": "operator@sentinel.bms",
        "full_name": "BMS Operator",
        "role": SentinelRole.OPERATOR,
    },
    # Developer users
    "dev@sentinel.bms": {
        "user_id": "dev-001",
        "email": "dev@sentinel.bms",
        "full_name": "Developer",
        "role": SentinelRole.DEVELOPER,
    },
    # Auditor users (read-only)
    "auditor@sentinel.bms": {
        "user_id": "auditor-001",
        "email": "auditor@sentinel.bms",
        "full_name": "Compliance Auditor",
        "role": SentinelRole.AUDITOR,
    },
}


def _create_jwt_token(user_data: dict, token_type: str = "access") -> str:
    """Create a JWT token for the user.

    Args:
        user_data: User information dict
        token_type: Token type - "access" or "refresh"

    Returns:
        Encoded JWT token string
    """
    # Use centralized token creation from middleware (Phase 65-02)
    role_value = user_data["role"].value if isinstance(user_data["role"], SentinelRole) else user_data["role"]
    return create_jwt_token(
        user_id=user_data["user_id"],
        email=user_data["email"],
        role=role_value,
        full_name=user_data["full_name"],
        token_type=token_type,
    )


def _extract_ip_address(request: Request) -> str:
    """Extract client IP from request with proxy support."""
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


@router.post("/login")
@limiter.limit("5/minute")
async def login_with_email(request: Request, email: str):
    """Login with email address (simple authentication).

    The email address IS the credential - no password required.
    Token expires after jwt_expiration_hours (default 8h, one work shift).

    Known demo users get specific roles (admin, operator, developer, auditor).
    Unknown emails automatically get AUDITOR (read-only) role.

    For ADMIN users, MFA is required (FSR 4.6.3). If MFA is required:
    - If not enrolled: Returns mfa_required=true, mfa_enrolled=false (prompt enrollment)
    - If enrolled but not verified: Returns mfa_required=true, mfa_enrolled=true (prompt challenge)
    - Token is only issued after MFA verification for users with MFA enabled

    Args:
        request: FastAPI request
        email: User's email address

    Returns:
        LoginResponse with JWT token, user info, role, and MFA status
    """
    email = email.strip().lower()

    # Brute-force check (Phase 58-04 M-5) — keyed by email
    _check_brute_force(email)

    # Look up user in demo store
    user_data = _DEMO_USERS.get(email)

    is_new_user = False
    if user_data:
        # Known demo user
        user_info = user_data.copy()
        logger.info(f"Demo user login: {email} as {user_data['role'].value}")
    else:
        # Unknown email - create a new AUDITOR (read-only) user
        # In production, this would require proper user registration
        user_info = {
            "user_id": f"user-{email[:8]}",
            "email": email,
            "full_name": email.split("@")[0].title(),
            "role": SentinelRole.AUDITOR,  # Read-only by default
        }
        is_new_user = True
        logger.info(f"New user login: {email} as AUDITOR (read-only)")

    # Check MFA status for the user (FSR 4.6.3 - MFA for privileged access)
    mfa_service = get_mfa_service()
    mfa_required = mfa_service.is_mfa_required(user_info["role"])
    mfa_enrolled = mfa_service.is_mfa_enrolled(email)
    mfa_enabled = mfa_service.is_mfa_enabled(email)

    # Get client IP
    source_ip = _extract_ip_address(request)
    user_agent = request.headers.get("User-Agent")

    # If MFA is required and enabled, don't issue token yet - require MFA challenge
    if mfa_required and mfa_enabled:
        logger.info(f"MFA challenge required for {email} (admin with MFA enabled)")

        # Log partial login (awaiting MFA)
        try:
            from app.database.repositories.login_audit_repository import (
                get_login_audit_repository,
            )
            audit_repo = get_login_audit_repository()
            audit_repo.log_login(
                user_email=email,
                user_id=user_info["user_id"],
                user_role=user_info["role"].value,
                source_ip=source_ip,
                user_agent=user_agent,
                is_new_user=is_new_user,
                success=True,  # Auth succeeded, MFA pending
                failure_reason="mfa_challenge_pending",
            )
        except Exception as e:
            logger.warning(f"Failed to audit log login for {email}: {e}")

        # Return partial auth response - frontend must complete MFA challenge
        return {
            "token": None,  # No token until MFA verified
            "user": {
                "id": user_info["user_id"],
                "email": user_info["email"],
                "full_name": user_info["full_name"],
                "role": user_info["role"].value,
            },
            "expires_at": None,
            "mfa_required": True,
            "mfa_enrolled": True,
            "mfa_challenge_pending": True,
            "message": "MFA verification required. Please enter your TOTP code.",
        }

    # If MFA is required but not enrolled, issue token but flag enrollment needed
    # This allows the user to access the MFA enrollment endpoints
    # Phase 65-02: Issue both access and refresh tokens
    access_token = _create_jwt_token(user_info, token_type="access")
    refresh_token = _create_jwt_token(user_info, token_type="refresh")

    # Grant default building access for new users
    if is_new_user:
        try:
            from app.database.repositories.user_site_access_repository import (
                get_user_site_access_repository,
            )
            access_repo = get_user_site_access_repository()
            if access_repo.grant_default_access(email, granted_by="system"):
                logger.info(f"Granted default building access to new user: {email}")
        except Exception as e:
            # Non-critical, user can be granted access later by admin
            logger.warning(f"Failed to grant default access to {email}: {e}")

    # Log the login
    logger.info(
        f"Login success: email={email} user_id={user_info['user_id']} "
        f"role={user_info['role'].value} ip={source_ip}"
    )

    # Audit log the login to database
    try:
        from app.database.repositories.login_audit_repository import (
            get_login_audit_repository,
        )
        audit_repo = get_login_audit_repository()
        audit_repo.log_login(
            user_email=email,
            user_id=user_info["user_id"],
            user_role=user_info["role"].value,
            source_ip=source_ip,
            user_agent=user_agent,
            is_new_user=is_new_user,
            success=True,
        )
    except Exception as e:
        # Non-critical, don't fail login if audit fails
        logger.warning(f"Failed to audit log login for {email}: {e}")

    response = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user_info["user_id"],
            "email": user_info["email"],
            "full_name": user_info["full_name"],
            "role": user_info["role"].value,
        },
        "expires_at": (datetime.utcnow() + timedelta(minutes=settings.jwt_access_token_ttl_minutes)).isoformat(),
        "mfa_required": mfa_required,
        "mfa_enrolled": mfa_enrolled,
        "mfa_challenge_pending": False,
    }

    # Add enrollment prompt for admins who haven't enrolled yet
    if mfa_required and not mfa_enrolled:
        response["message"] = "MFA enrollment required for admin users. Please set up MFA."

    return response


@router.post("/login/mfa-complete")
@limiter.limit("5/minute")
async def complete_mfa_login(request: Request, email: str, mfa_code: str):
    """Complete login after MFA verification.

    Called after initial login when MFA challenge is pending.
    Verifies the TOTP code and issues the JWT token.

    Args:
        request: FastAPI request
        email: User's email address (from initial login)
        mfa_code: 6-digit TOTP code from authenticator app

    Returns:
        LoginResponse with JWT token if MFA verification successful

    Raises:
        HTTPException 400 if MFA verification fails
        HTTPException 404 if user not found
    """
    email = email.strip().lower()

    # Brute-force check (Phase 58-04 M-5) — keyed by email
    _check_brute_force(email)

    # Look up user
    user_data = _DEMO_USERS.get(email)
    if not user_data:
        # Check if it's a dynamic user (non-demo)
        user_data = {
            "user_id": f"user-{email[:8]}",
            "email": email,
            "full_name": email.split("@")[0].title(),
            "role": SentinelRole.AUDITOR,
        }

    user_info = user_data.copy() if isinstance(user_data.get("role"), SentinelRole) else user_data

    # Verify MFA code
    mfa_service = get_mfa_service()
    source_ip = _extract_ip_address(request)
    user_agent = request.headers.get("User-Agent")

    success, error = mfa_service.verify_code(
        user_email=email,
        code=mfa_code,
        source_ip=source_ip,
        user_agent=user_agent,
    )

    if not success:
        _record_failed_attempt(email)
        logger.warning(f"MFA verification failed for {email}: {error}")
        raise HTTPException(status_code=400, detail=error)

    # MFA verified - issue token pair (Phase 65-02)
    access_token = _create_jwt_token(user_info, token_type="access")
    refresh_token = _create_jwt_token(user_info, token_type="refresh")

    logger.info(f"MFA login completed for {email}")

    # Update audit log
    try:
        from app.database.repositories.login_audit_repository import (
            get_login_audit_repository,
        )
        audit_repo = get_login_audit_repository()
        audit_repo.log_login(
            user_email=email,
            user_id=user_info["user_id"],
            user_role=user_info["role"].value if isinstance(user_info["role"], SentinelRole) else user_info["role"],
            source_ip=source_ip,
            user_agent=user_agent,
            is_new_user=False,
            success=True,
        )
    except Exception as e:
        logger.warning(f"Failed to audit log MFA login for {email}: {e}")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user_info["user_id"],
            "email": user_info["email"],
            "full_name": user_info["full_name"],
            "role": user_info["role"].value if isinstance(user_info["role"], SentinelRole) else user_info["role"],
        },
        "expires_at": (datetime.utcnow() + timedelta(minutes=settings.jwt_access_token_ttl_minutes)).isoformat(),
        "mfa_verified": True,
    }


@router.post("/verify")
async def verify_token(request: Request, token: str):
    """Verify a JWT token and return user info.

    Used by frontend to check if a stored token is still valid.
    Now uses centralized validation with blacklist checking (Phase 65-02).

    Args:
        request: FastAPI request
        token: JWT token string

    Returns:
        User info if token is valid

    Raises:
        HTTPException 401 if token is invalid or expired
    """
    payload = validate_jwt_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Extract user info from payload
    role_str = payload.get("role", "auditor")
    try:
        role = SentinelRole(role_str)
    except ValueError:
        role = SentinelRole.AUDITOR

    return {
        "valid": True,
        "user": {
            "id": payload.get("sub"),
            "email": payload.get("email"),
            "full_name": payload.get("full_name"),
            "role": role.value,
        },
    }


@router.get("/me")
async def get_current_user(request: Request):
    """Get current authenticated user info from Bearer token.

    Args:
        request: FastAPI request (must have Authorization header)

    Returns:
        Current user info

    Raises:
        HTTPException 401 if not authenticated
    """
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No token provided")

    token = auth_header[7:]

    # Use centralized validation (Phase 65-02)
    payload = validate_jwt_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    role_str = payload.get("role", "auditor")
    try:
        role = SentinelRole(role_str)
    except ValueError:
        role = SentinelRole.AUDITOR

    return {
        "id": payload.get("sub"),
        "email": payload.get("email"),
        "full_name": payload.get("full_name"),
        "role": role.value,
        "authenticated_at": payload.get("iat"),
    }


@router.post("/logout")
async def logout(request: Request, refresh_token: Optional[str] = None):
    """Logout endpoint - blacklist tokens to invalidate them.

    Phase 65-02: Now actually invalidates tokens by blacklisting them in Redis.

    Args:
        request: FastAPI request
        refresh_token: Optional refresh token to invalidate

    Returns:
        Success message
    """
    # Extract and blacklist access token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        access_token = auth_header[7:]
        payload = validate_jwt_token(access_token)
        if payload:
            jti = payload.get("jti")
            if jti:
                # Calculate remaining TTL
                exp = payload.get("exp", 0)
                now = int(datetime.utcnow().timestamp())
                ttl = max(0, exp - now)
                token_blacklist.blacklist_token(jti, ttl_seconds=ttl)

    # Blacklist refresh token if provided
    if refresh_token:
        payload = validate_jwt_token(refresh_token)
        if payload and payload.get("token_type") == "refresh":
            jti = payload.get("jti")
            if jti:
                exp = payload.get("exp", 0)
                now = int(datetime.utcnow().timestamp())
                ttl = max(0, exp - now)
                token_blacklist.blacklist_token(jti, ttl_seconds=ttl)

    return {"message": "Logged out successfully"}


@router.post("/refresh")
@limiter.limit("10/minute")
async def refresh_access_token(request: Request, refresh_token: str):
    """Refresh access token using a valid refresh token.

    Phase 65-02: Implements token rotation - old refresh token is invalidated,
    new access + refresh token pair is issued.

    Args:
        request: FastAPI request
        refresh_token: Valid refresh token

    Returns:
        New access_token and refresh_token

    Raises:
        HTTPException 401 if refresh token is invalid
    """
    payload = validate_jwt_token(refresh_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    # Verify this is a refresh token
    if payload.get("token_type") != "refresh":
        raise HTTPException(status_code=401, detail="Token is not a refresh token")

    # Get user info from payload
    user_info = {
        "user_id": payload.get("sub"),
        "email": payload.get("email"),
        "full_name": payload.get("full_name"),
        "role": payload.get("role"),
    }

    # Blacklist old refresh token (rotation)
    old_jti = payload.get("jti")
    if old_jti:
        exp = payload.get("exp", 0)
        now = int(datetime.utcnow().timestamp())
        ttl = max(0, exp - now)
        token_blacklist.blacklist_token(old_jti, ttl_seconds=ttl)

    # Issue new token pair
    new_access_token = _create_jwt_token(user_info, token_type="access")
    new_refresh_token = _create_jwt_token(user_info, token_type="refresh")

    logger.info(f"Token refresh for user {user_info['user_id']}")

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "expires_at": (datetime.utcnow() + timedelta(minutes=settings.jwt_access_token_ttl_minutes)).isoformat(),
    }

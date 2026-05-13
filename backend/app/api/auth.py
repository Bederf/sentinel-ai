"""
Authentication API endpoints for SENTINEL BMS Platform.

Email-based authentication with Supabase-backed user registry.
Users must be pre-registered; unknown emails are rejected.

FSR Domain: 4.6 - Logical Access Control (MFA for privileged access)
FSR Domain: 4.7 - Logical Access Control
"""

import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta

import bcrypt
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field

from app.config.settings import settings
from app.database.repositories.module_access_repository import get_module_access_repository
from app.database.repositories.system_settings_repository import SystemSettingsRepository
from app.database.repositories.user_repository import get_user_repository
from app.database.supabase_client import get_supabase_client
from app.middleware.auth_middleware import (
    _extract_ip_address,
    create_jwt_token,
    validate_jwt_token,
)
from app.middleware.rate_limiter import limiter
from app.models.auth import SentinelRole, generate_api_key
from app.models.module_registry import ModuleType
from app.security.step_up import (
    _extract_device_id,
    create_step_up_session,
)
from app.services.mfa_service import get_mfa_service
from app.services.session_service import session_service
from app.services.token_blacklist_service import token_blacklist

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HttpOnly cookie helpers (Phase 193 security hardening)
# ---------------------------------------------------------------------------
_REFRESH_COOKIE_NAME = "sentinel_refresh_token"
_ACCESS_COOKIE_NAME = "sentinel_access_token"


def _make_refresh_cookie(refresh_token: str) -> dict:
    """Build Set-Cookie params for the refresh token HttpOnly cookie."""
    return {
        "key": _REFRESH_COOKIE_NAME,
        "value": refresh_token,
        "max_age": settings.jwt_refresh_token_ttl_days * 86400,
        "path": "/api/auth",
        "httponly": True,
        "secure": True,
        "samesite": "strict",
    }


def _make_access_cookie(access_token: str) -> dict:
    """Build Set-Cookie params for the access token (non-HttpOnly, for read by JS)."""
    return {
        "key": _ACCESS_COOKIE_NAME,
        "value": access_token,
        "max_age": settings.jwt_access_token_ttl_minutes * 60,
        "path": "/",
        "httponly": False,
        "secure": True,
        "samesite": "lax",
    }


def _clear_auth_cookies() -> list[dict]:
    """Build Set-Cookie params to clear all auth cookies."""
    return [
        {"key": _REFRESH_COOKIE_NAME, "value": "", "max_age": 0, "path": "/api/auth", "httponly": True, "secure": True, "samesite": "strict"},
        {"key": _ACCESS_COOKIE_NAME, "value": "", "max_age": 0, "path": "/", "httponly": False, "secure": True, "samesite": "lax"},
    ]


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Attach both auth cookies to a response object."""
    for params in [_make_access_cookie(access_token), _make_refresh_cookie(refresh_token)]:
        response.set_cookie(**params)

# ---------------------------------------------------------------------------
# Brute-force protection (Phase 58-04 M-5)
# In-memory tracking: 5 failed attempts per email within 15 minutes = lockout
# ---------------------------------------------------------------------------
_login_attempts: dict[str, list[datetime]] = defaultdict(list)
_MAX_LOGIN_ATTEMPTS = 5
_LOCKOUT_MINUTES = 15


class ApiKeyCreateRequest(BaseModel):
    owner: str | None = None
    scopes: list[str] = Field(default_factory=list)
    role: str = "auditor"
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class RefreshTokenRequest(BaseModel):
    """SECURITY: Refresh token must be in request body, not URL (Phase 75-07)"""

    refresh_token: str = Field(..., description="Valid refresh token")


class AccessRequestCreateRequest(BaseModel):
    """Public access request submitted from the login screen."""

    email: EmailStr
    full_name: str | None = None
    company: str | None = None
    phone: str | None = None
    site_code: str = Field(..., description="Site code for access request")
    requested_modules: list[str] = Field(default_factory=list)
    notes: str | None = None


def _get_current_user_from_request(request: Request) -> dict:
    """Extract current user payload from access token."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No token provided")
    token = auth_header[7:]
    payload = validate_jwt_token(token, required_token_type="access")
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
        "role": role,
        "jti": payload.get("jti"),
    }


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


# ---------------------------------------------------------------------------
# Admin emails from environment (Phase 137-02)
# Comma-separated list of admin emails. Falls back to sentinel default.
# ---------------------------------------------------------------------------
_ADMIN_EMAILS: list[str] = [
    e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "admin@sentinel.bms").split(",") if e.strip()
]

# Admin PIN hash from environment (Phase 137-02)
# Generate with: python -c "import bcrypt; print(bcrypt.hashpw(b'YOUR_PIN', bcrypt.gensalt()).decode())"
_ADMIN_PIN_HASH: str = os.environ.get("ADMIN_PIN_HASH", "")


# User repository — canonical Supabase-backed store
_user_repo = get_user_repository()


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


@router.post("/login")
@limiter.limit("5/15minutes")
async def login_with_email(request: Request, email: str):
    """Login with email address.

    The email address IS the credential - no password required.
    Token expires after jwt_expiration_hours (default 8h, one work shift).

    Users must be pre-registered in sentinel_users.
    Unknown emails are rejected with 403.

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
    try:
        email = email.strip().lower()

        # Brute-force check (Phase 58-04 M-5) — keyed by email
        _check_brute_force(email)

        # Look up user in the canonical sentinel_users store
        user_data = _user_repo.get_user_by_email(email)

        if not user_data:
            _record_failed_attempt(email)
            logger.warning("Login rejected — unregistered email: %s", email)
            raise HTTPException(
                status_code=403,
                detail="User not registered. Contact your administrator.",
            )

        # Map role string to SentinelRole enum
        role_str = user_data.get("role", "auditor")
        try:
            role = SentinelRole(role_str)
        except ValueError:
            role = SentinelRole.AUDITOR

        user_info = {
            "user_id": user_data.get("user_id", f"user-{email[:8]}"),
            "email": user_data["email"],
            "full_name": user_data.get("full_name", email.split("@")[0].title()),
            "role": role,
        }
        is_new_user = False
        logger.info("User login: %s as %s", email, role.value)

        # Check MFA status for the user (FSR 4.6.3 - MFA for privileged access)
        mfa_service = get_mfa_service()
        mfa_required = mfa_service.is_mfa_required(user_info["role"])
        mfa_enrolled = mfa_service.is_mfa_enrolled(email)
        mfa_enabled = mfa_service.is_mfa_enabled(email)

        # Check for MFA pause bypass (for development/testing)
        pause_mfa_email = os.getenv("PAUSE_MFA_FOR_EMAIL", "").strip()
        if pause_mfa_email and pause_mfa_email.lower() == email.lower():
            logger.info(f"MFA bypass for {email} (PAUSE_MFA_FOR_EMAIL match)")
            mfa_required = False
            mfa_enabled = False

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
        refresh_payload = validate_jwt_token(refresh_token, required_token_type="refresh") or {}
        refresh_jti = refresh_payload.get("jti", "")
        session_id = (
            session_service.create_session(
                user_id=user_info["user_id"],
                ip=source_ip,
                user_agent=user_agent,
                token_jti=refresh_jti,
            )
            if refresh_jti
            else None
        )

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
            f"Login success: email={email} user_id={user_info['user_id']} role={user_info['role'].value} ip={source_ip}"
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
            "session_id": session_id,
        }

        # Building simulation auto-starts on server boot (startup/events.py).
        # All users observe the same running simulation — no per-login queue needed.

        # Add enrollment prompt for admins who haven't enrolled yet
        if mfa_required and not mfa_enrolled:
            response["message"] = "MFA enrollment required for admin users. Please set up MFA."

        # Set HttpOnly refresh cookie + access cookie on successful login
        from fastapi.responses import JSONResponse
        json_response = JSONResponse(content=response)
        _set_auth_cookies(json_response, access_token, refresh_token)
        return json_response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login failed for {email}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Login failed")


class VerifyPinRequest(BaseModel):
    """Request body for PIN verification."""

    pin: str = Field(..., description="PIN code to verify")


@router.post("/verify-admin-pin")
@limiter.limit("5/15minutes")
async def verify_admin_pin(request: Request, body: VerifyPinRequest):
    """Verify an admin PIN against the server-side bcrypt hash.

    Phase 137-02: Server-side PIN validation replaces client-side comparison.
    The PIN hash is stored in the ADMIN_PIN_HASH environment variable.

    Args:
        request: FastAPI request
        body: Request body containing the PIN

    Returns:
        200 with {"valid": true} if PIN matches
        403 with {"valid": false} if PIN does not match
        503 if ADMIN_PIN_HASH is not configured
    """
    source_ip = _extract_ip_address(request)

    # Brute-force protection
    _check_brute_force(f"pin:{source_ip}")

    if not _ADMIN_PIN_HASH:
        logger.error("ADMIN_PIN_HASH environment variable is not configured")
        raise HTTPException(
            status_code=503,
            detail="PIN verification is not configured. Set ADMIN_PIN_HASH env var.",
        )

    pin_bytes = body.pin.encode("utf-8")
    hash_bytes = _ADMIN_PIN_HASH.encode("utf-8")

    try:
        if bcrypt.checkpw(pin_bytes, hash_bytes):
            logger.info(f"PIN verification success from ip={source_ip}")
            return {"valid": True}
        else:
            _record_failed_attempt(f"pin:{source_ip}")
            logger.warning(f"PIN verification failed from ip={source_ip}")
            raise HTTPException(status_code=403, detail="Invalid PIN")
    except (ValueError, AttributeError, TypeError) as e:
        # Invalid hash format, None hash, or wrong type
        logger.error(f"PIN verification error ({type(e).__name__}): {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="PIN verification misconfigured")


@router.post("/verify-settings-password")
@limiter.limit("5/15minutes")
async def verify_settings_password(request: Request, body: VerifyPinRequest):
    """Verify settings admin password against Supabase-stored hash.

    Reads the bcrypt hash from the system_settings table (key: settings_admin_password).
    Falls back to 503 if not configured.

    Args:
        request: FastAPI request
        body: Request body containing the password

    Returns:
        200 with {"valid": true} if password matches
        403 if password does not match
        503 if settings_admin_password is not configured
    """
    source_ip = _extract_ip_address(request)

    # Brute-force protection
    _check_brute_force(f"settings_pwd:{source_ip}")

    settings_repo = SystemSettingsRepository()
    stored_hash = settings_repo.get_value("settings_admin_password")

    if not stored_hash:
        logger.error("settings_admin_password system setting is not configured")
        raise HTTPException(
            status_code=503,
            detail="Settings password is not configured. Contact your administrator.",
        )

    try:
        if bcrypt.checkpw(body.pin.encode("utf-8"), stored_hash.encode("utf-8")):
            logger.info(f"Settings password verification success from ip={source_ip}")
            return {"valid": True}
        else:
            _record_failed_attempt(f"settings_pwd:{source_ip}")
            logger.warning(f"Settings password verification failed from ip={source_ip}")
            raise HTTPException(status_code=403, detail="Invalid password")
    except (ValueError, AttributeError, TypeError) as e:
        logger.error(f"Settings password verification error ({type(e).__name__}): {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Settings password misconfigured")


class StepUpRequest(BaseModel):
    """Request body for step-up authentication."""

    pin: str = Field(..., description="PIN code for step-up re-authentication")


@router.post("/step-up")
@limiter.limit("5/15minutes")
async def step_up_auth(request: Request, body: StepUpRequest):
    """Create a step-up authentication session for sensitive operations.

    Phase 137-04: Step-up auth requires re-authentication before control actions.
    The session is keyed by (user_id, device_id) and lasts STEP_UP_VALIDITY_SECONDS (15min).

    The user must be authenticated (Bearer token) before calling this endpoint.

    Args:
        request: FastAPI request (must have Authorization header)
        body: Request body containing the PIN

    Returns:
        200 with session info if PIN valid
        401 if not authenticated
        403 if PIN invalid
        429 if rate limited
        503 if ADMIN_PIN_HASH not configured
    """
    # Get authenticated user
    user = _get_current_user_from_request(request)
    user_id = user["id"]
    device_id = _extract_device_id(request)
    source_ip = _extract_ip_address(request)

    valid = create_step_up_session(
        user_id=user_id,
        device_id=device_id,
        pin=body.pin,
    )

    if not valid:
        logger.warning(
            "Step-up auth failed: user=%s device=%s ip=%s",
            user_id,
            device_id,
            source_ip,
        )
        raise HTTPException(
            status_code=403,
            detail="Invalid PIN",
        )

    logger.info(
        "Step-up auth success: user=%s device=%s ip=%s",
        user_id,
        device_id,
        source_ip,
    )
    return {
        "success": True,
        "message": "Step-up authentication granted",
        "validity_seconds": 900,
    }


@router.post("/access-request")
@limiter.limit("20/hour")
async def create_access_request(request: Request, payload: AccessRequestCreateRequest):
    """Submit an access request for module grants before first login."""
    email = payload.email.strip().lower()
    site_code = payload.site_code.strip().lower()

    # Validate requested modules against known module registry types
    valid_module_values = {module.value for module in ModuleType}
    requested_modules = [
        module.strip().lower() for module in payload.requested_modules if module.strip().lower() in valid_module_values
    ]

    try:
        client = get_supabase_client()
        building = client.table("sites").select("id, code").eq("code", site_code).limit(1).execute()
        if not building.data:
            raise HTTPException(status_code=404, detail=f"Unknown site code: {site_code}")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Access request validation failed for %s: %s", email, exc)
        raise HTTPException(status_code=500, detail="Unable to submit access request")

    repo = get_module_access_repository()
    created = repo.submit_access_request(
        user_email=email,
        site_code=site_code,
        requested_modules=requested_modules,
        full_name=payload.full_name,
        company=payload.company,
        phone=payload.phone,
        request_notes=payload.notes,
    )
    if not created:
        raise HTTPException(status_code=500, detail="Failed to save access request")

    logger.info(
        "Access request submitted email=%s site=%s modules=%s",
        email,
        site_code,
        ",".join(requested_modules),
    )
    return {
        "success": True,
        "request_id": created.get("id"),
        "status": created.get("status", "pending"),
        "message": "Access request submitted. Admin approval is required before module access is granted.",
    }


@router.post("/login/mfa-complete")
@limiter.limit("5/15minutes")
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

    # Look up user in the canonical sentinel_users store
    user_data = _user_repo.get_user_by_email(email)
    if not user_data:
        raise HTTPException(status_code=403, detail="User not registered. Contact your administrator.")

    # Map role string to SentinelRole enum
    role_str = user_data.get("role", "auditor")
    try:
        role = SentinelRole(role_str)
    except ValueError:
        role = SentinelRole.AUDITOR

    user_info = {
        "user_id": user_data.get("user_id", f"user-{email[:8]}"),
        "email": user_data["email"],
        "full_name": user_data.get("full_name", email.split("@")[0].title()),
        "role": role,
    }

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

    # Fallback to backup code verification (65-03)
    if not success:
        if mfa_service.verify_backup_code(user_info["user_id"], mfa_code):
            success = True
            error = ""
        else:
            _record_failed_attempt(email)
            logger.warning(f"MFA verification failed for {email}: {error}")
            raise HTTPException(status_code=400, detail=error)

    # MFA verified - issue token pair (Phase 65-02)
    access_token = _create_jwt_token(user_info, token_type="access")
    refresh_token = _create_jwt_token(user_info, token_type="refresh")
    refresh_payload = validate_jwt_token(refresh_token, required_token_type="refresh") or {}
    refresh_jti = refresh_payload.get("jti", "")
    session_id = (
        session_service.create_session(
            user_id=user_info["user_id"],
            ip=source_ip,
            user_agent=user_agent,
            token_jti=refresh_jti,
        )
        if refresh_jti
        else None
    )

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

    response = {
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
        "session_id": session_id,
    }

    # Set HttpOnly refresh cookie + access cookie on successful MFA login
    from fastapi.responses import JSONResponse
    json_response = JSONResponse(content=response)
    _set_auth_cookies(json_response, access_token, refresh_token)
    return json_response


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
async def logout(request: Request, refresh_token: str | None = None):
    """Logout endpoint - blacklist tokens to invalidate them.

    Phase 65-02: Now actually invalidates tokens by blacklisting them in Redis.
    Phase 65-04: Add audit logging for logout events
    Phase 75-07: SECURITY - Accept refresh_token in request body, not URL

    Args:
        request: FastAPI request
        refresh_token: Optional refresh token from query param (deprecated, kept for backward compatibility)

    Returns:
        Success message
    """
    user_id: str | None = None
    source_ip = _extract_ip_address(request)

    # SECURITY: Try to get refresh_token from request body first (Phase 75-07)
    body_refresh_token = None
    try:
        body = await request.json()
        body_refresh_token = body.get("refresh_token")
    except Exception:
        pass

    # Use body token if available, fall back to query param for backward compatibility
    if body_refresh_token:
        refresh_token = body_refresh_token

    # Extract and blacklist access token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        access_token = auth_header[7:]
        payload = validate_jwt_token(access_token, required_token_type="access")
        if payload:
            user_id = payload.get("sub")
            jti = payload.get("jti")
            if jti:
                # Calculate remaining TTL
                exp = payload.get("exp", 0)
                now = int(datetime.utcnow().timestamp())
                ttl = max(0, exp - now)
                token_blacklist.blacklist_token(jti, ttl_seconds=ttl)

    # Blacklist refresh token if provided
    if refresh_token:
        payload = validate_jwt_token(refresh_token, required_token_type="refresh")
        if payload and payload.get("token_type") == "refresh":
            user_id = user_id or payload.get("sub")
            jti = payload.get("jti")
            if jti:
                exp = payload.get("exp", 0)
                now = int(datetime.utcnow().timestamp())
                ttl = max(0, exp - now)
                token_blacklist.blacklist_token(jti, ttl_seconds=ttl)
                if user_id:
                    session = session_service.find_session_by_token_jti(user_id, jti)
                    if session and session.get("session_id"):
                        session_service.revoke_session(user_id, session["session_id"])

    # Log logout event (Phase 65-04)
    if user_id:
        try:
            from app.database.repositories.audit_repository import AuditRepository

            audit_repo = AuditRepository()
            audit_repo.log_security_event(event_type="LOGOUT", user_id=user_id, ip_address=source_ip, result="SUCCESS")
            logger.info(f"User {user_id} logged out successfully")
        except Exception as e:
            logger.warning(f"Failed to audit log logout for {user_id}: {e}")

    # Clear auth cookies on logout
    from fastapi.responses import JSONResponse
    json_response = JSONResponse(content={"message": "Logged out successfully"})
    for params in _clear_auth_cookies():
        json_response.set_cookie(**params)
    return json_response


@router.post("/refresh")
@limiter.limit("5/15minutes")
async def refresh_access_token(request: Request, body: RefreshTokenRequest):
    """Refresh access token using a valid refresh token.

    Phase 65-02: Implements token rotation - old refresh token is invalidated,
    new access + refresh token pair is issued.
    Phase 65-04: Add audit logging for token refresh
    Phase 75-07: SECURITY - Accept refresh_token in request body, not URL

    Args:
        request: FastAPI request
        body: Request body containing refresh_token (SECURITY: not in URL)

    Returns:
        New access_token and refresh_token

    Raises:
        HTTPException 401 if refresh token is invalid
    """
    source_ip = _extract_ip_address(request)
    refresh_token = body.refresh_token
    payload = validate_jwt_token(refresh_token, required_token_type="refresh")
    if not payload:
        # Log failed refresh attempt
        try:
            from app.database.repositories.audit_repository import AuditRepository

            audit_repo = AuditRepository()
            audit_repo.log_security_event(
                event_type="TOKEN_REFRESH",
                ip_address=source_ip,
                result="FAILED",
                details={"reason": "invalid_or_expired_token"},
            )
        except Exception as e:
            logger.warning(f"Failed to audit log failed token refresh: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    # Verify this is a refresh token
    if payload.get("token_type") != "refresh":
        # Log failed refresh attempt
        try:
            from app.database.repositories.audit_repository import AuditRepository

            audit_repo = AuditRepository()
            audit_repo.log_security_event(
                event_type="TOKEN_REFRESH",
                user_id=payload.get("sub"),
                ip_address=source_ip,
                result="FAILED",
                details={"reason": "not_a_refresh_token"},
            )
        except Exception as e:
            logger.warning(f"Failed to audit log token validation error: {e}")
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
        existing_session = session_service.find_session_by_token_jti(user_info["user_id"], old_jti)
        if existing_session and existing_session.get("session_id"):
            session_service.revoke_session(user_info["user_id"], existing_session["session_id"])

    # Issue new token pair
    new_access_token = _create_jwt_token(user_info, token_type="access")
    new_refresh_token = _create_jwt_token(user_info, token_type="refresh")
    new_refresh_payload = validate_jwt_token(new_refresh_token, required_token_type="refresh") or {}
    new_refresh_jti = new_refresh_payload.get("jti", "")
    session_id = (
        session_service.create_session(
            user_id=user_info["user_id"],
            ip=source_ip,
            user_agent=request.headers.get("User-Agent"),
            token_jti=new_refresh_jti,
        )
        if new_refresh_jti
        else None
    )

    # Log successful token refresh (Phase 65-04)
    try:
        from app.database.repositories.audit_repository import AuditRepository

        audit_repo = AuditRepository()
        audit_repo.log_security_event(
            event_type="TOKEN_REFRESH",
            user_id=user_info["user_id"],
            ip_address=source_ip,
            result="SUCCESS",
            details={"session_id": session_id},
        )
    except Exception as e:
        logger.warning(f"Failed to audit log token refresh for {user_info['user_id']}: {e}")

    logger.info(f"Token refresh for user {user_info['user_id']}")

    from fastapi.responses import JSONResponse
    response = {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "expires_at": (datetime.utcnow() + timedelta(minutes=settings.jwt_access_token_ttl_minutes)).isoformat(),
        "session_id": session_id,
    }
    json_response = JSONResponse(content=response)
    _set_auth_cookies(json_response, new_access_token, new_refresh_token)
    return json_response


@router.get("/sessions")
async def list_sessions(request: Request):
    """List active sessions for current user."""
    user = _get_current_user_from_request(request)
    sessions = session_service.get_active_sessions(user["id"])
    return {"sessions": sessions, "count": len(sessions)}


@router.delete("/sessions/{session_id}")
async def revoke_session(request: Request, session_id: str):
    """Revoke a specific session for current user.

    Phase 65-04: Add audit logging for session revocation
    """
    user = _get_current_user_from_request(request)
    source_ip = _extract_ip_address(request)
    revoked = session_service.revoke_session(user["id"], session_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="Session not found")

    # Log session revocation (Phase 65-04)
    try:
        from app.database.repositories.audit_repository import AuditRepository

        audit_repo = AuditRepository()
        audit_repo.log_security_event(
            event_type="SESSION_REVOKED",
            user_id=user["id"],
            ip_address=source_ip,
            result="SUCCESS",
            details={"session_id": session_id},
        )
        logger.info(f"User {user['id']} revoked session {session_id}")
    except Exception as e:
        logger.warning(f"Failed to audit log session revocation: {e}")

    return {"message": "Session revoked", "session_id": session_id}


@router.delete("/sessions")
async def revoke_all_sessions(request: Request):
    """Revoke all sessions for current user.

    Phase 65-04: Add audit logging for bulk session revocation
    """
    user = _get_current_user_from_request(request)
    source_ip = _extract_ip_address(request)
    revoked_count = session_service.revoke_all_sessions(user["id"])

    # Log all sessions revocation (Phase 65-04)
    try:
        from app.database.repositories.audit_repository import AuditRepository

        audit_repo = AuditRepository()
        audit_repo.log_security_event(
            event_type="SESSION_REVOKED",
            user_id=user["id"],
            ip_address=source_ip,
            result="SUCCESS",
            details={"revoked_count": revoked_count, "action": "revoke_all"},
        )
        logger.info(f"User {user['id']} revoked all {revoked_count} sessions")
    except Exception as e:
        logger.warning(f"Failed to audit log revoke all sessions: {e}")

    return {"message": "Sessions revoked", "revoked_count": revoked_count}


@router.post("/api-keys")
@limiter.limit("5/15minutes")
async def create_api_key(request: Request, body: ApiKeyCreateRequest):
    """Create an API key and persist its hash in database.

    Phase 65-04: Add audit logging for API key creation
    """
    user = _get_current_user_from_request(request)
    owner = body.owner or user["email"] or user["id"]
    source_ip = _extract_ip_address(request)

    # Non-admin users can only create keys for themselves.
    if user["role"] != SentinelRole.ADMIN and owner != (user["email"] or user["id"]):
        raise HTTPException(status_code=403, detail="Cannot create key for another owner")

    key_plaintext, key_hash = generate_api_key()
    key_prefix = key_plaintext[:8]

    expires_at = None
    if body.expires_in_days:
        expires_at = (datetime.utcnow() + timedelta(days=body.expires_in_days)).isoformat()

    role_value = body.role.lower().strip()
    if role_value not in {r.value for r in SentinelRole}:
        raise HTTPException(status_code=400, detail="Invalid role value")
    if user["role"] != SentinelRole.ADMIN and role_value != "auditor":
        raise HTTPException(status_code=403, detail="Only admin can create elevated API roles")

    try:
        client = get_supabase_client()
        insert_payload = {
            "key_hash": key_hash,
            "key_prefix": key_prefix,
            "owner": owner,
            "role": role_value,
            "scopes": body.scopes,
            "expires_at": expires_at,
            "revoked": False,
        }
        result = client.table("api_keys").insert(insert_payload).execute()
        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create API key")
        row = result.data[0]

        # Log API key creation (Phase 65-04)
        try:
            from app.database.repositories.audit_repository import AuditRepository

            audit_repo = AuditRepository()
            audit_repo.log_security_event(
                event_type="API_KEY_CREATED",
                user_id=user["id"],
                ip_address=source_ip,
                result="SUCCESS",
                details={
                    "key_id": row.get("id"),
                    "key_prefix": key_prefix,
                    "owner": owner,
                    "role": role_value,
                    "expires_in_days": body.expires_in_days,
                },
            )
            logger.info(f"User {user['id']} created API key {key_prefix} for {owner}")
        except Exception as e:
            logger.warning(f"Failed to audit log API key creation: {e}")

        return {
            "id": row.get("id"),
            "api_key": key_plaintext,  # shown once
            "key_prefix": row.get("key_prefix"),
            "owner": row.get("owner"),
            "role": row.get("role"),
            "scopes": row.get("scopes") or [],
            "created_at": row.get("created_at"),
            "expires_at": row.get("expires_at"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed creating API key: %s", e)
        raise HTTPException(status_code=503, detail="API key store unavailable")


@router.get("/api-keys")
async def list_api_keys(request: Request):
    """List API keys for current owner (or all for admin)."""
    user = _get_current_user_from_request(request)
    owner = user["email"] or user["id"]
    try:
        client = get_supabase_client()
        query = client.table("api_keys").select(
            "id,key_prefix,owner,role,scopes,created_at,last_used_at,expires_at,revoked"
        )
        if user["role"] != SentinelRole.ADMIN:
            query = query.eq("owner", owner)
        rows = query.order("created_at", desc=True).execute().data or []
        return {"api_keys": rows, "count": len(rows)}
    except Exception as e:
        logger.error("Failed listing API keys: %s", e)
        raise HTTPException(status_code=503, detail="API key store unavailable")


@router.delete("/api-keys/{api_key_id}")
async def revoke_api_key(request: Request, api_key_id: str):
    """Revoke API key by id.

    Phase 65-04: Add audit logging for API key revocation
    """
    user = _get_current_user_from_request(request)
    owner = user["email"] or user["id"]
    source_ip = _extract_ip_address(request)
    try:
        client = get_supabase_client()
        query = client.table("api_keys").update({"revoked": True}).eq("id", api_key_id)
        if user["role"] != SentinelRole.ADMIN:
            query = query.eq("owner", owner)
        result = query.execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="API key not found")
        # No cache to invalidate (removed in Phase 168-01)
        row = result.data[0]

        # Log API key revocation (Phase 65-04)
        try:
            from app.database.repositories.audit_repository import AuditRepository

            audit_repo = AuditRepository()
            audit_repo.log_security_event(
                event_type="API_KEY_REVOKED",
                user_id=user["id"],
                ip_address=source_ip,
                result="SUCCESS",
                details={"key_id": api_key_id, "key_prefix": row.get("key_prefix"), "owner": row.get("owner")},
            )
            logger.info(f"User {user['id']} revoked API key {api_key_id}")
        except Exception as e:
            logger.warning(f"Failed to audit log API key revocation: {e}")

        return {"message": "API key revoked", "id": api_key_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed revoking API key: %s", e)
        raise HTTPException(status_code=503, detail="API key store unavailable")

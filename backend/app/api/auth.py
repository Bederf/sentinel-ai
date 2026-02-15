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
from pydantic import BaseModel, EmailStr, Field

from app.config.settings import settings
from app.middleware.auth_middleware import create_jwt_token, validate_jwt_token, _extract_ip_address
from app.middleware.rate_limiter import limiter
from app.models.auth import SentinelRole, generate_api_key
from app.database.supabase_client import get_supabase_client
from app.services.mfa_service import get_mfa_service
from app.services.session_service import session_service
from app.services.token_blacklist_service import token_blacklist
from app.database.repositories.module_access_repository import get_module_access_repository
from app.models.module_registry import ModuleType
from app.services.lifecycle_orchestrator import get_lifecycle_orchestrator

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Brute-force protection (Phase 58-04 M-5)
# In-memory tracking: 5 failed attempts per email within 15 minutes = lockout
# ---------------------------------------------------------------------------
_login_attempts: dict[str, list[datetime]] = defaultdict(list)
_MAX_LOGIN_ATTEMPTS = 5
_LOCKOUT_MINUTES = 15


class ApiKeyCreateRequest(BaseModel):
    owner: Optional[str] = None
    scopes: list[str] = Field(default_factory=list)
    role: str = "auditor"
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=3650)


class RefreshTokenRequest(BaseModel):
    """SECURITY: Refresh token must be in request body, not URL (Phase 75-07)"""
    refresh_token: str = Field(..., description="Valid refresh token")


class AccessRequestCreateRequest(BaseModel):
    """Public access request submitted from the login screen."""
    email: EmailStr
    full_name: Optional[str] = None
    company: Optional[str] = None
    phone: Optional[str] = None
    site_code: str = Field(default="site-002")
    requested_modules: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


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
    # Wardew Automation Specialist
    "grant@wardew.co.za": {
        "user_id": "wardew-grant-001",
        "email": "grant@wardew.co.za",
        "full_name": "Grant - Wardew",
        "role": SentinelRole.AUDITOR,  # Read-only access for Wardew demo
    },
    # Solar/BESS Demo User
    "bederf@protonmail.com": {
        "user_id": "bederf-solar-001",
        "email": "bederf@protonmail.com",
        "full_name": "Bederf - Solar Demo",
        "role": SentinelRole.AUDITOR,  # Read-only for demo
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


@router.post("/login")
@limiter.limit("5/15minutes")
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
    try:

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
        refresh_payload = validate_jwt_token(refresh_token, required_token_type="refresh") or {}
        refresh_jti = refresh_payload.get("jti", "")
        session_id = session_service.create_session(
            user_id=user_info["user_id"],
            ip=source_ip,
            user_agent=user_agent,
            token_jti=refresh_jti,
        ) if refresh_jti else None

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
            "session_id": session_id,
        }

        # Auto-start demo for Grant (grant@wardew.co.za)
        # DISABLED: Comment out to prevent auto-start during testing
        # if email == "grant@wardew.co.za":
        #     try:
        #         # Reset orchestrator for fresh demo on login
        #         orchestrator = get_lifecycle_orchestrator()
        #         orchestrator.reset()
        #     
        #         # Auto-start Grant's primary scenario: HVAC+DALI+Sentinel AI (365-day annual)
        #         # This demonstrates full predictive AI control with seasonal variations
        #         orchestrator.run_scenario(
        #             scenario_name="grant_hvac_dali_ai_annual",
        #             duration_minutes=240.0  # 365 days compressed to 4 hours real time
        #         )
        #     
        #         response["demo_auto_start"] = True
        #         response["demo_type"] = "annual-demonstration"
        #         response["demo_description"] = "HVAC + DALI + Sentinel AI (365-day full-year with seasonal variations)"
        #         response["demo_scenario"] = "grant_hvac_dali_ai_annual"
        #         response["demo_status"] = "running"
        #         logger.info(f"Auto-started Grant demo scenario: grant_hvac_dali_ai_annual (365 days, ~4 hours real time)")
        #     except Exception as e:
        #         logger.error(f"Error auto-starting Grant demo: {e}")
        #         response["demo_auto_start"] = True
        #         response["demo_type"] = "three-method-comparison"
        #         response["demo_error"] = str(e)
    
        # Auto-start demo for Solar/BESS client (bederf@protonmail.com)
        if email == "bederf@protonmail.com":
            # Reset orchestrator for fresh demo on login
            orchestrator = get_lifecycle_orchestrator()
            orchestrator.reset()
            response["demo_auto_start"] = True
            response["demo_type"] = "solar-bess-comparison"
            response["demo_description"] = "Solar+BESS Baseline vs Solar+BESS with Sentinel AI optimization"

        # Add enrollment prompt for admins who haven't enrolled yet
        if mfa_required and not mfa_enrolled:
            response["message"] = "MFA enrollment required for admin users. Please set up MFA."

        return response



    except Exception as e:
        logger.error(f"Login failed for {email}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")


@router.post("/access-request")
@limiter.limit("20/hour")
async def create_access_request(request: Request, payload: AccessRequestCreateRequest):
    """Submit an access request for module grants before first login."""
    email = payload.email.strip().lower()
    site_code = payload.site_code.strip().lower()

    # Validate requested modules against known module registry types
    valid_module_values = {module.value for module in ModuleType}
    requested_modules = [
        module.strip().lower()
        for module in payload.requested_modules
        if module.strip().lower() in valid_module_values
    ]

    try:
        client = get_supabase_client()
        building = client.table("buildings").select("id, code").eq("code", site_code).limit(1).execute()
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
    session_id = session_service.create_session(
        user_id=user_info["user_id"],
        ip=source_ip,
        user_agent=user_agent,
        token_jti=refresh_jti,
    ) if refresh_jti else None

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

    # Auto-start demo for Grant (grant@wardew.co.za)
    if email == "grant@wardew.co.za":
        try:
            # Reset orchestrator for fresh demo on login
            orchestrator = get_lifecycle_orchestrator()
            orchestrator.reset()
            
            # Auto-start Grant's primary scenario: HVAC+DALI+Sentinel AI (365-day annual)
            # This demonstrates full predictive AI control with seasonal variations
            orchestrator.run_scenario(
                scenario_name="grant_hvac_dali_ai_annual",
                duration_minutes=240.0  # 365 days compressed to 4 hours real time
            )
            
            response["demo_auto_start"] = True
            response["demo_type"] = "annual-demonstration"
            response["demo_description"] = "HVAC + DALI + Sentinel AI (365-day full-year with seasonal variations)"
            response["demo_scenario"] = "grant_hvac_dali_ai_annual"
            response["demo_status"] = "running"
            logger.info(f"Auto-started Grant demo scenario: grant_hvac_dali_ai_annual (365 days, ~4 hours real time)")
        except Exception as e:
            logger.error(f"Error auto-starting Grant demo: {e}")
            response["demo_auto_start"] = True
            response["demo_type"] = "three-method-comparison"
            response["demo_error"] = str(e)
    
    # Auto-start demo for Solar/BESS client (bederf@protonmail.com)
    if email == "bederf@protonmail.com":
        # Reset orchestrator for fresh demo on login
        orchestrator = get_lifecycle_orchestrator()
        orchestrator.reset()
        response["demo_auto_start"] = True
        response["demo_type"] = "solar-bess-comparison"
        response["demo_description"] = "Solar+BESS Baseline vs Solar+BESS with Sentinel AI optimization"

    return response


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
    Phase 65-04: Add audit logging for logout events
    Phase 75-07: SECURITY - Accept refresh_token in request body, not URL

    Args:
        request: FastAPI request
        refresh_token: Optional refresh token from query param (deprecated, kept for backward compatibility)

    Returns:
        Success message
    """
    user_id: Optional[str] = None
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
            audit_repo.log_security_event(
                event_type='LOGOUT',
                user_id=user_id,
                ip_address=source_ip,
                result='SUCCESS'
            )
            logger.info(f"User {user_id} logged out successfully")
        except Exception as e:
            logger.warning(f"Failed to audit log logout for {user_id}: {e}")

    return {"message": "Logged out successfully"}


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
                event_type='TOKEN_REFRESH',
                ip_address=source_ip,
                result='FAILED',
                details={'reason': 'invalid_or_expired_token'}
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
                event_type='TOKEN_REFRESH',
                user_id=payload.get("sub"),
                ip_address=source_ip,
                result='FAILED',
                details={'reason': 'not_a_refresh_token'}
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
    session_id = session_service.create_session(
        user_id=user_info["user_id"],
        ip=source_ip,
        user_agent=request.headers.get("User-Agent"),
        token_jti=new_refresh_jti,
    ) if new_refresh_jti else None

    # Log successful token refresh (Phase 65-04)
    try:
        from app.database.repositories.audit_repository import AuditRepository
        audit_repo = AuditRepository()
        audit_repo.log_security_event(
            event_type='TOKEN_REFRESH',
            user_id=user_info['user_id'],
            ip_address=source_ip,
            result='SUCCESS',
            details={'session_id': session_id}
        )
    except Exception as e:
        logger.warning(f"Failed to audit log token refresh for {user_info['user_id']}: {e}")

    logger.info(f"Token refresh for user {user_info['user_id']}")

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "expires_at": (datetime.utcnow() + timedelta(minutes=settings.jwt_access_token_ttl_minutes)).isoformat(),
        "session_id": session_id,
    }


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
            event_type='SESSION_REVOKED',
            user_id=user["id"],
            ip_address=source_ip,
            result='SUCCESS',
            details={'session_id': session_id}
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
            event_type='SESSION_REVOKED',
            user_id=user["id"],
            ip_address=source_ip,
            result='SUCCESS',
            details={'revoked_count': revoked_count, 'action': 'revoke_all'}
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
                event_type='API_KEY_CREATED',
                user_id=user["id"],
                ip_address=source_ip,
                result='SUCCESS',
                details={
                    'key_id': row.get("id"),
                    'key_prefix': key_prefix,
                    'owner': owner,
                    'role': role_value,
                    'expires_in_days': body.expires_in_days
                }
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
        # Best-effort cache invalidation in auth middleware by hash
        row = result.data[0]
        key_hash = row.get("key_hash")
        if key_hash:
            try:
                from app.middleware.auth_middleware import _API_KEY_CACHE

                _API_KEY_CACHE.pop(key_hash, None)
            except Exception:
                pass

        # Log API key revocation (Phase 65-04)
        try:
            from app.database.repositories.audit_repository import AuditRepository
            audit_repo = AuditRepository()
            audit_repo.log_security_event(
                event_type='API_KEY_REVOKED',
                user_id=user["id"],
                ip_address=source_ip,
                result='SUCCESS',
                details={
                    'key_id': api_key_id,
                    'key_prefix': row.get("key_prefix"),
                    'owner': row.get("owner")
                }
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

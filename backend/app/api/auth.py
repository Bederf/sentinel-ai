"""
Authentication API endpoints for SENTINEL BMS Platform.

Simple email-based authentication for demo purposes.
Users enter their email address and receive a JWT token for session management.

FSR Domain: 4.6 - Logical Access Control (MFA for privileged access)
FSR Domain: 4.7 - Logical Access Control
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import jwt as pyjwt
from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config.settings import settings
from app.models.auth import (
    AUTH_LEVEL_TO_MIN_ROLE,
    AuthContext,
    AuthLevel,
    SentinelRole,
)
from app.services.mfa_service import get_mfa_service

limiter = Limiter(key_func=get_remote_address)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

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


def _create_jwt_token(user_data: dict) -> str:
    """Create a JWT token for the user.

    Args:
        user_data: User information dict

    Returns:
        Encoded JWT token string
    """
    # Get JWT secret from settings or use demo secret
    secret = settings.supabase_key or "sentinel-demo-jwt-secret-change-in-production"

    payload = {
        "sub": user_data["user_id"],
        "email": user_data["email"],
        "role": user_data["role"].value,
        "full_name": user_data["full_name"],
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(days=30),  # Token expires in 30 days
        "iss": "sentinel.bms",
    }

    token = pyjwt.encode(payload, secret, algorithm="HS256")
    return token


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
    Once logged in, users stay authenticated for 30 days.

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
        LoginResponse with JWT token (valid for 30 days), user info, role, and MFA status
    """
    email = email.strip().lower()

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
    token = _create_jwt_token(user_info)

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
        "token": token,
        "user": {
            "id": user_info["user_id"],
            "email": user_info["email"],
            "full_name": user_info["full_name"],
            "role": user_info["role"].value,
        },
        "expires_at": (datetime.utcnow() + timedelta(days=30)).isoformat(),
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
        logger.warning(f"MFA verification failed for {email}: {error}")
        raise HTTPException(status_code=400, detail=error)

    # MFA verified - issue token
    token = _create_jwt_token(user_info)

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
        "token": token,
        "user": {
            "id": user_info["user_id"],
            "email": user_info["email"],
            "full_name": user_info["full_name"],
            "role": user_info["role"].value if isinstance(user_info["role"], SentinelRole) else user_info["role"],
        },
        "expires_at": (datetime.utcnow() + timedelta(days=30)).isoformat(),
        "mfa_verified": True,
    }


@router.post("/verify")
async def verify_token(request: Request, token: str):
    """Verify a JWT token and return user info.

    Used by frontend to check if a stored token is still valid.

    Args:
        request: FastAPI request
        token: JWT token string

    Returns:
        User info if token is valid

    Raises:
        HTTPException 401 if token is invalid or expired
    """
    secret = settings.supabase_key or "sentinel-demo-jwt-secret-change-in-production"

    try:
        payload = pyjwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"verify_exp": True},
        )

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

    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except pyjwt.InvalidTokenError as e:
        logger.warning(f"Token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")


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
    secret = settings.supabase_key or "sentinel-demo-jwt-secret-change-in-production"

    try:
        payload = pyjwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"verify_exp": True},
        )

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

    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.post("/logout")
async def logout():
    """Logout endpoint (token validation is stateless, so this is mainly for client-side cleanup).

    In a stateless JWT system, logout is handled client-side by deleting the token.
    This endpoint exists for API completeness and future session tracking.
    """
    return {"message": "Logged out successfully"}

"""
Authentication API endpoints for SENTINEL BMS Platform.

Simple email-based authentication for demo purposes.
Users enter their email address and receive a JWT token for session management.

FSR Domain: 4.7 - Logical Access Control
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import jwt as pyjwt
from fastapi import APIRouter, HTTPException, Request

from app.config.settings import settings
from app.models.auth import (
    AUTH_LEVEL_TO_MIN_ROLE,
    AuthContext,
    AuthLevel,
    SentinelRole,
)

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
async def login_with_email(request: Request, email: str):
    """Login with email address (simple authentication).

    The email address IS the credential - no password required.
    Once logged in, users stay authenticated for 30 days.

    Known demo users get specific roles (admin, operator, developer, auditor).
    Unknown emails automatically get AUDITOR (read-only) role.

    Args:
        request: FastAPI request
        email: User's email address

    Returns:
        LoginResponse with JWT token (valid for 30 days), user info, and role
    """
    email = email.strip().lower()

    # Look up user in demo store
    user_data = _DEMO_USERS.get(email)

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
        logger.info(f"New user login: {email} as AUDITOR (read-only)")

    # Create JWT token
    token = _create_jwt_token(user_info)

    # Get client IP
    source_ip = _extract_ip_address(request)

    # Log the login
    logger.info(
        f"Login success: email={email} user_id={user_info['user_id']} "
        f"role={user_info['role'].value} ip={source_ip}"
    )

    return {
        "token": token,
        "user": {
            "id": user_info["user_id"],
            "email": user_info["email"],
            "full_name": user_info["full_name"],
            "role": user_info["role"].value,
        },
        "expires_at": (datetime.utcnow() + timedelta(days=30)).isoformat(),
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

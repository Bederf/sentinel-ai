"""
Login Audit API - Admin endpoints for viewing login history.

ADMIN-only endpoints to view login audit logs and statistics.
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.middleware.auth_middleware import require_auth
from app.models.auth import AuthContext, AuthLevel
from app.database.repositories.login_audit_repository import (
    get_login_audit_repository,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/login-audit", tags=["login-audit"])


# =====================================================
# Response Models
# =====================================================


class LoginRecord(BaseModel):
    """A single login audit record."""
    id: str
    user_email: str
    user_id: Optional[str] = None
    user_role: Optional[str] = None
    source_ip: Optional[str] = None
    user_agent: Optional[str] = None
    login_at: str
    is_new_user: bool = False
    success: bool = True
    failure_reason: Optional[str] = None


class LoginListResponse(BaseModel):
    """Response with list of login records."""
    total: int
    records: List[LoginRecord]


class LoginStatsResponse(BaseModel):
    """Login statistics response."""
    period_hours: int
    total: int
    successful: int
    failed: int
    new_users: int
    unique_users: int


class SuspiciousActivityResponse(BaseModel):
    """Suspicious activity detection response."""
    period_hours: int
    failed_ips: List[dict]
    multi_ip_users: List[dict]
    new_user_surge: bool
    new_user_count: int


# =====================================================
# Endpoints
# =====================================================


@router.get("/recent", response_model=LoginListResponse)
async def get_recent_logins(
    limit: int = Query(100, ge=1, le=1000, description="Max records to return"),
    user_email: Optional[str] = Query(None, description="Filter by user email"),
    source_ip: Optional[str] = Query(None, description="Filter by source IP"),
    success_only: Optional[bool] = Query(None, description="Filter by success status"),
    hours: Optional[int] = Query(None, ge=1, le=720, description="Only logins within N hours"),
    auth: AuthContext = Depends(require_auth(AuthLevel.ADMIN)),
):
    """Get recent login records with optional filtering.

    Args:
        limit: Maximum records to return (1-1000, default 100)
        user_email: Filter by specific user email
        source_ip: Filter by source IP address
        success_only: True for successful only, False for failed only
        hours: Only show logins from the last N hours

    Returns:
        List of login audit records
    """
    repo = get_login_audit_repository()
    records = repo.get_recent_logins(
        limit=limit,
        user_email=user_email,
        source_ip=source_ip,
        success_only=success_only,
        hours=hours,
    )

    return LoginListResponse(
        total=len(records),
        records=[LoginRecord(**r) for r in records],
    )


@router.get("/stats", response_model=LoginStatsResponse)
async def get_login_stats(
    hours: int = Query(24, ge=1, le=720, description="Time period in hours"),
    auth: AuthContext = Depends(require_auth(AuthLevel.ADMIN)),
):
    """Get login statistics for a time period.

    Args:
        hours: Time period in hours (default 24)

    Returns:
        Statistics including total, successful, failed, new users, unique users
    """
    repo = get_login_audit_repository()
    stats = repo.get_login_stats(hours=hours)

    return LoginStatsResponse(**stats)


@router.get("/user/{email}", response_model=LoginListResponse)
async def get_user_login_history(
    email: str,
    limit: int = Query(50, ge=1, le=500, description="Max records to return"),
    auth: AuthContext = Depends(require_auth(AuthLevel.ADMIN)),
):
    """Get login history for a specific user.

    Args:
        email: User's email address
        limit: Maximum records to return

    Returns:
        List of login records for the user
    """
    repo = get_login_audit_repository()
    records = repo.get_user_login_history(user_email=email, limit=limit)

    return LoginListResponse(
        total=len(records),
        records=[LoginRecord(**r) for r in records],
    )


@router.get("/suspicious", response_model=SuspiciousActivityResponse)
async def get_suspicious_activity(
    hours: int = Query(24, ge=1, le=168, description="Time period in hours"),
    auth: AuthContext = Depends(require_auth(AuthLevel.ADMIN)),
):
    """Detect potentially suspicious login activity.

    Analyzes login patterns to identify:
    - IPs with multiple failed login attempts
    - Users logging in from many different IPs
    - Unusual surge in new user registrations

    Args:
        hours: Time period to analyze (default 24, max 168)

    Returns:
        Suspicious activity indicators
    """
    repo = get_login_audit_repository()
    activity = repo.get_suspicious_activity(hours=hours)

    return SuspiciousActivityResponse(**activity)

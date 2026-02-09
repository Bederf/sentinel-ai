"""
MFA API Endpoints - Multi-factor authentication for privileged access.

Provides endpoints for MFA enrollment, verification, and management.
FSR Domain: 4.6 - Logical Access Control (MFA for ADMIN role)
Phase 65-02: Rate limiting added to prevent brute force attacks.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.middleware.auth_middleware import validate_jwt_token, _extract_ip_address
from app.middleware.rate_limiter import limiter
from app.models.auth import SentinelRole
from app.services.mfa_service import get_mfa_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mfa", tags=["MFA"])


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================


class EnrollResponse(BaseModel):
    """Response from MFA enrollment."""

    success: bool
    provisioning_uri: Optional[str] = None
    secret: Optional[str] = None  # Only returned for manual entry
    backup_codes: Optional[list[str]] = None
    message: str


class VerifyRequest(BaseModel):
    """Request to verify MFA code."""

    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class VerifyResponse(BaseModel):
    """Response from MFA verification."""

    success: bool
    message: str


class StatusResponse(BaseModel):
    """MFA status for current user."""

    mfa_required: bool
    mfa_enrolled: bool
    mfa_enabled: bool
    last_used_at: Optional[str] = None
    enrolled_at: Optional[str] = None


class DisableRequest(BaseModel):
    """Request to disable MFA (admin only)."""

    user_email: str


class BackupCodeVerifyRequest(BaseModel):
    """Request to verify MFA backup code."""

    code: str = Field(..., min_length=6, max_length=16)


class RegenerateBackupCodesRequest(BaseModel):
    """Request to rotate backup codes using current TOTP code."""

    totp_code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _get_current_user(request: Request) -> dict:
    """
    Extract current user from JWT token in Authorization header.

    Args:
        request: FastAPI request

    Returns:
        User dict with id, email, role

    Raises:
        HTTPException 401 if not authenticated
    """
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
        "role": role,
    }


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.post("/enroll", response_model=EnrollResponse)
async def enroll_mfa(request: Request):
    """
    Start MFA enrollment for the current user.

    Generates a new TOTP secret and returns a provisioning URI for QR code.
    The user must verify the code before MFA is enabled.

    Phase 65-02: Rate limited to prevent abuse (5/15min).

    Requires authentication.
    """
    user = _get_current_user(request)
    mfa_service = get_mfa_service()

    source_ip = _extract_ip_address(request)
    user_agent = request.headers.get("User-Agent")

    # Generate secret and start enrollment
    success, secret, uri = mfa_service.enroll_user(
        user_email=user["email"],
        source_ip=source_ip,
        user_agent=user_agent,
    )

    if not success:
        return EnrollResponse(
            success=False,
            message="Failed to start MFA enrollment. Please try again.",
        )

    backup_codes = mfa_service.generate_backup_codes(user["id"])
    if not backup_codes:
        logger.warning("Failed to generate backup codes during enrollment for %s", user["id"])

    return EnrollResponse(
        success=True,
        provisioning_uri=uri,
        secret=secret,  # For manual entry if QR scan fails
        backup_codes=backup_codes,
        message="Scan the QR code with your authenticator app, then verify with a code.",
    )


@router.post("/verify", response_model=VerifyResponse)
@limiter.limit("5/15minutes")
async def verify_and_enable_mfa(request: Request, body: VerifyRequest):
    """
    Verify MFA code and enable MFA for the current user.

    Called during enrollment to confirm the authenticator is set up correctly.
    After successful verification, MFA will be required for future logins.

    Phase 65-02: Rate limited to 5 attempts per 15 minutes per IP.

    Requires authentication.

    Args:
        body: VerifyRequest with 6-digit TOTP code

    Returns:
        VerifyResponse indicating success or failure
    """
    user = _get_current_user(request)
    mfa_service = get_mfa_service()

    source_ip = _extract_ip_address(request)
    user_agent = request.headers.get("User-Agent")

    # Verify code and enable MFA
    success, error = mfa_service.enable_mfa(
        user_email=user["email"],
        code=body.code,
        source_ip=source_ip,
        user_agent=user_agent,
    )

    if not success:
        return VerifyResponse(success=False, message=error)

    return VerifyResponse(
        success=True,
        message="MFA enabled successfully. You will need to provide a code on future logins.",
    )


@router.post("/challenge", response_model=VerifyResponse)
@limiter.limit("5/15minutes")
async def challenge_mfa(request: Request, body: VerifyRequest):
    """
    Verify MFA code during login challenge.

    Called after password authentication when MFA is required.
    Does not require full authentication (uses pending login state).

    Phase 65-02: Rate limited to 5 attempts per 15 minutes per IP.

    Args:
        body: VerifyRequest with 6-digit TOTP code

    Returns:
        VerifyResponse indicating success or failure
    """
    # For challenge, we need the email from a pending login
    # This could be passed via a temporary token or session
    # For simplicity, we'll accept it via query param or header
    email = request.query_params.get("email") or request.headers.get("X-MFA-Email")

    if not email:
        # Fall back to trying to get from token (if partially authenticated)
        try:
            user = _get_current_user(request)
            email = user["email"]
        except HTTPException:
            raise HTTPException(
                status_code=400,
                detail="Email required for MFA challenge",
            )

    mfa_service = get_mfa_service()

    source_ip = _extract_ip_address(request)
    user_agent = request.headers.get("User-Agent")

    # Verify code
    success, error = mfa_service.verify_code(
        user_email=email,
        code=body.code,
        source_ip=source_ip,
        user_agent=user_agent,
    )

    if not success:
        return VerifyResponse(success=False, message=error)

    return VerifyResponse(
        success=True,
        message="MFA verification successful.",
    )


@router.post("/verify-backup", response_model=VerifyResponse)
@limiter.limit("5/15minutes")
async def verify_backup_code(request: Request, body: BackupCodeVerifyRequest):
    """Verify and consume a backup code as MFA alternative."""
    user = _get_current_user(request)
    mfa_service = get_mfa_service()

    if not mfa_service.is_mfa_enabled(user["email"]):
        raise HTTPException(status_code=400, detail="MFA is not enabled for this user")

    if not mfa_service.verify_backup_code(user["id"], body.code):
        return VerifyResponse(success=False, message="Invalid backup code")

    return VerifyResponse(success=True, message="Backup code verified")


@router.get("/backup-codes/remaining")
async def get_backup_codes_remaining(request: Request):
    """Get number of remaining unused backup codes."""
    user = _get_current_user(request)
    mfa_service = get_mfa_service()
    remaining = mfa_service.get_backup_codes_remaining(user["id"])
    return {"remaining": remaining}


@router.post("/backup-codes/regenerate")
@limiter.limit("5/15minutes")
async def regenerate_backup_codes(request: Request, body: RegenerateBackupCodesRequest):
    """Regenerate backup codes after verifying current TOTP code."""
    user = _get_current_user(request)
    mfa_service = get_mfa_service()

    source_ip = _extract_ip_address(request)
    user_agent = request.headers.get("User-Agent")
    success, error = mfa_service.verify_code(
        user_email=user["email"],
        code=body.totp_code,
        source_ip=source_ip,
        user_agent=user_agent,
    )
    if not success:
        raise HTTPException(status_code=400, detail=error)

    backup_codes = mfa_service.generate_backup_codes(user["id"])
    if not backup_codes:
        raise HTTPException(status_code=500, detail="Failed to regenerate backup codes")

    return {"backup_codes": backup_codes}


@router.get("/status", response_model=StatusResponse)
async def get_mfa_status(request: Request):
    """
    Get MFA status for the current user.

    Returns whether MFA is required, enrolled, and enabled.

    Requires authentication.

    Returns:
        StatusResponse with MFA status flags
    """
    user = _get_current_user(request)
    mfa_service = get_mfa_service()

    status = mfa_service.get_mfa_status(user["email"], user["role"])

    return StatusResponse(**status)


@router.delete("/disable", response_model=VerifyResponse)
@limiter.limit("10/minute")
async def disable_mfa(request: Request, body: DisableRequest):
    """
    Disable MFA for a user (admin only).

    This is a privileged operation that removes MFA protection.
    Should only be used for account recovery with proper verification.

    Phase 65-02: Rate limited to 10 attempts per minute per IP.

    Requires ADMIN role.

    Args:
        body: DisableRequest with user_email to disable

    Returns:
        VerifyResponse indicating success or failure
    """
    user = _get_current_user(request)

    # Only admins can disable MFA
    if user["role"] != SentinelRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Only administrators can disable MFA",
        )

    mfa_service = get_mfa_service()

    source_ip = _extract_ip_address(request)
    user_agent = request.headers.get("User-Agent")

    success = mfa_service.disable_mfa(
        user_email=body.user_email,
        admin_email=user["email"],
        source_ip=source_ip,
        user_agent=user_agent,
    )

    if not success:
        return VerifyResponse(
            success=False,
            message="Failed to disable MFA. User may not have MFA enabled.",
        )

    return VerifyResponse(
        success=True,
        message=f"MFA disabled for {body.user_email}. They will need to re-enroll.",
    )


@router.get("/events")
async def get_mfa_events(
    request: Request,
    user_email: Optional[str] = None,
    event_type: Optional[str] = None,
    hours: int = 24,
    limit: int = 100,
):
    """
    Get MFA events for audit purposes (admin only).

    Args:
        user_email: Optional filter by user email
        event_type: Optional filter by event type
        hours: Only events within the last N hours (default 24)
        limit: Maximum events to return (default 100)

    Returns:
        List of MFA event records
    """
    user = _get_current_user(request)

    # Only admins can view MFA events
    if user["role"] != SentinelRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Only administrators can view MFA events",
        )

    from app.database.repositories.mfa_repository import get_mfa_repository

    repository = get_mfa_repository()
    events = repository.get_mfa_events(
        user_email=user_email,
        event_type=event_type,
        hours=hours,
        limit=limit,
    )

    return {
        "events": events,
        "count": len(events),
        "filters": {
            "user_email": user_email,
            "event_type": event_type,
            "hours": hours,
        },
    }

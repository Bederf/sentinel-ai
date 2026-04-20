"""
Approval endpoint for supervised execution.

Phase 170-02: Control Actuation Loop — First live supervised execution
Endpoint: POST /api/v1/approval/execute/{site_id}

This endpoint implements the 14-step approval execution flow:
- Steps 1-11: Synchronous (< 100ms), returns ACCEPTED immediately
- Steps 12-14: Asynchronous (background task, not awaited)
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from app.database.repositories.parasite_decision_repository import ParasiteDecisionRepository
from app.middleware.auth_middleware import AuthContext, _authenticate_request
from app.models.approval_request import ApprovalRequest, ApprovalResponse
from app.services.approval_service import ApprovalService
from app.services.audit_logger import AuditLogger

router = APIRouter(prefix="/api/v1", tags=["approval"])


async def require_auth(request: Request) -> AuthContext:
    """Dependency: require authentication."""
    auth_ctx = await _authenticate_request(request)
    if auth_ctx is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return auth_ctx


@router.post("/approval/execute/{site_id}")
async def execute_decision(
    site_id: str,
    req: ApprovalRequest,
    auth: AuthContext = Depends(require_auth),
) -> ApprovalResponse:
    """
    Execute a decision with user approval.

    14-step flow:
    - Steps 1-11: Synchronous, return ACCEPTED
    - Steps 12-14: Asynchronous background task

    Args:
        site_id: Site ID (verified against decision)
        req: ApprovalRequest with decision_id, approval_outcome
        auth: Authenticated user context

    Returns:
        ApprovalResponse with status=ACCEPTED

    Raises:
        401: Not authenticated
        403: Insufficient role for this tier
        404: Decision not found
        409: Decision already locked
        422: Safety validation failed
    """
    # Initialize services
    approval_svc = ApprovalService()
    audit_logger = AuditLogger()
    decision_repo = ParasiteDecisionRepository()

    # Step 1: Fetch decision
    try:
        decision = await decision_repo.get_decision_by_id(req.decision_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e!s}")

    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")

    if decision.get("site_id") != site_id:
        raise HTTPException(status_code=404, detail="Decision not found for this site")

    # Step 2: Auth check (re-verify role)
    user_role = auth.role.value  # "operator", "engineer", "admin", etc.
    if user_role in ["viewer", "auditor"]:
        raise HTTPException(
            status_code=403,
            detail=f"Role '{user_role}' cannot approve decisions",
        )

    # Step 3: Tier lock check (Correction #7: blocks unsafe actions)
    tier = decision.get("tier", 1)
    if tier >= 3:  # CRITICAL
        if user_role not in ["engineer", "admin"]:
            raise HTTPException(
                status_code=403,
                detail=f"Tier {tier} (CRITICAL) requires ENGINEER or ADMIN role. User is {user_role}.",
            )

    # Generate correlation_id for audit trail threading
    correlation_id = str(uuid.uuid4())

    # Steps 4-11: Execute via approval service
    try:
        response = await approval_svc.execute_decision_with_audit(
            site_id=site_id,
            decision_id=req.decision_id,
            user_id=auth.user_id,
            user_role=user_role,
            approval_outcome=req.approval_outcome,
            correlation_id=correlation_id,
        )
        return ApprovalResponse(**response)

    except HTTPException:
        # Re-raise HTTP exceptions (401, 403, 404, 409, 422)
        raise
    except Exception as e:
        # Catch unhandled exceptions, log, and return 500
        await audit_logger.record_event(
            {
                "event_type": "DECISION_ERROR",
                "correlation_id": correlation_id,
                "decision_id": req.decision_id,
                "error": str(e),
                "user_id": auth.user_id,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error during approval execution",
        )

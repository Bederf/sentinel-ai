"""Approval Workflow API Endpoints for Niagara Equipment Control.

Handles:
- POST /api/approvals/recommendations/{id}/approve - Approve a recommendation
- POST /api/approvals/recommendations/{id}/reject - Reject a recommendation
- GET /api/approvals/recommendations/{id}/status - Get approval status
- POST /api/approvals/recommendations/{id}/rollback - Rollback an executed approval
"""

import logging
from fastapi import APIRouter, HTTPException, Depends, Path
from typing import Optional

from app.middleware.auth_middleware import require_auth
from app.models.auth import AuthContext
from app.security.step_up import require_step_up
from app.models.approval import ApprovalRequest, RejectionRequest, ApprovalResponse, ApprovalStatus
from app.core.site_resolver import get_primary_site_code
from app.services.approval_service import get_approval_service
from app.database.repositories.recommendation_repository import RecommendationRepository
from app.models.recommendation import RecommendationStatus
from app.models.module_registry import ModuleType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.post(
    "/recommendations/{recommendation_id}/approve",
    response_model=ApprovalResponse,
    summary="Approve a recommendation and execute device control",
)
async def approve_recommendation(
    recommendation_id: str = Path(..., description="ID of recommendation to approve"),
    request: ApprovalRequest = None,
    auth: AuthContext = Depends(require_auth),
    _step_up: None = Depends(require_step_up()),
) -> ApprovalResponse:
    """Approve a pending recommendation.

    This endpoint:
    1. Validates the recommendation exists and is pending approval
    2. Runs SafetyEngine validation before device write
    3. Executes the control change on the Niagara device
    4. Verifies COV feedback (confirms device accepted change)
    5. Updates recommendation status to 'executed'
    6. Creates audit log entry

    Args:
        recommendation_id: UUID of the recommendation
        request: ApprovalRequest with approved_by and optional approval_notes
        auth: Authentication context

    Returns:
        ApprovalResponse with execution result

    Raises:
        404: Recommendation not found
        400: Invalid approval request or safety violation
        500: Execution error
    """
    try:
        if not request:
            raise HTTPException(status_code=400, detail="Request body required with approved_by field")

        # Gate: control module must be active for equipment's domain
        recommendations_repo = RecommendationRepository()
        recommendation = await recommendations_repo.get_by_id(recommendation_id)
        if not recommendation:
            raise HTTPException(status_code=404, detail=f"Recommendation {recommendation_id} not found")

        control_module = _get_control_module_for_equipment(recommendation.target_equipment or "")
        if control_module:
            from app.services.module_registry_service import module_registry

            site_id = recommendation.site_id or get_primary_site_code() or "unknown"
            if not module_registry.is_module_active(site_id, control_module):
                raise HTTPException(
                    status_code=403,
                    detail=f"The {control_module.value.upper()} module is not active for this site. "
                    f"Recommendations are visible in monitoring mode, but control actions "
                    f"require the control module to be enabled.",
                )

        approval_service = get_approval_service()

        # Validate approval first
        is_valid, error_msg = await approval_service.validate_approval(
            recommendation_id=recommendation_id, approved_by=request.approved_by
        )

        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

        # Execute approval
        result = await approval_service.execute_approval(
            recommendation_id=recommendation_id, approved_by=request.approved_by, approval_notes=request.approval_notes
        )

        if not result.success:
            # Return 400 for safety violations, 500 for other errors
            status_code = 400 if "SafetyEngine" in (result.error_message or "") else 500
            raise HTTPException(status_code=status_code, detail=result.error_message or "Approval execution failed")

        # Convert to response model
        return ApprovalResponse(
            success=result.success,
            recommendation_id=result.recommendation_id,
            status=result.status,
            executed_at=result.executed_at,
            error_message=result.error_message,
            cov_verified=result.cov_verified,
            execution_result=result.execution_result,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving recommendation {recommendation_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to approve recommendation: {str(e)}")


@router.post(
    "/recommendations/{recommendation_id}/reject",
    response_model=ApprovalResponse,
    summary="Reject a pending recommendation",
)
async def reject_recommendation(
    recommendation_id: str = Path(..., description="ID of recommendation to reject"),
    request: RejectionRequest = None,
    auth: AuthContext = Depends(require_auth),
    _step_up: None = Depends(require_step_up()),
) -> ApprovalResponse:
    """Reject a pending recommendation.

    This endpoint:
    1. Validates the recommendation exists and is pending
    2. Updates status to 'rejected'
    3. Records rejection reason
    4. Creates audit log entry

    Args:
        recommendation_id: UUID of the recommendation
        request: RejectionRequest with rejected_by and reason
        auth: Authentication context

    Returns:
        ApprovalResponse confirming rejection

    Raises:
        404: Recommendation not found
        400: Invalid rejection or recommendation not pending
        500: Execution error
    """
    try:
        if not request:
            raise HTTPException(status_code=400, detail="Request body required with rejected_by and reason")

        approval_service = get_approval_service()

        result = await approval_service.reject_approval(
            recommendation_id=recommendation_id, rejected_by=request.rejected_by, reason=request.reason
        )

        if not result.success:
            raise HTTPException(status_code=400, detail=result.error_message or "Rejection failed")

        return ApprovalResponse(
            success=result.success,
            recommendation_id=result.recommendation_id,
            status=result.status,
            error_message=result.error_message,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting recommendation {recommendation_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to reject recommendation: {str(e)}")


@router.get(
    "/recommendations/{recommendation_id}/status",
    response_model=ApprovalStatus,
    summary="Get approval status of a recommendation",
)
async def get_approval_status(
    recommendation_id: str = Path(..., description="ID of recommendation"), auth: AuthContext = Depends(require_auth)
) -> ApprovalStatus:
    """Get the current approval status of a recommendation.

    Args:
        recommendation_id: UUID of the recommendation
        auth: Authentication context

    Returns:
        ApprovalStatus with current state

    Raises:
        404: Recommendation not found
        500: Query error
    """
    try:
        recommendations_repo = RecommendationRepository()
        recommendation = await recommendations_repo.get_by_id(recommendation_id)

        if not recommendation:
            raise HTTPException(status_code=404, detail=f"Recommendation {recommendation_id} not found")

        return ApprovalStatus(
            recommendation_id=recommendation.id,
            approval_status=recommendation.status.value,
            approved_by=recommendation.approved_by,
            approved_at=recommendation.timestamp,  # Fallback if approved_at doesn't exist
            executed_at=recommendation.executed_at,
            rejection_reason=recommendation.rejection_reason,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting approval status for {recommendation_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get approval status: {str(e)}")


@router.post(
    "/recommendations/{recommendation_id}/rollback",
    response_model=ApprovalResponse,
    summary="Rollback an executed approval to original state",
)
async def rollback_approval(
    recommendation_id: str = Path(..., description="ID of recommendation to rollback"),
    rollback_reason: Optional[str] = None,
    auth: AuthContext = Depends(require_auth),
    _step_up: None = Depends(require_step_up()),
) -> ApprovalResponse:
    """Rollback an executed approval to its original state.

    This endpoint:
    1. Validates the recommendation was previously executed
    2. Extracts original value from execution_result
    3. Writes original value back to device
    4. Updates recommendation status to mark as rolled back
    5. Creates audit log entry

    Args:
        recommendation_id: UUID of the recommendation
        rollback_reason: Optional reason for rollback
        auth: Authentication context

    Returns:
        ApprovalResponse confirming rollback

    Raises:
        404: Recommendation not found
        400: Recommendation not in executed state
        500: Rollback execution error
    """
    try:
        recommendations_repo = RecommendationRepository()
        recommendation = await recommendations_repo.get_by_id(recommendation_id)

        if not recommendation:
            raise HTTPException(status_code=404, detail=f"Recommendation {recommendation_id} not found")

        if recommendation.status != RecommendationStatus.EXECUTED:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot rollback {recommendation.status.value} recommendation. "
                    "Only executed recommendations can be rolled back."
                ),
            )

        # Execute rollback
        approval_service = get_approval_service()
        result = await approval_service.rollback_approval(
            recommendation_id=recommendation_id, rollback_reason=rollback_reason, initiated_by=auth.user_id
        )

        if not result.success:
            raise HTTPException(status_code=500, detail=result.error_message or "Rollback failed")

        return ApprovalResponse(
            success=result.success,
            recommendation_id=result.recommendation_id,
            status=result.status,
            executed_at=result.executed_at,
            cov_verified=result.cov_verified,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rolling back recommendation {recommendation_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to rollback recommendation: {str(e)}")


# Equipment type → control module mapping
# Uses SENTINEL naming convention: {SITE}-{TYPE}-{LOCATION}-{SEQ}
_EQUIPMENT_CONTROL_MAP: dict[str, ModuleType] = {
    "CHILLER": ModuleType.HVAC_CONTROL,
    "AHU": ModuleType.HVAC_CONTROL,
    "FCU": ModuleType.HVAC_CONTROL,
    "VAV": ModuleType.HVAC_CONTROL,
    "SPLIT": ModuleType.HVAC_CONTROL,
    "CT": ModuleType.HVAC_CONTROL,
    "CRAC": ModuleType.HVAC_CONTROL,
    "GEN": ModuleType.ENERGY_CONTROL,
    "UPS": ModuleType.ENERGY_CONTROL,
    "ATS": ModuleType.ENERGY_CONTROL,
    "TX": ModuleType.ENERGY_CONTROL,
    "MSB": ModuleType.ENERGY_CONTROL,
    "MTR": ModuleType.ENERGY_CONTROL,
    "DALI": ModuleType.LIGHTING_CONTROL,
    "LTG": ModuleType.LIGHTING_CONTROL,
    "LUM": ModuleType.LIGHTING_CONTROL,
    "INV": ModuleType.SOLAR_CONTROL,
    "BESS": ModuleType.SOLAR_CONTROL,
    "PV": ModuleType.SOLAR_CONTROL,
    "ACC": ModuleType.SECURITY_CONTROL,
    "CCTV": ModuleType.SECURITY_CONTROL,
    "FIRE": ModuleType.ENERGY_CONTROL,  # Fire panels are critical infrastructure
}


def _get_control_module_for_equipment(equipment_code: str) -> Optional[ModuleType]:
    """Derive the required control module from an equipment code.

    Equipment codes follow SENTINEL naming: {SITE}-{TYPE}-{LOCATION}-{SEQ}
    e.g. S002-CHILLER-B1-001, S002-VAV-101, S002-INV-R-001
    """
    if not equipment_code:
        return None
    parts = equipment_code.upper().split("-")
    # Try from longest prefix to shortest (handles MTR-R-SOLAR, etc.)
    for length in range(min(len(parts), 4), 0, -1):
        candidate = "-".join(parts[1 : 1 + length]) if len(parts) > 1 else parts[0]
        if candidate in _EQUIPMENT_CONTROL_MAP:
            return _EQUIPMENT_CONTROL_MAP[candidate]
        # Also try just the first token after site prefix
        if length == 1 and len(parts) > 1 and parts[1] in _EQUIPMENT_CONTROL_MAP:
            return _EQUIPMENT_CONTROL_MAP[parts[1]]
    return None

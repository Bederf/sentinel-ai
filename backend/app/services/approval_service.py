"""Approval Service for Niagara Equipment Control Recommendations.

Handles the approval workflow for equipment control recommendations:
- Validate approval requests
- Execute approved recommendations with safety checks
- Manage rejection workflow
- Audit trail recording
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass

from app.models.recommendation import Recommendation, RecommendationStatus
from app.services.safety_interlocks import SafetyEngine
from app.services.device_abstraction import get_device_manager
from app.database.repositories.recommendation_repository import RecommendationRepository
from app.database.repositories.audit_repository import AuditRepository

logger = logging.getLogger(__name__)


@dataclass
class ApprovalResult:
    """Result of an approval/rejection action."""
    success: bool
    recommendation_id: str
    status: str  # "approved", "rejected", "executed", "failed"
    executed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    cov_verified: bool = False
    execution_result: Optional[Dict[str, Any]] = None


class ApprovalService:
    """Service for managing equipment control recommendation approvals."""

    def __init__(self):
        """Initialize approval service with dependencies."""
        self.safety_engine = SafetyEngine()
        self.device_manager = get_device_manager()
        self.recommendations_repo = RecommendationRepository()
        self.audit_repo = AuditRepository()

    async def validate_approval(
        self,
        recommendation_id: str,
        approved_by: str
    ) -> Tuple[bool, str]:
        """Validate that a recommendation can be approved.

        Args:
            recommendation_id: ID of recommendation to validate
            approved_by: User ID approving the recommendation

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Get recommendation from database
            recommendation = await self.recommendations_repo.get_by_id(recommendation_id)

            if not recommendation:
                return False, f"Recommendation {recommendation_id} not found"

            if recommendation.status != RecommendationStatus.PENDING:
                return False, f"Recommendation is {recommendation.status.value}, not pending approval"

            if not approved_by or not approved_by.strip():
                return False, "Approver ID must be provided"

            logger.info(f"Approval validation passed for recommendation {recommendation_id}")
            return True, ""

        except Exception as e:
            logger.error(f"Error validating approval for {recommendation_id}: {str(e)}")
            return False, f"Validation error: {str(e)}"

    async def execute_approval(
        self,
        recommendation_id: str,
        approved_by: str,
        approval_notes: Optional[str] = None
    ) -> ApprovalResult:
        """Execute an approved recommendation with safety validation and device control.

        Flow:
        1. Validate recommendation exists and is pending
        2. Run SafetyEngine check (second validation before write)
        3. Extract control change from recommendation
        4. Write to Niagara device via device_manager
        5. Verify COV feedback (read back to confirm)
        6. Update recommendation status to "executed"
        7. Create audit log entry

        Args:
            recommendation_id: ID of recommendation to approve
            approved_by: User ID approving
            approval_notes: Optional notes about approval

        Returns:
            ApprovalResult with execution details
        """
        try:
            # Get recommendation
            recommendation = await self.recommendations_repo.get_by_id(recommendation_id)

            if not recommendation:
                return ApprovalResult(
                    success=False,
                    recommendation_id=recommendation_id,
                    status="failed",
                    error_message=f"Recommendation {recommendation_id} not found"
                )

            if recommendation.status != RecommendationStatus.PENDING:
                return ApprovalResult(
                    success=False,
                    recommendation_id=recommendation_id,
                    status="failed",
                    error_message=f"Recommendation is {recommendation.status.value}, not pending"
                )

            # CRITICAL: Run SafetyEngine validation AGAIN before write
            # (Defense-in-depth: validate at both recommendation creation and approval time)
            equipment_id = recommendation.target_equipment
            proposed_value = recommendation.action.get("value")

            logger.info(f"Running SafetyEngine validation for {equipment_id} = {proposed_value}")
            safety_result = await self._validate_safety(equipment_id, proposed_value)

            if not safety_result["is_safe"]:
                logger.warning(
                    f"SafetyEngine rejected approval for {recommendation_id}: {safety_result.get('reason')}"
                )
                return ApprovalResult(
                    success=False,
                    recommendation_id=recommendation_id,
                    status="rejected",
                    error_message=f"Safety constraint violation: {safety_result.get('reason')}"
                )

            # Extract control change from recommendation
            control_point = recommendation.action.get("point")
            target_value = recommendation.action.get("value")

            if not control_point or target_value is None:
                return ApprovalResult(
                    success=False,
                    recommendation_id=recommendation_id,
                    status="failed",
                    error_message="Recommendation action missing point or value"
                )

            # Execute write to Niagara device
            logger.info(
                f"Writing to device {equipment_id}: {control_point} = {target_value}"
            )
            write_result = await self._execute_device_write(
                equipment_id=equipment_id,
                point_name=control_point,
                target_value=target_value
            )

            if not write_result["success"]:
                logger.error(f"Device write failed: {write_result.get('error')}")
                return ApprovalResult(
                    success=False,
                    recommendation_id=recommendation_id,
                    status="failed",
                    error_message=f"Device write failed: {write_result.get('error')}"
                )

            # Verify COV feedback (confirm device actually accepted the change)
            cov_verified = await self._verify_cov_feedback(
                equipment_id=equipment_id,
                point_name=control_point,
                expected_value=target_value
            )

            if not cov_verified:
                logger.warning(
                    f"COV feedback verification failed for {equipment_id}.{control_point}"
                )

            # Update recommendation status
            recommendation.status = RecommendationStatus.EXECUTED
            recommendation.approved_by = approved_by
            recommendation.approval_reason = approval_notes
            recommendation.executed_at = datetime.utcnow()
            recommendation.execution_result = {
                "success": True,
                "device_write": write_result,
                "cov_verified": cov_verified,
                "timestamp": datetime.utcnow().isoformat()
            }

            await self.recommendations_repo.upsert(recommendation)

            # Create audit log entry
            await self._create_audit_log(
                action_type="equipment_approval",
                equipment_code=equipment_id,
                approved_by=approved_by,
                approval_notes=approval_notes,
                change_description=f"{control_point} = {target_value}",
                execution_status="success",
                cov_verified=cov_verified
            )

            logger.info(f"Approval executed successfully for {recommendation_id}")

            return ApprovalResult(
                success=True,
                recommendation_id=recommendation_id,
                status="executed",
                executed_at=recommendation.executed_at,
                cov_verified=cov_verified,
                execution_result=recommendation.execution_result
            )

        except Exception as e:
            logger.error(f"Error executing approval for {recommendation_id}: {str(e)}")
            return ApprovalResult(
                success=False,
                recommendation_id=recommendation_id,
                status="failed",
                error_message=f"Approval execution error: {str(e)}"
            )

    async def reject_approval(
        self,
        recommendation_id: str,
        rejected_by: str,
        reason: str
    ) -> ApprovalResult:
        """Reject a pending recommendation.

        Args:
            recommendation_id: ID of recommendation to reject
            rejected_by: User ID rejecting
            reason: Reason for rejection

        Returns:
            ApprovalResult
        """
        try:
            recommendation = await self.recommendations_repo.get_by_id(recommendation_id)

            if not recommendation:
                return ApprovalResult(
                    success=False,
                    recommendation_id=recommendation_id,
                    status="failed",
                    error_message=f"Recommendation {recommendation_id} not found"
                )

            if recommendation.status != RecommendationStatus.PENDING:
                return ApprovalResult(
                    success=False,
                    recommendation_id=recommendation_id,
                    status="failed",
                    error_message=f"Cannot reject {recommendation.status.value} recommendation"
                )

            # Update recommendation status
            recommendation.status = RecommendationStatus.REJECTED
            recommendation.approved_by = rejected_by
            recommendation.rejection_reason = reason

            await self.recommendations_repo.upsert(recommendation)

            # Create audit log entry
            await self._create_audit_log(
                action_type="equipment_rejection",
                equipment_code=recommendation.target_equipment,
                approved_by=rejected_by,
                approval_notes=reason,
                change_description=f"Rejected: {recommendation.action}",
                execution_status="rejected",
                cov_verified=False
            )

            logger.info(f"Recommendation {recommendation_id} rejected by {rejected_by}")

            return ApprovalResult(
                success=True,
                recommendation_id=recommendation_id,
                status="rejected"
            )

        except Exception as e:
            logger.error(f"Error rejecting recommendation {recommendation_id}: {str(e)}")
            return ApprovalResult(
                success=False,
                recommendation_id=recommendation_id,
                status="failed",
                error_message=f"Rejection error: {str(e)}"
            )

    async def _validate_safety(self, equipment_id: str, proposed_value: Any) -> Dict[str, Any]:
        """Validate control change against safety rules.

        Args:
            equipment_id: Equipment ID
            proposed_value: Proposed new value

        Returns:
            Dict with is_safe (bool) and reason (str)
        """
        try:
            await self.safety_engine.initialize()
            validation = self.safety_engine.validate(equipment_id, proposed_value)
            return validation
        except Exception as e:
            logger.error(f"Error in safety validation: {str(e)}")
            return {"is_safe": False, "reason": f"Safety validation error: {str(e)}"}

    async def _execute_device_write(
        self,
        equipment_id: str,
        point_name: str,
        target_value: Any
    ) -> Dict[str, Any]:
        """Execute write to Niagara device.

        Args:
            equipment_id: Equipment ID
            point_name: Point/property name to write
            target_value: Value to write

        Returns:
            Dict with success (bool) and error (str if failed)
        """
        try:
            result = await self.device_manager.set_value(
                equipment_id=equipment_id,
                point_name=point_name,
                value=target_value
            )
            return result
        except Exception as e:
            logger.error(f"Error writing to device {equipment_id}: {str(e)}")
            return {"success": False, "error": str(e)}

    async def _verify_cov_feedback(
        self,
        equipment_id: str,
        point_name: str,
        expected_value: Any
    ) -> bool:
        """Verify COV feedback (confirm device accepted the change).

        Args:
            equipment_id: Equipment ID
            point_name: Point to verify
            expected_value: Expected value after write

        Returns:
            True if verified, False otherwise
        """
        try:
            result = await self.device_manager.read_value(
                equipment_id=equipment_id,
                point_name=point_name
            )

            if result.get("success"):
                actual_value = result.get("value")
                verified = actual_value == expected_value

                if not verified:
                    logger.warning(
                        f"COV mismatch for {equipment_id}.{point_name}: "
                        f"wrote {expected_value}, read {actual_value}"
                    )

                return verified
            else:
                logger.warning(f"Failed to read COV feedback for {equipment_id}.{point_name}")
                return False

        except Exception as e:
            logger.error(f"Error verifying COV feedback: {str(e)}")
            return False

    async def _create_audit_log(
        self,
        action_type: str,
        equipment_code: str,
        approved_by: str,
        approval_notes: Optional[str],
        change_description: str,
        execution_status: str,
        cov_verified: bool
    ) -> None:
        """Create audit log entry for approval action.

        Args:
            action_type: Type of action (e.g., "equipment_approval")
            equipment_code: Equipment code
            approved_by: User who approved
            approval_notes: Optional notes
            change_description: What changed
            execution_status: Result status
            cov_verified: Whether COV feedback was verified
        """
        try:
            audit_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "action_type": action_type,
                "equipment_code": equipment_code,
                "approved_by": approved_by,
                "approval_notes": approval_notes or "",
                "change_description": change_description,
                "execution_status": execution_status,
                "verified_by_cov": cov_verified
            }

            await self.audit_repo.log_action(audit_entry)
            logger.info(f"Audit log created for {action_type} on {equipment_code}")

        except Exception as e:
            logger.error(f"Error creating audit log: {str(e)}")


# Singleton instance
_approval_service: Optional[ApprovalService] = None


def get_approval_service() -> ApprovalService:
    """Get or create approval service singleton."""
    global _approval_service
    if _approval_service is None:
        _approval_service = ApprovalService()
    return _approval_service

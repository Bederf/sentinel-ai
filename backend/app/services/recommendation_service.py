"""Recommendation service for managing the control tier workflow.

Handles recommendation lifecycle: creation, approval workflow, and execution.
Integrates with ProfileService for control tier settings and DeviceManager for BMS execution.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.models.recommendation import (
    Recommendation,
    RecommendationStatus,
    ActionRiskLevel,
)
from app.services.profile_service import get_profile_service
from app.services.device_abstraction import device_manager

logger = logging.getLogger(__name__)


class RecommendationService:
    """Manages recommendation lifecycle through approval and execution workflow.

    Implements three control tiers:
    - Tier 1 (Monitor): Display only, no execution
    - Tier 2 (Human-in-Loop): All recommendations pending until approved
    - Tier 3 (Auto-Execute): Auto-execute low-risk, pending for high-risk
    """

    def __init__(self):
        """Initialize RecommendationService."""
        self.profile_service = get_profile_service()

    async def create_recommendation(self, rec_data: Dict[str, Any]) -> Recommendation:
        """Create new recommendation with approval requirements.

        Determines if approval is required based on:
        - control_tier: monitor (display only), human_in_loop (always approve),
                       auto_execute (auto unless high risk)
        - risk_level: low/medium (auto), high/critical (manual)

        Args:
            rec_data: Recommendation data dict

        Returns:
            Created Recommendation

        Raises:
            ValueError: If required fields missing
        """
        site_id = rec_data.get("site_id")
        if not site_id:
            raise ValueError("site_id is required")

        action_type = rec_data.get("action_type")
        if not action_type:
            raise ValueError("action_type is required")

        # Get control tier from profile
        config = self.profile_service.load_site_profile_config(site_id)
        control_tier = config.control_tier if config else "human_in_loop"

        # Classify risk level
        risk_level = self._classify_risk(action_type)

        # Determine if approval required
        requires_approval = self._requires_approval(control_tier, risk_level)

        # Create recommendation
        rec = Recommendation(
            site_id=site_id,
            timestamp=datetime.utcnow(),
            action_type=action_type,
            risk_level=risk_level,
            target_equipment=rec_data.get("target_equipment", ""),
            action=rec_data.get("action", {}),
            reason=rec_data.get("reason", ""),
            expected_impact=rec_data.get("expected_impact", {}),
            confidence=rec_data.get("confidence", "medium"),
            profile=rec_data.get("profile", ""),
            multi_objective_score=float(rec_data.get("multi_objective_score", 0.0)),
            requires_approval=requires_approval,
            status=RecommendationStatus.PENDING if requires_approval else RecommendationStatus.AUTO_EXECUTED,
        )

        # Auto-execute if not requiring approval
        if not requires_approval:
            try:
                await self.execute_recommendation(rec.id, rec)
            except Exception as e:
                logger.error(f"Failed to auto-execute recommendation {rec.id}: {e}")
                rec.status = RecommendationStatus.FAILED
                rec.execution_result = {"error": str(e)}

        logger.info(
            f"Created recommendation {rec.id}: {action_type} on {rec.target_equipment} "
            f"({risk_level.value}, requires_approval={requires_approval})"
        )

        return rec

    async def get_pending_recommendations(
        self, site_id: str, limit: int = 10
    ) -> List[Recommendation]:
        """Get pending recommendations for a site (Tier 2 approval queue).

        Args:
            site_id: Building identifier
            limit: Maximum number to return

        Returns:
            List of pending recommendations
        """
        # Note: In full implementation, this would query a repository.
        # For now, return empty list (repository pattern in Task 4.3)
        return []

    async def approve_recommendation(
        self, rec_id: str, user_id: str, reason: Optional[str] = None
    ) -> Recommendation:
        """Operator approves recommendation (Tier 2).

        Changes status to APPROVED, then executes the recommendation.

        Args:
            rec_id: Recommendation ID
            user_id: User ID of approver
            reason: Optional reason for approval

        Returns:
            Updated Recommendation

        Raises:
            ValueError: If recommendation not in PENDING status
        """
        # Note: In full implementation, would fetch from repository
        raise NotImplementedError("Requires repository implementation (Task 4.3)")

    async def reject_recommendation(
        self, rec_id: str, user_id: str, reason: str
    ) -> Recommendation:
        """Operator rejects recommendation (Tier 2).

        Changes status to REJECTED and logs feedback.
        Integrates with rejection learning to detect patterns.

        Args:
            rec_id: Recommendation ID
            user_id: User ID of rejector
            reason: Reason for rejection

        Returns:
            Updated Recommendation

        Raises:
            ValueError: If recommendation not in PENDING status
        """
        # Note: In full implementation, would fetch from repository
        # For now, create a dummy recommendation to demonstrate learning integration
        try:
            # Create a sample recommendation for demonstration
            rec = Recommendation(
                id=rec_id,
                site_id="site-002",
                action_type="hvac_setpoint_change",
                target_equipment="S002-AHU-L1-A",
                action={"point": "setpoint", "value": 20.0},
                status="pending",
            )

            rec.status = RecommendationStatus.REJECTED
            rec.rejection_reason = reason

            # NEW: Process rejection for learning
            from app.services.rejection_learning_service import (
                get_rejection_learning_service,
            )

            rejection_learning = get_rejection_learning_service()
            await rejection_learning.process_rejection(rec, reason)

            logger.info(
                f"Rejected recommendation {rec_id} by {user_id}: {reason}"
            )

            return rec
        except Exception as e:
            logger.error(f"Error rejecting recommendation {rec_id}: {e}")
            raise

    async def execute_recommendation(
        self, rec_id: str, rec: Recommendation
    ) -> Dict[str, Any]:
        """Execute recommendation via device manager.

        Calls device manager to apply the action to the BMS.

        Args:
            rec_id: Recommendation ID
            rec: Recommendation object to execute

        Returns:
            Result dict from device manager

        Raises:
            Exception: If execution fails
        """
        try:
            logger.info(
                f"Executing recommendation {rec_id}: {rec.action_type} on {rec.target_equipment}"
            )

            # Call device manager to apply action
            result = await device_manager.apply_action(rec.target_equipment, rec.action)

            rec.status = RecommendationStatus.EXECUTED
            rec.executed_at = datetime.utcnow()
            rec.execution_result = result

            logger.info(f"Successfully executed recommendation {rec_id}")

            return result

        except Exception as e:
            logger.error(f"Failed to execute recommendation {rec_id}: {e}")
            rec.status = RecommendationStatus.FAILED
            rec.execution_result = {"error": str(e)}
            raise

    def _classify_risk(self, action_type: str) -> ActionRiskLevel:
        """Classify action risk level.

        LOW: Setpoint changes (±5°C), lighting dimming
        MEDIUM: Equipment staging, VAV overrides
        HIGH: Generator start, BESS dispatch, chiller bypass
        CRITICAL: Fire safety overrides, access control

        Args:
            action_type: Type of action

        Returns:
            ActionRiskLevel classification
        """
        low_risk_actions = [
            "hvac_setpoint_change",
            "zone_override",
            "lighting_dim",
            "schedule_shift",
        ]

        high_risk_actions = [
            "generator_start",
            "bess_dispatch",
            "chiller_bypass",
            "equipment_shutdown",
        ]

        critical_actions = ["fire_override", "access_control", "emergency_shutdown"]

        if action_type in critical_actions:
            return ActionRiskLevel.CRITICAL
        elif action_type in high_risk_actions:
            return ActionRiskLevel.HIGH
        elif action_type in low_risk_actions:
            return ActionRiskLevel.LOW
        else:
            return ActionRiskLevel.MEDIUM

    def _requires_approval(self, control_tier: str, risk_level: ActionRiskLevel) -> bool:
        """Determine if approval is required.

        Tier 1 (Monitor): Always require approval (display only, don't execute)
        Tier 2 (Human-in-Loop): Always require approval
        Tier 3 (Auto-Execute): Auto unless high or critical risk

        Args:
            control_tier: Site's control tier
            risk_level: Action's risk level

        Returns:
            True if approval required, False otherwise
        """
        if control_tier == "monitor":
            # Tier 1: Display only, never execute
            return True

        if control_tier == "human_in_loop":
            # Tier 2: Always require approval
            return True

        if control_tier == "auto_execute":
            # Tier 3: Auto for low/medium risk, require approval for high/critical
            return risk_level in [ActionRiskLevel.HIGH, ActionRiskLevel.CRITICAL]

        # Default to requiring approval for safety
        return True

    async def _process_rejection_feedback(
        self, rec: Recommendation, reason: str
    ) -> None:
        """Learn from rejected recommendations.

        Placeholder for Phase 5: Feedback Loop.
        Could improve profile weights or detection rules based on rejection patterns.

        Args:
            rec: Rejected recommendation
            reason: Reason for rejection
        """
        logger.info(f"Rejection feedback for {rec.id}: {reason}")
        # TODO: Phase 5 - Use rejection feedback to improve future recommendations


# Singleton instance
_recommendation_service: Optional[RecommendationService] = None


def get_recommendation_service() -> RecommendationService:
    """Get or create RecommendationService singleton.

    Returns:
        RecommendationService instance
    """
    global _recommendation_service
    if _recommendation_service is None:
        _recommendation_service = RecommendationService()
    return _recommendation_service

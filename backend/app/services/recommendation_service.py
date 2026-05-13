"""Recommendation service for managing the control tier workflow.

Handles recommendation lifecycle: creation, approval workflow, and execution.
Integrates with ProfileService for control tier settings and DeviceManager for BMS execution.
"""

import logging
from datetime import datetime
from typing import Any

from app.models.recommendation import (
    ActionRiskLevel,
    Recommendation,
    RecommendationStatus,
)
from app.services.device_abstraction import device_manager
from app.services.ml_feedback_service import get_ml_feedback_service
from app.services.profile_service import get_profile_service

logger = logging.getLogger(__name__)

# Priority correction overrides — when consumable is detected,
# the risk level may be downgraded from HIGH/CRITICAL to match corrected priority.
_PRIORITY_CORRECTION_RISK_OVERRIDE: dict[str, ActionRiskLevel] = {
    "low": ActionRiskLevel.LOW,
    "medium": ActionRiskLevel.MEDIUM,
}


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

    async def create_recommendation(self, rec_data: dict[str, Any]) -> Recommendation:
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

        # Phase gate: check onboarding_phase before creating recommendation
        try:
            from app.models.onboarding_phase import phase_allows as _rec_phase_allows
            from app.database.supabase_client import get_supabase_client
            _sb = get_supabase_client()
            _row = _sb.table("sites").select("onboarding_phase").eq("code", site_id).limit(1).execute()
            _phase = (_row.data[0].get("onboarding_phase") or "commissioning") if _row.data else "commissioning"
            if _phase in ("commissioning", "shadow_live"):
                logger.info("Phase %s blocks recommendation creation for %s", _phase, site_id)
                raise ValueError(f"Recommendations not allowed in phase '{_phase}'")
            if not _rec_phase_allows(_phase, "recommendations_ui"):
                logger.info("Phase %s limits to advisory recommendations for %s", _phase, site_id)
                rec_data["status"] = "advisory_display_only"
        except Exception as _exc:
            if "not allowed in phase" in str(_exc):
                raise
            logger.debug("Phase gate check failed, proceeding: %s", _exc)

        # Get control tier from profile
        config = self.profile_service.load_site_profile_config(site_id)
        control_tier = config.control_tier if config else "supervised"

        # Classify risk level
        risk_level = self._classify_risk(action_type)

        # Consumables priority correction — detect and correct misclassified consumables
        is_consumable = rec_data.get("is_consumable", False)
        priority_corrected = False
        priority_reason: str | None = None

        issue_title = rec_data.get("issue_title") or rec_data.get("title", "")
        issue_desc = rec_data.get("issue_description") or rec_data.get("description", "")

        if issue_title or issue_desc:
            try:
                from app.services.semantic_priority_classifier import get_semantic_priority_classifier

                classifier = get_semantic_priority_classifier()
                original_priority = rec_data.get("priority", risk_level.value)
                classification = classifier.classify_issue(issue_title, issue_desc, original_priority)

                is_consumable = classification.is_consumable
                if classification.is_consumable and classification.corrected_priority != original_priority:
                    priority_corrected = True
                    priority_reason = classification.reason
                    logger.info(
                        "Priority corrected for consumable issue '%s': %s → %s (%s)",
                        issue_title[:60],
                        original_priority,
                        classification.corrected_priority,
                        classification.classification_method,
                    )
                    # Downgrade risk level to match corrected priority
                    corrected_risk = _PRIORITY_CORRECTION_RISK_OVERRIDE.get(classification.corrected_priority)
                    if corrected_risk and corrected_risk.value != risk_level.value:
                        risk_level = corrected_risk
                        logger.info(
                            "Risk level downgraded from %s to %s for consumable", risk_level.value, corrected_risk.value
                        )
            except Exception as e:
                logger.warning("SemanticPriorityClassifier failed, proceeding with original priority: %s", e)

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
            is_consumable=is_consumable,
            priority_corrected=priority_corrected,
            priority_reason=priority_reason,
        )

        # Phase 207-04: Track fault occurrence for cluster detection (3rd occurrence = cluster alert)
        # Non-blocking: if tracking fails, log warning and proceed without cluster flag
        equipment_id = rec_data.get("target_equipment", "")
        issue_type = rec_data.get("issue_type") or rec_data.get("fault_type", "")
        if equipment_id and issue_type:
            try:
                from app.services.fault_occurrence_tracker import get_fault_occurrence_tracker

                tracker = get_fault_occurrence_tracker()
                occurrence = await tracker.track_fault(
                    site_code=site_id,
                    equipment_id=equipment_id,
                    issue_type=issue_type,
                    recommendation_id=rec.id,
                )
                rec.is_cluster_alert = occurrence.is_cluster_alert
                rec.cluster_count = occurrence.cluster_count
                if occurrence.is_cluster_alert:
                    logger.info(
                        "Cluster alert attached to recommendation %s: %s/%s (count=%d)",
                        rec.id,
                        equipment_id,
                        issue_type,
                        occurrence.cluster_count,
                    )
            except Exception as e:
                logger.warning("Fault occurrence tracking failed for rec %s: %s", rec.id, e)

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

    async def get_pending_recommendations(self, site_id: str, limit: int = 10) -> list[Recommendation]:
        """Get pending recommendations for a site (Tier 2 approval queue).

        Args:
            site_id: Building identifier (accepts 'site-002' or 'S002' format)
            limit: Maximum number to return

        Returns:
            List of pending recommendations
        """
        from app.database.repositories import get_recommendation_repository

        try:
            repo = get_recommendation_repository()
            recs = await repo.get_by_status(
                site_id=site_id,
                status=RecommendationStatus.PENDING,
                limit=limit,
            )
            logger.info(f"Found {len(recs)} pending recommendations for {site_id}")
            return recs
        except Exception as e:
            logger.error(f"Error fetching pending recommendations for {site_id}: {e}")
            return []

    async def get_history(
        self,
        site_id: str,
        status_filter: str | None = None,
        risk_level_filter: str | None = None,
        limit: int = 50,
    ) -> list[Recommendation]:
        """Get historical recommendations for a site with optional filters.

        Returns all non-pending recommendations (executed, rejected, auto_executed, failed).

        Args:
            site_id: Building identifier
            status_filter: Optional status to filter by
            risk_level_filter: Optional risk level to filter by
            limit: Maximum number to return

        Returns:
            List of historical recommendations
        """
        from app.database.repositories import get_recommendation_repository

        try:
            repo = get_recommendation_repository()
            recs = await repo.get_history(
                site_id,
                status_filter=status_filter,
                risk_level_filter=risk_level_filter,
                limit=limit,
            )
            return recs
        except Exception as e:
            logger.error(f"Error fetching recommendation history for {site_id}: {e}")
            return []

    async def approve_recommendation(self, rec_id: str, user_id: str, reason: str | None = None) -> Recommendation:
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
        from app.database.repositories import get_recommendation_repository

        try:
            repo = get_recommendation_repository()

            # Fetch recommendation
            rec = await repo.get(rec_id)
            if not rec:
                raise ValueError(f"Recommendation {rec_id} not found")

            # Verify it's in PENDING status
            if rec.status != RecommendationStatus.PENDING:
                raise ValueError(f"Can only approve PENDING recommendations, got {rec.status.value}")

            # Update status and metadata
            rec.status = RecommendationStatus.APPROVED
            rec.approved_by = user_id
            rec.approval_reason = reason

            # Execute the recommendation
            await self.execute_recommendation(rec_id, rec)

            # Save updated recommendation
            await repo.update(rec_id, rec)

            logger.info(f"Approved recommendation {rec_id} by {user_id}: {rec.action_type} on {rec.target_equipment}")

            return rec

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error approving recommendation {rec_id}: {e}")
            raise ValueError(f"Failed to approve recommendation: {e}") from e

    async def reject_recommendation(self, rec_id: str, user_id: str, reason: str) -> Recommendation:
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
        from app.database.repositories import get_recommendation_repository

        try:
            repo = get_recommendation_repository()

            # Fetch recommendation
            rec = await repo.get(rec_id)
            if not rec:
                raise ValueError(f"Recommendation {rec_id} not found")

            # Verify it's in PENDING status
            if rec.status != RecommendationStatus.PENDING:
                raise ValueError(f"Can only reject PENDING recommendations, got {rec.status.value}")

            # Update status and metadata
            rec.status = RecommendationStatus.REJECTED
            rec.rejection_reason = reason
            rec.approved_by = user_id  # Track who rejected it

            self._record_module_feedback(
                rec=rec,
                successful=False,
                outcome_status=RecommendationStatus.REJECTED.value,
                actual_impact={"reason": reason},
                metadata={"rejected_by": user_id},
            )

            # Save updated recommendation
            await repo.update(rec_id, rec)

            logger.info(f"Rejected recommendation {rec_id} by {user_id}: {reason}")

            return rec

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error rejecting recommendation {rec_id}: {e}")
            raise ValueError(f"Failed to reject recommendation: {e}") from e

    async def acknowledge_recommendation(self, rec_id: str, acknowledgement_type: str) -> None:
        """Acknowledge a recommendation (accept or dismiss) from Telegram inline button.

        Sets acknowledgement_type on the recommendation so it counts toward the
        advisory→supervised acceptance rate gate. Status stays PENDING — the
        recommendation still needs to be approved before execution.
        """
        from app.database.repositories import get_recommendation_repository

        if acknowledgement_type not in ("accepted", "dismissed"):
            raise ValueError(f"acknowledgement_type must be 'accepted' or 'dismissed', got {acknowledgement_type}")

        repo = get_recommendation_repository()
        rec = await repo.get(rec_id)
        if not rec:
            raise ValueError(f"Recommendation {rec_id} not found")

        rec.acknowledgement_type = acknowledgement_type
        await repo.update(rec_id, rec)
        logger.info(f"Recommendation {rec_id} acknowledged as {acknowledgement_type}")

    async def execute_recommendation(self, rec_id: str, rec: Recommendation) -> dict[str, Any]:
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
            logger.info(f"Executing recommendation {rec_id}: {rec.action_type} on {rec.target_equipment}")

            # Call device manager to apply action
            result = await device_manager.apply_action(rec.target_equipment, rec.action)

            rec.status = RecommendationStatus.EXECUTED
            rec.executed_at = datetime.utcnow()
            rec.execution_result = result

            self._record_module_feedback(
                rec=rec,
                successful=True,
                outcome_status=RecommendationStatus.EXECUTED.value,
                actual_impact=result if isinstance(result, dict) else {"result": str(result)},
            )

            logger.info(f"Successfully executed recommendation {rec_id}")

            return result

        except Exception as e:
            logger.error(f"Failed to execute recommendation {rec_id}: {e}")
            rec.status = RecommendationStatus.FAILED
            rec.execution_result = {"error": str(e)}
            self._record_module_feedback(
                rec=rec,
                successful=False,
                outcome_status=RecommendationStatus.FAILED.value,
                actual_impact={"error": str(e)},
            )
            raise

    def _record_module_feedback(
        self,
        *,
        rec: Recommendation,
        successful: bool,
        outcome_status: str,
        actual_impact: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record recommendation outcome into module-aware ML feedback."""
        try:
            module_type = self._infer_module_type(rec)
            confidence = rec.get_numeric_confidence()
            ml_feedback = get_ml_feedback_service()
            ml_feedback.record_module_outcome(
                site_id=rec.site_id,
                module_type=module_type,
                recommendation_id=rec.id,
                action_type=rec.action_type,
                successful=successful,
                outcome_status=outcome_status,
                predicted_impact=rec.expected_impact or {},
                actual_impact=actual_impact or {},
                confidence_score=confidence,
                equipment_id=rec.target_equipment or None,
                metadata={
                    "source": "recommendation_service",
                    "risk_level": rec.risk_level.value
                    if isinstance(rec.risk_level, ActionRiskLevel)
                    else str(rec.risk_level),
                    "requires_approval": rec.requires_approval,
                    **(metadata or {}),
                },
            )
        except Exception as e:
            logger.warning("Non-blocking module feedback recording failed for %s: %s", rec.id, e)

    def _infer_module_type(self, rec: Recommendation) -> str:
        """Infer module type for recommendation outcome attribution."""
        action = (rec.action_type or "").lower()
        target = (rec.target_equipment or "").lower()
        action_meta = rec.action or {}

        explicit = action_meta.get("module_type") or action_meta.get("source_module")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip().lower()

        if any(k in action for k in ["lighting", "dali", "luminaire"]):
            return "lighting"
        if any(k in action for k in ["solar", "bess", "pv", "battery"]):
            return "solar"
        if any(k in action for k in ["water", "leak", "hydro"]):
            return "water"
        if any(k in action for k in ["fire", "smoke"]):
            return "fire"
        if "access" in action:
            return "access"
        if "security" in action:
            return "security"
        if any(k in action for k in ["sustain", "carbon", "esg"]):
            return "sustainability"
        if any(k in action for k in ["contract", "sla", "budget"]):
            return "contracts"
        if any(k in action for k in ["energy", "generator", "ups", "power"]):
            return "energy"

        if any(k in target for k in ["chiller", "ahu", "fcu", "vav", "hvac"]):
            return "hvac"
        if any(k in target for k in ["light", "dali", "luminaire"]):
            return "lighting"
        if any(k in target for k in ["meter", "ups", "generator", "transformer", "energy"]):
            return "energy"
        if any(k in target for k in ["solar", "pv", "bess", "battery"]):
            return "solar"

        return "hvac"

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

        if control_tier == "supervised":
            # Tier 2: Always require approval
            return True

        if control_tier == "auto_execute":
            # Tier 3: Auto for low/medium risk, require approval for high/critical
            return risk_level in [ActionRiskLevel.HIGH, ActionRiskLevel.CRITICAL]

        # Default to requiring approval for safety
        return True

    async def _process_rejection_feedback(self, rec: Recommendation, reason: str) -> None:
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
_recommendation_service: RecommendationService | None = None


def get_recommendation_service() -> RecommendationService:
    """Get or create RecommendationService singleton.

    Returns:
        RecommendationService instance
    """
    global _recommendation_service
    if _recommendation_service is None:
        _recommendation_service = RecommendationService()
    return _recommendation_service

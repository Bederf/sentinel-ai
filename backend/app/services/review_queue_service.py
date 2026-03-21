"""Business logic service for review queue management.

Phase 162: Semantic Control Foundation — Plan 05.
Handles auto-approval logic, priority calculation, and review workflow
for semantic classification decisions.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.models.review_queue import ReviewQueueEntry

if TYPE_CHECKING:
    from app.models.point_classification import PointClassification

logger = logging.getLogger(__name__)


class ReviewQueueService:
    """Business logic for review queue management."""

    # Confidence thresholds
    HIGH_CONFIDENCE_THRESHOLD = 0.7
    MEDIUM_CONFIDENCE_THRESHOLD = 0.4

    # Priority thresholds
    HIGH_PRIORITY_THRESHOLD = 50  # Notify on priority <= this value

    def __init__(self) -> None:
        from app.database.repositories.review_queue_repository import ReviewQueueRepository

        self.repo = ReviewQueueRepository()

    # ------------------------------------------------------------------
    # Core queue ingestion
    # ------------------------------------------------------------------

    async def add_classification_to_queue(self, classification: PointClassification) -> str:
        """Add a classification to the review queue based on confidence and safety rules.

        Rules:
        - HIGH confidence (>= 0.7) + LOW safety + passed validation: auto-approve
        - All other cases: added to queue with calculated priority
        - HIGH safety class: forced to queue regardless of confidence
        - Validation errors: force to queue with boosted priority

        Returns:
            'auto_approved' if auto-approved, otherwise the queue entry ID.
        """
        confidence = classification.confidence_score
        safety_class = classification.highest_safety_class.value if classification.highest_safety_class else "LOW"
        validation_passed = classification.validation_passed

        # Auto-approve: high confidence, low safety, passing validations
        if confidence >= self.HIGH_CONFIDENCE_THRESHOLD and safety_class == "LOW" and validation_passed:
            await self._auto_approve(classification)
            return "auto_approved"

        # Calculate review priority
        priority = self._calculate_priority(confidence, safety_class, validation_passed)

        entry = ReviewQueueEntry(
            site_id=classification.site_id,
            equipment_id=classification.device_id or classification.point_id.split(".")[0],
            point_id=classification.point_id,
            classification_id=str(id(classification)),  # Use object id as proxy when no UUID
            semantic_tags=classification.semantic_tags,
            confidence_score=confidence,
            confidence_level=self._get_confidence_level(confidence),
            safety_class=safety_class,
            automation_tier=classification.control_envelope.get("automation_tier", "observe_only")
            if classification.control_envelope
            else "observe_only",
            validation_passed=validation_passed,
            validation_errors=list(classification.validation_errors),
            completeness_score=None,
            status="pending",
            priority=priority,
            classified_by="rule_based_v1",
            classified_at=classification.classification_date,
        )

        entry_id = await self.repo.add_to_queue(entry)

        if priority <= self.HIGH_PRIORITY_THRESHOLD:
            await self._notify_high_priority(entry)

        return entry_id

    # ------------------------------------------------------------------
    # Review decisions
    # ------------------------------------------------------------------

    async def approve_classification(self, entry_id: str, reviewed_by: str, notes: str) -> bool:
        """Approve a classification for control use."""
        success = await self.repo.make_decision(
            entry_id=entry_id,
            decision_type="approve",
            reviewed_by=reviewed_by,
            review_notes=notes,
        )

        if success:
            await self._enable_control(entry_id)

        return success

    async def reject_classification(self, entry_id: str, reviewed_by: str, reason: str, notes: str) -> bool:
        """Reject a classification — exclude from control decisions."""
        return await self.repo.make_decision(
            entry_id=entry_id,
            decision_type="reject",
            reviewed_by=reviewed_by,
            review_notes=notes,
            decision_reason=reason,
        )

    async def override_classification(
        self,
        entry_id: str,
        reviewed_by: str,
        correct_tags: list[str],
        justification: str,
    ) -> bool:
        """Override classification with corrected tags and re-validate."""
        success = await self.repo.make_override(
            entry_id=entry_id,
            reviewed_by=reviewed_by,
            correct_tags=correct_tags,
            justification=justification,
        )

        if success:
            await self._revalidate_overridden(entry_id)

        return success

    # ------------------------------------------------------------------
    # Priority calculation
    # ------------------------------------------------------------------

    def _calculate_priority(self, confidence: float, safety_class: str, validation_passed: bool) -> int:
        """Calculate review priority (1-100, lower is higher priority).

        Rules:
        - Base: 100
        - Confidence < 0.4: -40
        - Confidence 0.4-0.6: -20
        - Safety HIGH: -25
        - Safety MEDIUM: -10
        - Validation errors: -15
        """
        base_priority = 100

        # Confidence factor
        if confidence < self.MEDIUM_CONFIDENCE_THRESHOLD:
            base_priority -= 40
        elif confidence < self.HIGH_CONFIDENCE_THRESHOLD:
            base_priority -= 20

        # Safety class factor
        if safety_class == "HIGH":
            base_priority -= 25
        elif safety_class == "MEDIUM":
            base_priority -= 10

        # Validation errors
        if not validation_passed:
            base_priority -= 15

        return max(1, base_priority)

    def _get_confidence_level(self, confidence: float) -> str:
        """Map confidence score to level label."""
        if confidence >= self.HIGH_CONFIDENCE_THRESHOLD:
            return "HIGH"
        if confidence >= self.MEDIUM_CONFIDENCE_THRESHOLD:
            return "MEDIUM"
        return "LOW"

    # ------------------------------------------------------------------
    # Private helpers (stubs for future integration)
    # ------------------------------------------------------------------

    async def _auto_approve(self, classification: PointClassification) -> None:
        """Auto-approve a high-confidence, low-safety, passing classification.

        Creates an auto-approved entry for audit trail purposes.
        """
        logger.info(
            "Auto-approving classification for point %s (confidence=%.2f, safety=LOW)",
            classification.point_id,
            classification.confidence_score,
        )
        # Future: write directly to approved control registry

    async def _enable_control(self, entry_id: str) -> None:
        """Enable a reviewed point for control use (Phase 162B integration point)."""
        logger.debug("Control enabled for review entry %s (Phase 162B integration pending)", entry_id)

    async def _revalidate_overridden(self, entry_id: str) -> None:
        """Re-run static validation after an override (Phase 162B integration point)."""
        logger.debug("Revalidation requested for overridden entry %s (Phase 162B pending)", entry_id)

    async def _notify_high_priority(self, entry: ReviewQueueEntry) -> None:
        """Notify facility managers of high-priority items requiring review."""
        logger.info(
            "HIGH PRIORITY review needed: point=%s, safety=%s, confidence=%.2f, priority=%d",
            entry.point_id,
            entry.safety_class,
            entry.confidence_score,
            entry.priority,
        )
        # Future: integrate with notification_providers

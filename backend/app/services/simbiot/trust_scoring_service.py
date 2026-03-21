"""Trust scoring service — three-layer trust model for point classifications.

Phase 162: Semantic Control Foundation — Plan 04.
Combines classification confidence, data quality, and control trust history
into a holistic TrustProfile used to gate autonomous control decisions.
"""

from __future__ import annotations

import logging

from app.database.repositories.trust_history_repository import TrustHistoryRepository
from app.models.point_classification import PointClassification
from app.models.trust_history import TrustHistory, TrustProfile

logger = logging.getLogger(__name__)


class TrustScoringService:
    """Calculates three-layer trust scores for point classifications."""

    def __init__(self) -> None:
        self.trust_history_repo = TrustHistoryRepository()

    # ------------------------------------------------------------------
    # Core profile calculation
    # ------------------------------------------------------------------

    async def calculate_trust_profile(self, classification: PointClassification) -> TrustProfile:
        """Calculate complete trust profile for a point classification.

        Combines classification confidence, data quality score, and control
        trust history into a weighted overall score.  The automation tier
        and risk level are derived from the overall score and safety class.
        """
        # --- Layer 1: Classification confidence ---
        classification_confidence = classification.confidence_score
        evidence_count = len(classification.evidence_records)
        required_evidence_met = evidence_count > 0

        # --- Layer 2: Data quality score ---
        data_quality_score = classification.data_quality_score

        # --- Layer 3: Control trust score (from persisted history) ---
        trust_history = await self.trust_history_repo.get_trust_history(
            classification.point_id,
            classification.site_id,
        )

        if trust_history is not None:
            control_trust_score = trust_history.trust_score
            stability_days = trust_history.stability_days
            validation_runs = trust_history.validation_runs
            successful_actions = trust_history.successful_actions
            failed_actions = trust_history.failed_actions
        else:
            # No history yet — start with neutral trust (0.5)
            control_trust_score = 0.5
            stability_days = 0
            validation_runs = 0
            successful_actions = 0
            failed_actions = 0

        # --- Weighted overall trust ---
        overall_trust = TrustProfile.calculate_overall_trust(
            classification_confidence,
            data_quality_score,
            control_trust_score,
        )

        # --- Automation tier & risk level ---
        safety_class = classification.highest_safety_class.value if classification.highest_safety_class else "LOW"
        automation_tier = TrustProfile.determine_automation_tier(overall_trust, safety_class)
        risk_level = self._assess_risk_level(overall_trust, safety_class)

        return TrustProfile(
            point_id=classification.point_id,
            classification_confidence=classification_confidence,
            evidence_count=evidence_count,
            required_evidence_met=required_evidence_met,
            data_quality_score=data_quality_score,
            stability_days=stability_days,
            control_trust_score=control_trust_score,
            validation_runs=validation_runs,
            successful_actions=successful_actions,
            failed_actions=failed_actions,
            overall_trust_score=overall_trust,
            risk_level=risk_level,
            automation_tier=automation_tier,
        )

    # ------------------------------------------------------------------
    # Trust update helpers (called by validation engine / control layer)
    # ------------------------------------------------------------------

    async def update_trust_after_validation(self, point_id: str, site_id: str, validation_passed: bool) -> None:
        """Update trust history after a validation run."""
        await self.trust_history_repo.increment_validation_run(point_id, site_id, had_error=not validation_passed)

    async def update_trust_after_action(
        self,
        point_id: str,
        site_id: str,
        success: bool,
        expected_outcome: dict,
        actual_outcome: dict,
    ) -> None:
        """Update trust history after a control action completes."""
        await self.trust_history_repo.record_control_action(
            point_id, site_id, success, expected_outcome, actual_outcome
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _assess_risk_level(self, overall_trust: float, safety_class: str) -> str:
        """Assess risk level based on trust score and safety class.

        Returns: LOW | MEDIUM | HIGH
        """
        if safety_class == "HIGH":
            return "HIGH"  # Safety-critical points always carry high risk
        elif safety_class == "MEDIUM":
            return "HIGH" if overall_trust < 0.4 else "MEDIUM"
        else:  # LOW safety
            if overall_trust < 0.3:
                return "HIGH"
            elif overall_trust < 0.6:
                return "MEDIUM"
            else:
                return "LOW"

    # ------------------------------------------------------------------
    # Convenience factory for new-point bootstrap
    # ------------------------------------------------------------------

    @staticmethod
    def bootstrap_trust_history(point_id: str, site_id: str) -> TrustHistory:
        """Return a zeroed TrustHistory for a brand-new point."""
        return TrustHistory(point_id=point_id, site_id=site_id)

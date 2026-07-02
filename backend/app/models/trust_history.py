"""Pydantic models for trust history and three-layer trust profiles.

Phase 162: Semantic Control Foundation — Plan 04.
Trust history tracks how points accumulate confidence over time through
stable operation and successful control actions.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TrustHistory(BaseModel):
    """Historical trust data for a point over time."""

    point_id: str
    site_id: str
    equipment_id: str = ""  # Canonical equipment code (empty for legacy rows)
    stability_days: int = 0  # Days without validation errors
    validation_runs: int = 0  # Total validation runs since first classification
    successful_actions: int = 0  # Control actions that achieved expected outcome
    failed_actions: int = 0  # Control actions that did NOT achieve expected outcome
    last_validation_error: datetime | None = None
    last_successful_action: datetime | None = None
    trust_score: float = 0.0  # Calculated: stability * success_rate
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @staticmethod
    def calculate_trust_score(
        stability_days: int,
        validation_runs: int,
        successful_actions: int,
        failed_actions: int,
    ) -> float:
        """Calculate trust score (0.0 to 1.0) from trust history metrics.

        Formula:
        - Base score from stability (stability_days / 30, max 0.6)
        - Boost from successful actions (+0.1 per 10 successes, max 0.3)
        - Penalty from failures (-0.1 per failure, min 0.0)
        - Minimum validation runs required (5 runs before full trust)
        """
        validation_factor = validation_runs / 5.0 if validation_runs < 5 else 1.0

        stability_score = min(stability_days / 30.0, 0.6) * validation_factor
        success_rate = (
            (successful_actions / (successful_actions + failed_actions + 1))
            if (successful_actions + failed_actions) > 0
            else 0.5
        )
        action_score = min(successful_actions / 10.0, 0.3)
        failure_penalty = failed_actions * 0.1

        trust_score = stability_score + (action_score * success_rate) - failure_penalty
        return max(0.0, min(1.0, trust_score))


class TrustProfile(BaseModel):
    """Three-layer trust model combining classification, data quality, and control trust."""

    point_id: str

    # Layer 1: Classification confidence
    classification_confidence: float  # From semantic classifier
    evidence_count: int  # Number of evidence records
    required_evidence_met: bool

    # Layer 2: Data quality score
    data_quality_score: float  # From data quality service
    stability_days: int  # Consecutive days without errors

    # Layer 3: Control trust score
    control_trust_score: float  # Calculated from trust history
    validation_runs: int
    successful_actions: int
    failed_actions: int

    # Overall trust score
    overall_trust_score: float  # Weighted combination of all layers

    # Risk assessment
    risk_level: str  # LOW, MEDIUM, HIGH
    automation_tier: str  # observe_only, supervised, automatic

    @staticmethod
    def calculate_overall_trust(
        classification_confidence: float,
        data_quality_score: float,
        control_trust_score: float,
    ) -> float:
        """Calculate overall trust score with weighted formula.

        Weights:
        - Classification confidence: 40% (semantic accuracy)
        - Data quality score: 30% (sensor reliability)
        - Control trust score: 30% (historical performance)
        """
        return 0.4 * classification_confidence + 0.3 * data_quality_score + 0.3 * control_trust_score

    @staticmethod
    def determine_automation_tier(overall_trust: float, safety_class: str) -> str:
        """Determine automation tier based on trust score and safety class.

        Decision table:
        - HIGH safety + any trust: observe_only
        - MEDIUM safety + trust < 0.6: supervised
        - MEDIUM safety + trust >= 0.6: automatic
        - LOW safety + trust < 0.4: supervised
        - LOW safety + trust >= 0.4: automatic
        """
        if safety_class == "HIGH":
            return "observe_only"
        elif safety_class == "MEDIUM":
            return "supervised" if overall_trust < 0.6 else "automatic"
        else:  # LOW safety
            return "supervised" if overall_trust < 0.4 else "automatic"

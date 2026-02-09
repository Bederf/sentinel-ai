"""Recommendation scorer service for multi-objective scoring and ranking.

Implements profile-based scoring of AI-generated recommendations using
configurable weights for comfort, cost, runtime, energy, and maintenance impacts.
"""

import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class RecommendationScorer:
    """Score and rank recommendations based on profile weights.

    Applies multi-objective scoring using profile weights to rank recommendations
    in order of their value across multiple competing objectives:
    - Comfort: occupant satisfaction (temperature, lighting, air quality)
    - Cost: operational expense reduction
    - Runtime: equipment utilization and lifecycle extension
    - Energy: kWh consumption reduction
    - Maintenance: reduced service calls and preventive care
    """

    def __init__(self, profile: Dict[str, Any]):
        """Initialize scorer with a profile definition.

        Args:
            profile: Profile dictionary containing weights dict:
                {
                    "weights": {
                        "comfort": 0.40,
                        "cost": 0.10,
                        "runtime": 0.10,
                        "energy": 0.20,
                        "maintenance": 0.20
                    }
                }
        """
        self.profile = profile

        # Extract weights, defaulting to uniform distribution if not provided
        weights = profile.get("weights", {})
        total_weight = sum(weights.values()) if weights else 0

        if total_weight == 0:
            # Default to uniform weights
            weights = {
                "comfort": 0.2,
                "cost": 0.2,
                "runtime": 0.2,
                "energy": 0.2,
                "maintenance": 0.2,
            }

        self.weights = weights
        logger.debug(f"Initialized RecommendationScorer with weights: {self.weights}")

    def score_recommendation(self, recommendation: Dict[str, Any]) -> float:
        """Score a single recommendation against profile weights.

        Uses profile weights to calculate weighted score:
        score = Σ(normalized_impact * weight)

        Impact values are extracted and normalized to 0-1 scale:
        - comfort_impact: -2 to +2 → 0..1
        - cost_impact: -100 to +100 → 0..1 (clamped)
        - health_impact: -2 to +2 → 0..1
        - energy_impact: -50 to +50 → 0..1 (clamped)
        - maintenance_impact: -2 to +2 → 0..1

        Args:
            recommendation: Dictionary containing impact fields

        Returns:
            Float score between 0-1 (higher is better)
        """
        # Extract impact scores from recommendation
        comfort_impact = recommendation.get("comfort_impact", 0)
        cost_impact = recommendation.get("cost_impact", 0)
        health_impact = recommendation.get("health_impact", 0)
        energy_impact = recommendation.get("energy_impact", 0)
        maintenance_impact = recommendation.get("maintenance_impact", 0)

        # Normalize impacts to 0-1 scale
        # (impact values are typically -2 to +2 or -100 to +100)
        comfort_norm = (comfort_impact + 2) / 4  # -2..+2 → 0..1
        cost_norm = min(1.0, max(0.0, cost_impact / 100))  # -100..+100 → 0..1
        health_norm = (health_impact + 2) / 4  # -2..+2 → 0..1
        energy_norm = min(1.0, max(0.0, energy_impact / 50))  # -50..+50 → 0..1
        maintenance_norm = (maintenance_impact + 2) / 4  # -2..+2 → 0..1

        # Apply profile weights
        score = (
            comfort_norm * self.weights.get("comfort", 0.2) +
            cost_norm * self.weights.get("cost", 0.2) +
            health_norm * self.weights.get("runtime", 0.2) +
            energy_norm * self.weights.get("energy", 0.2) +
            maintenance_norm * self.weights.get("maintenance", 0.2)
        )

        return score

    def rank_recommendations(
        self,
        recommendations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Rank recommendations by multi-objective score.

        Scores all recommendations and sorts them by score in descending order
        (highest score first). Adds 'multi_objective_score' field to each recommendation.

        Args:
            recommendations: List of recommendation dictionaries

        Returns:
            List sorted by score descending (highest value first).
            Each recommendation now includes 'multi_objective_score' field.
        """
        # Score all recommendations
        for rec in recommendations:
            rec["multi_objective_score"] = self.score_recommendation(rec)

        # Sort by score descending (highest value first)
        sorted_recs = sorted(
            recommendations,
            key=lambda r: r.get("multi_objective_score", 0),
            reverse=True
        )

        return sorted_recs

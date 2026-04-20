"""Tests for RecommendationScorer service.

Tests multi-objective scoring and ranking logic with different profile weights.
"""

import pytest

from app.services.recommendation_scorer import RecommendationScorer


class TestRecommendationScorer:
    """Test RecommendationScorer scoring and ranking logic."""

    def test_scorer_initialization(self):
        """Test scorer initializes with profile weights."""
        profile = {
            "weights": {
                "comfort": 0.40,
                "cost": 0.10,
                "runtime": 0.10,
                "energy": 0.20,
                "maintenance": 0.20,
            }
        }

        scorer = RecommendationScorer(profile)
        assert scorer.profile == profile
        assert scorer.weights == profile["weights"]

    def test_scorer_default_weights(self):
        """Test scorer defaults to uniform weights when profile has no weights."""
        profile = {}

        scorer = RecommendationScorer(profile)
        expected_weights = {
            "comfort": 0.2,
            "cost": 0.2,
            "runtime": 0.2,
            "energy": 0.2,
            "maintenance": 0.2,
        }
        assert scorer.weights == expected_weights

    def test_score_single_recommendation(self):
        """Test scoring a single recommendation."""
        profile = {
            "weights": {
                "comfort": 0.40,
                "cost": 0.10,
                "runtime": 0.10,
                "energy": 0.20,
                "maintenance": 0.20,
            }
        }

        scorer = RecommendationScorer(profile)

        recommendation = {
            "action": "lower_setpoint",
            "comfort_impact": 2.0,
            "cost_impact": -50,
            "health_impact": -1,
            "energy_impact": 25,
            "maintenance_impact": -0.5,
        }

        score = scorer.score_recommendation(recommendation)

        # Score should be between 0 and 1
        assert 0 <= score <= 1

        # With high comfort weight and positive comfort impact, score should be good
        assert score > 0.5

    def test_score_with_zero_impacts(self):
        """Test scoring with zero impacts."""
        profile = {
            "weights": {
                "comfort": 0.40,
                "cost": 0.10,
                "runtime": 0.10,
                "energy": 0.20,
                "maintenance": 0.20,
            }
        }

        scorer = RecommendationScorer(profile)

        recommendation = {
            "action": "no_op",
            # All impacts are 0
        }

        score = scorer.score_recommendation(recommendation)

        # With all zero impacts, normalized values should be 0.5 (center of scale)
        # Score = 0.5 * (0.40 + 0.10 + 0.10 + 0.20 + 0.20) = 0.5 * 1.0 = 0.5
        assert score == pytest.approx(0.5, abs=0.01)

    def test_score_weights_applied_correctly(self):
        """Test that profile weights are applied correctly to impacts.

        When a profile heavily weights comfort, recommendations with strong
        positive comfort impact should score higher than those with negative
        comfort impact, all else being equal.
        """
        # Comfort-first profile
        comfort_profile = {
            "weights": {
                "comfort": 0.40,
                "cost": 0.10,
                "runtime": 0.10,
                "energy": 0.20,
                "maintenance": 0.20,
            }
        }

        scorer_comfort = RecommendationScorer(comfort_profile)

        # Positive comfort impact (base)
        positive_comfort_rec = {
            "action": "high_comfort",
            "comfort_impact": 2.0,  # Max positive comfort
            "cost_impact": 0,
            "health_impact": 0,
            "energy_impact": 0,
            "maintenance_impact": 0,
        }

        # Negative comfort impact (same cost, energy, etc.)
        negative_comfort_rec = {
            "action": "low_comfort",
            "comfort_impact": -2.0,  # Max negative comfort
            "cost_impact": 0,
            "health_impact": 0,
            "energy_impact": 0,
            "maintenance_impact": 0,
        }

        score_positive = scorer_comfort.score_recommendation(positive_comfort_rec)
        score_negative = scorer_comfort.score_recommendation(negative_comfort_rec)

        # Comfort-first profile should rank positive comfort much higher
        assert score_positive > score_negative
        # Since comfort has 0.40 weight and range 0 to 1, difference should be ~0.4
        assert (score_positive - score_negative) >= 0.35

    def test_ranking_sorts_by_score_descending(self):
        """Test that ranking sorts recommendations by score descending."""
        profile = {
            "weights": {
                "comfort": 0.40,
                "cost": 0.10,
                "runtime": 0.10,
                "energy": 0.20,
                "maintenance": 0.20,
            }
        }

        scorer = RecommendationScorer(profile)

        recommendations = [
            {
                "action": "action_1",
                "comfort_impact": 0.5,
                "cost_impact": 0,
                "health_impact": 0,
                "energy_impact": 0,
                "maintenance_impact": 0,
            },
            {
                "action": "action_2",
                "comfort_impact": 2.0,
                "cost_impact": 50,
                "health_impact": 1,
                "energy_impact": 25,
                "maintenance_impact": 1,
            },
            {
                "action": "action_3",
                "comfort_impact": -1.0,
                "cost_impact": -50,
                "health_impact": -1,
                "energy_impact": -25,
                "maintenance_impact": -1,
            },
        ]

        ranked = scorer.rank_recommendations(recommendations)

        # All recommendations should have scores added
        assert all("multi_objective_score" in r for r in ranked)

        # Should be sorted descending
        scores = [r["multi_objective_score"] for r in ranked]
        assert scores == sorted(scores, reverse=True)

        # action_2 should be highest (best impacts)
        assert ranked[0]["action"] == "action_2"

    def test_ranking_empty_list(self):
        """Test ranking with empty recommendations list."""
        profile = {
            "weights": {
                "comfort": 0.40,
                "cost": 0.10,
                "runtime": 0.10,
                "energy": 0.20,
                "maintenance": 0.20,
            }
        }

        scorer = RecommendationScorer(profile)
        ranked = scorer.rank_recommendations([])

        assert ranked == []

    def test_ranking_single_item(self):
        """Test ranking with single recommendation."""
        profile = {
            "weights": {
                "comfort": 0.40,
                "cost": 0.10,
                "runtime": 0.10,
                "energy": 0.20,
                "maintenance": 0.20,
            }
        }

        scorer = RecommendationScorer(profile)

        recommendations = [
            {
                "action": "single_action",
                "comfort_impact": 1.0,
                "cost_impact": 50,
            }
        ]

        ranked = scorer.rank_recommendations(recommendations)

        assert len(ranked) == 1
        assert "multi_objective_score" in ranked[0]
        assert 0 <= ranked[0]["multi_objective_score"] <= 1

    def test_score_range_validation(self):
        """Test that scores stay within 0-1 range with extreme values.

        The scorer clamps individual normalized scores and the final result,
        so even extreme values should stay within 0-1.
        """
        profile = {
            "weights": {
                "comfort": 0.40,
                "cost": 0.10,
                "runtime": 0.10,
                "energy": 0.20,
                "maintenance": 0.20,
            }
        }

        scorer = RecommendationScorer(profile)

        # Extreme positive impacts (all clamped to 1.0)
        max_positive_rec = {
            "action": "max_positive",
            "comfort_impact": 100,  # Way beyond normal range, clamped to 1.0
            "cost_impact": 1000,  # Way beyond normal range, clamped to 1.0
            "health_impact": 100,
            "energy_impact": 1000,
            "maintenance_impact": 100,
        }

        # Extreme negative impacts (all clamped to 0.0)
        max_negative_rec = {
            "action": "max_negative",
            "comfort_impact": -100,
            "cost_impact": -1000,
            "health_impact": -100,
            "energy_impact": -1000,
            "maintenance_impact": -100,
        }

        score_pos = scorer.score_recommendation(max_positive_rec)
        score_neg = scorer.score_recommendation(max_negative_rec)

        # Both should be within 0-1 range (clamped)
        assert 0 <= score_pos <= 1, f"Positive score {score_pos} out of range"
        assert 0 <= score_neg <= 1, f"Negative score {score_neg} out of range"

    def test_cost_saving_profile_favors_cost(self):
        """Test that cost-saving profile ranks cost higher.

        With a cost-focused profile, recommendations with high cost savings
        should rank higher than comfort-focused recommendations.
        """
        cost_profile = {
            "weights": {
                "comfort": 0.15,
                "cost": 0.35,
                "runtime": 0.10,
                "energy": 0.30,
                "maintenance": 0.10,
            }
        }

        scorer_cost = RecommendationScorer(cost_profile)

        # Cost-saving recommendation
        cost_saving_rec = {
            "action": "reduce_runtime",
            "comfort_impact": -1.0,
            "cost_impact": 100,  # High cost savings
            "health_impact": -0.5,
            "energy_impact": 40,
            "maintenance_impact": -0.5,
        }

        # Comfort-focused recommendation
        comfort_rec = {
            "action": "tight_control",
            "comfort_impact": 2.0,  # High comfort
            "cost_impact": -80,  # High cost increase
            "health_impact": 1,
            "energy_impact": -30,
            "maintenance_impact": 1,
        }

        score_cost = scorer_cost.score_recommendation(cost_saving_rec)
        score_comfort = scorer_cost.score_recommendation(comfort_rec)

        # Cost-focused profile should rank cost-saving higher
        assert score_cost > score_comfort

    def test_asset_sweating_profile_favors_runtime(self):
        """Test that asset-sweating profile ranks runtime higher.

        With a runtime-focused profile, recommendations with high runtime
        should rank higher than cost-reduction recommendations.
        """
        sweat_profile = {
            "weights": {
                "runtime": 0.35,
                "comfort": 0.10,
                "cost": 0.15,
                "maintenance": 0.10,
                "energy": 0.30,
            }
        }

        scorer_sweat = RecommendationScorer(sweat_profile)

        # High runtime recommendation
        high_runtime_rec = {
            "action": "maximize_utilization",
            "comfort_impact": -1.0,
            "cost_impact": -50,
            "health_impact": 2.0,  # High runtime/utilization
            "energy_impact": 30,
            "maintenance_impact": -1.5,
        }

        # Cost-reduction recommendation
        cost_reduction_rec = {
            "action": "reduce_load",
            "comfort_impact": -0.5,
            "cost_impact": 100,  # High cost savings
            "health_impact": -2.0,  # Low runtime
            "energy_impact": -40,
            "maintenance_impact": 0.5,
        }

        score_sweat = scorer_sweat.score_recommendation(high_runtime_rec)
        score_cost = scorer_sweat.score_recommendation(cost_reduction_rec)

        # Runtime-focused profile should rank runtime higher
        assert score_sweat > score_cost

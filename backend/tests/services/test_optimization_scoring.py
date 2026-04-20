"""Integration tests for recommendation scoring in optimization API.

Tests that scoring is properly integrated into AI optimizer and API responses.
"""

import pytest

from app.models.optimization import OptimizationRecommendation


class TestOptimizationScoringIntegration:
    """Test recommendation scoring in optimization service."""

    @pytest.mark.asyncio
    async def test_ai_optimizer_scores_recommendations(self):
        """Test that AIOptimizer applies scoring to recommendations."""
        from app.services.ai_optimizer import AIOptimizerService

        optimizer = AIOptimizerService()

        # Create mock recommendation
        mock_rec = OptimizationRecommendation(
            site_id="site-002",
            timestamp="2024-01-01T00:00:00Z",
            recommendations=[
                {
                    "action": "lower_setpoint",
                    "equipment": "chiller-1",
                    "comfort_impact": 1.0,
                    "cost_impact": 50,
                    "health_impact": 0.5,
                    "energy_impact": 25,
                    "maintenance_impact": -0.5,
                },
                {
                    "action": "generator_dispatch",
                    "equipment": "gen-1",
                    "comfort_impact": -0.5,
                    "cost_impact": 100,
                    "health_impact": 1.0,
                    "energy_impact": 40,
                    "maintenance_impact": 0.5,
                },
            ],
            projected_savings={},
            confidence=0.8,
            reasoning="Test recommendations",
        )

        # Create test profile
        test_profile = {
            "name": "Test Profile",
            "weights": {
                "comfort": 0.40,
                "cost": 0.10,
                "runtime": 0.10,
                "energy": 0.20,
                "maintenance": 0.20,
            },
        }

        # Score the recommendations
        scored_rec = optimizer._score_and_rank_recommendations(mock_rec, test_profile)

        # Verify scoring was applied
        assert len(scored_rec.recommendations) == 2
        assert all("multi_objective_score" in r for r in scored_rec.recommendations)

        # Verify scores are in valid range
        for rec in scored_rec.recommendations:
            assert 0 <= rec["multi_objective_score"] <= 1

        # Verify sorted descending
        scores = [r["multi_objective_score"] for r in scored_rec.recommendations]
        assert scores == sorted(scores, reverse=True)

        # Verify scoring summary
        assert scored_rec.scoring_summary is not None
        assert scored_rec.scoring_summary["total_recommendations"] == 2
        assert scored_rec.scoring_summary["top_score"] > 0
        assert scored_rec.scoring_summary["avg_score"] > 0

    @pytest.mark.asyncio
    async def test_optimization_response_includes_scores(self):
        """Test that optimization API response includes scoring info."""
        from app.services.ai_optimizer import AIOptimizerService

        optimizer = AIOptimizerService()

        # Create test recommendation with multiple items
        mock_rec = OptimizationRecommendation(
            site_id="site-002",
            timestamp="2024-01-01T00:00:00Z",
            recommendations=[
                {
                    "action": "action_1",
                    "comfort_impact": 2.0,
                    "cost_impact": 0,
                    "health_impact": 0,
                    "energy_impact": 0,
                    "maintenance_impact": 0,
                },
                {
                    "action": "action_2",
                    "comfort_impact": -1.0,
                    "cost_impact": 100,
                    "health_impact": 1,
                    "energy_impact": 25,
                    "maintenance_impact": 1,
                },
            ],
            projected_savings={},
            confidence=0.8,
            reasoning="Test",
        )

        # Score with comfort profile
        comfort_profile = {
            "name": "Comfort First",
            "weights": {
                "comfort": 0.40,
                "cost": 0.10,
                "runtime": 0.10,
                "energy": 0.20,
                "maintenance": 0.20,
            },
        }

        scored = optimizer._score_and_rank_recommendations(mock_rec, comfort_profile)

        # Convert to dict for API response
        response_dict = scored.to_dict()

        # Verify response includes scoring info
        assert "recommendations" in response_dict
        assert "scoring_summary" in response_dict
        assert response_dict["scoring_summary"]["total_recommendations"] == 2
        assert "top_score" in response_dict["scoring_summary"]
        assert "avg_score" in response_dict["scoring_summary"]

        # Verify all recommendations have scores
        for rec in response_dict["recommendations"]:
            assert "multi_objective_score" in rec

    @pytest.mark.asyncio
    async def test_different_profiles_produce_different_rankings(self):
        """Test that different profiles produce different ranking orders."""
        from app.services.ai_optimizer import AIOptimizerService

        optimizer = AIOptimizerService()

        # Test recommendations with different impact profiles
        test_recs = OptimizationRecommendation(
            site_id="site-002",
            timestamp="2024-01-01T00:00:00Z",
            recommendations=[
                {
                    "id": "comfort_action",
                    "action": "tight_control",
                    "comfort_impact": 2.0,
                    "cost_impact": -100,
                    "health_impact": 0,
                    "energy_impact": -40,
                    "maintenance_impact": 0,
                },
                {
                    "id": "cost_action",
                    "action": "reduce_runtime",
                    "comfort_impact": -1.0,
                    "cost_impact": 100,
                    "health_impact": -0.5,
                    "energy_impact": 30,
                    "maintenance_impact": -0.5,
                },
                {
                    "id": "runtime_action",
                    "action": "maximize_utilization",
                    "comfort_impact": -0.5,
                    "cost_impact": -50,
                    "health_impact": 2.0,
                    "energy_impact": 20,
                    "maintenance_impact": -1.0,
                },
            ],
            projected_savings={},
            confidence=0.8,
            reasoning="Test",
        )

        # Comfort profile
        comfort_profile = {
            "name": "Comfort",
            "weights": {
                "comfort": 0.40,
                "cost": 0.10,
                "runtime": 0.10,
                "energy": 0.20,
                "maintenance": 0.20,
            },
        }

        # Cost profile
        cost_profile = {
            "name": "Cost",
            "weights": {
                "comfort": 0.15,
                "cost": 0.35,
                "runtime": 0.10,
                "energy": 0.30,
                "maintenance": 0.10,
            },
        }

        # Asset-sweating profile
        sweat_profile = {
            "name": "Asset Sweating",
            "weights": {
                "runtime": 0.35,
                "comfort": 0.10,
                "cost": 0.15,
                "maintenance": 0.10,
                "energy": 0.30,
            },
        }

        # Score with different profiles
        comfort_ranked = optimizer._score_and_rank_recommendations(
            OptimizationRecommendation(
                site_id=test_recs.site_id,
                timestamp=test_recs.timestamp,
                recommendations=[r.copy() for r in test_recs.recommendations],
                projected_savings={},
                confidence=test_recs.confidence,
                reasoning=test_recs.reasoning,
            ),
            comfort_profile,
        )

        cost_ranked = optimizer._score_and_rank_recommendations(
            OptimizationRecommendation(
                site_id=test_recs.site_id,
                timestamp=test_recs.timestamp,
                recommendations=[r.copy() for r in test_recs.recommendations],
                projected_savings={},
                confidence=test_recs.confidence,
                reasoning=test_recs.reasoning,
            ),
            cost_profile,
        )

        sweat_ranked = optimizer._score_and_rank_recommendations(
            OptimizationRecommendation(
                site_id=test_recs.site_id,
                timestamp=test_recs.timestamp,
                recommendations=[r.copy() for r in test_recs.recommendations],
                projected_savings={},
                confidence=test_recs.confidence,
                reasoning=test_recs.reasoning,
            ),
            sweat_profile,
        )

        # Extract ranking order
        comfort_order = [r.get("id") for r in comfort_ranked.recommendations]
        cost_order = [r.get("id") for r in cost_ranked.recommendations]
        sweat_order = [r.get("id") for r in sweat_ranked.recommendations]

        # Different profiles should produce different rankings
        # Comfort profile should rank comfort_action first
        assert comfort_order[0] == "comfort_action"

        # Cost profile should rank cost_action first
        assert cost_order[0] == "cost_action"

        # Runtime profile should rank runtime_action first
        assert sweat_order[0] == "runtime_action"

    @pytest.mark.asyncio
    async def test_scoring_preserves_recommendation_fields(self):
        """Test that scoring doesn't lose original recommendation fields."""
        from app.services.ai_optimizer import AIOptimizerService

        optimizer = AIOptimizerService()

        original_rec = OptimizationRecommendation(
            site_id="site-002",
            timestamp="2024-01-01T00:00:00Z",
            recommendations=[
                {
                    "action": "test_action",
                    "equipment": "test-equip",
                    "reason": "Test reason",
                    "expected_savings": 1000,
                    "comfort_impact": 1.0,
                    "cost_impact": 50,
                    "health_impact": 0,
                    "energy_impact": 0,
                    "maintenance_impact": 0,
                    "custom_field": "custom_value",
                }
            ],
            projected_savings={},
            confidence=0.8,
            reasoning="Test",
        )

        test_profile = {
            "name": "Test",
            "weights": {
                "comfort": 0.2,
                "cost": 0.2,
                "runtime": 0.2,
                "energy": 0.2,
                "maintenance": 0.2,
            },
        }

        scored = optimizer._score_and_rank_recommendations(original_rec, test_profile)

        # Verify original fields are preserved
        scored_rec = scored.recommendations[0]
        assert scored_rec["action"] == "test_action"
        assert scored_rec["equipment"] == "test-equip"
        assert scored_rec["reason"] == "Test reason"
        assert scored_rec["expected_savings"] == 1000
        assert scored_rec["custom_field"] == "custom_value"

        # And new score field is added
        assert "multi_objective_score" in scored_rec

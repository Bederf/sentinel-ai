"""Performance tests for recommendation scoring.

Ensures that scoring doesn't create unacceptable latency in recommendations.
"""

import time
import random
from app.services.recommendation_scorer import RecommendationScorer


class TestScoringPerformance:
    """Test performance of recommendation scoring."""

    def test_scoring_100_recommendations_under_100ms(self):
        """Test that scoring 100 recommendations completes in < 100ms."""
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

        # Generate 100 recommendations with random impacts
        recommendations = []
        for i in range(100):
            rec = {
                "id": f"rec_{i}",
                "action": f"action_{i}",
                "comfort_impact": random.uniform(-2, 2),
                "cost_impact": random.uniform(-100, 100),
                "health_impact": random.uniform(-2, 2),
                "energy_impact": random.uniform(-50, 50),
                "maintenance_impact": random.uniform(-2, 2),
            }
            recommendations.append(rec)

        # Time the scoring
        start = time.time()
        ranked = scorer.rank_recommendations(recommendations)
        elapsed = time.time() - start

        # Should complete in < 100ms
        elapsed_ms = elapsed * 1000
        assert elapsed < 0.1, f"Scoring 100 recommendations took {elapsed_ms:.2f}ms"

        # Verify all recommendations were scored
        assert len(ranked) == 100
        assert all("multi_objective_score" in r for r in ranked)

        # Verify sorted
        scores = [r["multi_objective_score"] for r in ranked]
        assert scores == sorted(scores, reverse=True)

        print(f"✓ Scored 100 recommendations in {elapsed_ms:.2f}ms")

    def test_scoring_1000_recommendations_acceptable_performance(self):
        """Test that scoring 1000 recommendations has acceptable performance."""
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

        # Generate 1000 recommendations
        recommendations = []
        for i in range(1000):
            rec = {
                "id": f"rec_{i}",
                "action": f"action_{i}",
                "comfort_impact": random.uniform(-2, 2),
                "cost_impact": random.uniform(-100, 100),
                "health_impact": random.uniform(-2, 2),
                "energy_impact": random.uniform(-50, 50),
                "maintenance_impact": random.uniform(-2, 2),
            }
            recommendations.append(rec)

        # Time the scoring
        start = time.time()
        ranked = scorer.rank_recommendations(recommendations)
        elapsed = time.time() - start

        # Should complete in < 1 second (even for 1000 items)
        elapsed_ms = elapsed * 1000
        assert elapsed < 1.0, f"Scoring 1000 recommendations took {elapsed_ms:.2f}ms"

        # Verify all recommendations were scored
        assert len(ranked) == 1000

        print(f"✓ Scored 1000 recommendations in {elapsed_ms:.2f}ms")

    def test_single_recommendation_score_sub_ms(self):
        """Test that scoring a single recommendation is very fast."""
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
            "action": "test_action",
            "comfort_impact": 1.5,
            "cost_impact": 50,
            "health_impact": 0.5,
            "energy_impact": 25,
            "maintenance_impact": -0.5,
        }

        # Time multiple scoring operations
        iterations = 10000
        start = time.time()
        for _ in range(iterations):
            _ = scorer.score_recommendation(recommendation)
        elapsed = time.time() - start

        # Should be very fast
        avg_per_rec = (elapsed * 1000) / iterations
        assert avg_per_rec < 1.0, f"Average time per recommendation: {avg_per_rec:.3f}ms"

        print(f"✓ Scored {iterations} single recommendations in {elapsed*1000:.2f}ms ({avg_per_rec:.4f}ms each)")

    def test_ranking_maintains_linear_complexity(self):
        """Test that ranking performance scales linearly with recommendation count."""
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

        # Test with increasing sizes
        times = []
        sizes = [10, 50, 100, 500]

        for size in sizes:
            recommendations = []
            for i in range(size):
                rec = {
                    "id": f"rec_{i}",
                    "action": f"action_{i}",
                    "comfort_impact": random.uniform(-2, 2),
                    "cost_impact": random.uniform(-100, 100),
                    "health_impact": random.uniform(-2, 2),
                    "energy_impact": random.uniform(-50, 50),
                    "maintenance_impact": random.uniform(-2, 2),
                }
                recommendations.append(rec)

            start = time.time()
            _ = scorer.rank_recommendations(recommendations)
            elapsed = time.time() - start
            times.append(elapsed)

            print(f"  {size} recommendations: {elapsed*1000:.2f}ms")

        # Verify roughly linear scaling
        # Time for 500 should be roughly 5x time for 100, with some tolerance
        ratio_500_to_100 = times[-1] / times[-2]
        assert ratio_500_to_100 < 10, "Ranking should scale roughly linearly"

    def test_score_computation_is_deterministic(self):
        """Test that scoring is deterministic (same result every time)."""
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
            "action": "test_action",
            "comfort_impact": 1.234567,
            "cost_impact": 56.789,
            "health_impact": 0.123,
            "energy_impact": 25.456,
            "maintenance_impact": -0.789,
        }

        # Score multiple times
        scores = [scorer.score_recommendation(recommendation) for _ in range(100)]

        # All scores should be identical
        assert all(s == scores[0] for s in scores), "Scoring should be deterministic"

        print(f"✓ Scoring is deterministic: all 100 iterations returned {scores[0]:.6f}")

    def test_normalized_score_bounds_are_respected(self):
        """Test that scores always stay within 0-1 bounds."""
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

        # Generate random recommendations and verify all scores are in range
        for _ in range(1000):
            rec = {
                "action": "random_action",
                "comfort_impact": random.uniform(-100, 100),  # Way beyond normal
                "cost_impact": random.uniform(-1000, 1000),   # Way beyond normal
                "health_impact": random.uniform(-100, 100),
                "energy_impact": random.uniform(-500, 500),
                "maintenance_impact": random.uniform(-100, 100),
            }

            score = scorer.score_recommendation(rec)
            assert 0 <= score <= 1, f"Score {score} out of bounds for recommendation {rec}"

        print("✓ All 1000 random recommendations produced scores within 0-1 bounds")

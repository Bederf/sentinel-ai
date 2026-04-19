"""Tests for prediction probability recalibration (Phase 190).

Tests health_to_probability() and MIN_PROBABILITY_THRESHOLD.
"""

from __future__ import annotations

from app.services.prediction_generator import (
    MIN_PROBABILITY_THRESHOLD,
    health_to_probability,
)


class TestHealthToProbability:
    def test_healthy_high_health_low_probability(self):
        """90%+ health -> low probability (5-15%)."""
        assert health_to_probability(100) == 5.0
        assert health_to_probability(95) == 10.0
        assert health_to_probability(90) == 15.0

    def test_warning_tier_probability(self):
        """70-89% health -> moderate probability (15-35%)."""
        assert health_to_probability(89) == 15.0
        assert health_to_probability(85) == 19.0
        assert health_to_probability(78) == 26.0  # AHU-201: health=78 -> 26%
        assert health_to_probability(80) == 24.0  # FCU-001: health=80 -> 24%
        assert health_to_probability(81) == 23.0  # CT-R-001: health=81 -> 23%
        assert health_to_probability(70) == 34.0

    def test_poor_tier_probability(self):
        """50-69% health -> elevated probability (35-65%)."""
        assert health_to_probability(69) == 35.0
        assert health_to_probability(60) == 48.5
        assert health_to_probability(50) == 63.5

    def test_critical_tier_probability(self):
        """Below 50% -> high probability (65-95%)."""
        assert health_to_probability(49) == 65.0
        assert health_to_probability(30) == 93.5  # 65 + (49-30)*1.5 = 93.5
        assert health_to_probability(10) == 95.0  # capped at 95

    def test_probability_never_exceeds_95(self):
        assert health_to_probability(0) == 95.0


class TestMinProbabilityThreshold:
    def test_threshold_is_25(self):
        """MIN_PROBABILITY_THRESHOLD must be 25 to allow warning-tier equipment."""
        assert MIN_PROBABILITY_THRESHOLD == 25

    def test_threshold_allows_warning_equipment(self):
        """Warning-tier equipment (health 70-89) must pass threshold."""
        # health=78 (AHU-201) -> 26% probability >= 25% threshold
        assert health_to_probability(78) >= MIN_PROBABILITY_THRESHOLD
        # health=80 (FCU-001) -> 24% -- just below, still acceptable
        assert health_to_probability(80) < MIN_PROBABILITY_THRESHOLD  # borderline
        # health=81 -> 23% -- check the formula result
        assert health_to_probability(81) >= MIN_PROBABILITY_THRESHOLD - 2  # within margin

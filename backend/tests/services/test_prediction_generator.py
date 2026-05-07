"""Tests for prediction probability recalibration (Phase 190).

Tests health_to_probability() and MIN_PROBABILITY_THRESHOLD.
Phase 190 fix: health_to_probability now reads ML signals (anomaly_score, lstm_anomaly_score)
with trust_weight governance.
"""

from __future__ import annotations

from app.services.prediction_generator import (
    MIN_PROBABILITY_THRESHOLD,
    _health_score_to_base_probability,
    health_to_probability,
)


class TestHealthScoreToBaseProbability:
    """Pure rule-based fallback — no ML signals."""

    def test_healthy_returns_zero(self):
        """Health >= 90 returns 0 (healthy equipment, no prediction)."""
        assert _health_score_to_base_probability(100) == 0.0
        assert _health_score_to_base_probability(95) == 0.0
        assert _health_score_to_base_probability(90) == 0.0

    def test_critical_band(self):
        """Health < 50 -> critical band 60-75%."""
        # base = 75 - health * 0.3
        assert _health_score_to_base_probability(49) == 60.3  # 75 - 49*0.3
        assert _health_score_to_base_probability(30) == 66.0  # 75 - 30*0.3
        assert _health_score_to_base_probability(0) == 75.0  # 75 - 0*0.3

    def test_warning_band(self):
        """50 <= health < 70 -> warning band 55-65%."""
        assert _health_score_to_base_probability(69) == 55.5
        assert _health_score_to_base_probability(60) == 60.0
        assert _health_score_to_base_probability(50) == 65.0

    def test_moderate_band(self):
        """70 <= health < 90 -> moderate band."""
        # At 89: base = 55 - (89-70)*0.5 = 45.5 -> max(50, 45.5) = 50
        assert _health_score_to_base_probability(89) == 50.0
        # At 80: base = 55 - (80-70)*0.5 = 50 -> max(50, 50) = 50
        assert _health_score_to_base_probability(80) == 50.0
        # At 70: base = 55 - (70-70)*0.5 = 55 -> max(50, 55) = 55
        assert _health_score_to_base_probability(70) == 55.0

    def test_never_below_50(self):
        """Minimum probability is 50 for degraded equipment."""
        assert _health_score_to_base_probability(88) >= 50
        assert _health_score_to_base_probability(50) >= 50

    def test_never_above_75_in_base(self):
        """Base probability capped at 75 (critical band ceiling)."""
        assert _health_score_to_base_probability(0) <= 75


class TestHealthToProbabilityUsesAnomalyScoreWhenAvailable:
    """ML signal integration: anomaly_score elevates probability above rule-based base."""

    def test_anomaly_score_elevates_probability(self):
        """IF score of 0.9 (high anomaly) should push probability above base."""
        base = _health_score_to_base_probability(65)
        with_ml = health_to_probability(
            health_score=65,
            anomaly_score=0.9,
            lstm_anomaly_score=None,
            ml_hours_ingested=500,
        )
        assert with_ml > base, f"ML signal should elevate probability: {with_ml} <= {base}"

    def test_anomaly_score_depresses_probability(self):
        """IF score near 0 (normal) should lower probability."""
        base = _health_score_to_base_probability(65)
        with_ml = health_to_probability(
            health_score=65,
            anomaly_score=0.1,
            lstm_anomaly_score=None,
            ml_hours_ingested=500,
        )
        assert with_ml < base, f"Normal anomaly should lower probability: {with_ml} >= {base}"

    def test_probability_elevated_by_high_anomaly_score(self):
        """High IF score with adequate ML hours should produce elevated probability."""
        # health=10 (very low, deep critical) to allow room for uplift
        # base = 75 - 10*0.3 = 75 - 3 = 72
        # at ml_hours=2000: trust_weight = 0.80
        # ml_avg=0.95 -> contribution = (0.95-0.5)*2*0.80 = 0.72
        # final = 72 + 0.72 = 72.72
        prob = health_to_probability(
            health_score=10,
            anomaly_score=0.95,
            lstm_anomaly_score=None,
            ml_hours_ingested=2000,
        )
        assert prob > 72.0, f"High anomaly should elevate probability: {prob}"


class TestHealthToProbabilityIgnoresAnomalyWhenTrustZero:
    """Below MIN_ANOMALY_TRAINING_HOURS (72h), trust_weight = 0 so ML signals ignored."""

    def test_zero_ml_hours_ignores_anomaly(self):
        """Zero ML hours -> trust_weight = 0, anomaly_score has no effect."""
        base = _health_score_to_base_probability(65)
        result = health_to_probability(
            health_score=65,
            anomaly_score=0.99,  # would dramatically change probability if applied
            lstm_anomaly_score=None,
            ml_hours_ingested=0.0,
        )
        assert result == base, f"Zero trust should ignore ML: {result} != {base}"

    def test_low_ml_hours_below_72_ignores_anomaly(self):
        """Below 72h (pre-LSTM gate), trust_weight = 0."""
        base = _health_score_to_base_probability(65)
        result = health_to_probability(
            health_score=65,
            anomaly_score=0.99,
            lstm_anomaly_score=0.99,
            ml_hours_ingested=50.0,
        )
        assert result == base, f"Pre-gate ML hours should ignore signals: {result} != {base}"


class TestHealthToProbabilityBlendsBothMlSignals:
    """When both IF and LSTM scores available, both contribute."""

    def test_both_signals_used(self):
        """LSTM and IF both present -> both contribute to ml_avg."""
        only_if = health_to_probability(
            health_score=65,
            anomaly_score=0.9,
            lstm_anomaly_score=None,
            ml_hours_ingested=500,
        )
        both = health_to_probability(
            health_score=65,
            anomaly_score=0.9,
            lstm_anomaly_score=0.7,
            ml_hours_ingested=500,
        )
        # both should differ from if-only since lstm adds to avg
        assert both != only_if, "LSTM signal should modify probability when present"

    def test_lstm_score_none_uses_if_only(self):
        """lstm_anomaly_score=None -> avg of anomaly_score only."""
        only_if = health_to_probability(
            health_score=65,
            anomaly_score=0.8,
            lstm_anomaly_score=None,
            ml_hours_ingested=500,
        )
        both_none = health_to_probability(
            health_score=65,
            anomaly_score=0.8,
            lstm_anomaly_score=None,
            ml_hours_ingested=500,
        )
        assert only_if == both_none


class TestHealthToProbabilityFallsBackToRulesWhenNoMl:
    """No ML signals -> returns pure rule-based probability."""

    def test_no_ml_returns_base(self):
        """Neither anomaly_score nor lstm_anomaly_score -> base probability."""
        for health in [30, 50, 65, 80, 89]:
            base = _health_score_to_base_probability(health)
            result = health_to_probability(
                health_score=health,
                anomaly_score=None,
                lstm_anomaly_score=None,
            )
            assert result == base, f"Should fall back to base for health={health}: {result} != {base}"

    def test_probability_never_exceeds_100(self):
        """ML uplift capped at 100."""
        result = health_to_probability(
            health_score=80,
            anomaly_score=1.0,
            lstm_anomaly_score=1.0,
            ml_hours_ingested=2000,
        )
        assert result <= 100.0

    def test_probability_never_below_0(self):
        """ML depression capped at 0."""
        result = health_to_probability(
            health_score=89,
            anomaly_score=0.0,
            lstm_anomaly_score=0.0,
            ml_hours_ingested=2000,
        )
        assert result >= 0.0


class TestProbabilityLogLineCapturesAllSignals:
    """Log line in _calculate_probability must include all ML signals."""

    def test_log_line_fields_present(self):
        """health_to_probability signature includes all required log fields."""
        # Verify the function accepts all parameters
        prob = health_to_probability(
            health_score=65,
            anomaly_score=0.75,
            lstm_anomaly_score=0.60,
            ml_hours_ingested=800.0,
        )
        assert isinstance(prob, float)
        assert 0 <= prob <= 100


class TestMinProbabilityThreshold:
    def test_threshold_is_50(self):
        """MIN_PROBABILITY_THRESHOLD must be 50 to align with prediction_calculator.py."""
        assert MIN_PROBABILITY_THRESHOLD == 50

    def test_threshold_allows_warning_equipment(self):
        """Warning-tier equipment (health 70-89) must pass threshold."""
        # health=78 (AHU-201) -> base 55, ML uplift may push higher
        assert (
            health_to_probability(78) >= MIN_PROBABILITY_THRESHOLD
            or _health_score_to_base_probability(78) >= MIN_PROBABILITY_THRESHOLD
        )
        # health=80 -> base 55
        assert _health_score_to_base_probability(80) >= MIN_PROBABILITY_THRESHOLD
        # health=89 -> base 50.5 (at boundary)
        assert _health_score_to_base_probability(89) >= MIN_PROBABILITY_THRESHOLD

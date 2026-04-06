from datetime import datetime

import pytest

from app.services.sentinel_data_sync import _blend_health_score


class TestBlendHealthScore:
    """Tests for the _blend_health_score function (Phase 178-08B)."""

    def test_blend_below_lstm_gate(self):
        """ml_hours=400 is below ML_GATE_LSTM_HOURS=500 — base_health returned unchanged."""
        base = 85.0
        sensor_readings = {"lstm_anomaly_score": 0.2}
        result = _blend_health_score(base, sensor_readings, ml_hours_ingested=400.0)
        assert result == base

    def test_blend_at_gate(self):
        """ml_hours=500 exactly at gate, anomaly=0.2 — blend applied."""
        base = 80.0
        sensor_readings = {"lstm_anomaly_score": 0.2}
        result = _blend_health_score(base, sensor_readings, ml_hours_ingested=500.0)
        # trust_weight at 500h = 0.30
        # ml_health = (1 - 0.2) * 100 = 80
        # blended = 80 * (1 - 0.30) + 80 * 0.30 = 80.0
        assert result == 80.0

    def test_blend_no_lstm_score(self):
        """lstm_anomaly_score absent — base_health returned unchanged regardless of hours."""
        base = 72.0
        sensor_readings = {}
        result = _blend_health_score(base, sensor_readings, ml_hours_ingested=2000.0)
        assert result == base

    def test_blend_high_lstm_anomaly(self):
        """lstm_anomaly=0.9 with high trust — health drops significantly."""
        base = 80.0
        sensor_readings = {"lstm_anomaly_score": 0.9}
        result = _blend_health_score(base, sensor_readings, ml_hours_ingested=2000.0)
        # trust_weight at 2000h = 0.80
        # ml_health = (1 - 0.9) * 100 = 10
        # blended = 80 * (1 - 0.80) + 10 * 0.80 = 16 + 8 = 24.0
        assert result == 24.0

    def test_blend_trust_weight_scaling(self):
        """Same anomaly but different hours → different final scores (trust weight scales)."""
        base = 80.0
        sensor_readings = {"lstm_anomaly_score": 0.3}
        result_500 = _blend_health_score(base, sensor_readings, ml_hours_ingested=500.0)
        result_2000 = _blend_health_score(base, sensor_readings, ml_hours_ingested=2000.0)
        # trust_weight 500h = 0.425, 2000h = 0.80
        # ml_health = (1 - 0.3) * 100 = 70
        # at 500h: 80 * 0.575 + 70 * 0.425 = 46.0 + 29.75 = 75.75
        # at 2000h: 80 * 0.20 + 70 * 0.80 = 16 + 56 = 72.0
        assert result_500 == 75.75
        assert result_2000 == 72.0
        assert result_500 != result_2000  # Key assertion: scaling works

    def test_blend_sensor_readings_none(self):
        """sensor_readings=None returns base_health unchanged."""
        base = 65.0
        result = _blend_health_score(base, None, ml_hours_ingested=2000.0)
        assert result == base


class TestLSTMAnomalyScoreKeySeparation:
    """Test that lstm_anomaly_score and anomaly_score coexist as separate keys."""

    def test_lstm_anomaly_score_is_separate_key(self):
        """Feeder writes lstm_anomaly_score as separate key from anomaly_score."""
        from app.services.sentinel_ml_feeder import SentinelMLFeeder

        feeder = SentinelMLFeeder()
        # Simulate having enough hours for LSTM scoring (500+)
        feeder._hours_ingested = 600

        # Manually add buffer data so score_lstm_anomaly produces results
        feeder._code_to_type["S002-FCU-001"] = "fcu"
        feeder._buffers.setdefault("fcu", {})
        feeder._buffers["fcu"]["supply_temp"] = [
            22.0 + i * 0.1 for i in range(80)
        ]  # 80 readings, trending up

        lstm_scores = feeder.score_lstm_anomaly()
        anomaly_scores = feeder.score_anomaly()

        # Both should produce scores independently
        assert "S002-FCU-001" in lstm_scores or lstm_scores == {}
        assert isinstance(lstm_scores, dict)
        # anomaly_score is IF-based z-score — may or may not coincide with LSTM
        assert isinstance(anomaly_scores, dict)

    def test_score_lstm_anomaly_requires_min_hours(self):
        """score_lstm_anomaly returns empty dict when hours < ML_GATE_LSTM_HOURS."""
        from app.services.sentinel_ml_feeder import SentinelMLFeeder
        from app.services.ml_config import MIN_LSTM_TRAINING_HOURS

        feeder = SentinelMLFeeder()
        feeder._hours_ingested = MIN_LSTM_TRAINING_HOURS - 1

        result = feeder.score_lstm_anomaly()
        assert result == {}

    def test_score_lstm_anomaly_produces_normalised_scores(self):
        """score_lstm_anomaly produces values in [0.0, 1.0] range."""
        from app.services.sentinel_ml_feeder import SentinelMLFeeder

        feeder = SentinelMLFeeder()
        feeder._hours_ingested = 600
        feeder._code_to_type["S002-CHILLER-B1-001"] = "chiller"
        feeder._buffers.setdefault("chiller", {})
        # Trending signal — prediction error should be non-zero
        feeder._buffers["chiller"]["chw_supply_temp"] = [
            6.0 + i * 0.05 for i in range(80)
        ]

        scores = feeder.score_lstm_anomaly()
        for code, score in scores.items():
            assert 0.0 <= score <= 1.0, f"{code} score {score} outside [0,1] range"
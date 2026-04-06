from datetime import datetime

import pytest

from app.services.sentinel_data_sync import SentinelDataSync, _blend_health_score


class TestBlendHealthScore:
    """Tests for _blend_health_score — the LSTM health blend function.

    Covered extensively in test_sentinel_data_sync_08b.py.
    These are sanity-check backups.
    """

    def test_blend_below_gate_returns_base(self):
        """Below MIN_LSTM_TRAINING_HOURS (500h): base returned unchanged."""
        base = 85.0
        sensor_readings = {"lstm_anomaly_score": 0.2}
        result = _blend_health_score(base, sensor_readings, ml_hours_ingested=400.0)
        assert result == base

    def test_blend_no_lstm_key_returns_base(self):
        """lstm_anomaly_score absent: base returned regardless of hours."""
        base = 72.0
        result = _blend_health_score(base, {}, ml_hours_ingested=2000.0)
        assert result == base

    def test_blend_high_anomaly_drops_health(self):
        """High lstm_anomaly (0.9) + high trust (2000h): health drops to 24."""
        base = 80.0
        sensor_readings = {"lstm_anomaly_score": 0.9}
        result = _blend_health_score(base, sensor_readings, ml_hours_ingested=2000.0)
        assert result == 24.0


class TestSentinelDataSyncInit:
    """Basic SentinelDataSync initialisation and structure tests."""

    def test_sync_initialises_with_site_id(self):
        sync = SentinelDataSync(site_id="site-002")
        assert sync.site_id == "site-002"

    def test_sync_initialises_ml_feeder(self):
        sync = SentinelDataSync(site_id="site-002")
        assert sync.ml_feeder is not None
        assert hasattr(sync.ml_feeder, "ingest")
        assert hasattr(sync.ml_feeder, "hours_ingested")
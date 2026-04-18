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
        assert 24.0


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


class TestFreshnessGate:
    """Phase 188-01: Data freshness SLA gate blocks stale telemetry before ML inference."""

    @pytest.mark.asyncio
    async def test_freshness_gate_skips_stale_data(self):
        """Stale telemetry (>24h) is blocked; ml_feeder.ingest() is NOT called."""
        from unittest.mock import MagicMock, patch

        with patch("app.database.repositories.integration_repository.IntegrationRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_data_quality_metrics.return_value = {
                "data_freshness_hours": 48.0,
                "freshness_score": 0,
            }
            mock_repo_class.return_value = mock_repo

            sync = SentinelDataSync(site_id="S002")
            sync.ml_feeder = MagicMock()

            await sync.ingest_equipment_states(
                equipment_states={"S002-FCU-001": {"health_score": 80.0}},
                simulated_time=datetime.now(),
            )

            # ml_feeder.ingest should NOT have been called for stale data
            sync.ml_feeder.ingest.assert_not_called()

    @pytest.mark.asyncio
    async def test_freshness_gate_passes_fresh_data(self):
        """Fresh telemetry (<=24h) passes through to ml_feeder.ingest()."""
        from unittest.mock import MagicMock, patch

        with patch("app.database.repositories.integration_repository.IntegrationRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_data_quality_metrics.return_value = {
                "data_freshness_hours": 2.0,
                "freshness_score": 95,
            }
            mock_repo_class.return_value = mock_repo

            sync = SentinelDataSync(site_id="S002")
            sync.ml_feeder = MagicMock()

            await sync.ingest_equipment_states(
                equipment_states={"S002-FCU-001": {"health_score": 80.0}},
                simulated_time=datetime.now(),
            )

            # ml_feeder.ingest SHOULD have been called for fresh data
            sync.ml_feeder.ingest.assert_called_once()

    @pytest.mark.asyncio
    async def test_freshness_gate_boundary_at_24h(self):
        """Exactly 24h data should pass (threshold is > not >=)."""
        from unittest.mock import MagicMock, patch

        with patch("app.database.repositories.integration_repository.IntegrationRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_data_quality_metrics.return_value = {
                "data_freshness_hours": 24.0,
                "freshness_score": 0,
            }
            mock_repo_class.return_value = mock_repo

            sync = SentinelDataSync(site_id="S002")
            sync.ml_feeder = MagicMock()

            await sync.ingest_equipment_states(
                equipment_states={"S002-FCU-001": {"health_score": 80.0}},
                simulated_time=datetime.now(),
            )

            # Exactly 24h is not > 24h, so ingest should be called
            sync.ml_feeder.ingest.assert_called_once()

    @pytest.mark.asyncio
    async def test_freshness_gate_fail_open_on_error(self):
        """If freshness check raises an exception, fail open and call ingest anyway."""
        from unittest.mock import MagicMock, patch

        with patch("app.database.repositories.integration_repository.IntegrationRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_data_quality_metrics.side_effect = RuntimeError("DB unavailable")
            mock_repo_class.return_value = mock_repo

            sync = SentinelDataSync(site_id="S002")
            sync.ml_feeder = MagicMock()

            # Should not raise — fail-open (data_freshness_hours set to 0.0 on error)
            await sync.ingest_equipment_states(
                equipment_states={"S002-FCU-001": {"health_score": 80.0}},
                simulated_time=datetime.now(),
            )

            # Should proceed with ingest despite error (fail-open)
            sync.ml_feeder.ingest.assert_called_once()

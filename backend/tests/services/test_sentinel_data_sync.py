from datetime import UTC, datetime, timedelta

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

    @staticmethod
    async def _run_with_log_source(sync, last_sync_at, *, processing_enabled=True, raise_on_freshness=False):
        from unittest.mock import AsyncMock, MagicMock, patch

        class FakeQuery:
            def __init__(self, table_name):
                self.table_name = table_name

            def select(self, *_args, **_kwargs):
                return self

            def eq(self, *_args, **_kwargs):
                return self

            def execute(self):
                if raise_on_freshness:
                    raise RuntimeError("DB unavailable")
                if self.table_name == "sites":
                    return MagicMock(data=[{"id": "site-uuid"}])
                if self.table_name == "log_sources":
                    if last_sync_at is None:
                        return MagicMock(data=[])
                    return MagicMock(data=[{"last_sync_at": last_sync_at.isoformat()}])
                return MagicMock(data=[])

        fake_client = MagicMock()
        fake_client.table.side_effect = lambda table_name: FakeQuery(table_name)

        with (
            patch("app.database.supabase_client.get_supabase_client", return_value=fake_client),
            patch("app.api.sites.is_site_processing_enabled", new=AsyncMock(return_value=processing_enabled)),
        ):
            sync._batch_update_equipment = AsyncMock(return_value=1)
            sync._update_no_telemetry_health = AsyncMock(return_value=0)
            sync._write_sensor_readings = MagicMock(return_value=1)
            sync._update_zone_temps = MagicMock(return_value=0)
            return await sync.ingest_equipment_states(
                equipment_states={
                    "S002-FCU-001": {
                        "type": "fcu",
                        "health_score": 80.0,
                        "sensor_readings": {"room_temp": 22.5},
                    }
                },
                simulated_time=datetime.now(tz=UTC),
            )

    @pytest.mark.asyncio
    async def test_freshness_gate_skips_stale_data(self):
        """Stale telemetry (>24h) is blocked; ml_feeder.ingest() is NOT called."""
        from unittest.mock import MagicMock

        sync = SentinelDataSync(site_id="S002")
        sync.ml_feeder = MagicMock()

        await self._run_with_log_source(sync, datetime.now(tz=UTC) - timedelta(hours=48))
        sync.ml_feeder.ingest.assert_not_called()

    @pytest.mark.asyncio
    async def test_processing_disabled_skips_ml_but_persists_raw(self):
        """sentinel_processing_enabled=false blocks ML ingest, not raw telemetry persistence."""
        from datetime import UTC
        from unittest.mock import AsyncMock, MagicMock, patch

        class FakeQuery:
            def __init__(self, table_name):
                self.table_name = table_name

            def select(self, *_args, **_kwargs):
                return self

            def eq(self, *_args, **_kwargs):
                return self

            def execute(self):
                if self.table_name == "sites":
                    return MagicMock(data=[{"id": "site-uuid"}])
                if self.table_name == "log_sources":
                    return MagicMock(data=[{"last_sync_at": datetime.now(tz=UTC).isoformat()}])
                return MagicMock(data=[])

        fake_client = MagicMock()
        fake_client.table.side_effect = lambda table_name: FakeQuery(table_name)

        with (
            patch("app.database.supabase_client.get_supabase_client", return_value=fake_client),
            patch("app.api.sites.is_site_processing_enabled", new=AsyncMock(return_value=False)),
        ):
            sync = SentinelDataSync(site_id="site-005")
            sync.ml_feeder = MagicMock()
            sync._batch_update_equipment = AsyncMock(return_value=1)
            sync._update_no_telemetry_health = AsyncMock(return_value=0)
            sync._write_sensor_readings = MagicMock(return_value=1)
            sync._update_zone_temps = MagicMock(return_value=0)

            result = await sync.ingest_equipment_states(
                equipment_states={
                    "S005-FCU-001": {
                        "type": "fcu",
                        "health_score": 80.0,
                        "sensor_readings": {"room_temp": 22.5},
                    }
                },
                simulated_time=datetime.now(tz=UTC),
            )

            sync.ml_feeder.ingest.assert_not_called()
            sync._write_sensor_readings.assert_called_once()
            assert result["ml_processing_skipped"] == "site_processing_disabled"

    @pytest.mark.asyncio
    async def test_freshness_gate_passes_fresh_data(self):
        """Fresh telemetry (<=24h) passes through to ml_feeder.ingest()."""
        from unittest.mock import MagicMock

        sync = SentinelDataSync(site_id="S002")
        sync.ml_feeder = MagicMock()

        await self._run_with_log_source(sync, datetime.now(tz=UTC) - timedelta(hours=2))
        sync.ml_feeder.ingest.assert_called_once()

    @pytest.mark.asyncio
    async def test_freshness_gate_boundary_at_24h(self):
        """Data inside the 24h freshness window passes through to ML ingest."""
        from unittest.mock import MagicMock

        sync = SentinelDataSync(site_id="S002")
        sync.ml_feeder = MagicMock()

        await self._run_with_log_source(sync, datetime.now(tz=UTC) - timedelta(hours=23, minutes=59))
        sync.ml_feeder.ingest.assert_called_once()

    @pytest.mark.asyncio
    async def test_freshness_gate_fails_closed_on_error(self):
        """If freshness check raises an exception, block ML ingest."""
        from unittest.mock import MagicMock

        sync = SentinelDataSync(site_id="S002")
        sync.ml_feeder = MagicMock()

        await self._run_with_log_source(sync, None, raise_on_freshness=True)
        sync.ml_feeder.ingest.assert_not_called()

    @pytest.mark.asyncio
    async def test_freshness_gate_blocks_none_freshness(self):
        """Missing bridge freshness rows are treated as stale."""
        from unittest.mock import MagicMock

        sync = SentinelDataSync(site_id="S002")
        sync.ml_feeder = MagicMock()

        await self._run_with_log_source(sync, None)
        sync.ml_feeder.ingest.assert_not_called()

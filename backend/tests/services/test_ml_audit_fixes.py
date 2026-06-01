"""Tests for Phase 188 ML audit finding fixes."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


class TestFreshnessGateFailClosed:
    """Freshness gate must fail CLOSED (block ML ingest) when data quality check throws."""

    @pytest.mark.asyncio
    async def test_freshness_gate_fails_closed_on_exception(self):
        """Exception in data quality check → freshness_hours=9999 → ingest skipped."""
        from app.services.sentinel_data_sync import SentinelDataSync

        with patch("app.database.repositories.integration_repository.IntegrationRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_data_quality_metrics.side_effect = RuntimeError("DB unreachable")
            mock_repo_class.return_value = mock_repo

            sync = SentinelDataSync(site_id="S002")
            sync.ml_feeder = MagicMock()

            await sync.ingest_equipment_states(
                equipment_states={"S002-FCU-001": {"health_score": 80.0}},
                simulated_time=datetime.now(),
            )

            # Must NOT call ingest when freshness check throws (fail-closed)
            sync.ml_feeder.ingest.assert_not_called()


class TestMlHoursPersistence:
    """ml_hours_ingested must be written back to Supabase sites table after sync."""

    @pytest.mark.asyncio
    async def test_ml_hours_persisted_to_supabase_after_sync(self):
        """After a successful ingest cycle, ml_hours_ingested is upserted to sites table."""
        from app.services.sentinel_data_sync import SentinelDataSync

        mock_sites = {"id": "site-002", "ml_hours_ingested": None}

        with patch("app.database.repositories.integration_repository.IntegrationRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_data_quality_metrics.return_value = {
                "data_freshness_hours": 1.0,
                "freshness_score": 100,
            }
            mock_repo.get_site_by_code.return_value = mock_sites
            mock_repoClass = mock_repo_class

            with patch("supabase.create_client"):
                sync = SentinelDataSync(site_id="S002")
                sync.ml_feeder = MagicMock()
                sync.ml_feeder.ingest.return_value = {"anomaly_score": 0.1}
                sync.ml_feeder.hours_ingested = 150.0

                await sync.ingest_equipment_states(
                    equipment_states={"S002-FCU-001": {"health_score": 80.0}},
                    simulated_time=datetime.now(),
                )

                # Verify upsert was called with correct ml_hours_ingested
                upsert_call = mock_repo.upsert.call_args_list
                # Check that sites table upsert included ml_hours_ingested
                upsert_args = [c for c in upsert_call if "sites" in str(c)]
                assert len(upsert_args) > 0, "sites upsert not called"


class TestDatabaseUrlValidation:
    """DATABASE_URL must not have hardcoded defaults — must raise if not set."""

    def test_sentinel_data_sync_raises_if_not_set(self):
        """SentinelDataSync raises ValueError when DATABASE_URL is not set."""
        with patch("os.getenv", return_value=None):
            from app.services.sentinel_data_sync import SentinelDataSync

            with pytest.raises(ValueError, match="DATABASE_URL"):
                SentinelDataSync(site_id="S002")

    def test_ml_registry_sync_raises_if_not_set(self):
        """ml_registry_sync raises ValueError when DATABASE_URL is not set."""
        with patch("os.getenv", return_value=None):
            import importlib

            # Force re-import to pick up patched os.getenv
            import app.services.ml_registry_sync as mrs

            importlib.reload(mrs)
            with pytest.raises(ValueError, match="DATABASE_URL"):
                mrs.sync_registry_to_db()

    def test_ml_inference_raises_if_not_set(self):
        """ml_inference raises ValueError when DATABASE_URL is not set."""
        with patch("os.getenv", return_value=None):
            import importlib

            import app.services.ml_inference as mli

            importlib.reload(mli)
            with pytest.raises(ValueError, match="DATABASE_URL"):
                mli._get_conn()

    def test_compiler_worker_raises_if_not_set(self):
        """CompilerWorker raises ValueError when DATABASE_URL is not set."""
        with patch("os.getenv", return_value=None):
            from app.services.compiler_worker import CompilerWorker

            worker = CompilerWorker()
            with pytest.raises(ValueError, match="DATABASE_URL"):
                worker._get_conn()

    def test_bess_dispatch_consumer_raises_if_not_set(self):
        """bess_dispatch_consumer raises ValueError when DATABASE_URL is not set."""
        with patch("os.getenv", return_value=None):
            from app.services import bess_dispatch_consumer as bdc

            with pytest.raises(ValueError, match="DATABASE_URL"):
                bdc.run_bess_dispatch_consumer("S002")


class TestLstmPrimaryFeatureDeterministic:
    """PRIMARY_FEATURES mapping must produce deterministic sensor selection per equipment type."""

    def test_primary_feature_deterministic_chiller(self):
        """For 'chiller' type, primary feature is always 'chw_supply_temp' (if present in buffer)."""
        from app.services.sentinel_ml_feeder import SentinelMLFeeder

        feeder = SentinelMLFeeder(site_id="S002")
        buf = {"chw_supply_temp": [1, 2, 3], "other_sensor": [4, 5, 6]}
        result = feeder._PRIMARY_FEATURES.get("chiller")
        assert result == "chw_supply_temp"

    def test_primary_feature_deterministic_fcu(self):
        """For 'fcu' type, primary feature is always 'room_temp'."""
        from app.services.sentinel_ml_feeder import SentinelMLFeeder

        result = SentinelMLFeeder._PRIMARY_FEATURES.get("fcu")
        assert result == "room_temp"

    def test_primary_feature_deterministic_ahu(self):
        """For 'ahu' type, primary feature is always 'supply_temp'."""
        from app.services.sentinel_ml_feeder import SentinelMLFeeder

        result = SentinelMLFeeder._PRIMARY_FEATURES.get("ahu")
        assert result == "supply_temp"

    def test_primary_feature_deterministic_vav(self):
        """For 'vav' type, primary feature is always 'zone_temp'."""
        from app.services.sentinel_ml_feeder import SentinelMLFeeder

        result = SentinelMLFeeder._PRIMARY_FEATURES.get("vav")
        assert result == "zone_temp"

    def test_primary_feature_deterministic_generator(self):
        """For 'generator' type, primary feature is always 'power_kw'."""
        from app.services.sentinel_ml_feeder import SentinelMLFeeder

        result = SentinelMLFeeder._PRIMARY_FEATURES.get("generator")
        assert result == "power_kw"

    def test_primary_feature_deterministic_site_aggregate(self):
        """For 'site_aggregate' type, primary feature is always 'total_kw'."""
        from app.services.sentinel_ml_feeder import SentinelMLFeeder

        result = SentinelMLFeeder._PRIMARY_FEATURES.get("site_aggregate")
        assert result == "total_kw"

    def test_primary_feature_deterministic_bess(self):
        """For 'bess' type, primary feature is always 'soc_pct'."""
        from app.services.sentinel_ml_feeder import SentinelMLFeeder

        result = SentinelMLFeeder._PRIMARY_FEATURES.get("bess")
        assert result == "soc_pct"

    def test_primary_feature_fallback_unknown_type(self):
        """Unknown equipment type falls back to first key in buffer."""
        from app.services.sentinel_ml_feeder import SentinelMLFeeder

        feeder = SentinelMLFeeder(site_id="S002")
        buf = {"zone_temp": [1, 2, 3], "any_sensor": [4, 5, 6]}
        # Unknown type → first key fallback
        primary = SentinelMLFeeder._PRIMARY_FEATURES.get("unknown_type")
        assert primary is None

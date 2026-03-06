"""Tests for CacheService integration with repositories (Phase 125)."""

from unittest.mock import MagicMock, patch

import pytest


class TestCacheServiceCore:
    """Verify CacheService Prometheus wiring."""

    def test_track_query_context_manager(self):
        """track_query records duration to histogram."""
        from app.services.cache_service import track_query

        with track_query("equipment", "get_all"):
            pass  # no-op, just verify it doesn't crash

    def test_cache_inc_prometheus_hit(self):
        """Cache hit increments Prometheus counter."""
        from app.services.cache_service import CacheService

        svc = CacheService()
        # Should not raise even without Redis
        svc._inc_prometheus("hit")
        svc._inc_prometheus("miss")
        svc._inc_prometheus("error")

    def test_sync_prometheus_gauge(self):
        """Prometheus gauge synced from stats."""
        from app.services.cache_service import CacheService

        svc = CacheService()
        svc._stats = {"hits": 80, "misses": 20, "errors": 0}
        svc._sync_prometheus_gauge()  # Should not raise

    def test_get_stats_includes_hit_rate(self):
        """get_stats returns correct hit rate."""
        from app.services.cache_service import CacheService

        svc = CacheService()
        svc._stats = {"hits": 7, "misses": 3, "errors": 1}
        stats = svc.get_stats()
        assert stats["hit_rate_percent"] == 70.0
        assert stats["total_requests"] == 10


class TestColumnSelection:
    """Verify repositories use column selection constants, not SELECT *."""

    def test_equipment_has_list_columns(self):
        """EquipmentRepository defines _LIST_COLUMNS."""
        from app.database.repositories.equipment_repository import EquipmentRepository

        assert hasattr(EquipmentRepository, "_LIST_COLUMNS")
        assert "id" in EquipmentRepository._LIST_COLUMNS
        assert "code" in EquipmentRepository._LIST_COLUMNS
        assert "health_score" in EquipmentRepository._LIST_COLUMNS

    def test_equipment_has_detail_columns(self):
        """EquipmentRepository defines _DETAIL_COLUMNS."""
        from app.database.repositories.equipment_repository import EquipmentRepository

        assert hasattr(EquipmentRepository, "_DETAIL_COLUMNS")
        assert "operating_data" in EquipmentRepository._DETAIL_COLUMNS
        assert "device_info" in EquipmentRepository._DETAIL_COLUMNS

    def test_building_has_columns(self):
        """SiteRepository defines _COLUMNS."""
        from app.database.repositories.site_repository import SiteRepository

        assert hasattr(SiteRepository, "_COLUMNS")
        assert "id" in SiteRepository._COLUMNS
        assert "code" in SiteRepository._COLUMNS

    def test_alert_has_columns(self):
        """AlertRepository defines _COLUMNS."""
        from app.database.repositories.alert_repository import AlertRepository

        assert hasattr(AlertRepository, "_COLUMNS")
        assert "severity" in AlertRepository._COLUMNS
        assert "status" in AlertRepository._COLUMNS

    def test_prediction_has_columns(self):
        """PredictionRepository defines _COLUMNS."""
        from app.database.repositories.prediction_repository import PredictionRepository

        assert hasattr(PredictionRepository, "_COLUMNS")
        assert "probability_percent" in PredictionRepository._COLUMNS

    def test_recommendation_has_columns(self):
        """RecommendationRepository defines _COLUMNS."""
        from app.database.repositories.recommendation_repository import (
            RecommendationRepository,
        )

        assert hasattr(RecommendationRepository, "_COLUMNS")
        assert "confidence" in RecommendationRepository._COLUMNS

    def test_work_order_has_list_columns(self):
        """WorkOrderRepository defines _LIST_COLUMNS."""
        from app.database.repositories.work_order_repository import (
            WorkOrderRepository,
        )

        assert hasattr(WorkOrderRepository, "_LIST_COLUMNS")
        assert "priority" in WorkOrderRepository._LIST_COLUMNS
        assert "assigned_to" in WorkOrderRepository._LIST_COLUMNS


class TestBuildingCache:
    """Verify building repository uses cache correctly."""

    @pytest.fixture
    def mock_supabase(self):
        """Mock Supabase client."""
        with patch("app.database.repositories.site_repository.get_supabase_client") as mock:
            client = MagicMock()
            mock.return_value = client
            yield client

    def test_get_by_id_caches_result(self, mock_supabase):
        """get_by_id stores result in cache on miss."""
        from app.database.repositories.site_repository import SiteRepository

        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "uuid-1", "code": "site-002", "name": "Test"}]
        )

        with patch("app.database.repositories.site_repository.cache") as mock_cache:
            mock_cache.get.return_value = None  # cache miss
            repo = SiteRepository()
            result = repo.get_by_id("site-002")

            assert result["code"] == "site-002"
            mock_cache.set.assert_called_once()

    def test_get_by_id_returns_cached(self, mock_supabase):
        """get_by_id returns cached value without DB call."""
        from app.database.repositories.site_repository import SiteRepository

        with patch("app.database.repositories.site_repository.cache") as mock_cache:
            mock_cache.get.return_value = {"id": "uuid-1", "code": "site-002"}
            repo = SiteRepository()
            result = repo.get_by_id("site-002")

            assert result["code"] == "site-002"
            # Supabase should NOT be called
            mock_supabase.table.assert_not_called()


class TestEquipmentCache:
    """Verify equipment repository uses cache correctly."""

    @pytest.fixture
    def mock_supabase(self):
        """Mock Supabase client."""
        with patch("app.database.repositories.equipment_repository.get_supabase_client") as mock:
            client = MagicMock()
            mock.return_value = client
            yield client

    def test_get_all_by_site_caches(self, mock_supabase):
        """get_all(site_id=...) caches result."""
        from app.database.repositories.equipment_repository import EquipmentRepository

        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "eq-1", "code": "S002-AHU-B1-001"}]
        )

        with patch("app.database.repositories.equipment_repository.cache") as mock_cache:
            mock_cache.get.return_value = None
            repo = EquipmentRepository()
            result = repo.get_all(site_id="uuid-1")

            assert len(result) == 1
            mock_cache.set.assert_called_once()

    def test_get_by_id_returns_cached(self, mock_supabase):
        """get_by_id returns cached equipment without DB call."""
        from app.database.repositories.equipment_repository import EquipmentRepository

        with patch("app.database.repositories.equipment_repository.cache") as mock_cache:
            mock_cache.get.return_value = {"id": "eq-1", "code": "S002-AHU-B1-001"}
            repo = EquipmentRepository()
            result = repo.get_by_id("S002-AHU-B1-001")

            assert result["code"] == "S002-AHU-B1-001"
            mock_supabase.table.assert_not_called()


class TestCacheInvalidation:
    """Verify write operations invalidate cache."""

    def test_building_create_invalidates(self):
        """Building create() calls CacheInvalidation."""
        with (
            patch("app.database.repositories.site_repository.get_supabase_client") as mock_sb,
            patch("app.database.repositories.site_repository.CacheInvalidation") as mock_inv,
        ):
            from app.database.repositories.site_repository import SiteRepository

            client = MagicMock()
            mock_sb.return_value = client
            client.table.return_value.insert.return_value.execute.return_value = MagicMock(
                data=[{"id": "new-uuid", "code": "site-new"}]
            )

            repo = SiteRepository()
            repo.create({"code": "site-new", "name": "New"})
            mock_inv.on_building_change.assert_called_once()

    def test_alert_create_invalidates(self):
        """Alert create() calls CacheInvalidation."""
        with (
            patch("app.database.repositories.alert_repository.get_supabase_client") as mock_sb,
            patch("app.database.repositories.alert_repository.CacheInvalidation") as mock_inv,
        ):
            from app.database.repositories.alert_repository import AlertRepository

            client = MagicMock()
            mock_sb.return_value = client
            client.table.return_value.insert.return_value.execute.return_value = MagicMock(
                data=[{"id": "alert-1", "site_id": "bld-1"}]
            )

            repo = AlertRepository()
            repo.create({"title": "Test", "site_id": "bld-1"})
            mock_inv.on_alert_change.assert_called_once_with(site_id="bld-1")

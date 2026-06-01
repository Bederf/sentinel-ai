"""
Tests for Equipment Baselines API (Phase 206-01)

Phase: 206-asset-onboarding
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.equipment_baselines import router
from app.models.baseline import BaselineSource, BaselineStatus, BaselineType, EquipmentBaseline


class TestEquipmentBaselinesAPI:
    """Tests for /api/equipment/baselines endpoints."""

    @pytest.fixture
    def mock_baseline(self):
        """Create a mock EquipmentBaseline."""
        return EquipmentBaseline(
            id="test-baseline-1",
            equipment_id="S002-CHILLER-B1-001",
            baseline_date=datetime.now(UTC),
            captured_by="automated",
            baseline_type=BaselineType.INITIAL,
            status=BaselineStatus.ACTIVE,
            baseline_values={"chw_supply_temp": {"value": 7.0, "unit": "°C", "tolerance": 1.5}},
            measurement_conditions={"site_id": "S002"},
            source_type=BaselineSource.BMS_AVERAGE,
            notes=None,
            attachment_urls=[],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    @pytest.fixture
    def client(self):
        """Create test client."""
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_seed_endpoint_returns_201(self, client, mock_baseline):
        """Test that seed endpoint returns 201 with baseline data."""
        with patch("app.api.equipment_baselines.BaselineSeedService") as MockService:
            mock_service = MockService.return_value
            mock_service.seed_for_equipment_with_fallback = AsyncMock(return_value=(mock_baseline, "seeded"))

            response = client.post(
                "/api/equipment/baselines/seed",
                params={
                    "equipment_id": "S002-CHILLER-B1-001",
                    "site_id": "S002",
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["status"] == "seeded"
            assert data["baseline_id"] == "test-baseline-1"
            assert data["equipment_id"] == "S002-CHILLER-B1-001"

    def test_seed_batch_endpoint_returns_201(self, client):
        """Test that seed-batch endpoint returns 201 with batch results."""
        mock_results = [
            {
                "equipment_id": "EQ1",
                "status": "seeded",
                "baseline_id": "baseline-1",
                "message": "Baseline seeded",
            },
            {
                "equipment_id": "EQ2",
                "status": "error",
                "baseline_id": None,
                "message": "Equipment not found",
            },
        ]

        with patch("app.api.equipment_baselines.BaselineSeedService") as MockService:
            mock_service = MockService.return_value
            mock_service.seed_batch = AsyncMock(return_value=mock_results)

            response = client.post(
                "/api/equipment/baselines/seed-batch",
                json={
                    "equipment_ids": ["EQ1", "EQ2"],
                    "site_id": "S002",
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["total_requested"] == 2
            assert data["seeded_count"] == 1
            assert data["error_count"] == 1

    def test_seed_endpoint_returns_404_for_missing_equipment(self, client):
        """Test that seed endpoint returns 404 when equipment not found."""
        with patch("app.api.equipment_baselines.BaselineSeedService") as MockService:
            mock_service = MockService.return_value
            mock_service.seed_for_equipment_with_fallback = AsyncMock(side_effect=Exception("not found"))

            response = client.post(
                "/api/equipment/baselines/seed",
                params={
                    "equipment_id": "NONEXISTENT",
                    "site_id": "S002",
                },
            )

            assert response.status_code == 404

    def test_get_baseline_returns_200(self, client, mock_baseline):
        """Test that get baseline returns 200 with baseline data."""
        with patch("app.api.equipment_baselines.BaselineRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_active_equipment_baseline = AsyncMock(return_value=mock_baseline)

            response = client.get("/api/equipment/baselines/S002-CHILLER-B1-001")

            assert response.status_code == 200

    def test_get_baseline_returns_404_when_not_found(self, client):
        """Test that get baseline returns 404 when no baseline exists."""
        with patch("app.api.equipment_baselines.BaselineRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_active_equipment_baseline = AsyncMock(return_value=None)

            response = client.get("/api/equipment/baselines/S002-CHILLER-B1-001")

            assert response.status_code == 404

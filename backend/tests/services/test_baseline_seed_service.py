"""
Tests for BaselineSeedService (Phase 206-01)

Phase: 206-asset-onboarding
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.baseline_seed_service import BaselineSeedService
from app.models.baseline import BaselineSource, BaselineType, BaselineStatus, EquipmentBaseline


class TestBaselineSeedService:
    """Tests for BaselineSeedService."""

    @pytest.fixture
    def service(self):
        """Create service instance."""
        return BaselineSeedService()

    @pytest.fixture
    def mock_baseline(self):
        """Create a mock EquipmentBaseline."""
        return EquipmentBaseline(
            id="test-baseline-1",
            equipment_id="S002-CHILLER-B1-001",
            baseline_date=datetime.now(timezone.utc),
            captured_by="test",
            baseline_type=BaselineType.INITIAL,
            status=BaselineStatus.ACTIVE,
            baseline_values={},
            measurement_conditions={},
            source_type=BaselineSource.BMS_AVERAGE,
            notes=None,
            attachment_urls=[],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    @pytest.mark.asyncio
    async def test_seed_for_equipment_uses_capture_service(self, service, mock_baseline):
        """Test that seed_for_equipment calls capture service."""
        with patch.object(service, '_capture_service') as mock_capture:
            mock_capture.capture_equipment_baseline = AsyncMock(return_value=mock_baseline)

            result = await service.seed_for_equipment(
                equipment_id="S002-CHILLER-B1-001",
                site_id="S002",
                source=BaselineSource.BMS_AVERAGE,
                captured_by="test",
            )

            mock_capture.capture_equipment_baseline.assert_called_once()
            call_kwargs = mock_capture.capture_equipment_baseline.call_args.kwargs
            assert call_kwargs["equipment_id"] == "S002-CHILLER-B1-001"
            assert call_kwargs["source"] == BaselineSource.BMS_AVERAGE
            assert result.id == "test-baseline-1"

    @pytest.mark.asyncio
    async def test_seed_for_equipment_fallback(self, service, mock_baseline):
        """Test that fallback is used when device unavailable."""
        with patch.object(service, '_capture_service') as mock_capture:
            # Simulate device not available
            mock_capture.capture_equipment_baseline = AsyncMock(
                side_effect=Exception("Device not available")
            )

            with patch.object(service, '_seed_with_defaults', new_callable=AsyncMock) as mock_fallback:
                mock_fallback.return_value = mock_baseline

                result, status = await service.seed_for_equipment_with_fallback(
                    equipment_id="S002-CHILLER-B1-001",
                    site_id="S002",
                    captured_by="test",
                )

                # Should fall back to defaults
                assert status == "seeded_fallback"

    @pytest.mark.asyncio
    async def test_seed_batch_returns_results_list(self, service, mock_baseline):
        """Test that seed_batch returns proper results."""
        with patch.object(service, 'seed_for_equipment_with_fallback', new_callable=AsyncMock) as mock_seed:
            mock_seed.side_effect = [
                (mock_baseline, "seeded"),
                (None, "error: equipment not found"),
            ]

            results = await service.seed_batch(
                equipment_ids=["EQ1", "EQ2"],
                site_id="S002",
                captured_by="test",
            )

            assert len(results) == 2
            assert results[0]["status"] == "seeded"
            assert "error" in results[1]["status"]  # error message contains "error"

    def test_get_default_baseline_values_chiller(self, service):
        """Test default baseline values for chiller."""
        defaults = service._get_default_baseline_values("chiller")
        assert "chw_supply_temp" in defaults
        assert defaults["chw_supply_temp"]["unit"] == "°C"

    def test_get_default_baseline_values_unknown(self, service):
        """Test default baseline values for unknown type."""
        defaults = service._get_default_baseline_values("unknown")
        assert "status" in defaults

    @pytest.mark.asyncio
    async def test_seed_for_equipment_raises_not_found(self, service):
        """Test that EquipmentNotFound is raised properly."""
        from app.services.baseline_capture_service import EquipmentNotFound

        with patch.object(service, '_capture_service') as mock_capture:
            mock_capture.capture_equipment_baseline = AsyncMock(
                side_effect=EquipmentNotFound("S002-CHILLER-B1-001 not found")
            )

            with pytest.raises(EquipmentNotFound):
                await service.seed_for_equipment(
                    equipment_id="S002-CHILLER-B1-001",
                    site_id="S002",
                )
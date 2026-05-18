"""
Tests for ODS-E Export Service

 Validates ODS-E v0.4.0 compliance and data transformation logic.
"""

import pytest
from datetime import datetime, timedelta

from app.models.odse_models import (
    ODSEAssetExport,
    ODSETimeseriesExport,
    ODSEValidationResult,
)
from app.services.odse_service import ODSEExportService


@pytest.fixture
def odse_service():
    """Fixture for ODSEExportService."""
    return ODSEExportService()


@pytest.fixture
def sample_reading():
    """Sample energy reading for testing."""
    return {
        "timestamp": datetime(2026, 5, 1, 12, 0, 0),
        "kwh": 15.5,
        "equipment_type": "CHILLER",
        "health_score": 82.0,
        "power_factor": 0.95,
        "kva": 16.3,
    }


@pytest.fixture
def sample_equipment():
    """Sample equipment for testing."""
    return {
        "equipment_code": "S002-CHILLER-B1-001",
        "equipment_type": "CHILLER",
        "capacity_kw": 350.0,
        "site_id": "site-002",
        "manufacturer": "Carrier",
        "protocol": "BACnet/IP",
        "health_score": 82,
        "last_seen": datetime.utcnow(),
        "zone": "plant-room",
        "site_config": {
            "country_code": "ZA",
            "municipality_id": "za.gt.johannesburg",
            "timezone": "Africa/Johannesburg",
        },
    }


class TestODSEService:
    """Test cases for ODSEExportService."""

    def test_health_to_error_type_mapping(self, odse_service):
        """Test health score to error_type mapping."""
        assert odse_service._map_health_to_error_type(90) == "normal"
        assert odse_service._map_health_to_error_type(80) == "normal"
        assert odse_service._map_health_to_error_type(70) == "warning"
        assert odse_service._map_health_to_error_type(60) == "warning"
        assert odse_service._map_health_to_error_type(50) == "critical"
        assert odse_service._map_health_to_error_type(40) == "critical"
        assert odse_service._map_health_to_error_type(30) == "fault"
        assert odse_service._map_health_to_error_type(None) == "unknown"

    def test_eskom_tariff_period_weekday_peak(self, odse_service):
        """Test Eskom tariff period calculation - weekday peak hours."""
        # Peak: 07:00-10:00 and 18:00-20:00 on weekdays
        peak_morning = datetime(2026, 5, 5, 8, 0, 0)  # Monday 8am
        peak_evening = datetime(2026, 5, 5, 19, 0, 0)  # Monday 7pm

        assert odse_service._get_eskom_tariff_period(peak_morning) == "peak"
        assert odse_service._get_eskom_tariff_period(peak_evening) == "peak"

    def test_eskom_tariff_period_weekday_standard(self, odse_service):
        """Test Eskom tariff period calculation - weekday standard hours."""
        standard_midday = datetime(2026, 5, 5, 12, 0, 0)  # Monday noon

        assert odse_service._get_eskom_tariff_period(standard_midday) == "standard"

    def test_eskom_tariff_period_weekday_off_peak(self, odse_service):
        """Test Eskom tariff period calculation - weekday off-peak hours."""
        off_peak_night = datetime(2026, 5, 5, 3, 0, 0)  # Monday 3am

        assert odse_service._get_eskom_tariff_period(off_peak_night) == "off_peak"

    def test_eskom_tariff_period_weekend(self, odse_service):
        """Test Eskom tariff period calculation - weekend always off-peak."""
        saturday_peak_hour = datetime(2026, 5, 2, 9, 0, 0)  # Saturday 9am (would be peak on weekday)
        sunday_evening = datetime(2026, 5, 3, 19, 0, 0)  # Sunday 7pm

        assert odse_service._get_eskom_tariff_period(saturday_peak_hour) == "off_peak"
        assert odse_service._get_eskom_tariff_period(sunday_evening) == "off_peak"

    def test_end_use_mapping(self, odse_service, sample_reading):
        """Test equipment type to end_use mapping."""
        record = odse_service._map_reading_to_odse(sample_reading, "consumption")
        assert record.end_use == "cooling"  # CHILLER -> cooling

        # Test other mappings
        sample_reading["equipment_type"] = "BOILER"
        record = odse_service._map_reading_to_odse(sample_reading, "consumption")
        assert record.end_use == "heating"

        sample_reading["equipment_type"] = "DALI_CONTROLLER"
        record = odse_service._map_reading_to_odse(sample_reading, "consumption")
        assert record.end_use == "lighting"

        sample_reading["equipment_type"] = "GEN"
        record = odse_service._map_reading_to_odse(sample_reading, "generation")
        assert record.end_use == "generation"

    def test_map_reading_preserves_values(self, odse_service, sample_reading):
        """Test that reading values are preserved in mapping."""
        record = odse_service._map_reading_to_odse(sample_reading, "consumption")

        assert record.kWh == 15.5
        assert record.PF == 0.95
        assert record.kVA == 16.3
        assert record.fuel_type == "electricity"
        assert record.tariff_currency == "ZAR"
        assert record.direction == "consumption"

    def test_map_equipment_preserves_values(self, odse_service, sample_equipment):
        """Test that equipment values are preserved in mapping."""
        asset = odse_service._map_equipment_to_odse_asset(sample_equipment, include_health=True)

        assert asset.asset_id == "S002-CHILLER-B1-001"
        assert asset.asset_type == "chiller"
        assert asset.capacity_kw == 350.0
        assert asset.oem == "Carrier"
        assert asset.site_id == "site-002"
        assert asset.sentinel_extensions.health_score == 82
        assert asset.sentinel_extensions.floor == "B1"
        assert asset.sentinel_extensions.zone == "plant-room"

    def test_map_equipment_excludes_health_when_flag_false(self, odse_service, sample_equipment):
        """Test that health_score is excluded when include_health=False."""
        asset = odse_service._map_equipment_to_odse_asset(sample_equipment, include_health=False)

        assert asset.sentinel_extensions.health_score is None

    def test_map_equipment_extracts_floor_from_code(self, odse_service):
        """Test floor extraction from equipment codes."""
        test_cases = [
            ("S002-CHILLER-B1-001", "B1"),
            ("S002-AHU-L3-001", "L3"),
            ("S002-FCU-G-001", "G"),
            ("S002-GEN-R-001", "R"),
        ]

        for code, expected_floor in test_cases:
            equipment = {
                "equipment_code": code,
                "equipment_type": "TEST",
                "site_id": "site-002",
                "site_config": {"country_code": "ZA"},
            }
            asset = odse_service._map_equipment_to_odse_asset(equipment, include_health=False)
            assert asset.sentinel_extensions.floor == expected_floor, f"Failed for {code}"


@pytest.mark.asyncio
class TestODSEAsyncOperations:
    """Async test cases requiring pytest-asyncio."""

    async def test_export_timeseries_structure(self, odse_service):
        """Test that export_timeseries returns correct structure."""
        start = datetime(2026, 5, 1, 0, 0, 0)
        end = datetime(2026, 5, 1, 1, 0, 0)  # 1 hour window

        result = await odse_service.export_timeseries(
            site_id="site-002",
            start=start,
            end=end,
            interval_minutes=15,
        )

        assert isinstance(result, ODSETimeseriesExport)
        assert result.schema_version == "0.4.0"
        assert result.source_system == "sentinel-bms"
        assert result.site_id == "site-002"
        assert result.record_count > 0
        assert len(result.records) > 0
        assert result.asset_metadata is not None
        assert result.odse_validation is not None

    async def test_export_asset_metadata_structure(self, odse_service):
        """Test that export_asset_metadata returns correct structure."""
        result = await odse_service.export_asset_metadata(
            site_id="site-002",
            include_health=True,
        )

        assert isinstance(result, ODSEAssetExport)
        assert result.schema_version == "0.4.0"
        assert result.source_system == "sentinel-bms"
        assert result.site_id == "site-002"
        assert len(result.assets) > 0

        # Verify asset structure
        for asset in result.assets:
            assert asset.asset_id
            assert asset.asset_type
            assert asset.location.country_code == "ZA"
            assert asset.sentinel_extensions is not None

    async def test_export_asset_metadata_with_type_filter(self, odse_service):
        """Test equipment type filtering in asset export."""
        result = await odse_service.export_asset_metadata(
            site_id="site-002",
            equipment_type="CHILLER",
            include_health=True,
        )

        # All returned assets should be CHILLER type
        for asset in result.assets:
            assert asset.asset_type == "chiller"


class TestODSERecordValidation:
    """Test ODS-E record validation."""

    def test_odse_record_valid_power_factor(self):
        """Test that power factor is validated to 0.0-1.0 range."""
        from app.models.odse_models import ODSERecord

        # Valid power factor
        record = ODSERecord(timestamp="2026-05-01T00:00:00Z", kWh=10.0, PF=0.95)
        assert record.PF == 0.95

        # Edge cases
        record = ODSERecord(timestamp="2026-05-01T00:00:00Z", kWh=10.0, PF=0.0)
        assert record.PF == 0.0

        record = ODSERecord(timestamp="2026-05-01T00:00:00Z", kWh=10.0, PF=1.0)
        assert record.PF == 1.0

    def test_odse_record_invalid_power_factor(self):
        """Test that invalid power factor raises validation error."""
        from app.models.odse_models import ODSERecord
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ODSERecord(timestamp="2026-05-01T00:00:00Z", kWh=10.0, PF=1.5)

        with pytest.raises(ValidationError):
            ODSERecord(timestamp="2026-05-01T00:00:00Z", kWh=10.0, PF=-0.5)

    def test_odse_record_error_type_enum(self):
        """Test that error_type accepts only valid enum values."""
        from app.models.odse_models import ODSERecord
        from pydantic import ValidationError

        # Valid values
        for error_type in ["normal", "warning", "critical", "fault", "unknown"]:
            record = ODSERecord(timestamp="2026-05-01T00:00:00Z", kWh=10.0, error_type=error_type)
            assert record.error_type == error_type

        # Invalid value
        with pytest.raises(ValidationError):
            ODSERecord(timestamp="2026-05-01T00:00:00Z", kWh=10.0, error_type="invalid")

    def test_odse_record_direction_enum(self):
        """Test that direction accepts only valid enum values."""
        from app.models.odse_models import ODSERecord
        from pydantic import ValidationError

        # Valid values
        for direction in ["consumption", "generation", "net"]:
            record = ODSERecord(timestamp="2026-05-01T00:00:00Z", kWh=10.0, direction=direction)
            assert record.direction == direction

        # Invalid value
        with pytest.raises(ValidationError):
            ODSERecord(timestamp="2026-05-01T00:00:00Z", kWh=10.0, direction="invalid")

    def test_odse_record_tariff_period_enum(self):
        """Test that tariff_period accepts only valid enum values."""
        from app.models.odse_models import ODSERecord
        from pydantic import ValidationError

        # Valid values
        for period in ["peak", "standard", "off_peak", None]:
            record = ODSERecord(
                timestamp="2026-05-01T00:00:00Z",
                kWh=10.0,
                tariff_period=period
            )
            assert record.tariff_period == period

        # Invalid value
        with pytest.raises(ValidationError):
            ODSERecord(timestamp="2026-05-01T00:00:00Z", kWh=10.0, tariff_period="invalid")

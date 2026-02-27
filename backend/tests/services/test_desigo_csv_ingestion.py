"""Tests for Desigo CSV point export ingestion and lighting classification.

Tests cover:
    - CSV parsing (hierarchical names, flat names, edge cases) (4 tests)
    - Tridonic/net4more lighting point classification (5 tests)
    - Mixed HVAC + lighting export classification (2 tests)
    - Lighting summary extraction (2 tests)
    - API endpoint validation (2 tests)

Total: 15 tests

Validates that when a real Desigo CSV export (with Tridonic lighting points
exposed via net4more BACnet gateway) is uploaded, the PointClassifier
correctly identifies all lighting equipment and telemetry categories.
"""

from unittest.mock import patch

import pytest

from app.services.niagara.point_classifier import (
    PointClassifier,
)
from app.services.niagara.point_discovery import PointDiscoveryService


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


# Realistic Tridonic/net4more BACnet point names as they'd appear
# in a Desigo CSV export. These follow the STC/{level}/{equip}/{point}
# convention with Tridonic-style point naming.
TRIDONIC_LIGHTING_CSV = """\
name,object_type,instance,units,present_value,description,min_value,max_value,writable
STC/L1/DALI-01/Lum01_DimLevel,analogOutput,3000,percent,85,Luminaire 01 dimming level,0,100,True
STC/L1/DALI-01/Lum01_ActivePower,analogInput,3001,watt,42.5,Luminaire 01 active power,0,120,False
STC/L1/DALI-01/Lum01_AccumEnergy,analogInput,3002,kwh,1247.3,Luminaire 01 accumulated energy,0,99999,False
STC/L1/DALI-01/Lum01_DriverTemp,analogInput,3003,degC,52.3,Luminaire 01 driver temperature,0,120,False
STC/L1/DALI-01/Lum01_LampHours,analogInput,3004,hours,12450,Luminaire 01 operating hours,0,100000,False
STC/L1/DALI-01/Lum01_LightOutput,analogInput,3005,percent,94.2,Luminaire 01 light output maintenance,0,100,False
STC/L1/DALI-01/Lum01_LampFail,binaryInput,3006,,0,Luminaire 01 lamp failure alarm,,,False
STC/L1/DALI-01/Lum01_DriverFault,binaryInput,3007,,0,Luminaire 01 driver fault alarm,,,False
STC/L1/DALI-01/Lum02_DimLevel,analogOutput,3010,percent,70,Luminaire 02 dimming level,0,100,True
STC/L1/DALI-01/Lum02_ActivePower,analogInput,3011,watt,35.0,Luminaire 02 active power,0,120,False
STC/L1/DALI-01/Sens01_Lux,analogInput,3020,lux,485,Sensor 01 ambient lux level,0,5000,False
STC/L1/DALI-01/Sens01_Occupancy,binaryInput,3021,,1,Sensor 01 presence detection,,,False
STC/L1/DALI-01/Sens01_AmbientLux,analogInput,3022,lux,485,Sensor 01 ambient illuminance,0,5000,False
STC/L1/DALI-01/Em01_BattLevel,analogInput,3030,percent,96,Emergency luminaire 01 battery level,0,100,False
STC/L1/DALI-01/Em01_ChargeStatus,multistateValue,3031,,1,Emergency luminaire 01 charge state,,,False
STC/L1/DALI-01/Em01_TestResult,multistateValue,3032,,1,Emergency luminaire 01 last test result,,,False
STC/L1/DALI-01/Ctrl_Status,binaryInput,3040,,1,DALI controller 01 online status,,,False
STC/L1/DALI-01/Ctrl_BusFault,binaryInput,3041,,0,DALI controller 01 bus fault,,,False
STC/L1/DALI-01/SceneRecall,multistateValue,3050,,3,Scene recall command,,,True
"""

# Mixed export with both HVAC and lighting
MIXED_HVAC_LIGHTING_CSV = """\
name,object_type,instance,units,present_value,description,min_value,max_value,writable
STC/RF/AHU-01/SupplyAirTemp,analogInput,1000,degC,15.2,Supply air temperature,12.0,25.0,False
STC/RF/AHU-01/FanStatus,binaryValue,1002,,1,Fan on/off status,,,True
STC/B1/CH-01/ChwSupplyTemp,analogInput,1006,degC,7.0,Chilled water supply temperature,4.0,15.0,False
STC/L1/FCU-01/RoomTemp,analogInput,1011,degC,22.8,Room temperature,16.0,32.0,False
STC/L1/DALI-01/Lum01_DimLevel,analogOutput,3000,percent,85,Luminaire 01 dimming level,0,100,True
STC/L1/DALI-01/Lum01_ActivePower,analogInput,3001,watt,42.5,Luminaire 01 active power,0,120,False
STC/L1/DALI-01/Sens01_Lux,analogInput,3020,lux,485,Sensor 01 ambient lux level,0,5000,False
STC/L1/DALI-01/Ctrl_Status,binaryInput,3040,,1,DALI controller online,,,False
STC/L1/DALI-01/Em01_BattLevel,analogInput,3030,percent,96,Emergency battery level,0,100,False
STC/B1/MTR-MAIN/kW,analogInput,1100,kW,450,Main meter power,0,2000,False
"""


@pytest.fixture
def classifier():
    """Fresh PointClassifier instance."""
    return PointClassifier()


@pytest.fixture
def discovery_service():
    """PointDiscoveryService with mocked Supabase."""
    with patch("app.services.niagara.point_discovery.get_supabase_client"):
        return PointDiscoveryService()


# ------------------------------------------------------------------
# 1. CSV Parsing
# ------------------------------------------------------------------


class TestCSVParsing:
    """Verify CSV parsing handles Desigo format correctly."""

    def test_parse_tridonic_csv_point_count(self, discovery_service):
        """All rows from Tridonic CSV are parsed."""
        points = discovery_service._parse_csv_export(TRIDONIC_LIGHTING_CSV)
        assert len(points) == 19

    def test_parse_hierarchical_name_extracts_equipment_id(self, discovery_service):
        """STC/L1/DALI-01/Lum01_ActivePower → equipment_id = DALI-01."""
        equip_id, suffix = discovery_service._parse_hierarchical_name("STC/L1/DALI-01/Lum01_ActivePower")
        assert equip_id == "DALI-01"
        assert suffix == "Lum01_ActivePower"

    def test_parse_hierarchical_name_handles_flat(self, discovery_service):
        """DALI-01_Lum01_ActivePower → equipment_id = DALI-01."""
        equip_id, suffix = discovery_service._parse_hierarchical_name("DALI-01_Lum01_ActivePower")
        assert equip_id == "DALI-01"
        assert suffix == "Lum01_ActivePower"

    def test_csv_writable_field_parsed(self, discovery_service):
        """Writable field correctly parsed as boolean."""
        points = discovery_service._parse_csv_export(TRIDONIC_LIGHTING_CSV)
        # DimLevel is writable=True
        dim_point = next(p for p in points if "DimLevel" in p["name"])
        assert dim_point["writable"] is True
        # ActivePower is writable=False
        power_point = next(p for p in points if "ActivePower" in p["name"])
        assert power_point["writable"] is False


# ------------------------------------------------------------------
# 2. Tridonic Lighting Point Classification
# ------------------------------------------------------------------


class TestTridonicLightingClassification:
    """Verify classifier detects Tridonic lighting points from net4more BACnet names."""

    def test_dim_level_classified_as_brightness(self, classifier):
        """DimLevel → brightness category, writable command."""
        result = classifier.classify_point(
            point_name="STC/L1/DALI-01/Lum01_DimLevel",
            point_description="Luminaire 01 dimming level",
            object_type="analogOutput",
            units="percent",
            writable=True,
            metadata_equipment_id="DALI-01",
        )
        assert result.point_category == "brightness"
        assert result.equipment_type in ("dali_controller", "dali", "luminaire")

    def test_active_power_classified_as_lighting_power(self, classifier):
        """ActivePower → lighting_power category."""
        result = classifier.classify_point(
            point_name="STC/L1/DALI-01/Lum01_ActivePower",
            point_description="Luminaire 01 active power",
            object_type="analogInput",
            units="watt",
            writable=False,
            metadata_equipment_id="DALI-01",
        )
        # Should be power or lighting_power category
        assert result.point_category in ("power", "lighting_power")

    def test_lux_sensor_classified(self, classifier):
        """Lux → lux category with correct unit."""
        result = classifier.classify_point(
            point_name="STC/L1/DALI-01/Sens01_Lux",
            point_description="Sensor 01 ambient lux level",
            object_type="analogInput",
            units="lux",
            writable=False,
            metadata_equipment_id="DALI-01",
        )
        assert result.point_category == "lux"
        assert result.unit == "lux"

    def test_lamp_hours_classified(self, classifier):
        """LampHours → lamp_hours category."""
        result = classifier.classify_point(
            point_name="STC/L1/DALI-01/Lum01_LampHours",
            point_description="Luminaire 01 operating hours",
            object_type="analogInput",
            units="hours",
            writable=False,
            metadata_equipment_id="DALI-01",
        )
        assert result.point_category == "lamp_hours"

    def test_emergency_battery_classified(self, classifier):
        """Em01_BattLevel → emergency_battery category."""
        result = classifier.classify_point(
            point_name="STC/L1/DALI-01/Em01_BattLevel",
            point_description="Emergency luminaire 01 battery level",
            object_type="analogInput",
            units="percent",
            writable=False,
            metadata_equipment_id="DALI-01",
        )
        assert result.point_category == "emergency_battery"


# ------------------------------------------------------------------
# 3. Mixed HVAC + Lighting Export
# ------------------------------------------------------------------


class TestMixedExportClassification:
    """Verify classifier handles both HVAC and lighting in same export."""

    def test_mixed_csv_detects_both_hvac_and_lighting(self, discovery_service):
        """Mixed CSV correctly separates HVAC from lighting."""
        result = discovery_service.discover_from_csv(
            csv_content=MIXED_HVAC_LIGHTING_CSV,
            site_id="site-002",
            source_label="test-mixed",
        )
        assert result.status == "complete"

        # Should have both HVAC and lighting equipment
        equip_types = set(result.summary.get("equipment_type_counts", {}).keys())
        # HVAC types
        assert "ahu" in equip_types or "chiller" in equip_types or "fcu" in equip_types
        # Lighting detected
        lighting = result.summary.get("lighting_points", {})
        assert lighting["total"] > 0

    def test_mixed_csv_equipment_count(self, discovery_service):
        """Mixed CSV identifies correct number of equipment entities."""
        result = discovery_service.discover_from_csv(
            csv_content=MIXED_HVAC_LIGHTING_CSV,
            site_id="site-002",
            source_label="test-mixed",
        )
        # Should identify: AHU-01, CH-01, FCU-01, DALI-01, MTR-MAIN = at least 4 unique
        unique_equip = result.summary.get("unique_equipment", {})
        total_unique = sum(len(ids) for ids in result.summary.get("equipment_ids", {}).values())
        assert total_unique >= 4


# ------------------------------------------------------------------
# 4. Lighting Summary Extraction
# ------------------------------------------------------------------


class TestLightingSummary:
    """Verify lighting-specific summary statistics."""

    def test_lighting_summary_counts_by_category(self, discovery_service):
        """Lighting summary breaks down points by category."""
        result = discovery_service.discover_from_csv(
            csv_content=TRIDONIC_LIGHTING_CSV,
            site_id="site-002",
            source_label="test-tridonic",
        )
        lighting = result.summary.get("lighting_points", {})
        by_cat = lighting.get("by_category", {})
        # Should have multiple lighting categories
        assert len(by_cat) >= 3, f"Expected 3+ lighting categories, got {by_cat}"

    def test_full_tridonic_csv_lighting_total(self, discovery_service):
        """Full Tridonic CSV has most/all points classified as lighting."""
        result = discovery_service.discover_from_csv(
            csv_content=TRIDONIC_LIGHTING_CSV,
            site_id="site-002",
            source_label="test-tridonic",
        )
        lighting = result.summary.get("lighting_points", {})
        # 19 points total, most should be lighting
        assert lighting["total"] >= 12, f"Expected 12+ lighting points, got {lighting['total']}"


# ------------------------------------------------------------------
# 5. API Endpoint Validation
# ------------------------------------------------------------------


class TestCSVUploadAPI:
    """Verify the CSV upload API endpoint structure."""

    @pytest.mark.asyncio
    async def test_csv_upload_endpoint_exists(self):
        """CSV upload endpoint is registered on router."""
        from app.api.niagara_discovery import router

        paths = [route.path for route in router.routes]
        assert "/api/niagara/discover/csv" in paths

    @pytest.mark.asyncio
    async def test_csv_upload_rejects_non_csv(self):
        """Non-CSV uploads are rejected with 400."""
        from fastapi.testclient import TestClient

        from app.api.niagara_discovery import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.post(
            "/api/niagara/discover/csv",
            files={"file": ("points.txt", b"not,a,csv", "text/plain")},
            params={"site_id": "site-002"},
        )
        assert response.status_code == 400

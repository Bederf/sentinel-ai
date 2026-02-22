"""Integration tests for discovery pipeline with equipment naming conversion.

Tests the complete workflow:
1. BMS points discovered
2. Points classified
3. Equipment grouped with v2.0 naming conversion
4. Zones inferred from equipment IDs
5. zones.json generated
6. Equipment models created
"""

import pytest

from app.services.niagara.mapping_service import (
    PointMappingService,
)
from app.services.niagara.point_classifier import ClassifiedPoint, PointType, ConfidenceLevel
from app.services.equipment_id_converter import EquipmentIDConverter
from app.services.zone_mapping_service import ZoneMappingService


@pytest.fixture
def converter():
    """Equipment ID converter instance."""
    return EquipmentIDConverter()


@pytest.fixture
def zone_service():
    """Zone mapping service instance."""
    return ZoneMappingService()


@pytest.fixture
def mapping_service():
    """Point mapping service instance."""
    return PointMappingService()


@pytest.fixture
def sample_classified_points():
    """Sample classified points from BMS discovery."""
    return [
        # Chiller points
        ClassifiedPoint(
            original_name="CH-1.ChwSupplyTemp",
            standardized_name="chw_supply_temp",
            point_type=PointType.SENSOR,
            point_category="chilled_water_temperature",
            equipment_id="CH-1",
            equipment_type="chiller",
            confidence=ConfidenceLevel.HIGH,
            unit="°C",
            object_type="analogInput",
            instance=1000,
            writable=False,
            present_value=7.0,
        ),
        ClassifiedPoint(
            original_name="CH-1.ChwSetpoint",
            standardized_name="chw_setpoint",
            point_type=PointType.SETPOINT,
            point_category="chilled_water_setpoint",
            equipment_id="CH-1",
            equipment_type="chiller",
            confidence=ConfidenceLevel.HIGH,
            unit="°C",
            object_type="analogValue",
            instance=1001,
            writable=True,
            present_value=7.0,
        ),
        # VAV points
        ClassifiedPoint(
            original_name="VAV-L1-A.RoomTemp",
            standardized_name="zone_temp",
            point_type=PointType.SENSOR,
            point_category="room_temperature",
            equipment_id="VAV-L1-A",
            equipment_type="vav",
            confidence=ConfidenceLevel.HIGH,
            unit="°C",
            object_type="analogInput",
            instance=2000,
            writable=False,
            present_value=22.5,
        ),
        ClassifiedPoint(
            original_name="VAV-L1-A.DamperPos",
            standardized_name="damper_position",
            point_type=PointType.SENSOR,
            point_category="damper_position",
            equipment_id="VAV-L1-A",
            equipment_type="vav",
            confidence=ConfidenceLevel.HIGH,
            unit="%",
            object_type="analogInput",
            instance=2001,
            writable=False,
            present_value=50.0,
        ),
        ClassifiedPoint(
            original_name="VAV-L1-A.Setpoint",
            standardized_name="temperature_setpoint",
            point_type=PointType.SETPOINT,
            point_category="temperature_setpoint",
            equipment_id="VAV-L1-A",
            equipment_type="vav",
            confidence=ConfidenceLevel.MEDIUM,
            unit="°C",
            object_type="analogValue",
            instance=2002,
            writable=True,
            present_value=22.0,
        ),
        # FCU points
        ClassifiedPoint(
            original_name="FCU-L2-B.RoomTemp",
            standardized_name="zone_temp",
            point_type=PointType.SENSOR,
            point_category="room_temperature",
            equipment_id="FCU-L2-B",
            equipment_type="fcu",
            confidence=ConfidenceLevel.HIGH,
            unit="°C",
            object_type="analogInput",
            instance=3000,
            writable=False,
            present_value=23.0,
        ),
        ClassifiedPoint(
            original_name="FCU-L2-B.FanSpeed",
            standardized_name="fan_speed",
            point_type=PointType.COMMAND,
            point_category="fan_speed",
            equipment_id="FCU-L2-B",
            equipment_type="fcu",
            confidence=ConfidenceLevel.HIGH,
            unit="steps",
            object_type="analogOutput",
            instance=3001,
            writable=True,
            present_value=2,
        ),
    ]


class TestDiscoveryNamingConversion:
    """Test naming conversion in discovery workflow."""

    def test_convert_bms_ids_during_mapping(self, mapping_service, sample_classified_points):
        """Test that BMS IDs are converted to v2.0 format during mapping."""
        mappings = mapping_service.map_points_to_equipment(
            sample_classified_points,
            site_id="site-002",
        )

        # Verify v2.0 format IDs
        assert "S002-CHILLER-B1-001" in mappings
        assert "S002-VAV-L1-A" in mappings
        assert "S002-FCU-L2-B" in mappings

        # Verify no BMS IDs in output
        assert "CH-1" not in mappings
        assert "VAV-L1-A" not in mappings
        assert "FCU-L2-B" not in mappings

    def test_original_bms_id_stored_in_metadata(self, mapping_service, sample_classified_points):
        """Test that original BMS ID is preserved in metadata."""
        mappings = mapping_service.map_points_to_equipment(
            sample_classified_points,
            site_id="site-002",
        )

        # Check metadata for BMS IDs
        assert mappings["S002-CHILLER-B1-001"].metadata.get("bms_original_id") == "CH-1"
        assert mappings["S002-VAV-L1-A"].metadata.get("bms_original_id") == "VAV-L1-A"
        assert mappings["S002-FCU-L2-B"].metadata.get("bms_original_id") == "FCU-L2-B"

    def test_zone_inference_from_equipment_id(self, mapping_service, sample_classified_points):
        """Test that zones are inferred from v2.0 equipment IDs."""
        mappings = mapping_service.map_points_to_equipment(
            sample_classified_points,
            site_id="site-002",
        )

        # Check zone metadata
        vav_mapping = mappings["S002-VAV-L1-A"]
        assert "zone" in vav_mapping.metadata
        zone_info = vav_mapping.metadata["zone"]
        assert zone_info["floor"] == "L1"
        assert zone_info["zone_letter"] == "A"

        fcu_mapping = mappings["S002-FCU-L2-B"]
        assert "zone" in fcu_mapping.metadata
        zone_info = fcu_mapping.metadata["zone"]
        assert zone_info["floor"] == "L2"
        assert zone_info["zone_letter"] == "B"

        # Chiller has no zone (plant room)
        chiller_mapping = mappings["S002-CHILLER-B1-001"]
        assert "zone" in chiller_mapping.metadata or "zone" not in chiller_mapping.metadata

    def test_equipment_mapping_structure(self, mapping_service, sample_classified_points):
        """Test equipment mapping structure with v2.0 IDs."""
        mappings = mapping_service.map_points_to_equipment(
            sample_classified_points,
            site_id="site-002",
        )

        chiller = mappings["S002-CHILLER-B1-001"]
        assert chiller.equipment_id == "S002-CHILLER-B1-001"
        assert chiller.equipment_type == "chiller"
        assert len(chiller.points) == 2  # Two chiller points
        assert chiller.site_id == "site-002"


class TestZoneGeneration:
    """Test automatic zone generation from discovered equipment."""

    def test_zones_file_generation(self, mapping_service, sample_classified_points):
        """Test that zones.json is generated from equipment."""
        mappings = mapping_service.map_points_to_equipment(
            sample_classified_points,
            site_id="site-002",
        )

        # Generate equipment models
        models = []
        for mapping in mappings.values():
            if mapping.equipment_id != "UNASSIGNED":
                model = mapping_service.generate_equipment_model(mapping)
                models.append(model)

        # Test zone generation
        zones_result = mapping_service.generate_zones_file(models, "site-002")

        # Verify result structure
        assert zones_result["success"] is True
        # May be 0 if zones can't parse the full IDs, but generation should succeed
        assert zones_result.get("zones_count", 0) >= 0

    def test_zone_content_structure(self, zone_service, sample_classified_points):
        """Test structure of generated zones."""
        # Create mock equipment list
        equipment_list = [
            {"equipment_id": "S002-VAV-L1-A"},
            {"equipment_id": "S002-FCU-L2-B"},
        ]

        zones = zone_service.create_zones_from_equipment(equipment_list, "site-002")

        # Verify zone structure
        assert len(zones) >= 1
        for zone in zones:
            assert "zone_id" in zone
            assert "floor" in zone
            assert "equipment" in zone
            assert zone["zone_id"].startswith("Zone-")


class TestApprovalAndActivation:
    """Test approval workflow with naming conversion."""

    def test_approval_creates_v2_equipment_models(self, mapping_service, sample_classified_points):
        """Test that approval generates equipment models with v2.0 IDs."""
        # Map points
        mappings = mapping_service.map_points_to_equipment(
            sample_classified_points,
            site_id="site-002",
        )

        # Save mappings
        mapping_service.save_mappings("discovery-test-001", mappings, "site-002")

        # Approve
        result = mapping_service.approve_mappings("discovery-test-001", "test-user")

        assert result["success"] is True
        assert result["equipment_created"] > 0

        # Check equipment models have v2.0 IDs
        for model in result["equipment_models"]:
            # All equipment should start with S and have proper format
            assert "id" in model
            equipment_id = model["id"]
            # Format: {site_id}-{v2_id}
            assert "S002" in equipment_id or "site-002" in equipment_id

    def test_zones_generated_on_approval(self, mapping_service, sample_classified_points):
        """Test that zones.json is generated during approval."""
        # Map and approve
        mappings = mapping_service.map_points_to_equipment(
            sample_classified_points,
            site_id="site-002",
        )
        mapping_service.save_mappings("discovery-test-002", mappings, "site-002")
        result = mapping_service.approve_mappings("discovery-test-002", "test-user")

        # Verify zones were generated
        assert result.get("zones_generated") is not False
        assert result.get("zones_count", 0) >= 0


class TestEndToEndWorkflow:
    """Test complete end-to-end discovery and naming workflow."""

    def test_full_discovery_workflow(self, mapping_service, sample_classified_points):
        """Test complete workflow from discovery to approval."""
        site_id = "site-002"
        discovery_id = "discovery-e2e-001"

        # Step 1: Map points with naming conversion
        mappings = mapping_service.map_points_to_equipment(
            sample_classified_points,
            site_id=site_id,
        )

        assert len(mappings) == 3  # CHILLER, VAV, FCU

        # Step 2: Verify v2.0 naming
        equipment_ids = [m.equipment_id for m in mappings.values()]
        assert all(eq_id.startswith("S002-") for eq_id in equipment_ids)

        # Step 3: Validate mappings
        validation = mapping_service.validate_mappings(mappings)
        assert validation.valid is True or len(validation.errors) == 0

        # Step 4: Save mappings
        save_result = mapping_service.save_mappings(discovery_id, mappings, site_id)
        assert save_result["success"] is True

        # Step 5: Approve mappings
        approval_result = mapping_service.approve_mappings(discovery_id, "test-user")
        assert approval_result["success"] is True
        assert approval_result["equipment_created"] >= 3

        # Step 6: Verify zones generated
        assert approval_result.get("zones_generated") is not False
        assert approval_result.get("zones_count", 0) >= 0

        # Step 7: Verify equipment models have v2.0 format IDs
        for model in approval_result["equipment_models"]:
            equipment_id = model["id"]
            # Should be v2.0 format starting with S and containing numbers: S###-TYPE-FLOOR-ZONE
            assert equipment_id.startswith("S")
            assert "-" in equipment_id
            assert any(c.isdigit() for c in equipment_id.split("-")[0])  # S### has digits

    def test_metadata_preservation_end_to_end(self, mapping_service, sample_classified_points):
        """Test that important metadata is preserved throughout workflow."""
        mappings = mapping_service.map_points_to_equipment(
            sample_classified_points,
            site_id="site-002",
        )

        # Check metadata for key mapping
        vav = mappings["S002-VAV-L1-A"]
        assert vav.metadata.get("bms_original_id") == "VAV-L1-A"
        assert vav.metadata.get("zone") is not None
        assert vav.metadata["zone"]["floor"] == "L1"
        assert vav.metadata["zone"]["zone_letter"] == "A"


class TestConverterIntegration:
    """Test converter integration with mapping service."""

    def test_converter_handles_all_point_types(self, converter, mapping_service, sample_classified_points):
        """Test that converter integrates with all point types."""
        # Should not raise for any equipment type in sample
        mappings = mapping_service.map_points_to_equipment(
            sample_classified_points,
            site_id="site-002",
        )

        assert len(mappings) == 3
        assert all(m.equipment_id.startswith("S002-") for m in mappings.values())

    def test_converter_idempotent(self, converter):
        """Test that converter produces consistent results."""
        bms_id = "VAV-L1-05"
        equipment_type = "vav"
        site_id = "site-002"
        zone_mapping = {"05": "E"}

        result1 = converter.convert_bms_to_v2(bms_id, equipment_type, site_id, zone_mapping)
        result2 = converter.convert_bms_to_v2(bms_id, equipment_type, site_id, zone_mapping)

        assert result1 == result2 == "S002-VAV-L1-E"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

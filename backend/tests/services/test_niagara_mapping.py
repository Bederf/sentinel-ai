"""Tests for Niagara point mapping service.

Tests cover:
- Point-to-equipment grouping
- Equipment model generation
- Mapping validation (orphans, duplicates, missing)
- Manual corrections
- Approval workflow
- Dual-write storage (JSON)
- Version history tracking
"""

import json
import pytest
from pathlib import Path

from app.services.niagara.point_classifier import (
    ClassifiedPoint,
    ConfidenceLevel,
    PointClassifier,
    PointType,
)
from app.services.niagara.mapping_service import (
    EquipmentMapping,
    MappingValidationResult,
    PointMappingService,
    get_mapping_service,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mapping_service():
    """Create a fresh PointMappingService."""
    return PointMappingService()


@pytest.fixture
def classifier():
    """Create a fresh PointClassifier."""
    return PointClassifier()


@pytest.fixture
def demo_classified_points(classifier):
    """Classify demo points for use in mapping tests."""
    tags_path = Path(__file__).parent.parent.parent / "app" / "data" / "niagara" / "haystack_tags.json"
    with open(tags_path) as f:
        data = json.load(f)

    demo_points = data.get("demo_points", [])
    return classifier.classify_points(demo_points)


@pytest.fixture
def sample_classified_points():
    """Create sample classified points for testing."""
    return [
        ClassifiedPoint(
            original_name="CH-1_CHW_Supply_Temp",
            equipment_type="chiller",
            equipment_id="CH-1",
            point_type=PointType.SENSOR,
            point_category="temperature",
            confidence=ConfidenceLevel.HIGH,
            object_type="analogInput",
            instance=1,
            present_value=6.5,
        ),
        ClassifiedPoint(
            original_name="CH-1_CHW_Return_Temp",
            equipment_type="chiller",
            equipment_id="CH-1",
            point_type=PointType.SENSOR,
            point_category="temperature",
            confidence=ConfidenceLevel.HIGH,
            object_type="analogInput",
            instance=2,
            present_value=12.3,
        ),
        ClassifiedPoint(
            original_name="CH-1_Compressor_Status",
            equipment_type="chiller",
            equipment_id="CH-1",
            point_type=PointType.STATUS,
            point_category="status",
            confidence=ConfidenceLevel.HIGH,
            object_type="binaryInput",
            instance=3,
            present_value=1,
        ),
        ClassifiedPoint(
            original_name="AHU-1_Supply_Air_Temp",
            equipment_type="ahu",
            equipment_id="AHU-1",
            point_type=PointType.SENSOR,
            point_category="temperature",
            confidence=ConfidenceLevel.HIGH,
            object_type="analogInput",
            instance=10,
            present_value=14.2,
        ),
        ClassifiedPoint(
            original_name="AHU-1_Fan_Speed",
            equipment_type="ahu",
            equipment_id="AHU-1",
            point_type=PointType.COMMAND,
            point_category="speed",
            confidence=ConfidenceLevel.MEDIUM,
            object_type="analogOutput",
            instance=11,
            present_value=78,
            writable=True,
        ),
        ClassifiedPoint(
            original_name="UNKNOWN_POINT_1",
            equipment_type="unknown",
            equipment_id="",
            point_type=PointType.UNKNOWN,
            point_category="unknown",
            confidence=ConfidenceLevel.UNKNOWN,
            object_type="analogInput",
            instance=99,
        ),
    ]


# ---------------------------------------------------------------------------
# Point-to-Equipment Mapping Tests
# ---------------------------------------------------------------------------


class TestPointMapping:
    """Tests for point-to-equipment grouping."""

    def test_group_points_by_equipment(self, mapping_service, sample_classified_points):
        """Test that points are grouped correctly by equipment ID."""
        mappings = mapping_service.map_points_to_equipment(sample_classified_points, "site-002")

        # Equipment IDs are now in v2.0 format (converted from BMS IDs)
        assert "S002-CHILLER-B1-001" in mappings
        assert "S002-AHU-B1-001" in mappings
        assert len(mappings["S002-CHILLER-B1-001"].points) == 3  # 3 chiller points
        assert len(mappings["S002-AHU-B1-001"].points) == 2  # 2 AHU points

    def test_orphan_points_grouped_as_unassigned(self, mapping_service, sample_classified_points):
        """Test that orphan points go to UNASSIGNED."""
        mappings = mapping_service.map_points_to_equipment(sample_classified_points, "site-002")

        assert "UNASSIGNED" in mappings
        assert len(mappings["UNASSIGNED"].points) == 1

    def test_equipment_type_majority_vote(self, mapping_service, sample_classified_points):
        """Test that equipment type is determined by majority."""
        mappings = mapping_service.map_points_to_equipment(sample_classified_points, "site-002")

        # Equipment IDs are now in v2.0 format
        assert mappings["S002-CHILLER-B1-001"].equipment_type == "chiller"
        assert mappings["S002-AHU-B1-001"].equipment_type == "ahu"

    def test_demo_points_grouping(self, mapping_service, demo_classified_points):
        """Test grouping with full demo point set."""
        mappings = mapping_service.map_points_to_equipment(demo_classified_points, "site-002")

        # Should have at least 5 equipment groups
        real_equipment = {k: v for k, v in mappings.items() if k != "UNASSIGNED"}
        assert len(real_equipment) >= 5

    def test_equipment_confidence_scoring(self, mapping_service, sample_classified_points):
        """Test group confidence is based on point confidences."""
        mappings = mapping_service.map_points_to_equipment(sample_classified_points, "site-002")

        # Equipment IDs are now in v2.0 format
        assert mappings["S002-CHILLER-B1-001"].confidence == "high"  # All high confidence points


# ---------------------------------------------------------------------------
# Equipment Model Generation Tests
# ---------------------------------------------------------------------------


class TestEquipmentModelGeneration:
    """Tests for generating device-compatible equipment models."""

    def test_generate_equipment_model(self, mapping_service, sample_classified_points):
        """Test equipment model generation."""
        mappings = mapping_service.map_points_to_equipment(sample_classified_points, "site-002")

        # Equipment IDs are now in v2.0 format
        model = mapping_service.generate_equipment_model(mappings["S002-CHILLER-B1-001"])

        assert model["equipment_type"] == "chiller"
        assert model["device_type"] == "hvac"
        assert model["site_id"] == "site-002"
        assert "points" in model
        assert len(model["points"]) > 0
        assert model["metadata"]["auto_generated"] is True

    def test_model_has_bacnet_references(self, mapping_service, sample_classified_points):
        """Test that equipment model includes BACnet references."""
        mappings = mapping_service.map_points_to_equipment(sample_classified_points, "site-002")

        # Equipment IDs are now in v2.0 format
        model = mapping_service.generate_equipment_model(mappings["S002-CHILLER-B1-001"])
        points = model["points"]

        # At least one point should have a bacnet_ref
        has_bacnet = any(p.get("bacnet_ref") for p in points.values())
        assert has_bacnet

    def test_model_device_type_mapping(self, mapping_service):
        """Test device type mapping for different equipment types."""
        for eq_type, expected_device in [
            ("chiller", "hvac"),
            ("ahu", "hvac"),
            ("generator", "power"),
            ("dali_controller", "lighting"),
            ("meter", "power"),
        ]:
            mapping = EquipmentMapping(
                equipment_id=f"TEST-{eq_type}",
                equipment_type=eq_type,
                site_id="site-002",
                points=[{"original_name": "test", "point_type": "sensor"}],
            )
            model = mapping_service.generate_equipment_model(mapping)
            assert model["device_type"] == expected_device, f"Wrong device type for {eq_type}"


# ---------------------------------------------------------------------------
# Validation Tests
# ---------------------------------------------------------------------------


class TestMappingValidation:
    """Tests for mapping validation."""

    def test_detect_orphan_points(self, mapping_service, sample_classified_points):
        """Test that orphan points are detected."""
        mappings = mapping_service.map_points_to_equipment(sample_classified_points, "site-002")

        result = mapping_service.validate_mappings(mappings)

        assert len(result.orphan_points) == 1  # One unknown point
        assert "UNKNOWN_POINT_1" in result.orphan_points

    def test_detect_duplicate_points(self, mapping_service):
        """Test that duplicate points are detected."""
        # Create mappings with duplicate point
        mappings = {
            "CH-1": EquipmentMapping(
                equipment_id="CH-1",
                equipment_type="chiller",
                site_id="site-002",
                points=[{"original_name": "SHARED_POINT", "confidence": "high"}],
            ),
            "AHU-1": EquipmentMapping(
                equipment_id="AHU-1",
                equipment_type="ahu",
                site_id="site-002",
                points=[{"original_name": "SHARED_POINT", "confidence": "high"}],
            ),
        }

        result = mapping_service.validate_mappings(mappings)
        assert len(result.duplicate_points) > 0

    def test_detect_low_confidence(self, mapping_service, sample_classified_points):
        """Test that low confidence points are flagged."""
        mappings = mapping_service.map_points_to_equipment(sample_classified_points, "site-002")

        result = mapping_service.validate_mappings(mappings)
        # The UNASSIGNED point should be flagged
        assert len(result.low_confidence_points) >= 1

    def test_validation_result_serialization(self):
        """Test MappingValidationResult serialization."""
        result = MappingValidationResult()
        result.orphan_points = ["point1"]
        result.warnings = ["test warning"]

        data = result.to_dict()
        assert data["valid"] is True
        assert len(data["orphan_points"]) == 1
        assert len(data["warnings"]) == 1


# ---------------------------------------------------------------------------
# Storage and Correction Tests
# ---------------------------------------------------------------------------


class TestMappingStorage:
    """Tests for mapping storage and corrections."""

    def test_save_and_load_mappings(self, mapping_service, sample_classified_points, tmp_path):
        """Test saving and loading mappings from JSON."""
        mappings = mapping_service.map_points_to_equipment(sample_classified_points, "site-002")

        save_result = mapping_service.save_mappings("test-001", mappings, "site-002")

        assert save_result["success"] is True
        assert save_result["equipment_count"] > 0

    def test_mapping_caching(self, mapping_service, sample_classified_points):
        """Test that mappings are cached in memory."""
        mappings = mapping_service.map_points_to_equipment(sample_classified_points, "site-002")

        mapping_service.save_mappings("test-002", mappings, "site-002")

        cached = mapping_service.get_mappings("test-002")
        assert cached is not None
        # Equipment IDs are now in v2.0 format
        assert "S002-CHILLER-B1-001" in cached

    def test_correct_point_type(self, mapping_service, sample_classified_points):
        """Test manual correction of point type."""
        mappings = mapping_service.map_points_to_equipment(sample_classified_points, "site-002")
        mapping_service.save_mappings("test-003", mappings, "site-002")

        result = mapping_service.correct_point(
            "test-003",
            "CH-1_CHW_Supply_Temp",
            new_point_type="setpoint",
        )

        assert result["success"] is True
        assert "point_type -> setpoint" in result["corrections"]

    def test_correct_move_point_to_different_equipment(self, mapping_service, sample_classified_points):
        """Test moving a point to different equipment."""
        mappings = mapping_service.map_points_to_equipment(sample_classified_points, "site-002")
        mapping_service.save_mappings("test-004", mappings, "site-002")

        result = mapping_service.correct_point(
            "test-004",
            "AHU-1_Fan_Speed",
            new_equipment_id="AHU-2",
        )

        assert result["success"] is True

        # Verify point moved
        updated = mapping_service.get_mappings("test-004")
        assert "AHU-2" in updated

    def test_mapping_history_tracked(self, mapping_service, sample_classified_points):
        """Test that mapping changes are tracked in history."""
        mappings = mapping_service.map_points_to_equipment(sample_classified_points, "site-002")
        mapping_service.save_mappings("test-005", mappings, "site-002")

        history = mapping_service.get_mapping_history("test-005")
        assert len(history) >= 1
        assert history[0]["action"] == "save"

    def test_approve_mappings(self, mapping_service, sample_classified_points):
        """Test approval workflow."""
        mappings = mapping_service.map_points_to_equipment(sample_classified_points, "site-002")
        mapping_service.save_mappings("test-006", mappings, "site-002")

        result = mapping_service.approve_mappings("test-006", approved_by="admin")

        assert result["success"] is True
        assert result["equipment_created"] > 0
        assert len(result["equipment_models"]) > 0

        # Verify approval status
        updated = mapping_service.get_mappings("test-006")
        for eid, mapping in updated.items():
            if eid != "UNASSIGNED":
                assert mapping.approved is True

    def test_equipment_mapping_serialization(self):
        """Test EquipmentMapping serialization."""
        mapping = EquipmentMapping(
            equipment_id="CH-1",
            equipment_type="chiller",
            equipment_name="Chiller 1",
            site_id="site-002",
            points=[{"name": "temp", "value": 6.5}],
            confidence="high",
        )

        data = mapping.to_dict()
        assert data["equipment_id"] == "CH-1"
        assert data["point_count"] == 1
        assert data["approved"] is False


# ---------------------------------------------------------------------------
# Singleton Tests
# ---------------------------------------------------------------------------


class TestMappingSingleton:
    """Test singleton factory."""

    def test_get_mapping_service_singleton(self):
        """Verify singleton pattern."""
        import app.services.niagara.mapping_service as mod

        old = mod._mapping_service
        mod._mapping_service = None
        try:
            s1 = get_mapping_service()
            s2 = get_mapping_service()
            assert s1 is s2
        finally:
            mod._mapping_service = old

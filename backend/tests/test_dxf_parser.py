"""Unit tests for DXF parser service.

Tests coordinate transformations, geometry utilities, and DXF parsing logic.
"""

import pytest

from app.services.geometry_utils import (
    BoundingBox,
    normalize_coordinates,
    infer_floor_from_z_coordinate,
    euclidean_distance,
    cluster_points,
    get_cluster_centroid,
)
from app.services.dxf_parser_service import get_dxf_parser_service


class TestGeometryUtils:
    """Test coordinate transformations and geometric calculations."""

    def test_bounding_box_properties(self):
        """Test BoundingBox property calculations."""
        bbox = BoundingBox(0, 0, 100, 80)
        assert bbox.width == 100
        assert bbox.height == 80
        assert bbox.center == (50, 40)
        assert bbox.area == 8000

    def test_normalize_coordinates_center(self):
        """Test coordinate normalization at center."""
        bbox = BoundingBox(0, 0, 1000, 800)  # DXF in millimeters
        x_norm, y_norm = normalize_coordinates(
            500, 400, bbox, target_width=100, target_depth=80
        )
        assert x_norm == pytest.approx(50, abs=1)  # Center
        assert y_norm == pytest.approx(40, abs=1)

    def test_normalize_coordinates_corner(self):
        """Test coordinate normalization at corners."""
        bbox = BoundingBox(0, 0, 1000, 800)
        x_norm, y_norm = normalize_coordinates(0, 0, bbox, 100, 80)
        assert x_norm == pytest.approx(0, abs=1)
        assert y_norm == pytest.approx(0, abs=1)

    def test_normalize_coordinates_top_right(self):
        """Test coordinate normalization at top-right corner."""
        bbox = BoundingBox(0, 0, 1000, 800)
        x_norm, y_norm = normalize_coordinates(1000, 800, bbox, 100, 80)
        assert x_norm == pytest.approx(100, abs=1)
        assert y_norm == pytest.approx(80, abs=1)

    def test_infer_floor_basement_single(self):
        """Test floor inference for basement."""
        assert infer_floor_from_z_coordinate(-3.5) == "B1"

    def test_infer_floor_basement_double(self):
        """Test floor inference for second basement."""
        assert infer_floor_from_z_coordinate(-7.0) == "B2"

    def test_infer_floor_ground(self):
        """Test floor inference for ground floor."""
        assert infer_floor_from_z_coordinate(0) == "G"
        assert infer_floor_from_z_coordinate(0.5) == "G"

    def test_infer_floor_levels(self):
        """Test floor inference for office levels."""
        assert infer_floor_from_z_coordinate(3.5) == "L1"
        assert infer_floor_from_z_coordinate(7.0) == "L2"
        assert infer_floor_from_z_coordinate(10.5) == "L3"

    def test_euclidean_distance_simple(self):
        """Test Euclidean distance calculation."""
        d = euclidean_distance((0, 0), (3, 4))
        assert d == pytest.approx(5.0)

    def test_euclidean_distance_identical(self):
        """Test distance between identical points."""
        d = euclidean_distance((5, 5), (5, 5))
        assert d == pytest.approx(0.0)

    def test_cluster_points_single_cluster(self):
        """Test clustering nearby points."""
        points = [(0, 0), (1, 1), (2, 2)]
        clusters = cluster_points(points, distance_threshold=5.0)
        assert len(clusters) == 1

    def test_cluster_points_multiple_clusters(self):
        """Test clustering distant points."""
        points = [(0, 0), (1, 1), (50, 50), (51, 51)]
        clusters = cluster_points(points, distance_threshold=3.0)
        assert len(clusters) == 2

    def test_get_cluster_centroid(self):
        """Test centroid calculation."""
        points = [(0, 0), (10, 0), (10, 10), (0, 10)]
        centroid = get_cluster_centroid(points)
        assert centroid == pytest.approx((5, 5))

    def test_get_cluster_centroid_single_point(self):
        """Test centroid of single point."""
        points = [(5, 5)]
        centroid = get_cluster_centroid(points)
        assert centroid == pytest.approx((5, 5))


class TestDXFParser:
    """Test DXF file parsing."""

    @pytest.fixture
    def parser(self):
        """Get DXF parser instance."""
        return get_dxf_parser_service()

    def test_classify_equipment_type_chiller(self, parser):
        """Test equipment type classification - Chiller."""
        assert parser._classify_equipment_type("CH-1") == "CHILLER"
        assert parser._classify_equipment_type("CHILLER-1") == "CHILLER"

    def test_classify_equipment_type_hvac(self, parser):
        """Test equipment type classification - HVAC."""
        assert parser._classify_equipment_type("AHU-L1-01") == "AHU"
        assert parser._classify_equipment_type("FCU-L2-A") == "FCU"
        assert parser._classify_equipment_type("VAV-L1-01") == "VAV"

    def test_classify_equipment_type_electrical(self, parser):
        """Test equipment type classification - Electrical."""
        assert parser._classify_equipment_type("GEN-1") == "GEN"
        assert parser._classify_equipment_type("TX-001") == "TX"
        assert parser._classify_equipment_type("UPS-1") == "UPS"
        assert parser._classify_equipment_type("MSB-01") == "MSB"

    def test_classify_equipment_type_unknown(self, parser):
        """Test equipment type classification - Unknown."""
        assert parser._classify_equipment_type("UNKNOWN-XYZ") == "UNKNOWN"

    def test_infer_floor_from_name(self, parser):
        """Test floor inference from equipment name."""
        assert parser._infer_floor(0, "FCU-L2-A") == "L2"
        assert parser._infer_floor(0, "AHU-B1-01") == "B1"
        assert parser._infer_floor(0, "GEN-G-001") == "G"

    def test_infer_floor_from_z_coordinate(self, parser):
        """Test floor inference from Z-coordinate."""
        assert parser._infer_floor(3.5, "EQUIPMENT-001") == "L1"
        assert parser._infer_floor(0, "EQUIPMENT-001") == "G"

    def test_infer_zone_from_name(self, parser):
        """Test zone inference from equipment name."""
        assert parser._infer_zone("FCU-L2-A", 50, 40, "L2") == "A"
        assert parser._infer_zone("FCU-L2-B", 50, 40, "L2") == "B"

    def test_infer_zone_from_position(self, parser):
        """Test zone inference from position."""
        assert parser._infer_zone("EQ-001", 15, 40, "L1") == "A"
        assert parser._infer_zone("EQ-001", 45, 40, "L1") == "B"
        assert parser._infer_zone("EQ-001", 75, 40, "L1") == "C"

    def test_build_v2_equipment_id_chiller(self, parser):
        """Test v2.0 equipment ID generation."""
        eq_id = parser._build_v2_equipment_id("site-002", "CHILLER", "B1", "001")
        assert eq_id == "S002-CHILLER-B1-001"

    def test_build_v2_equipment_id_fcu(self, parser):
        """Test v2.0 equipment ID for FCU."""
        eq_id = parser._build_v2_equipment_id("site-002", "FCU", "L2", "A")
        assert eq_id == "S002-FCU-L2-A"

    def test_build_v2_equipment_id_site_extraction(self, parser):
        """Test site code extraction from building code."""
        eq_id = parser._build_v2_equipment_id("sandton-city-005", "AHU", "G", "001")
        # Should extract 005 and pad to S005
        assert eq_id.startswith("S005-AHU-G-001")

    def test_infer_floor_definitions_empty(self, parser):
        """Test floor definition inference with empty equipment."""
        floors = parser._infer_floor_definitions([])
        assert floors == []

    def test_infer_floor_definitions_single_floor(self, parser):
        """Test floor definition inference with single floor."""
        equipment = [
            {
                "name": "EQ1",
                "floor": "G",
                "x": 50,
                "y": 40,
                "equipment_type": "ahu",
            },
            {
                "name": "EQ2",
                "floor": "G",
                "x": 60,
                "y": 50,
                "equipment_type": "fcu",
            },
        ]
        floors = parser._infer_floor_definitions(equipment)
        assert len(floors) == 1
        assert floors[0]["level"] == "G"
        assert floors[0]["height"] == 3.5

    def test_infer_floor_definitions_multiple_floors(self, parser):
        """Test floor definition inference with multiple floors."""
        equipment = [
            {"name": "EQ1", "floor": "B1", "x": 50, "y": 40, "equipment_type": "ahu"},
            {"name": "EQ2", "floor": "G", "x": 50, "y": 40, "equipment_type": "ahu"},
            {"name": "EQ3", "floor": "L1", "x": 50, "y": 40, "equipment_type": "fcu"},
            {"name": "EQ4", "floor": "L2", "x": 50, "y": 40, "equipment_type": "fcu"},
        ]
        floors = parser._infer_floor_definitions(equipment)
        assert len(floors) == 4
        assert [f["level"] for f in floors] == ["B1", "G", "L1", "L2"]

    def test_create_zones_from_equipment(self, parser):
        """Test zone creation from equipment."""
        equipment = [
            {
                "name": "S002-FCU-L1-A",
                "equipment_type": "fcu",
                "floor": "L1",
                "zone": "A",
            },
            {
                "name": "S002-FCU-L1-B",
                "equipment_type": "fcu",
                "floor": "L1",
                "zone": "B",
            },
            {
                "name": "S002-AHU-G-001",
                "equipment_type": "ahu",
                "floor": "G",
                "zone": "001",
            },
        ]
        zones = parser._create_zones_from_equipment(equipment)
        assert len(zones) >= 2
        # Check for presence of mechanical zone
        mechanical_zones = [z for z in zones if z["zone_type"] == "mechanical"]
        assert len(mechanical_zones) >= 1


class TestDXFParserIntegration:
    """Integration tests for DXF parsing (requires ezdxf)."""

    @pytest.fixture
    def sample_dxf_bytes(self):
        """Generate minimal valid DXF for testing."""
        import ezdxf
        import tempfile

        doc = ezdxf.new("R2010")
        msp = doc.modelspace()

        # Add layers
        doc.layers.new("AR-WALL")
        doc.layers.new("AE-HVAC")

        # Add walls
        msp.add_line((0, 0), (100, 0), dxfattribs={"layer": "AR-WALL"})
        msp.add_line((100, 0), (100, 80), dxfattribs={"layer": "AR-WALL"})
        msp.add_line((100, 80), (0, 80), dxfattribs={"layer": "AR-WALL"})
        msp.add_line((0, 80), (0, 0), dxfattribs={"layer": "AR-WALL"})

        # Add HVAC equipment
        msp.add_circle((50, 40, 0), radius=2, dxfattribs={"layer": "AE-HVAC"})
        msp.add_text(
            "CH-1", dxfattribs={"layer": "AE-HVAC", "insert": (50, 40, 0)}
        )

        # Save to temp file then read as bytes
        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
            temp_path = f.name

        doc.saveas(temp_path)

        with open(temp_path, "rb") as f:
            dxf_bytes = f.read()

        import os
        os.remove(temp_path)

        return dxf_bytes

    @pytest.mark.asyncio
    async def test_parse_dxf_returns_valid_config(self, sample_dxf_bytes):
        """Test DXF parsing returns valid config structure."""
        parser = get_dxf_parser_service()
        config = await parser.parse_dxf_file(
            sample_dxf_bytes, "site-002", "Test Building"
        )

        assert config is not None
        assert "equipment" in config
        assert "floors" in config
        assert "zones" in config
        assert config["building_code"] == "site-002"
        assert config["building_name"] == "Test Building"

    @pytest.mark.asyncio
    async def test_parse_dxf_extracts_equipment(self, sample_dxf_bytes):
        """Test DXF parsing extracts equipment."""
        parser = get_dxf_parser_service()
        config = await parser.parse_dxf_file(
            sample_dxf_bytes, "site-002", "Test Building"
        )

        equipment = config["equipment"]
        assert len(equipment) > 0

        # Check equipment structure
        first_eq = equipment[0]
        assert "name" in first_eq
        assert "equipment_type" in first_eq
        assert "floor" in first_eq
        assert "x" in first_eq
        assert "y" in first_eq
        assert "zone" in first_eq
        assert "confidence" in first_eq

    @pytest.mark.asyncio
    async def test_parse_dxf_invalid_file(self):
        """Test DXF parsing with invalid file."""
        parser = get_dxf_parser_service()

        with pytest.raises(ValueError):
            await parser.parse_dxf_file(b"invalid dxf content", "site-002", "Test")

    def test_parse_dxf_file_loading(self):
        """Test DXF file loading."""
        import ezdxf
        import tempfile

        doc = ezdxf.new("R2010")
        msp = doc.modelspace()
        msp.add_line((0, 0), (100, 80))

        # Save to temp file then read as bytes
        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
            temp_path = f.name

        doc.saveas(temp_path)

        with open(temp_path, "rb") as f:
            dxf_bytes = f.read()

        import os
        os.remove(temp_path)

        parser = get_dxf_parser_service()
        loaded_doc = parser._load_dxf(dxf_bytes)
        assert loaded_doc is not None
        assert loaded_doc.dxfversion.startswith("AC")

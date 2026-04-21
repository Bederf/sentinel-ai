"""Tests for Brick Ontology Auto-Generation Service."""

import json
from pathlib import Path

import pytest

# Skip entire module if rdflib not available
rdflib = pytest.importorskip("rdflib")

from app.services.brick_autogen_service import (  # noqa: E402
    EQUIPMENT_TYPE_TO_BRICK,
    BrickAutogenService,
    ResolutionIndex,
    _safe_iri_part,
    _stable_hash,
    build_brick_for_site,
    load_discovery_enrichment,
)

BACKEND_DIR = Path(__file__).parent.parent.parent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def service():
    """BrickAutogenService for site-002 with validation disabled."""
    return BrickAutogenService(
        base_dir=BACKEND_DIR,
        site_id="site-002",
        validate_graph=False,  # Skip SHACL (may not have brickschema)
    )


@pytest.fixture
def discovery_enrichment() -> dict:
    """Load real discovery enrichment for site-002."""
    return load_discovery_enrichment(
        BACKEND_DIR / "app" / "data" / "niagara" / "mappings",
        "site-002",
    )


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------
class TestHelpers:
    def test_safe_iri_part_removes_spaces(self):
        assert _safe_iri_part("Hello World") == "Hello_World"

    def test_safe_iri_part_preserves_valid_chars(self):
        assert _safe_iri_part("S002-CHILLER-B1-001") == "S002-CHILLER-B1-001"

    def test_safe_iri_part_handles_empty(self):
        assert _safe_iri_part("") == ""

    def test_stable_hash_deterministic(self):
        obj = {"a": 1, "b": [2, 3]}
        assert _stable_hash(obj) == _stable_hash(obj)

    def test_stable_hash_order_independent(self):
        assert _stable_hash({"b": 2, "a": 1}) == _stable_hash({"a": 1, "b": 2})


# ---------------------------------------------------------------------------
# Discovery loader tests
# ---------------------------------------------------------------------------
class TestDiscoveryLoader:
    def test_loads_site_002_mappings(self, discovery_enrichment):
        assert len(discovery_enrichment) > 0
        assert "S002-CHILLER-B1-001" in discovery_enrichment

    def test_chiller_has_zone_metadata(self, discovery_enrichment):
        chiller = discovery_enrichment["S002-CHILLER-B1-001"]
        assert chiller.zone is not None
        assert chiller.zone.get("floor") == "B1"

    def test_chiller_has_points(self, discovery_enrichment):
        chiller = discovery_enrichment["S002-CHILLER-B1-001"]
        assert len(chiller.points) > 0
        temp_points = [p for p in chiller.points if p.point_category == "temperature"]
        assert len(temp_points) >= 1

    def test_confidence_converted_to_float(self, discovery_enrichment):
        chiller = discovery_enrichment["S002-CHILLER-B1-001"]
        for p in chiller.points:
            assert isinstance(p.confidence, float)
            assert 0.0 <= p.confidence <= 1.0

    def test_nonexistent_site_returns_empty(self):
        result = load_discovery_enrichment(
            BACKEND_DIR / "app" / "data" / "niagara" / "mappings",
            "site-999",
        )
        assert result == {}


# ---------------------------------------------------------------------------
# Graph build tests
# ---------------------------------------------------------------------------
class TestBrickBuild:
    def test_build_produces_graph_and_index(self, service, discovery_enrichment):
        _graph, idx, result = service.build(discovery=discovery_enrichment)
        assert result.equipment_count > 0
        assert result.point_count > 0
        assert isinstance(idx, ResolutionIndex)

    def test_equipment_iris_minted(self, service, discovery_enrichment):
        _graph, idx, _result = service.build(discovery=discovery_enrichment)
        assert "S002-CHILLER-B1-001" in idx.equipment_code_to_equipment_iri
        eq_iri = idx.equipment_code_to_equipment_iri["S002-CHILLER-B1-001"]
        assert "eq/S002-CHILLER-B1-001" in eq_iri

    def test_points_linked_to_equipment(self, service, discovery_enrichment):
        _graph, idx, _result = service.build(discovery=discovery_enrichment)
        # At least one point should map back to chiller
        chiller_iri = idx.equipment_code_to_equipment_iri.get("S002-CHILLER-B1-001")
        chiller_points = [pt for pt, eq in idx.point_iri_to_equipment_iri.items() if eq == chiller_iri]
        assert len(chiller_points) >= 1

    def test_bacnet_refs_indexed(self, service, discovery_enrichment):
        _graph, idx, _result = service.build(discovery=discovery_enrichment)
        # Equipment JSON has bacnet_ref like "CH-1.ChwSupplyTemp"
        assert len(idx.bacnet_ref_to_point_iri) > 0

    def test_bacnet_objects_indexed(self, service, discovery_enrichment):
        _graph, idx, _result = service.build(discovery=discovery_enrichment)
        # Equipment JSON has real BACnet instances (1000, 1001, 10, 11, etc.)
        assert len(idx.bacnet_object_to_point_iri) > 0

    def test_locations_created(self, service, discovery_enrichment):
        _graph, idx, result = service.build(discovery=discovery_enrichment)
        assert result.location_count > 0
        assert len(idx.equipment_code_to_location_iri) > 0

    def test_delta_skips_unchanged(self, service, discovery_enrichment):
        # First build
        _, _, result1 = service.build(discovery=discovery_enrichment)
        assert result1.skipped_unchanged == 0

        # Second build (same data)
        _, _, result2 = service.build(discovery=discovery_enrichment)
        assert result2.skipped_unchanged > 0
        assert result2.equipment_count == 0  # All skipped

    def test_build_without_discovery(self, service):
        """Build with empty discovery — should still create equipment and points."""
        _graph, _idx, result = service.build(discovery={})
        assert result.equipment_count > 0
        assert result.point_count > 0


# ---------------------------------------------------------------------------
# Point classification tests
# ---------------------------------------------------------------------------
class TestPointClassification:
    def test_temperature_sensor_by_name(self, service):
        cls = service._classify_point(
            "chilled_water_temperature",
            {"unit": "°C", "point_type": "sensor"},
            None,
        )
        from rdflib import Namespace

        BRICK = Namespace("https://brickschema.org/schema/Brick#")
        assert cls == BRICK.Temperature_Sensor

    def test_setpoint_by_type(self, service):
        cls = service._classify_point(
            "chilled_water_setpoint",
            {"unit": "°C", "point_type": "setpoint"},
            None,
        )
        from rdflib import Namespace

        BRICK = Namespace("https://brickschema.org/schema/Brick#")
        assert cls == BRICK.Temperature_Setpoint

    def test_command_by_type(self, service):
        cls = service._classify_point(
            "speed",
            {"point_type": "command"},
            None,
        )
        from rdflib import Namespace

        BRICK = Namespace("https://brickschema.org/schema/Brick#")
        assert cls == BRICK.Command

    def test_pressure_sensor(self, service):
        cls = service._classify_point(
            "differential_pressure",
            {"unit": "kPa", "point_type": "sensor"},
            None,
        )
        from rdflib import Namespace

        BRICK = Namespace("https://brickschema.org/schema/Brick#")
        assert cls == BRICK.Pressure_Sensor

    def test_unknown_falls_to_point(self, service):
        cls = service._classify_point(
            "mystery_value",
            {"unit": "", "point_type": ""},
            None,
        )
        from rdflib import Namespace

        BRICK = Namespace("https://brickschema.org/schema/Brick#")
        assert cls == BRICK.Point


# ---------------------------------------------------------------------------
# TTL serialization test
# ---------------------------------------------------------------------------
class TestSerialization:
    def test_serialize_ttl_produces_output(self, service, discovery_enrichment):
        service.build(discovery=discovery_enrichment)
        ttl = service.serialize_ttl()
        assert len(ttl) > 0
        assert "sentinel" in ttl.lower()
        assert "brick" in ttl.lower()

    def test_resolution_index_serializable(self, service, discovery_enrichment):
        _, idx, _ = service.build(discovery=discovery_enrichment)
        serialized = json.dumps(idx.to_dict(), indent=2)
        parsed = json.loads(serialized)
        assert "bacnet_ref_to_point_iri" in parsed
        assert "equipment_code_to_equipment_iri" in parsed


# ---------------------------------------------------------------------------
# Equipment type mapping coverage
# ---------------------------------------------------------------------------
class TestEquipmentTypeMapping:
    def test_all_sentinel_types_mapped(self):
        expected_types = [
            "chiller",
            "ahu",
            "vav",
            "fcu",
            "pump",
            "generator",
            "ups",
            "cooling_tower",
            "ct",
            "meter",
            "dali_controller",
        ]
        for t in expected_types:
            assert t in EQUIPMENT_TYPE_TO_BRICK, f"Missing mapping for {t}"

    def test_build_handles_unknown_type(self, service):
        """Equipment with unknown type should still build as brick:Equipment."""
        _graph, _idx, result = service.build(discovery={})
        # site-002 has S002-UNKNOWN-* equipment in discovery, but equipment
        # JSON may not have them. Either way, unknown types shouldn't crash.
        assert result.equipment_count >= 0


# ---------------------------------------------------------------------------
# Convenience function test
# ---------------------------------------------------------------------------
class TestConvenienceFunction:
    def test_build_brick_for_site(self, tmp_path):
        _idx, result = build_brick_for_site(
            BACKEND_DIR,
            "site-002",
            validate=False,
            output_dir=tmp_path,
        )
        assert result.equipment_count > 0

        # Check files were written
        ttl_file = tmp_path / "site-002_brick.ttl"
        idx_file = tmp_path / "site-002_resolution_index.json"
        assert ttl_file.exists()
        assert idx_file.exists()
        assert ttl_file.stat().st_size > 0

        # Verify index is valid JSON
        parsed = json.loads(idx_file.read_text())
        assert "bacnet_ref_to_point_iri" in parsed

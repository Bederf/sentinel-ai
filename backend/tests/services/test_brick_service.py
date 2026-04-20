"""Tests for Brick Ontology Runtime Service."""

import json
from pathlib import Path

import pytest

rdflib = pytest.importorskip("rdflib")

from app.services.brick_service import (  # noqa: E402
    BrickEquipmentContext,
    BrickPointRef,
    BrickService,
    get_brick_service,
)

BACKEND_DIR = Path(__file__).parent.parent.parent
BRICK_DIR = BACKEND_DIR / "app" / "data" / "buildings" / "site-002" / "brick"
TTL_PATH = BRICK_DIR / "site-002_brick.ttl"
IDX_PATH = BRICK_DIR / "site-002_resolution_index.json"


@pytest.fixture(scope="module")
def brick_svc():
    """Load BrickService from generated site-002 artifacts."""
    if not TTL_PATH.exists() or not IDX_PATH.exists():
        pytest.skip("Brick artifacts not generated for site-002")
    return BrickService(brick_ttl_path=TTL_PATH, resolution_index_path=IDX_PATH)


@pytest.fixture(scope="module")
def resolution_index():
    """Load raw resolution index for reference."""
    if not IDX_PATH.exists():
        pytest.skip("Resolution index not generated")
    return json.loads(IDX_PATH.read_text())


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------
class TestInit:
    def test_loads_graph(self, brick_svc):
        assert len(brick_svc.g) > 0

    def test_loads_bacnet_ref_index(self, brick_svc):
        assert len(brick_svc.bacnet_ref_to_point) > 0

    def test_loads_equipment_code_index(self, brick_svc):
        assert len(brick_svc.equipment_code_to_iri) > 0

    def test_chiller_in_index(self, brick_svc):
        assert "S002-CHILLER-B1-001" in brick_svc.equipment_code_to_iri


# ---------------------------------------------------------------------------
# list_equipment
# ---------------------------------------------------------------------------
class TestListEquipment:
    def test_returns_sorted_list(self, brick_svc):
        equipment = brick_svc.list_equipment()
        assert len(equipment) >= 10
        assert equipment == sorted(equipment)

    def test_contains_known_equipment(self, brick_svc):
        equipment = brick_svc.list_equipment()
        assert "S002-CHILLER-B1-001" in equipment


# ---------------------------------------------------------------------------
# get_context
# ---------------------------------------------------------------------------
class TestGetContext:
    def test_returns_context_for_known_equipment(self, brick_svc):
        ctx = brick_svc.get_context("S002-CHILLER-B1-001")
        assert ctx is not None
        assert isinstance(ctx, BrickEquipmentContext)
        assert ctx.equipment_id == "S002-CHILLER-B1-001"

    def test_returns_none_for_unknown_equipment(self, brick_svc):
        ctx = brick_svc.get_context("NONEXISTENT-EQUIP-999")
        assert ctx is None

    def test_context_has_equipment_type(self, brick_svc):
        ctx = brick_svc.get_context("S002-CHILLER-B1-001")
        assert ctx.equipment_type is not None
        assert "Chiller" in ctx.equipment_type

    def test_context_has_points(self, brick_svc):
        ctx = brick_svc.get_context("S002-CHILLER-B1-001", include_points=True)
        assert len(ctx.points) > 0
        assert all(isinstance(p, BrickPointRef) for p in ctx.points)

    def test_context_without_points(self, brick_svc):
        ctx = brick_svc.get_context("S002-CHILLER-B1-001", include_points=False)
        assert len(ctx.points) == 0

    def test_context_has_location_path(self, brick_svc):
        ctx = brick_svc.get_context("S002-CHILLER-B1-001")
        assert len(ctx.location_path) > 0
        # Should have at least site level
        labels = [lbl for _, lbl in ctx.location_path]
        assert any("site" in lbl.lower() or "002" in lbl for lbl in labels)

    def test_context_to_dict(self, brick_svc):
        ctx = brick_svc.get_context("S002-CHILLER-B1-001")
        d = ctx.to_dict()
        assert d["equipment_id"] == "S002-CHILLER-B1-001"
        assert "points" in d
        assert "location_path" in d

    def test_points_have_bacnet_refs(self, brick_svc):
        ctx = brick_svc.get_context("S002-CHILLER-B1-001")
        refs = [p for p in ctx.points if p.bacnet_ref]
        assert len(refs) > 0

    def test_points_have_brick_class(self, brick_svc):
        ctx = brick_svc.get_context("S002-CHILLER-B1-001")
        classified = [p for p in ctx.points if p.brick_class]
        assert len(classified) > 0


# ---------------------------------------------------------------------------
# resolve_point
# ---------------------------------------------------------------------------
class TestResolvePoint:
    def test_resolve_by_bacnet_ref(self, brick_svc):
        # Pick the first bacnet_ref from the index
        if not brick_svc.bacnet_ref_to_point:
            pytest.skip("No BACnet refs in index")
        ref = next(iter(brick_svc.bacnet_ref_to_point))
        result = brick_svc.resolve_point(bacnet_ref=ref)
        assert result is not None
        point_iri, equipment_iri = result
        assert point_iri
        assert equipment_iri

    def test_resolve_by_bacnet_object(self, brick_svc):
        if not brick_svc.bacnet_object_to_point:
            pytest.skip("No BACnet objects in index")
        key = next(iter(brick_svc.bacnet_object_to_point))
        parts = key.split(",")
        obj_type = parts[0]
        instance = int(parts[1])
        result = brick_svc.resolve_point(object_type=obj_type, instance=instance)
        assert result is not None

    def test_resolve_unknown_ref_returns_none(self, brick_svc):
        result = brick_svc.resolve_point(bacnet_ref="NONEXISTENT.Point.999")
        assert result is None

    def test_resolve_no_args_returns_none(self, brick_svc):
        result = brick_svc.resolve_point()
        assert result is None


# ---------------------------------------------------------------------------
# resolve_equipment_id
# ---------------------------------------------------------------------------
class TestResolveEquipmentId:
    def test_resolve_to_equipment_code(self, brick_svc):
        if not brick_svc.bacnet_ref_to_point:
            pytest.skip("No BACnet refs in index")
        ref = next(iter(brick_svc.bacnet_ref_to_point))
        eq_id = brick_svc.resolve_equipment_id(bacnet_ref=ref)
        assert eq_id is not None
        assert eq_id.startswith("S002-")

    def test_resolve_unknown_returns_none(self, brick_svc):
        eq_id = brick_svc.resolve_equipment_id(bacnet_ref="FAKE.Point.999")
        assert eq_id is None


# ---------------------------------------------------------------------------
# Singleton loader
# ---------------------------------------------------------------------------
class TestSingleton:
    def test_get_brick_service_returns_instance(self):
        import app.services.brick_service as mod

        mod._instance = None  # Reset singleton
        svc = get_brick_service("site-002", base_dir=BACKEND_DIR)
        if TTL_PATH.exists():
            assert svc is not None
        else:
            assert svc is None

    def test_get_brick_service_nonexistent_site(self):
        import app.services.brick_service as mod

        mod._instance = None
        svc = get_brick_service("site-999", base_dir=BACKEND_DIR)
        assert svc is None

    def test_get_brick_service_caches(self):
        import app.services.brick_service as mod

        mod._instance = None
        svc1 = get_brick_service("site-002", base_dir=BACKEND_DIR)
        svc2 = get_brick_service("site-002", base_dir=BACKEND_DIR)
        assert svc1 is svc2
        mod._instance = None  # Clean up

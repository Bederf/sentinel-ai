import pytest

from app.services.onboarding_hierarchy_service import (
    OnboardingHierarchyService,
    ResolvedNode,
    _equipment_code_aliases,
    _equipment_type_from_code,
    _is_sentinel_equipment_code,
    _preferred_canonical_code,
    _score_relationship,
    _zone_key_from_equipment_code,
)


def test_desigo_served_zone_relationship_is_approved_high_confidence():
    service = OnboardingHierarchyService(client=object())
    equipment_lookup = {
        "S002-AHU-R-001": {"id": "eq-ahu-roof", "canonical_code": "S002-AHU-R-001"},
    }
    zone_ids = {"Zone-201"}
    resolved_nodes = {
        "Plant/HVAC/AHU-R-001": ResolvedNode(
            source_id="Plant/HVAC/AHU-R-001",
            node_type="equipment",
            canonical_code="S002-AHU-R-001",
        ),
        "Location/L2/North": ResolvedNode(
            source_id="Location/L2/North",
            node_type="zone",
            zone_id="Zone-201",
        ),
    }

    plan = service._plan_relationship(
        {
            "parent": "Plant/HVAC/AHU-R-001",
            "child": "Location/L2/North",
            "relationship_type": "serves",
            "evidence_basis": "Desigo Plant > HVAC > AHU-R-001",
        },
        source="desigo_plant_tree",
        resolved_nodes=resolved_nodes,
        equipment_lookup=equipment_lookup,
        zone_ids=zone_ids,
    )

    assert plan.skipped_reason is None
    assert plan.equipment_id == "eq-ahu-roof"
    assert plan.zone_id == "Zone-201"
    assert plan.zone_relationship_type == "serves"
    assert plan.confidence == pytest.approx(0.95)
    assert plan.review_status == "approved"


def test_manual_simulation_relationship_stays_suggested_low_confidence():
    confidence, review_status = _score_relationship(
        "manual_simulation",
        "serves",
        explicit_confidence=None,
        explicit_review_status=None,
    )

    assert confidence == pytest.approx(0.55)
    assert review_status == "suggested"


def test_naming_inference_equipment_hierarchy_is_suggested():
    service = OnboardingHierarchyService(client=object())
    equipment_lookup = {
        "S005-JACE-B1-001": {"id": "eq-jace", "canonical_code": "S005-JACE-B1-001"},
        "S005-AHU-304": {"id": "eq-ahu", "canonical_code": "S005-AHU-304"},
    }
    resolved_nodes = {
        "S005-JACE-B1-001": ResolvedNode(
            source_id="S005-JACE-B1-001",
            node_type="equipment",
            canonical_code="S005-JACE-B1-001",
        ),
        "S005-AHU-304": ResolvedNode(
            source_id="S005-AHU-304",
            node_type="equipment",
            canonical_code="S005-AHU-304",
        ),
    }

    plan = service._plan_relationship(
        {
            "parent": "S005-JACE-B1-001",
            "child": "S005-AHU-304",
            "relationship_type": "manages",
        },
        source="naming_inference",
        resolved_nodes=resolved_nodes,
        equipment_lookup=equipment_lookup,
        zone_ids=set(),
    )

    assert plan.skipped_reason is None
    assert plan.parent_canonical_code == "S005-JACE-B1-001"
    assert plan.child_canonical_code == "S005-AHU-304"
    assert plan.confidence == pytest.approx(0.75)
    assert plan.review_status == "suggested"


def test_compact_plant_equipment_aliases_resolve_to_canonical_bridge_codes():
    assert _preferred_canonical_code("S002-AHU-B01") == "S002-AHU-B1-001"
    assert _preferred_canonical_code("S002-AHU-R01") == "S002-AHU-R-001"

    aliases = _equipment_code_aliases("S002-CT-R-001")
    assert "S002-CT-R01" in aliases


def test_equipment_aliases_do_not_collapse_distinct_named_assets():
    aliases = _equipment_code_aliases("S002-PUMP-B1-CHW1")

    assert "S002-PUMP-B1-CHW1" in aliases
    assert "S002-PUMP-B1-001" not in aliases
    assert "S002-PUMP-B01" not in aliases


def test_dali_numeric_and_letter_aliases_are_equivalent():
    assert "S002-DALI-L1-A" in _equipment_code_aliases("S002-DALI-101")
    assert "S002-DALI-202" in _equipment_code_aliases("S002-DALI-L2-B")
    assert "S002-DALI-B1-001" not in _equipment_code_aliases("S002-DALI_CONTROLLER-B1-001")


def test_hierarchy_stub_helpers_accept_only_sentinel_style_codes():
    assert _is_sentinel_equipment_code("S002-PUMP-B1-CHW1")
    assert not _is_sentinel_equipment_code("site-005-UMH-PUMP-B1-CHW1")

    assert _equipment_type_from_code("S002-PUMP-B1-CHW1") == "pump"
    assert _zone_key_from_equipment_code("S002-FCU-301") == "Zone-301"
    assert _zone_key_from_equipment_code("S002-CHILLER-B1-002") == "Zone-B1-002"

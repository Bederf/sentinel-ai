from types import SimpleNamespace

import pytest

from app.services.zone_scope_decomposer import (
    PARENT_CLOSED_EMPTY_HVAC_RULES,
    PARENT_OCCUPANCY_CONFLICT_RULE,
    ZONE_SCOPE_DECOMPOSITION_RULE,
    ZoneScopeDecomposer,
)


class _FakeFusion:
    def __init__(self, verdicts):
        self.verdicts = verdicts

    async def get_fused_occupancy(self, site_id, zone_id=None, force_refresh=False):
        return self.verdicts[zone_id]


class _AllowAllWhitelist:
    def can_write(self, equipment_id, point_name):
        return SimpleNamespace(allowed=True)


class _NoopZoneResolver:
    async def resolve(self, site_id, zone_id, source_context="unknown", record_gap=True):
        return SimpleNamespace(canonical_zone_id=zone_id)


def _verdict(pct=0.0, count=0, occupied=False, uncertain=False, co2=None):
    signals = {}
    if co2 is not None:
        signals["co2_elevation"] = SimpleNamespace(raw_value={"avg_co2": co2})
    return SimpleNamespace(
        occupancy_percent=pct,
        occupancy_count=count,
        is_occupied=occupied,
        is_uncertain=uncertain,
        signals=signals,
    )


def _parent():
    return {
        "target_equipment": "SITE-002-HVAC-ZONE-SCOPE",
        "metadata": {
            "rule": PARENT_OCCUPANCY_CONFLICT_RULE,
            "advisory_type": "occupancy_conflict_control_gate",
        },
    }


def _closed_empty_parent():
    return {
        "target_equipment": "SITE-002-HVAC-SCHEDULE",
        "metadata": {
            "rule": "closed_empty_building_hvac_running",
            "advisory_type": "site_profile_hvac_state_correction",
        },
    }


def _conditions(
    timestamp="2026-06-29T22:00:00+02:00",
    bindings=None,
    writable_points=None,
    zone_states=None,
    operating_hours=None,
):
    return {
        "timestamp": timestamp,
        "operating_hours": operating_hours or {"start": "08:00", "end": "18:00"},
        "zone_scope_decomposition": {
            "bindings": bindings or [],
            "writable_points": writable_points or [],
            "zone_states": zone_states or {},
        },
    }


def _binding(zone, equipment, equipment_type="vav"):
    return {"zone_id": zone, "equipment_id": equipment, "equipment_type": equipment_type}


def _point(equipment, point="damper_position", parameter_type="command:analogOutput:%"):
    return {"equipment_id": equipment, "point_name": point, "parameter_type": parameter_type}


@pytest.mark.asyncio
async def test_mixed_outside_hours_emits_only_verified_empty_zone_equipment():
    verdicts = {
        "Zone-001": _verdict(0),
        "Zone-002": _verdict(2),
        "Zone-003": _verdict(0),
        "Zone-004": _verdict(60, count=5, occupied=True),
    }
    decomposer = ZoneScopeDecomposer(
        fusion_service=_FakeFusion(verdicts),
        zone_resolver=_NoopZoneResolver(),
        whitelist=_AllowAllWhitelist(),
    )

    result = await decomposer.decompose(
        "site-002",
        _parent(),
        current_conditions=_conditions(
            bindings=[
                _binding("Zone-001", "S002-VAV-001"),
                _binding("Zone-002", "S002-VAV-002"),
                _binding("Zone-003", "S002-VAV-003"),
                _binding("Zone-004", "S002-VAV-004"),
            ],
            writable_points=[
                _point("S002-VAV-001"),
                _point("S002-VAV-002"),
                _point("S002-VAV-003"),
                _point("S002-VAV-004"),
            ],
        ),
    )

    assert {rec["target_equipment"] for rec in result.recommendations} == {
        "S002-VAV-001",
        "S002-VAV-002",
        "S002-VAV-003",
    }
    assert all(rec["metadata"]["rule"] == ZONE_SCOPE_DECOMPOSITION_RULE for rec in result.recommendations)
    assert all(
        rec["action"] == {"point": "damper_position", "value": 0, "execution_blocked": False}
        for rec in result.recommendations
    )
    assert result.zone_classifications["Zone-004"].classification == "verified_occupied"


@pytest.mark.asyncio
async def test_closed_empty_parent_decomposes_to_verified_empty_zone_equipment():
    decomposer = ZoneScopeDecomposer(
        fusion_service=_FakeFusion({"Zone-001": _verdict(0)}),
        zone_resolver=_NoopZoneResolver(),
        whitelist=_AllowAllWhitelist(),
    )

    result = await decomposer.decompose(
        "site-002",
        _closed_empty_parent(),
        current_conditions=_conditions(
            bindings=[_binding("Zone-001", "S002-VAV-001")],
            writable_points=[_point("S002-VAV-001")],
        ),
    )

    assert len(result.recommendations) == 1
    rec = result.recommendations[0]
    assert rec["target_equipment"] == "S002-VAV-001"
    assert rec["metadata"]["parent_rule"] == "closed_empty_building_hvac_running"
    assert rec["metadata"]["parent_target_equipment"] == "SITE-002-HVAC-SCHEDULE"
    assert set(PARENT_CLOSED_EMPTY_HVAC_RULES).issubset(set(rec["metadata"]["supersedes_rules"]))
    assert PARENT_OCCUPANCY_CONFLICT_RULE in rec["metadata"]["supersedes_rules"]


@pytest.mark.asyncio
async def test_patrol_level_signal_outside_hours_still_classifies_empty():
    decomposer = ZoneScopeDecomposer(
        fusion_service=_FakeFusion({"Zone-001": _verdict(8, count=1, occupied=True, uncertain=True)}),
        zone_resolver=_NoopZoneResolver(),
        whitelist=_AllowAllWhitelist(),
    )

    result = await decomposer.decompose(
        "site-002",
        _parent(),
        current_conditions=_conditions(
            bindings=[_binding("Zone-001", "S002-VAV-001")],
            writable_points=[_point("S002-VAV-001")],
        ),
    )

    assert len(result.recommendations) == 1
    assert result.zone_classifications["Zone-001"].classification == "verified_empty"
    assert result.zone_classifications["Zone-001"].reason_code == "outside_hours_below_genuine_staff_threshold"


@pytest.mark.asyncio
async def test_sub_staff_threshold_uncertain_signal_outside_hours_still_decomposes():
    decomposer = ZoneScopeDecomposer(
        fusion_service=_FakeFusion({"Zone-001": _verdict(14.8, count=0, occupied=False, uncertain=True)}),
        zone_resolver=_NoopZoneResolver(),
        whitelist=_AllowAllWhitelist(),
    )

    result = await decomposer.decompose(
        "site-002",
        _parent(),
        current_conditions=_conditions(
            timestamp="2026-06-29T19:00:00+02:00",
            operating_hours={"weekday": "07:00-18:00", "weekend": "closed"},
            bindings=[_binding("Zone-001", "S002-VAV-001")],
            writable_points=[_point("S002-VAV-001")],
        ),
    )

    assert len(result.recommendations) == 1
    assert result.zone_classifications["Zone-001"].classification == "verified_empty"
    assert result.zone_classifications["Zone-001"].reason_code == "outside_hours_below_genuine_staff_threshold"


@pytest.mark.asyncio
async def test_inside_hours_protects_occupied_zone_and_sets_back_empty_zones():
    verdicts = {
        "Zone-001": _verdict(0),
        "Zone-002": _verdict(25, count=2, occupied=True),
        "Zone-003": _verdict(0),
    }
    decomposer = ZoneScopeDecomposer(
        fusion_service=_FakeFusion(verdicts),
        zone_resolver=_NoopZoneResolver(),
        whitelist=_AllowAllWhitelist(),
    )

    result = await decomposer.decompose(
        "site-002",
        _parent(),
        current_conditions=_conditions(
            timestamp="2026-06-29T10:00:00+02:00",
            bindings=[
                _binding("Zone-001", "S002-VAV-001"),
                _binding("Zone-002", "S002-VAV-002"),
                _binding("Zone-003", "S002-VAV-003"),
            ],
            writable_points=[_point("S002-VAV-001"), _point("S002-VAV-002"), _point("S002-VAV-003")],
        ),
    )

    assert {rec["target_equipment"] for rec in result.recommendations} == {"S002-VAV-001", "S002-VAV-003"}
    assert result.zone_classifications["Zone-002"].classification == "verified_occupied"


@pytest.mark.asyncio
async def test_fault_gate_excludes_verified_empty_equipment():
    decomposer = ZoneScopeDecomposer(
        fusion_service=_FakeFusion({"Zone-001": _verdict(0)}),
        zone_resolver=_NoopZoneResolver(),
        whitelist=_AllowAllWhitelist(),
    )

    result = await decomposer.decompose(
        "site-002",
        _parent(),
        current_conditions=_conditions(
            bindings=[_binding("Zone-001", "S002-AHU-001", "ahu")],
            writable_points=[_point("S002-AHU-001", "plant_enable", "command:binaryOutput")],
        ),
        fault_gate_context={
            "decisions": {
                "S002-AHU-001": {
                    "suppress": True,
                    "fault_type": "coupled",
                    "reason_codes": ["Coupled equipment S002-CHILLER-001 has active critical alert"],
                }
            }
        },
    )

    assert result.recommendations == []
    assert result.parent_retained is True
    assert result.skipped_equipment[0]["reason"] == "fault_gate_suppressed"


@pytest.mark.asyncio
async def test_direct_zone_co2_overrides_high_site_level_co2_signal():
    decomposer = ZoneScopeDecomposer(
        fusion_service=_FakeFusion({"Zone-001": _verdict(0, co2=1100)}),
        zone_resolver=_NoopZoneResolver(),
        whitelist=_AllowAllWhitelist(),
    )

    result = await decomposer.decompose(
        "site-002",
        _parent(),
        current_conditions=_conditions(
            bindings=[_binding("Zone-001", "S002-VAV-001")],
            writable_points=[_point("S002-VAV-001")],
            zone_states={"Zone-001": {"co2_ppm": 450}},
        ),
    )

    assert len(result.recommendations) == 1
    assert result.zone_classifications["Zone-001"].classification == "verified_empty"


@pytest.mark.asyncio
async def test_generic_fcu_setpoint_uses_temperature_setback_value():
    decomposer = ZoneScopeDecomposer(
        fusion_service=_FakeFusion({"Zone-001": _verdict(0)}),
        zone_resolver=_NoopZoneResolver(),
        whitelist=_AllowAllWhitelist(),
    )

    result = await decomposer.decompose(
        "site-002",
        _parent(),
        current_conditions=_conditions(
            bindings=[_binding("Zone-001", "S002-FCU-001", "fcu")],
            writable_points=[_point("S002-FCU-001", "setpoint", "command:analogOutput:degC")],
        ),
    )

    assert len(result.recommendations) == 1
    rec = result.recommendations[0]
    assert rec["action"] == {"point": "setpoint", "value": 26, "execution_blocked": False}
    assert rec["unit"] == "degC"


@pytest.mark.asyncio
async def test_all_zones_uncertain_keeps_parent_manual_advisory():
    decomposer = ZoneScopeDecomposer(
        fusion_service=_FakeFusion(
            {
                "Zone-001": _verdict(50, uncertain=True),
                "Zone-002": _verdict(70, uncertain=True, co2=1100),
            }
        ),
        zone_resolver=_NoopZoneResolver(),
        whitelist=_AllowAllWhitelist(),
    )

    result = await decomposer.decompose(
        "site-002",
        _parent(),
        current_conditions=_conditions(
            timestamp="2026-06-29T10:00:00+02:00",
            bindings=[_binding("Zone-001", "S002-VAV-001"), _binding("Zone-002", "S002-VAV-002")],
            writable_points=[_point("S002-VAV-001"), _point("S002-VAV-002")],
        ),
    )

    assert result.recommendations == []
    assert result.parent_retained is True
    assert {item.classification for item in result.zone_classifications.values()} == {"conflicted_uncertain"}

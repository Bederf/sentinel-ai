from app.services.onboarding_canonicalization_service import (
    _equipment_type_from_canonical_code,
    canonical_zone_from_floor_index,
    compact_plant_code,
    source_alias_key,
    split_canonical_code,
)


def test_canonical_zone_from_floor_index_uses_reserved_floor_ranges_without_preallocation():
    assert canonical_zone_from_floor_index("G", "003") == "Zone-003"
    assert canonical_zone_from_floor_index("L1", "001") == "Zone-100"
    assert canonical_zone_from_floor_index("L1", "005") == "Zone-104"
    assert canonical_zone_from_floor_index("L5", "011") == "Zone-510"


def test_canonical_zone_from_floor_index_rejects_unsafe_values():
    assert canonical_zone_from_floor_index("L3", "ICU") is None
    assert canonical_zone_from_floor_index("L3", "000") is None
    assert canonical_zone_from_floor_index("L3", "100") is None
    assert canonical_zone_from_floor_index("ROOF", "001") is None


def test_source_alias_key_preserves_source_floor_label():
    assert source_alias_key("G", "1") == "Zone-G-001"
    assert source_alias_key("L4", "03") == "Zone-L4-003"
    assert source_alias_key("L3", "ICU") == "Zone-L3-ICU"


def test_compact_plant_code_normalizes_basement_and_roof_sequences():
    assert compact_plant_code("S005", "CT", "R", "2") == ("S005-CT-R-002", "Zone-R-002")
    assert compact_plant_code("S005", "CHILLER", "B01", "1") == (
        "S005-CHILLER-B1-001",
        "Zone-B1-001",
    )


def test_split_canonical_code_accepts_occupied_zone_equipment_only():
    assert split_canonical_code("S005-AHU-402") == ("S005", "AHU", "402")
    assert split_canonical_code("S005-CT-R-001") is None


def test_equipment_type_from_canonical_code_handles_source_alias_rows():
    assert _equipment_type_from_canonical_code("S005-MEDGAS-B1-001") == "medical_gas"
    assert _equipment_type_from_canonical_code("S005-MSB-B1-001") == "switchboard"
    assert _equipment_type_from_canonical_code("S005-KEF-B1-001") == "exhaust_fan"
    assert _equipment_type_from_canonical_code("S002-DALI_CONTROLLER-B1-001") == "dali_controller"
    assert _equipment_type_from_canonical_code("site-005-UMH-AHU-L3-ICU") is None

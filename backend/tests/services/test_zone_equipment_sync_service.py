from app.services.zone_equipment_sync_service import (
    ZoneEquipmentSyncService,
    _normalize_equipment_type,
)


def test_normalize_equipment_type_collapses_lighting_variants():
    assert _normalize_equipment_type("luminaire") == "lighting"
    assert _normalize_equipment_type("DALI_CONTROLLER") == "dali"
    assert _normalize_equipment_type("S005-AHU-304") == "ahu"


def test_zone_equipment_sync_service_builds_assignments_from_equipment_and_relationships():
    service = ZoneEquipmentSyncService(client=object())
    equipment_rows = [
        {
            "id": "eq-ahu",
            "code": "S002-AHU-B1-001",
            "canonical_code": "S002-AHU-B1-001",
            "type": "ahu",
            "zone_key": "Zone-301",
            "canonical_zone_id": "Zone-301",
        },
        {
            "id": "eq-vav",
            "code": "S002-VAV-301",
            "canonical_code": "S002-VAV-301",
            "type": "vav",
            "zone_key": "Zone-301",
            "canonical_zone_id": "Zone-301",
        },
    ]
    relationship_rows = [
        {"equipment_id": "eq-ahu", "zone_id": "Zone-301", "relationship_type": "serves", "review_status": "approved"}
    ]

    assignments = service._build_assignments(equipment_rows, relationship_rows)

    assert assignments["Zone-301"]["ahu_id"] == "S002-AHU-B1-001"
    assert assignments["Zone-301"]["vav_id"] == "S002-VAV-301"

from app.services.health_snapshot_service import HealthSnapshotService


class _FakeEquipmentRepo:
    def __init__(self, equipment_id: str):
        self._equipment_id = equipment_id

    def get_by_id(self, code: str):
        if code == "S002-CHILLER-B1-001":
            return {"id": self._equipment_id, "code": code}
        return None


def test_resolve_equipment_storage_id_maps_code_to_uuid():
    svc = HealthSnapshotService()
    svc._get_equipment_repo = lambda: _FakeEquipmentRepo("11111111-1111-1111-1111-111111111111")

    resolved = svc._resolve_equipment_storage_id("S002-CHILLER-B1-001")

    assert resolved == "11111111-1111-1111-1111-111111111111"


def test_resolve_equipment_storage_id_keeps_uuid():
    svc = HealthSnapshotService()
    equipment_id = "22222222-2222-2222-2222-222222222222"

    resolved = svc._resolve_equipment_storage_id(equipment_id)

    assert resolved == equipment_id

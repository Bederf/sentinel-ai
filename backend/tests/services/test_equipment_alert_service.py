from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services import equipment_alert_service as equipment_alert_module
from app.services.equipment_alert_service import EquipmentAlertService


class _FakeQuery:
    def __init__(self, lookup):
        self._lookup = lookup
        self._field = None
        self._value = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, field, value):
        self._field = field
        self._value = value
        return self

    def execute(self):
        return SimpleNamespace(data=self._lookup.get((self._field, self._value), []))


class _FakeSupabase:
    def __init__(self, table_name: str, lookup):
        self._table_name = table_name
        self._lookup = lookup

    def table(self, table_name):
        assert table_name == self._table_name
        return _FakeQuery(self._lookup)


def test_create_alert_resolves_code_inputs_to_uuid(monkeypatch):
    svc = EquipmentAlertService.__new__(EquipmentAlertService)
    svc.alert_repo = MagicMock()
    svc.supabase = MagicMock()

    equipment = {
        "id": "eq-uuid-1",
        "code": "S002-FCU-L1-A",
        "name": "Level 1 Zone A FCU",
        "type": "fcu",
        "building_id": "bld-uuid-1",
        "zone_name": "Level 1 Zone A",
    }
    building = {"id": "bld-uuid-1", "code": "site-002", "name": "Sandton Data Centre"}

    svc._get_equipment = MagicMock(return_value=equipment)
    svc._get_building = MagicMock(side_effect=lambda bid: building if bid in ("site-002", "bld-uuid-1") else None)
    svc.alert_repo.create.return_value = {"id": "alert-1"}
    monkeypatch.setattr(equipment_alert_module.alert_notifier, "send_alert_sync", lambda _payload: True)

    result = svc.create_alert_for_equipment(
        equipment_id="S002-FCU-L1-A",
        building_id="site-002",
        severity="warning",
        message="Health degraded",
    )

    assert result["telegram_sent"] is True
    payload = svc.alert_repo.create.call_args.args[0]
    assert payload["equipment_id"] == "eq-uuid-1"
    assert payload["building_id"] == "bld-uuid-1"


def test_create_alert_falls_back_to_equipment_building_id(monkeypatch):
    svc = EquipmentAlertService.__new__(EquipmentAlertService)
    svc.alert_repo = MagicMock()
    svc.supabase = MagicMock()

    equipment = {
        "id": "eq-uuid-2",
        "code": "S002-FCU-L2-B",
        "name": "Level 2 Zone B FCU",
        "type": "fcu",
        "building_id": "bld-uuid-2",
        "zone_name": "Level 2 Zone B",
    }

    svc._get_equipment = MagicMock(return_value=equipment)
    svc._get_building = MagicMock(return_value=None)
    svc.alert_repo.create.return_value = {"id": "alert-2"}
    monkeypatch.setattr(equipment_alert_module.alert_notifier, "send_alert_sync", lambda _payload: False)

    result = svc.create_alert_for_equipment(
        equipment_id="S002-FCU-L2-B",
        building_id="site-002",
        severity="warning",
        message="Health degraded",
    )

    assert result["telegram_sent"] is False
    payload = svc.alert_repo.create.call_args.args[0]
    assert payload["equipment_id"] == "eq-uuid-2"
    assert payload["building_id"] == "bld-uuid-2"


def test_get_equipment_falls_back_to_code_lookup():
    svc = EquipmentAlertService.__new__(EquipmentAlertService)
    svc.supabase = _FakeSupabase(
        "equipment",
        {
            ("id", "S002-FCU-L1-A"): [],
            (
                "code",
                "S002-FCU-L1-A",
            ): [{"id": "eq-uuid-3", "code": "S002-FCU-L1-A", "name": "Fan Coil Unit (S002-FCU-L1-A)", "type": "fcu"}],
        },
    )

    equipment = svc._get_equipment("S002-FCU-L1-A")

    assert equipment is not None
    assert equipment["id"] == "eq-uuid-3"
    assert equipment["code"] == "S002-FCU-L1-A"


def test_get_building_falls_back_to_code_lookup():
    svc = EquipmentAlertService.__new__(EquipmentAlertService)
    svc.supabase = _FakeSupabase(
        "buildings",
        {
            ("id", "site-002"): [],
            ("code", "site-002"): [{"id": "bld-uuid-3", "code": "site-002", "name": "Sandton Data Centre"}],
        },
    )

    building = svc._get_building("site-002")

    assert building is not None
    assert building["id"] == "bld-uuid-3"
    assert building["code"] == "site-002"

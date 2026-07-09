from unittest.mock import patch

import pytest

from app.database.repositories.security_repository import SecurityRepository


class _Result:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self.filters = {}
        self.payload = None
        self.limit_count = None
        self.order_field = None
        self.order_desc = False

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def in_(self, key, values):
        self.filters[key] = set(values)
        return self

    def order(self, field, desc=False):
        self.order_field = field
        self.order_desc = desc
        return self

    def limit(self, count):
        self.limit_count = count
        return self

    def insert(self, payload):
        self.payload = payload
        return self

    def execute(self):
        if self.payload is not None:
            self.client.inserted.setdefault(self.table_name, []).append(self.payload)
            return _Result([self.payload])

        rows = list(self.client.tables.get(self.table_name, []))
        for key, value in self.filters.items():
            if isinstance(value, set):
                rows = [row for row in rows if row.get(key) in value]
            else:
                rows = [row for row in rows if row.get(key) == value]

        if self.order_field:
            rows = sorted(rows, key=lambda row: row.get(self.order_field) or "", reverse=self.order_desc)
        if self.limit_count is not None:
            rows = rows[: self.limit_count]
        return _Result(rows)


class _FakeClient:
    def __init__(self, tables):
        self.tables = tables
        self.inserted = {}

    def table(self, table_name):
        return _FakeQuery(self, table_name)


@pytest.fixture
def fake_security_client():
    tables = {
        "security_access_zones": [
            {"zone_id": "zone-101", "building_id": "site-002", "name": "Level 1", "floor": "L1"},
            {"zone_id": "zone-201", "building_id": "site-001", "name": "Other Site", "floor": "L2"},
        ],
        "security_doors": [
            {"door_id": "door-1", "zone_id": "zone-101", "name": "Level 1 Door", "status": "locked"},
            {"door_id": "door-2", "zone_id": "zone-201", "name": "Other Door", "status": "open"},
        ],
        "security_badge_events": [
            {
                "event_id": "evt-2",
                "door_id": "door-1",
                "zone_id": "zone-101",
                "badge_id": "badge-2",
                "person_name": "Jane",
                "direction": "exit",
                "timestamp": "2026-07-03T09:05:00+00:00",
                "granted": True,
                "reason": "",
            },
            {
                "event_id": "evt-1",
                "door_id": "door-1",
                "zone_id": "zone-101",
                "badge_id": "badge-1",
                "person_name": "John",
                "direction": "entry",
                "timestamp": "2026-07-03T10:05:00+00:00",
                "granted": True,
                "reason": "",
                "after_hours": False,
            },
        ],
        "security_cameras": [],
        "security_alarm_zones": [],
    }
    return _FakeClient(tables)


def test_get_badge_events_returns_site_zone_rows_in_descending_order(fake_security_client):
    with patch("app.database.repositories.security_repository.get_supabase_client", return_value=fake_security_client):
        repo = SecurityRepository()

    events = repo.get_badge_events(zone_id="zone-101", limit=10)

    assert [event["event_id"] for event in events] == ["evt-1", "evt-2"]


def test_log_badge_event_maps_access_fields_into_badge_event_row(fake_security_client):
    with patch("app.database.repositories.security_repository.get_supabase_client", return_value=fake_security_client):
        repo = SecurityRepository()

    saved = repo.log_badge_event(
        {
            "equipment_id": "door-1",
            "person_id": "badge-9",
            "person_name": "Pieter",
            "direction": "entry",
            "zone_id": "zone-101",
            "status": "granted",
            "reason": "Valid badge",
        }
    )

    assert saved["door_id"] == "door-1"
    assert saved["badge_id"] == "badge-9"
    assert saved["person_name"] == "Pieter"
    assert saved["event_type"] == "access_granted"
    assert fake_security_client.inserted["security_badge_events"][0]["zone_id"] == "zone-101"


def test_get_doors_filters_to_site_zones(fake_security_client):
    with patch("app.database.repositories.security_repository.get_supabase_client", return_value=fake_security_client):
        repo = SecurityRepository()

    doors = repo.get_doors(site="site-002")

    assert [door["door_id"] for door in doors] == ["door-1"]

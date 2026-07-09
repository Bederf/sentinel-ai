from unittest.mock import patch

import pytest

from app.database.repositories.work_order_repository import WorkOrderRepository


class _Result:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self.filters = {}
        self.payload = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def limit(self, *_args):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def insert(self, payload):
        self.payload = payload
        return self

    def execute(self):
        if self.table_name == "equipment":
            return _Result([])
        if self.table_name == "sites":
            if self.filters == {"code": "site-002"}:
                return _Result([{"id": "d7ad3a57-a67c-4aa3-968b-fb4566e07246"}])
            if self.filters == {"id": "d7ad3a57-a67c-4aa3-968b-fb4566e07246"}:
                return _Result([{"code": "site-002"}])
            return _Result([])
        if self.table_name == "technicians":
            assert self.filters == {"site_id": "site-002", "active": True}
            return _Result(
                [
                    {
                        "id": "02786048-3daa-4fe2-9e61-056ddd868be9",
                        "name": "John Smith",
                        "email": "bederf@gmail.com",
                        "telegram_id": "8359288792",
                        "specialty": "electrical",
                        "site_id": "site-002",
                    }
                ]
            )
        if self.table_name == "work_orders":
            self.client.inserted_payload = self.payload
            return _Result([{"id": "wo-id", "code": "WO-2026-0001", **self.payload}])
        return _Result([])


class _FakeClient:
    def __init__(self):
        self.inserted_payload = None

    def table(self, table_name):
        return _FakeQuery(self, table_name)


@pytest.mark.asyncio
async def test_create_work_order_resolves_site_code_for_site_scoped_recommendation():
    fake_client = _FakeClient()
    with patch("app.database.repositories.work_order_repository.get_supabase_client", return_value=fake_client):
        repo = WorkOrderRepository()

    created = await repo.create_work_order(
        {
            "title": "SENTINEL Advisory Action: SITE-002-HVAC-ZONE-SCOPE",
            "description": "Created from SENTINEL AI advisory recommendation.",
            "site_id": "site-002",
            "equipment_code": "SITE-002-HVAC-ZONE-SCOPE",
            "recommendation_id": "bc89adc4-272c-486e-b916-ec00aea4bffb",
            "service_type": "callout",
        }
    )

    assert created["code"] == "WO-2026-0001"
    assert fake_client.inserted_payload["site_id"] == "d7ad3a57-a67c-4aa3-968b-fb4566e07246"
    assert fake_client.inserted_payload["assigned_to"] == "John Smith"
    assert fake_client.inserted_payload["assigned_team"] == "electrical"
    assert fake_client.inserted_payload["work_type"] == "callout"
    assert "service_type" not in fake_client.inserted_payload
    assert "equipment_id" not in fake_client.inserted_payload


@pytest.mark.asyncio
async def test_create_work_order_does_not_include_category_in_payload():
    """Regression: category must not be in the insert payload because
    work_orders table has no category column."""
    fake_client = _FakeClient()
    with patch("app.database.repositories.work_order_repository.get_supabase_client", return_value=fake_client):
        repo = WorkOrderRepository()

    created = await repo.create_work_order(
        {
            "title": "HVAC: Temperature too cold",
            "description": "Desk 104 — Temperature too cold",
            "site_id": "site-002",
            "category": "HVAC",
            "priority": "medium",
            "status": "scheduled",
            "service_type": "callout",
        }
    )

    assert created["code"] == "WO-2026-0001"
    assert "category" not in fake_client.inserted_payload
    assert fake_client.inserted_payload["work_type"] == "callout"

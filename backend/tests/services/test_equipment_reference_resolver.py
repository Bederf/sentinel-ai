from unittest.mock import MagicMock

import pytest


class _FakeQuery:
    def __init__(self, data=None):
        self.data = data or []
        self.filters = {}

    def select(self, *args, **kwargs):
        return self

    def eq(self, field, value):
        self.filters[field] = value
        return self

    def limit(self, *args, **kwargs):
        return self

    def execute(self):
        if self.filters.get("code") == "S002-CHILLER-B1-001":
            return MagicMock(
                data=[
                    {
                        "id": "eq-1",
                        "code": "S002-CHILLER-B1-001",
                        "site_id": "site-002",
                        "type": "chiller",
                        "name": "Main Chiller 1",
                    }
                ]
            )

        if self.filters.get("site_id") == "site-002" and self.filters.get("active") is True:
            return MagicMock(
                data=[
                    {
                        "id": "eq-1",
                        "code": "S002-CHILLER-B1-001",
                        "type": "chiller",
                        "manufacturer": "",
                        "model": "",
                        "display_name": "Main Chiller 1",
                    },
                    {
                        "id": "eq-2",
                        "code": "S002-CHILLER-B1-002",
                        "type": "chiller",
                        "manufacturer": "",
                        "model": "",
                        "display_name": "Main Chiller 2",
                    },
                ]
            )

        return MagicMock(data=[])


class _FakeSupabase:
    def table(self, name):
        assert name in {"equipment", "asset_resolver_aliases"}
        return _FakeQuery()


@pytest.mark.asyncio
async def test_resolve_equipment_reference_maps_bare_chiller_alias(monkeypatch):
    monkeypatch.setattr(
        "app.services.equipment_reference_resolver.get_supabase_client",
        lambda: _FakeSupabase(),
    )

    from app.services.equipment_reference_resolver import resolve_equipment_reference

    equipment = await resolve_equipment_reference("S002-CHILLER-B1")

    assert equipment is not None
    assert equipment["code"] == "S002-CHILLER-B1-001"

import pytest

from app.services.zone_identity_resolver import ZoneIdentityResolver


class FakeZoneIdentityRepository:
    def __init__(self):
        self.gaps = []

    async def list_zone_identifiers(self, site_id):
        return [
            {"source": "zones", "zone_id": "Zone-101"},
            {"source": "zones", "zone_id": "Zone-201"},
            {"source": "hvac_zones", "zone_id": "Zone-B"},
            {"source": "equipment.zone_key", "zone_id": "Zone-L1-1"},
            {"source": "equipment.zone_key", "zone_id": "Zone-L2-1"},
            {"source": "equipment.zone_key", "zone_id": "B1"},
            {"source": "fcu_zone_state", "zone_id": "Zone-101"},
            {"source": "fcu_zone_state", "zone_id": "Zone-888"},
            {"source": "equipment.zone_key", "zone_id": "Zone-L0-21"},
        ]

    async def record_resolution_gap(self, **kwargs):
        self.gaps.append(kwargs)


@pytest.mark.asyncio
async def test_numeric_site_zone_stays_canonical():
    repo = FakeZoneIdentityRepository()
    resolver = ZoneIdentityResolver(repository=repo)

    result = await resolver.resolve("site-002", "Zone-101")

    assert result.resolved is True
    assert result.canonical_zone_id == "Zone-101"
    assert result.reason == "canonical_site_zone_inventory"
    assert repo.gaps == []


@pytest.mark.asyncio
async def test_level_alias_resolves_to_site_zone_inventory():
    repo = FakeZoneIdentityRepository()
    resolver = ZoneIdentityResolver(repository=repo)

    result = await resolver.resolve("site-002", "Zone-L1-1")

    assert result.resolved is True
    assert result.canonical_zone_id == "Zone-101"
    assert result.reason == "zone_alias_matches_site_inventory"
    assert repo.gaps == []


@pytest.mark.asyncio
async def test_basement_alias_resolves_to_site_zone_inventory():
    repo = FakeZoneIdentityRepository()
    resolver = ZoneIdentityResolver(repository=repo)

    result = await resolver.resolve("site-002", "B1")

    assert result.resolved is True
    assert result.canonical_zone_id == "Zone-B"
    assert result.reason == "zone_alias_matches_site_inventory"
    assert repo.gaps == []


@pytest.mark.asyncio
async def test_unresolved_zone_records_visible_gap():
    repo = FakeZoneIdentityRepository()
    resolver = ZoneIdentityResolver(repository=repo)

    result = await resolver.resolve("site-002", "Zone-999", source_context="test")

    assert result.resolved is False
    assert result.reason == "zone_id_not_seen_in_site_inventory"
    assert repo.gaps[0]["source_zone_id"] == "Zone-999"
    assert repo.gaps[0]["source_context"] == "test"


@pytest.mark.asyncio
async def test_fcu_only_zone_without_inventory_is_unresolved_gap():
    repo = FakeZoneIdentityRepository()
    resolver = ZoneIdentityResolver(repository=repo)

    result = await resolver.resolve("site-002", "Zone-888", source_context="fcu_zone_state")

    assert result.resolved is False
    assert result.reason == "fcu_zone_state_zone_not_in_site_zone_inventory"
    assert repo.gaps[0]["source_zone_id"] == "Zone-888"


@pytest.mark.asyncio
async def test_equipment_only_alias_without_site_inventory_records_gap():
    repo = FakeZoneIdentityRepository()
    resolver = ZoneIdentityResolver(repository=repo)

    result = await resolver.resolve("site-002", "Zone-L0-21", source_context="equipment.zone_key")

    assert result.resolved is False
    assert result.reason == "equipment_zone_key_not_in_site_zone_inventory"
    assert repo.gaps[0]["source_zone_id"] == "Zone-L0-21"

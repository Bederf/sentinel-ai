import json

from app.services.site_capacity_service import SiteCapacityService


class StubDeskRepository:
    def get_by_site_code(self, site_id: str):
        assert site_id == "site-002"
        return [{"desk_id": f"D{i:03d}"} for i in range(300)]


class EmptyDeskRepository:
    def get_by_site_code(self, _site_id: str):
        return []


def test_site_capacity_service_derives_capacity_from_desks(tmp_path):
    site_dir = tmp_path / "site-002"
    site_dir.mkdir()
    (site_dir / "building.json").write_text(json.dumps({"metadata": {"occupancy_capacity": 11}}))

    service = SiteCapacityService(data_path=tmp_path, desk_repository_factory=StubDeskRepository)

    assert service.get_desk_count("site-002") == 300
    assert service.get_total_capacity("site-002") == 333
    assert service.get_support_staff_capacity("site-002") == 33


def test_site_capacity_service_prefers_curated_building_metadata(tmp_path):
    site_dir = tmp_path / "site-002"
    site_dir.mkdir()
    (site_dir / "building.json").write_text(json.dumps({"metadata": {"total_desks": 300, "occupancy_capacity": 333}}))
    (site_dir / "desks.json").write_text(json.dumps([{"desk_id": "001"}, {"desk_id": "002"}]))

    service = SiteCapacityService(data_path=tmp_path, desk_repository_factory=EmptyDeskRepository)

    assert service.get_desk_count("site-002") == 300
    assert service.get_total_capacity("site-002") == 333

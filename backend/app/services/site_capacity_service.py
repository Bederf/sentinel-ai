"""Site occupancy-capacity helpers backed by desks and building metadata."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.database.repositories.desk_repository import DeskRepository

logger = logging.getLogger(__name__)

DATA_PATH = Path(__file__).parent.parent / "data" / "buildings"
DESK_SHARE_OF_TOTAL_CAPACITY = 0.90


class SiteCapacityService:
    """Resolves desk counts and derived occupancy capacity per site."""

    def __init__(self, data_path: Path | None = None, desk_repository_factory=DeskRepository):
        self._data_path = data_path or DATA_PATH
        self._desk_repository_factory = desk_repository_factory

    def _load_building_data(self, site_id: str) -> dict:
        path = self._data_path / site_id / "building.json"
        if not path.exists():
            return {}
        with open(path) as handle:
            return json.load(handle)

    def _load_building_desks(self, site_id: str) -> list[dict]:
        path = self._data_path / site_id / "desks.json"
        if not path.exists():
            return []
        with open(path) as handle:
            data = json.load(handle)
        return data if isinstance(data, list) else data.get("desks", [])

    def get_desk_count(self, site_id: str) -> int:
        metadata = self._load_building_data(site_id).get("metadata", {})
        if metadata.get("total_desks"):
            return int(metadata["total_desks"])

        try:
            repo = self._desk_repository_factory()
            desks = repo.get_by_site_code(site_id)
            if desks:
                return len(desks)
        except Exception as exc:
            logger.debug("Desk query failed for %s, falling back to local files: %s", site_id, exc)

        building_desks = self._load_building_desks(site_id)
        if building_desks:
            return len(building_desks)

        occupancy_capacity = metadata.get("occupancy_capacity")
        if occupancy_capacity:
            return round(float(occupancy_capacity) * DESK_SHARE_OF_TOTAL_CAPACITY)

        return 0

    def get_total_capacity(self, site_id: str) -> int:
        desk_count = self.get_desk_count(site_id)
        if desk_count:
            return round(desk_count / DESK_SHARE_OF_TOTAL_CAPACITY)

        metadata = self._load_building_data(site_id).get("metadata", {})
        if metadata.get("occupancy_capacity"):
            return int(metadata["occupancy_capacity"])

        return 0

    def get_support_staff_capacity(self, site_id: str) -> int:
        total_capacity = self.get_total_capacity(site_id)
        desk_count = self.get_desk_count(site_id)
        return max(0, total_capacity - desk_count)


_capacity_service: SiteCapacityService | None = None


def get_site_capacity_service() -> SiteCapacityService:
    global _capacity_service
    if _capacity_service is None:
        _capacity_service = SiteCapacityService()
    return _capacity_service

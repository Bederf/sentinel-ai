"""
Building Data Loader
====================
Modular building data loader that supports:
- Supabase as primary data source (when available)
- Per-building folder structure for JSON config (fallback)
- Backward compatibility with flat JSON files

Data Priority:
1. Supabase tables (hvac_zones, desks, etc.) - primary
2. Building folder JSON files - fallback
3. Flat JSON files - legacy fallback

Structure:
    data/buildings/
    ├── _registry.json          # Active buildings list
    ├── sandton/
    │   ├── building.json       # Building metadata
    │   ├── desks.json          # Desk definitions
    │   ├── zones.json          # HVAC zones
    │   └── devices.json        # Device config (optional)
    └── other_building/
        └── ...

Usage:
    loader = get_site_loader()
    building = loader.get_site("sandton")
    desks = loader.get_desks("sandton")
    all_desks = loader.get_all_desks()  # Merged from all active buildings
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _is_supabase_available() -> bool:
    """Check if Supabase is configured and available."""
    try:
        from app.config.settings import settings

        return bool(settings.supabase_url and settings.supabase_service_role_key)
    except Exception:
        return False


@dataclass
class Building:
    """Building metadata."""

    id: str
    name: str
    display_name: str = ""
    address: str = ""
    timezone: str = "Africa/Johannesburg"
    floors: list[str] = field(default_factory=list)
    features: dict[str, bool] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name or self.name,
            "address": self.address,
            "timezone": self.timezone,
            "floors": self.floors,
            "features": self.features,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Building":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            display_name=data.get("display_name", data.get("name", "")),
            address=data.get("address", ""),
            timezone=data.get("timezone", "Africa/Johannesburg"),
            floors=data.get("floors", []),
            features=data.get("features", {}),
            metadata=data.get("metadata", {}),
        )


class BuildingDataLoader:
    """
    Loads building data from modular folder structure.
    Falls back to flat JSON files for backward compatibility.
    """

    def __init__(self, data_path: Path | None = None):
        self._data_path = data_path or Path(__file__).parent.parent / "data"
        self._buildings_path = self._data_path / "sites"
        self._registry: dict[str, Any] = {}
        self._buildings: dict[str, Building] = {}
        self._desks: dict[str, list[dict]] = {}  # site_id -> desks
        self._zones: dict[str, list[dict]] = {}  # site_id -> zones
        self._devices: dict[str, list[dict]] = {}  # site_id -> devices
        self._loaded = False

    def _load_registry(self) -> dict[str, Any]:
        """Load building registry."""
        registry_path = self._buildings_path / "_registry.json"
        if registry_path.exists():
            with open(registry_path) as f:
                return json.load(f)
        return {"active_sites": [], "default_building": None}

    def _load_building(self, site_id: str) -> Building | None:
        """Load a single building's metadata."""
        site_path = self._buildings_path / site_id / "building.json"
        if site_path.exists():
            with open(site_path) as f:
                data = json.load(f)
                data["id"] = site_id  # Ensure ID matches folder
                return Building.from_dict(data)
        return None

    def _load_site_data(self, site_id: str, filename: str) -> list[dict]:
        """Load a data file for a building (desks, zones, devices)."""
        file_path = self._buildings_path / site_id / filename
        if file_path.exists():
            with open(file_path) as f:
                data = json.load(f)
                # Handle both formats: direct array or wrapped in object
                if isinstance(data, dict):
                    # If it's a dict, look for common keys that contain the array
                    if "zones" in data:
                        data = data["zones"]
                    elif "desks" in data:
                        data = data["desks"]
                    elif "devices" in data:
                        data = data["devices"]
                    else:
                        # If it's a dict but no known array key, return empty
                        return []

                # Now ensure data is a list
                if not isinstance(data, list):
                    return []

                # Add site_id to each record
                for record in data:
                    if isinstance(record, dict):
                        record["site_id"] = site_id
                return data
        return []

    def load(self, force: bool = False) -> None:
        """Load all building data from the modular structure."""
        if self._loaded and not force:
            return

        self._registry = self._load_registry()
        active_sites = self._registry.get("active_sites", [])

        logger.info(f"Loading {len(active_sites)} buildings from registry")

        for site_id in active_sites:
            # Load building metadata
            building = self._load_building(site_id)
            if building:
                self._buildings[site_id] = building
                logger.info(f"Loaded building: {building.name} ({site_id})")

                # Load building data
                self._desks[site_id] = self._load_site_data(site_id, "desks.json")
                self._zones[site_id] = self._load_site_data(site_id, "zones.json")
                self._devices[site_id] = self._load_site_data(site_id, "devices.json")

                logger.info(
                    f"  - {len(self._desks[site_id])} desks, "
                    f"{len(self._zones[site_id])} zones, "
                    f"{len(self._devices[site_id])} devices"
                )
            else:
                logger.warning(f"Building '{site_id}' in registry but not found")

        # Fallback: Load from flat files if no modular data
        if not self._buildings:
            self._load_fallback()

        self._loaded = True

    def _load_fallback(self) -> None:
        """Fallback to loading from flat JSON files (backward compatibility)."""
        logger.info("No modular buildings found, using fallback flat files")

        # Create a default building from flat files
        default_id = "default"
        self._buildings[default_id] = Building(
            id=default_id,
            name="Default Building",
            display_name="Default Building",
        )

        # Load desks
        desks_path = self._data_path / "desks.json"
        if desks_path.exists():
            with open(desks_path) as f:
                desks = json.load(f)
                for desk in desks:
                    desk["site_id"] = default_id
                self._desks[default_id] = desks

        # Load zones
        zones_path = self._data_path / "hvac_zones.json"
        if zones_path.exists():
            with open(zones_path) as f:
                zones = json.load(f)
                for zone in zones:
                    zone["site_id"] = default_id
                self._zones[default_id] = zones

    def get_registry(self) -> dict[str, Any]:
        """Get the building registry."""
        self.load()
        return self._registry

    def get_default_site_id(self) -> str | None:
        """Get the default building ID."""
        self.load()
        return self._registry.get("default_building")

    def get_active_site_ids(self) -> list[str]:
        """Get list of active building IDs."""
        self.load()
        return self._registry.get("active_sites", [])

    def get_site(self, site_id: str) -> Building | None:
        """Get a building by ID."""
        self.load()
        return self._buildings.get(site_id)

    def get_all_sites(self) -> list[Building]:
        """Get all active buildings."""
        self.load()
        return list(self._buildings.values())

    def get_desks(self, site_id: str) -> list[dict]:
        """Get desks for a building.

        Tries Supabase first, then falls back to JSON files.
        """
        self.load()

        # Try Supabase first
        if _is_supabase_available():
            try:
                from app.database.repositories import DeskRepository

                repo = DeskRepository()
                supabase_desks = repo.get_by_site_code(site_id)
                if supabase_desks and isinstance(supabase_desks, list):
                    # Add building name to each desk (ensure each item is a dict)
                    building = self._buildings.get(site_id)
                    desks_with_building = []
                    for desk in supabase_desks:
                        if isinstance(desk, dict):
                            desk_copy = dict(desk)  # Copy to avoid modifying cached data
                            if building:
                                desk_copy["building"] = building.name
                            desks_with_building.append(desk_copy)
                        else:
                            logger.warning(f"Skipping non-dict desk record: {type(desk).__name__}")
                    if desks_with_building:
                        logger.debug(f"Loaded {len(desks_with_building)} desks from Supabase for {site_id}")
                        return desks_with_building
            except Exception as e:
                logger.debug(f"Supabase desk query failed, using JSON: {e}")

        # Fall back to JSON
        desks = self._desks.get(site_id, [])
        # Add building name to each desk for display
        building = self._buildings.get(site_id)
        desks_with_building = []
        for desk in desks:
            if isinstance(desk, dict):
                desk_copy = dict(desk)
                if building:
                    desk_copy["building"] = building.name
                desks_with_building.append(desk_copy)
        return desks_with_building

    def get_all_desks(self) -> list[dict]:
        """Get all desks across all active buildings."""
        self.load()
        all_desks = []
        for site_id in self._buildings:
            all_desks.extend(self.get_desks(site_id))
        return all_desks

    def get_zones(self, site_id: str) -> list[dict]:
        """Get zones for a building (from zones table, not hvac_zones).

        Tries Supabase first, then falls back to JSON files.
        Uses ZoneRepository for the modern zones table which has multi-site support.
        """
        self.load()

        # Try Supabase first
        if _is_supabase_available():
            try:
                from app.database.repositories import ZoneRepository

                repo = ZoneRepository()
                supabase_zones = repo.get_by_site(
                    # Get building UUID from building code
                    self._get_site_uuid(site_id)
                )
                if supabase_zones and isinstance(supabase_zones, list):
                    # Add building name to each zone (ensure each item is a dict)
                    building = self._buildings.get(site_id)
                    zones_with_building = []
                    for zone in supabase_zones:
                        if isinstance(zone, dict):
                            zone_copy = dict(zone)
                            if building:
                                zone_copy["building"] = building.name
                            zones_with_building.append(zone_copy)
                        else:
                            logger.warning(f"Skipping non-dict zone record: {type(zone).__name__}")
                    if zones_with_building:
                        logger.debug(f"Loaded {len(zones_with_building)} zones from Supabase zones table for {site_id}")
                        return zones_with_building
            except Exception as e:
                logger.debug(f"Supabase zone query failed, using JSON: {e}")

        # Fall back to JSON
        zones = self._zones.get(site_id, [])
        building = self._buildings.get(site_id)
        zones_with_building = []
        for zone in zones:
            if isinstance(zone, dict):
                zone_copy = dict(zone)
                if building:
                    zone_copy["building"] = building.name
                zones_with_building.append(zone_copy)
        return zones_with_building

    def _get_site_uuid(self, site_id: str) -> str | None:
        """Get building UUID from building ID using Supabase.

        Args:
            site_id: Building code (e.g., 'sandton')

        Returns:
            Building UUID or None
        """
        if not _is_supabase_available():
            return None

        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            response = client.table("sites").select("id").eq("code", site_id).execute()
            if response.data:
                return response.data[0]["id"]
        except Exception as e:
            logger.debug(f"Failed to get building UUID for {site_id}: {e}")
        return None

    def get_all_zones(self) -> list[dict]:
        """Get all zones across all active buildings."""
        self.load()
        all_zones = []
        for site_id in self._buildings:
            all_zones.extend(self.get_zones(site_id))
        return all_zones

    def get_devices(self, site_id: str) -> list[dict]:
        """Get devices for a building."""
        self.load()
        return self._devices.get(site_id, [])

    def get_all_devices(self) -> list[dict]:
        """Get all devices across all active buildings."""
        self.load()
        all_devices = []
        for site_id in self._buildings:
            all_devices.extend(self.get_devices(site_id))
        return all_devices

    def find_desk(self, desk_id: str, site_id: str | None = None) -> dict | None:
        """Find a desk by ID, optionally filtered by building.

        Tries Supabase first, then falls back to JSON files.
        """
        self.load()

        # Try Supabase first
        if _is_supabase_available():
            try:
                from app.database.repositories import DeskRepository

                repo = DeskRepository()
                desk = repo.find_desk(desk_id, site_id)
                if desk:
                    # Add building name
                    bid = desk.get("site_id")
                    if bid:
                        # Look up building name from our cache
                        for b_id, building in self._buildings.items():
                            if b_id == site_id or site_id is None:
                                desk["building"] = building.name
                                break
                    logger.debug(f"Found desk {desk_id} in Supabase")
                    return desk
            except Exception as e:
                logger.debug(f"Supabase desk find failed, using JSON: {e}")

        # Normalize desk ID for JSON search
        normalized = desk_id.strip().lower()
        normalized = normalized.replace("desk ", "").strip()

        # Search in specific building or all buildings
        buildings_to_search = [site_id] if site_id else list(self._buildings.keys())

        for bid in buildings_to_search:
            for desk in self.get_desks(bid):
                if desk["desk_id"].lower() == normalized:
                    return desk
                # Also try matching just the number
                if desk["desk_id"].lower().endswith(normalized):
                    return desk

        return None

    def find_zone(self, zone_id: str, site_id: str | None = None) -> dict | None:
        """Find a zone by ID, optionally filtered by building.

        Tries Supabase first, then falls back to JSON files.
        """
        self.load()

        # Try Supabase first
        if _is_supabase_available():
            try:
                from app.database.repositories import HVACZoneRepository

                repo = HVACZoneRepository()
                zone = repo.get_by_zone_id(zone_id)
                if zone:
                    # Add building name
                    for b_id, building in self._buildings.items():
                        if b_id == site_id or site_id is None:
                            zone["building"] = building.name
                            break
                    logger.debug(f"Found zone {zone_id} in Supabase")
                    return zone
            except Exception as e:
                logger.debug(f"Supabase zone find failed, using JSON: {e}")

        # Fall back to JSON
        buildings_to_search = [site_id] if site_id else list(self._buildings.keys())

        for bid in buildings_to_search:
            for zone in self.get_zones(bid):
                if zone["zone_id"] == zone_id:
                    return zone

        return None


# Singleton instance
_loader: BuildingDataLoader | None = None


def get_site_loader() -> BuildingDataLoader:
    """Get singleton BuildingDataLoader instance."""
    global _loader
    if _loader is None:
        _loader = BuildingDataLoader()
    return _loader

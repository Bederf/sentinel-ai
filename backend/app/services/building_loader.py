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
    loader = get_building_loader()
    building = loader.get_building("sandton")
    desks = loader.get_desks("sandton")
    all_desks = loader.get_all_desks()  # Merged from all active buildings
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any

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
    floors: List[str] = field(default_factory=list)
    features: Dict[str, bool] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

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

    def __init__(self, data_path: Optional[Path] = None):
        self._data_path = data_path or Path(__file__).parent.parent / "data"
        self._buildings_path = self._data_path / "buildings"
        self._registry: Dict[str, Any] = {}
        self._buildings: Dict[str, Building] = {}
        self._desks: Dict[str, List[dict]] = {}  # building_id -> desks
        self._zones: Dict[str, List[dict]] = {}  # building_id -> zones
        self._devices: Dict[str, List[dict]] = {}  # building_id -> devices
        self._loaded = False

    def _load_registry(self) -> Dict[str, Any]:
        """Load building registry."""
        registry_path = self._buildings_path / "_registry.json"
        if registry_path.exists():
            with open(registry_path) as f:
                return json.load(f)
        return {"active_buildings": [], "default_building": None}

    def _load_building(self, building_id: str) -> Optional[Building]:
        """Load a single building's metadata."""
        building_path = self._buildings_path / building_id / "building.json"
        if building_path.exists():
            with open(building_path) as f:
                data = json.load(f)
                data["id"] = building_id  # Ensure ID matches folder
                return Building.from_dict(data)
        return None

    def _load_building_data(self, building_id: str, filename: str) -> List[dict]:
        """Load a data file for a building (desks, zones, devices)."""
        file_path = self._buildings_path / building_id / filename
        if file_path.exists():
            with open(file_path) as f:
                data = json.load(f)
                # Add building_id to each record
                for record in data:
                    record["building_id"] = building_id
                return data
        return []

    def load(self, force: bool = False) -> None:
        """Load all building data from the modular structure."""
        if self._loaded and not force:
            return

        self._registry = self._load_registry()
        active_buildings = self._registry.get("active_buildings", [])

        logger.info(f"Loading {len(active_buildings)} buildings from registry")

        for building_id in active_buildings:
            # Load building metadata
            building = self._load_building(building_id)
            if building:
                self._buildings[building_id] = building
                logger.info(f"Loaded building: {building.name} ({building_id})")

                # Load building data
                self._desks[building_id] = self._load_building_data(building_id, "desks.json")
                self._zones[building_id] = self._load_building_data(building_id, "zones.json")
                self._devices[building_id] = self._load_building_data(building_id, "devices.json")

                logger.info(
                    f"  - {len(self._desks[building_id])} desks, "
                    f"{len(self._zones[building_id])} zones, "
                    f"{len(self._devices[building_id])} devices"
                )
            else:
                logger.warning(f"Building '{building_id}' in registry but not found")

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
                    desk["building_id"] = default_id
                self._desks[default_id] = desks

        # Load zones
        zones_path = self._data_path / "hvac_zones.json"
        if zones_path.exists():
            with open(zones_path) as f:
                zones = json.load(f)
                for zone in zones:
                    zone["building_id"] = default_id
                self._zones[default_id] = zones

    def get_registry(self) -> Dict[str, Any]:
        """Get the building registry."""
        self.load()
        return self._registry

    def get_default_building_id(self) -> Optional[str]:
        """Get the default building ID."""
        self.load()
        return self._registry.get("default_building")

    def get_active_building_ids(self) -> List[str]:
        """Get list of active building IDs."""
        self.load()
        return self._registry.get("active_buildings", [])

    def get_building(self, building_id: str) -> Optional[Building]:
        """Get a building by ID."""
        self.load()
        return self._buildings.get(building_id)

    def get_all_buildings(self) -> List[Building]:
        """Get all active buildings."""
        self.load()
        return list(self._buildings.values())

    def get_desks(self, building_id: str) -> List[dict]:
        """Get desks for a building.

        Tries Supabase first, then falls back to JSON files.
        """
        self.load()

        # Try Supabase first
        if _is_supabase_available():
            try:
                from app.database.repositories import DeskRepository
                repo = DeskRepository()
                supabase_desks = repo.get_by_building_code(building_id)
                if supabase_desks:
                    # Add building name to each desk
                    building = self._buildings.get(building_id)
                    if building:
                        for desk in supabase_desks:
                            desk["building"] = building.name
                    logger.debug(f"Loaded {len(supabase_desks)} desks from Supabase for {building_id}")
                    return supabase_desks
            except Exception as e:
                logger.debug(f"Supabase desk query failed, using JSON: {e}")

        # Fall back to JSON
        desks = self._desks.get(building_id, [])
        # Add building name to each desk for display
        building = self._buildings.get(building_id)
        if building:
            for desk in desks:
                desk["building"] = building.name
        return desks

    def get_all_desks(self) -> List[dict]:
        """Get all desks across all active buildings."""
        self.load()
        all_desks = []
        for building_id in self._buildings:
            all_desks.extend(self.get_desks(building_id))
        return all_desks

    def get_zones(self, building_id: str) -> List[dict]:
        """Get HVAC zones for a building.

        Tries Supabase first, then falls back to JSON files.
        """
        self.load()

        # Try Supabase first
        if _is_supabase_available():
            try:
                from app.database.repositories import HVACZoneRepository
                repo = HVACZoneRepository()
                supabase_zones = repo.get_by_building_code(building_id)
                if supabase_zones:
                    # Add building name to each zone
                    building = self._buildings.get(building_id)
                    if building:
                        for zone in supabase_zones:
                            zone["building"] = building.name
                    logger.debug(f"Loaded {len(supabase_zones)} zones from Supabase for {building_id}")
                    return supabase_zones
            except Exception as e:
                logger.debug(f"Supabase zone query failed, using JSON: {e}")

        # Fall back to JSON
        zones = self._zones.get(building_id, [])
        building = self._buildings.get(building_id)
        if building:
            for zone in zones:
                zone["building"] = building.name
        return zones

    def get_all_zones(self) -> List[dict]:
        """Get all zones across all active buildings."""
        self.load()
        all_zones = []
        for building_id in self._buildings:
            all_zones.extend(self.get_zones(building_id))
        return all_zones

    def get_devices(self, building_id: str) -> List[dict]:
        """Get devices for a building."""
        self.load()
        return self._devices.get(building_id, [])

    def get_all_devices(self) -> List[dict]:
        """Get all devices across all active buildings."""
        self.load()
        all_devices = []
        for building_id in self._buildings:
            all_devices.extend(self.get_devices(building_id))
        return all_devices

    def find_desk(self, desk_id: str, building_id: Optional[str] = None) -> Optional[dict]:
        """Find a desk by ID, optionally filtered by building.

        Tries Supabase first, then falls back to JSON files.
        """
        self.load()

        # Try Supabase first
        if _is_supabase_available():
            try:
                from app.database.repositories import DeskRepository
                repo = DeskRepository()
                desk = repo.find_desk(desk_id, building_id)
                if desk:
                    # Add building name
                    bid = desk.get("building_id")
                    if bid:
                        # Look up building name from our cache
                        for b_id, building in self._buildings.items():
                            if b_id == building_id or building_id is None:
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
        buildings_to_search = [building_id] if building_id else list(self._buildings.keys())

        for bid in buildings_to_search:
            for desk in self.get_desks(bid):
                if desk["desk_id"].lower() == normalized:
                    return desk
                # Also try matching just the number
                if desk["desk_id"].lower().endswith(normalized):
                    return desk

        return None

    def find_zone(self, zone_id: str, building_id: Optional[str] = None) -> Optional[dict]:
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
                        if b_id == building_id or building_id is None:
                            zone["building"] = building.name
                            break
                    logger.debug(f"Found zone {zone_id} in Supabase")
                    return zone
            except Exception as e:
                logger.debug(f"Supabase zone find failed, using JSON: {e}")

        # Fall back to JSON
        buildings_to_search = [building_id] if building_id else list(self._buildings.keys())

        for bid in buildings_to_search:
            for zone in self.get_zones(bid):
                if zone["zone_id"] == zone_id:
                    return zone

        return None


# Singleton instance
_loader: Optional[BuildingDataLoader] = None


def get_building_loader() -> BuildingDataLoader:
    """Get singleton BuildingDataLoader instance."""
    global _loader
    if _loader is None:
        _loader = BuildingDataLoader()
    return _loader

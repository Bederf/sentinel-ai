"""Zone Mapping Service for cross-system optimization.

Maps HVAC zones to DALI lighting zones for coordinated recommendations.
Enables occupancy-driven multi-system control.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ZoneMapping:
    """Mapping between HVAC and DALI zones."""

    hvac_zone_id: str
    dali_zone_id: str
    floor: str
    area_name: str
    zone_type: str  # open_office, meeting_room, executive, etc.
    priority: int  # 1=critical, 5=lowest


class ZoneMappingService:
    """Service to map HVAC zones to DALI lighting zones.

    The DALI system uses zones like Zone-L12-N (Level 12 North)
    while HVAC may use zones like Zone-L12-A, Zone-L12-B (subdivisions).

    This service provides:
    1. Mappings between HVAC and DALI zone IDs
    2. Aggregation of HVAC readings to DALI zone level
    3. Cross-system recommendation generation
    4. Zone inference from equipment IDs
    5. Auto-assignment of equipment to zones
    """

    def __init__(self):
        self._mappings: dict[str, ZoneMapping] = {}
        self._dali_to_hvac: dict[str, list[str]] = {}
        self._hvac_to_dali: dict[str, str] = {}
        self._load_mappings()

    def _load_mappings(self):
        """Load zone mappings from configuration or generate defaults."""
        # Try to load from JSON file
        config_path = Path(__file__).parent.parent / "data" / "zone_mappings.json"
        if config_path.exists():
            try:
                with open(config_path) as f:
                    data = json.load(f)
                    self._parse_mappings(data)
                    return
            except Exception as e:
                logger.warning(f"Failed to load zone mappings from {config_path}: {e}")

        # Generate default mappings based on naming convention
        # DALI zones: Zone-L12-N, Zone-L12-S, Zone-L11-N, etc.
        # HVAC zones often subdivide: Zone-L12-N-A, Zone-L12-N-B or Zone-L12-A, Zone-L12-B
        self._generate_default_mappings()

    def _parse_mappings(self, data: dict[str, Any]):
        """Parse mapping configuration."""
        for mapping_data in data.get("mappings", []):
            mapping = ZoneMapping(
                hvac_zone_id=mapping_data["hvac_zone_id"],
                dali_zone_id=mapping_data["dali_zone_id"],
                floor=mapping_data.get("floor", ""),
                area_name=mapping_data.get("area_name", ""),
                zone_type=mapping_data.get("zone_type", "open_office"),
                priority=mapping_data.get("priority", 3),
            )
            self._mappings[mapping.hvac_zone_id] = mapping

            # Build reverse lookup
            self._hvac_to_dali[mapping.hvac_zone_id] = mapping.dali_zone_id

            if mapping.dali_zone_id not in self._dali_to_hvac:
                self._dali_to_hvac[mapping.dali_zone_id] = []
            self._dali_to_hvac[mapping.dali_zone_id].append(mapping.hvac_zone_id)

    def _generate_default_mappings(self):
        """Generate default mappings based on Sandton City floor layout.

        DALI zones for site-002 (with standardized L0/L1/L2 floor codes):
        - Zone-L2-A, Zone-L2-B, etc.: Level 2 Zones
        - Zone-L1-A, Zone-L1-B, etc.: Level 1 Zones
        - Zone-L0-A, Zone-L0-B, etc.: Ground/Base Level Zones

        Note: Older mappings used L10, L11, L12 which are migrated to L0, L1, L2
        """
        default_mappings = [
            # Level 3
            ZoneMapping("Zone-L3-A", "Zone-L3-A", "L3", "Level 3 Zone A", "open_office", 3),
            ZoneMapping("Zone-L3-B", "Zone-L3-B", "L3", "Level 3 Zone B", "open_office", 3),
            ZoneMapping("Zone-L3-C", "Zone-L3-C", "L3", "Level 3 Zone C", "open_office", 3),
            ZoneMapping("Zone-L3-D", "Zone-L3-D", "L3", "Level 3 Zone D", "open_office", 3),
            ZoneMapping("Zone-L3-E", "Zone-L3-E", "L3", "Level 3 Zone E", "open_office", 3),
            # Level 2 (formerly L12)
            ZoneMapping("Zone-L2-A", "Zone-L2-A", "L2", "Level 2 Zone A", "open_office", 3),
            ZoneMapping("Zone-L2-B", "Zone-L2-B", "L2", "Level 2 Zone B", "open_office", 3),
            ZoneMapping("Zone-L2-C", "Zone-L2-C", "L2", "Level 2 Zone C", "open_office", 3),
            ZoneMapping("Zone-L2-D", "Zone-L2-D", "L2", "Level 2 Zone D", "open_office", 3),
            ZoneMapping("Zone-L2-E", "Zone-L2-E", "L2", "Level 2 Zone E", "open_office", 3),
            # Level 1 (formerly L11)
            ZoneMapping("Zone-L1-A", "Zone-L1-A", "L1", "Level 1 Zone A", "open_office", 3),
            ZoneMapping("Zone-L1-B", "Zone-L1-B", "L1", "Level 1 Zone B", "open_office", 3),
            ZoneMapping("Zone-L1-C", "Zone-L1-C", "L1", "Level 1 Zone C", "open_office", 3),
            ZoneMapping("Zone-L1-D", "Zone-L1-D", "L1", "Level 1 Zone D", "open_office", 3),
            ZoneMapping("Zone-L1-E", "Zone-L1-E", "L1", "Level 1 Zone E", "open_office", 3),
            # Level 0/Ground (formerly L10)
            ZoneMapping("Zone-L0-A", "Zone-L0-A", "L0", "Ground Level Zone A", "open_office", 3),
            ZoneMapping("Zone-L0-B", "Zone-L0-B", "L0", "Ground Level Zone B", "open_office", 3),
            ZoneMapping("Zone-L0-C", "Zone-L0-C", "L0", "Ground Level Zone C", "open_office", 3),
            ZoneMapping("Zone-L0-D", "Zone-L0-D", "L0", "Ground Level Zone D", "open_office", 3),
            ZoneMapping("Zone-L0-E", "Zone-L0-E", "L0", "Ground Level Zone E", "open_office", 3),
            # Basement
            ZoneMapping("Zone-B1-001", "Zone-B1-001", "B1", "Basement Level 1", "plant_room", 2),
        ]

        for mapping in default_mappings:
            self._mappings[mapping.hvac_zone_id] = mapping
            self._hvac_to_dali[mapping.hvac_zone_id] = mapping.dali_zone_id

            if mapping.dali_zone_id not in self._dali_to_hvac:
                self._dali_to_hvac[mapping.dali_zone_id] = []
            if mapping.hvac_zone_id not in self._dali_to_hvac[mapping.dali_zone_id]:
                self._dali_to_hvac[mapping.dali_zone_id].append(mapping.hvac_zone_id)

        logger.info(f"Generated {len(self._mappings)} default zone mappings")

    def get_dali_zone_for_hvac(self, hvac_zone_id: str) -> str | None:
        """Get the corresponding DALI zone for an HVAC zone.

        Args:
            hvac_zone_id: HVAC zone identifier

        Returns:
            DALI zone ID or None if no mapping exists
        """
        return self._hvac_to_dali.get(hvac_zone_id)

    def get_hvac_zones_for_dali(self, dali_zone_id: str) -> list[str]:
        """Get all HVAC zones that map to a DALI zone.

        Args:
            dali_zone_id: DALI zone identifier

        Returns:
            List of HVAC zone IDs
        """
        return self._dali_to_hvac.get(dali_zone_id, [])

    def get_mapping(self, hvac_zone_id: str) -> ZoneMapping | None:
        """Get full mapping details for an HVAC zone."""
        return self._mappings.get(hvac_zone_id)

    def get_all_mappings(self) -> list[ZoneMapping]:
        """Get all zone mappings."""
        return list(self._mappings.values())

    def get_zones_by_floor(self, floor: str) -> list[ZoneMapping]:
        """Get all zone mappings for a specific floor."""
        return [m for m in self._mappings.values() if m.floor == floor]

    def get_zones_by_type(self, zone_type: str) -> list[ZoneMapping]:
        """Get all zone mappings of a specific type."""
        return [m for m in self._mappings.values() if m.zone_type == zone_type]

    def get_zones_by_priority(self, max_priority: int) -> list[ZoneMapping]:
        """Get all zone mappings with priority <= max_priority.

        Args:
            max_priority: Maximum priority level (1=critical, 5=lowest)

        Returns:
            List of mappings with priority at or above the threshold
        """
        return [m for m in self._mappings.values() if m.priority <= max_priority]

    def should_coordinate_zones(self, dali_zone_id: str) -> bool:
        """Check if a DALI zone has multiple HVAC zones to coordinate.

        When True, changes to HVAC should consider impact on lighting and vice versa.
        """
        hvac_zones = self.get_hvac_zones_for_dali(dali_zone_id)
        return len(hvac_zones) > 0

    def _parse_combined_zone(self, zone_id: str) -> tuple[str, str]:
        """Parse floor and zone from combined zone ID.

        Zone format: {level}{zone_2digit}
        204 → ("L2", "04"), 102 → ("L1", "02"), B01 → ("B1", "01")
        """
        if zone_id[0] in ("B", "R"):
            return (f"{zone_id[0]}1", zone_id[1:].zfill(2))
        level = zone_id[0]
        zone = zone_id[1:].zfill(2)
        return (f"L{level}", zone)

    def infer_zone_from_equipment_id(
        self,
        equipment_id: str,
        site_id: str,
    ) -> dict[str, str] | None:
        """Parse floor and zone from v2.0 equipment ID.

        Args:
            equipment_id: v2.0 format equipment ID (e.g., "S002-FCU-L2-A")
            site_id: Site identifier

        Returns:
            Dict with zone metadata or None if parsing fails

        Example:
            equipment_id="S002-FCU-L2-A", site="site-002"
            → {
                "zone_id": "Zone-L2-A",
                "floor": "L2",
                "zone_letter": "A",
                "zone_type": "open_office",
                "site_id": "site-002"
              }
        """
        import re

        # Parse v2.0 format: S###-TYPE-ZONE_ID
        # Zone ID is combined level+zone (e.g., 204 = level 2, zone 04)
        match = re.match(r"S\d+-[A-Z]+-([A-Z0-9]{2,4})", equipment_id)
        if not match:
            logger.warning(f"Could not parse v2.0 equipment ID: {equipment_id}")
            return None

        zone_id = match.group(1).upper()

        # Parse floor and zone from combined zone ID
        floor, zone = self._parse_combined_zone(zone_id)

        # Determine zone type based on equipment type and floor
        zone_type = "open_office"
        if "DALI" in equipment_id or "LUM" in equipment_id:
            zone_type = "lighting"
        elif "MEETING" in equipment_id:
            zone_type = "meeting_room"
        elif "EXEC" in equipment_id:
            zone_type = "executive"

        return {
            "zone_id": f"Zone-{floor}-{zone}",
            "floor": floor,
            "zone_letter": zone,
            "zone_type": zone_type,
            "site_id": site_id,
        }

    def auto_assign_equipment_to_zones(
        self,
        equipment_list: list[dict[str, Any]],
        site_id: str,
    ) -> dict[str, list[str]]:
        """Auto-assign equipment to zones based on parsed location.

        Args:
            equipment_list: List of equipment dicts with 'equipment_id' keys
            site_id: Site identifier

        Returns:
            Dict mapping zone_id → [equipment_ids...]

        Example:
            Input: [
              {"equipment_id": "S002-FCU-L2-A"},
              {"equipment_id": "S002-FCU-L2-B"},
              {"equipment_id": "S002-AHU-L2"}
            ]
            Output: {
              "Zone-L2-A": ["S002-FCU-L2-A"],
              "Zone-L2-B": ["S002-FCU-L2-B"],
              "Zone-L2": ["S002-AHU-L2"]
            }
        """
        zone_assignments: dict[str, list[str]] = {}

        for equipment in equipment_list:
            eq_id = equipment.get("equipment_id", "")
            if not eq_id:
                continue

            zone_info = self.infer_zone_from_equipment_id(eq_id, site_id)
            if zone_info:
                zone_id = zone_info["zone_id"]
                if zone_id not in zone_assignments:
                    zone_assignments[zone_id] = []
                zone_assignments[zone_id].append(eq_id)

        logger.info(f"Auto-assigned {len(equipment_list)} equipment to {len(zone_assignments)} zones")
        return zone_assignments

    def _load_zones_data(self) -> list:
        """Load zones from the canonical zones.json file.

        Searches for zones.json under data/sites/*/zones.json — the first file
        found is used. Returns [] on missing or malformed file (logs warning).

        This is intentionally separate from _load_mappings() which deals with
        HVAC↔DALI cross-zone mapping config, not the zone→equipment membership.
        """
        data_root = Path(__file__).parent.parent / "data" / "sites"
        candidates = sorted(data_root.glob("*/zones.json"))
        if not candidates:
            logger.warning("No zones.json found under data/sites/*/zones.json")
            return []

        zones_path = candidates[0]
        try:
            with open(zones_path) as f:
                data = json.load(f)
            return data.get("zones", [])
        except Exception as e:
            logger.warning(f"Failed to load zones.json from {zones_path}: {e}")
            return []

    def get_zones_for_equipment(self, equipment_id: str) -> list[str]:
        """Return all zone_ids that contain the given equipment_id.

        Traverses zones.json and collects every zone whose ``equipment`` array
        includes *equipment_id*.  The lookup is exact-match and case-sensitive
        (matching the storage convention in zones.json).

        Args:
            equipment_id: Equipment identifier, e.g. ``"S002-CHILLER-B1-001"``

        Returns:
            List of zone_id strings.  Empty list if the equipment is not found
            in any zone, or if zones.json is missing/malformed.  Never raises.
        """
        zones = self._load_zones_data()
        matched: list[str] = []
        for zone in zones:
            equipment_list = zone.get("equipment", [])
            if equipment_id in equipment_list:
                matched.append(zone["zone_id"])
        return matched

    def get_zone_label(self, zone_id: str) -> str:
        """Return a human-readable label for a zone.

        Looks up the zone in zones.json and constructs a label from the
        ``floor`` and ``zone_letter`` fields when available.  Falls back to
        *zone_id* itself if the zone is not found or metadata is incomplete.

        Args:
            zone_id: Zone identifier, e.g. ``"Zone-B1-001"``

        Returns:
            Human-readable string, e.g. ``"Basement 1 — Zone 001"``.
            Never raises.
        """
        floor_labels: dict[str, str] = {
            "B1": "Basement 1",
            "B2": "Basement 2",
            "G": "Ground Floor",
            "L0": "Ground Floor",
            "L1": "Level 1",
            "L2": "Level 2",
            "L3": "Level 3",
            "R": "Roof",
        }
        zones = self._load_zones_data()
        for zone in zones:
            if zone.get("zone_id") == zone_id:
                floor = zone.get("floor", "")
                letter = zone.get("zone_letter", "")
                floor_readable = floor_labels.get(floor, floor)
                if floor_readable and letter:
                    return f"{floor_readable} — Zone {letter}"
                if floor_readable:
                    return floor_readable
                break
        # Fallback: return zone_id unchanged
        return zone_id

    def create_zones_from_equipment(
        self,
        equipment_list: list[dict[str, Any]],
        site_id: str,
    ) -> list[dict[str, Any]]:
        """Auto-generate zone definitions from discovered equipment.

        Args:
            equipment_list: List of equipment dicts
            site_id: Site identifier

        Returns:
            List of zone definition dicts

        Example:
            Input: FCU-L2-A, FCU-L2-B, FCU-L2-C discovered
            Output: [
              {
                "zone_id": "Zone-L2",
                "floor": "L2",
                "zones": [
                  {"zone_letter": "A", "type": "open_office"},
                  {"zone_letter": "B", "type": "open_office"},
                  {"zone_letter": "C", "type": "open_office"}
                ],
                "equipment_count": 3
              }
            ]
        """
        zones_by_floor_letter: dict[str, dict[str, Any]] = {}

        for equipment in equipment_list:
            eq_id = equipment.get("equipment_id", "")
            if not eq_id:
                continue

            zone_info = self.infer_zone_from_equipment_id(eq_id, site_id)
            if not zone_info:
                continue

            floor = zone_info["floor"]
            zone_letter = zone_info["zone_letter"]
            zone_type = zone_info["zone_type"]

            # Group by floor-letter combination
            key = f"{floor}-{zone_letter}"
            if key not in zones_by_floor_letter:
                zones_by_floor_letter[key] = {
                    "zone_id": f"Zone-{floor}-{zone_letter}",
                    "floor": floor,
                    "zone_letter": zone_letter,
                    "zone_type": zone_type,
                    "equipment": [],
                }

            zones_by_floor_letter[key]["equipment"].append(eq_id)

        # Build final zones list
        zones = list(zones_by_floor_letter.values())
        logger.info(f"Generated {len(zones)} zones from {len(equipment_list)} equipment")

        return zones


# Singleton instance
_zone_mapping_service: ZoneMappingService | None = None


def get_zone_mapping_service() -> ZoneMappingService:
    """Get the singleton zone mapping service instance."""
    global _zone_mapping_service
    if _zone_mapping_service is None:
        _zone_mapping_service = ZoneMappingService()
    return _zone_mapping_service

"""Zone Mapping Service for cross-system optimization.

Maps HVAC zones to DALI lighting zones for coordinated recommendations.
Enables occupancy-driven multi-system control.
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from pathlib import Path
import json

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
    """

    def __init__(self):
        self._mappings: Dict[str, ZoneMapping] = {}
        self._dali_to_hvac: Dict[str, List[str]] = {}
        self._hvac_to_dali: Dict[str, str] = {}
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

    def _parse_mappings(self, data: Dict[str, Any]):
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

        DALI zones for site-002:
        - Zone-L12-N: Level 12 North Open Plan
        - Zone-L12-S: Level 12 South Open Plan
        - Zone-L12-MR: Level 12 Meeting Rooms
        - Zone-L12-EX: Level 12 Executive
        - Zone-L11-N, Zone-L11-S, Zone-L11-MR
        - Zone-L10-N, Zone-L10-S, Zone-L10-MR
        """
        default_mappings = [
            # Level 12
            ZoneMapping("Zone-L12-N", "Zone-L12-N", "L12", "North Open Plan", "open_office", 3),
            ZoneMapping("Zone-L12-N-A", "Zone-L12-N", "L12", "North A", "open_office", 3),
            ZoneMapping("Zone-L12-N-B", "Zone-L12-N", "L12", "North B", "open_office", 3),
            ZoneMapping("Zone-L12-S", "Zone-L12-S", "L12", "South Open Plan", "open_office", 3),
            ZoneMapping("Zone-L12-S-A", "Zone-L12-S", "L12", "South A", "open_office", 3),
            ZoneMapping("Zone-L12-S-B", "Zone-L12-S", "L12", "South B", "open_office", 3),
            ZoneMapping("Zone-L12-MR", "Zone-L12-MR", "L12", "Meeting Rooms", "meeting_room", 2),
            ZoneMapping("Zone-L12-EX", "Zone-L12-EX", "L12", "Executive", "executive", 1),

            # Level 11
            ZoneMapping("Zone-L11-N", "Zone-L11-N", "L11", "North Open Plan", "open_office", 3),
            ZoneMapping("Zone-L11-N-A", "Zone-L11-N", "L11", "North A", "open_office", 3),
            ZoneMapping("Zone-L11-N-B", "Zone-L11-N", "L11", "North B", "open_office", 3),
            ZoneMapping("Zone-L11-S", "Zone-L11-S", "L11", "South Open Plan", "open_office", 4),  # Unoccupied wing
            ZoneMapping("Zone-L11-S-A", "Zone-L11-S", "L11", "South A", "open_office", 4),
            ZoneMapping("Zone-L11-S-B", "Zone-L11-S", "L11", "South B", "open_office", 4),
            ZoneMapping("Zone-L11-MR", "Zone-L11-MR", "L11", "Meeting Rooms", "meeting_room", 2),

            # Level 10
            ZoneMapping("Zone-L10-N", "Zone-L10-N", "L10", "North Open Plan", "open_office", 3),
            ZoneMapping("Zone-L10-N-A", "Zone-L10-N", "L10", "North A", "open_office", 3),
            ZoneMapping("Zone-L10-N-B", "Zone-L10-N", "L10", "North B", "open_office", 3),
            ZoneMapping("Zone-L10-S", "Zone-L10-S", "L10", "South Open Plan", "open_office", 3),
            ZoneMapping("Zone-L10-S-A", "Zone-L10-S", "L10", "South A", "open_office", 3),
            ZoneMapping("Zone-L10-S-B", "Zone-L10-S", "L10", "South B", "open_office", 3),
            ZoneMapping("Zone-L10-MR", "Zone-L10-MR", "L10", "Meeting Rooms", "meeting_room", 2),
        ]

        for mapping in default_mappings:
            self._mappings[mapping.hvac_zone_id] = mapping
            self._hvac_to_dali[mapping.hvac_zone_id] = mapping.dali_zone_id

            if mapping.dali_zone_id not in self._dali_to_hvac:
                self._dali_to_hvac[mapping.dali_zone_id] = []
            if mapping.hvac_zone_id not in self._dali_to_hvac[mapping.dali_zone_id]:
                self._dali_to_hvac[mapping.dali_zone_id].append(mapping.hvac_zone_id)

        logger.info(f"Generated {len(self._mappings)} default zone mappings")

    def get_dali_zone_for_hvac(self, hvac_zone_id: str) -> Optional[str]:
        """Get the corresponding DALI zone for an HVAC zone.

        Args:
            hvac_zone_id: HVAC zone identifier

        Returns:
            DALI zone ID or None if no mapping exists
        """
        return self._hvac_to_dali.get(hvac_zone_id)

    def get_hvac_zones_for_dali(self, dali_zone_id: str) -> List[str]:
        """Get all HVAC zones that map to a DALI zone.

        Args:
            dali_zone_id: DALI zone identifier

        Returns:
            List of HVAC zone IDs
        """
        return self._dali_to_hvac.get(dali_zone_id, [])

    def get_mapping(self, hvac_zone_id: str) -> Optional[ZoneMapping]:
        """Get full mapping details for an HVAC zone."""
        return self._mappings.get(hvac_zone_id)

    def get_all_mappings(self) -> List[ZoneMapping]:
        """Get all zone mappings."""
        return list(self._mappings.values())

    def get_zones_by_floor(self, floor: str) -> List[ZoneMapping]:
        """Get all zone mappings for a specific floor."""
        return [m for m in self._mappings.values() if m.floor == floor]

    def get_zones_by_type(self, zone_type: str) -> List[ZoneMapping]:
        """Get all zone mappings of a specific type."""
        return [m for m in self._mappings.values() if m.zone_type == zone_type]

    def get_zones_by_priority(self, max_priority: int) -> List[ZoneMapping]:
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


# Singleton instance
_zone_mapping_service: Optional[ZoneMappingService] = None


def get_zone_mapping_service() -> ZoneMappingService:
    """Get the singleton zone mapping service instance."""
    global _zone_mapping_service
    if _zone_mapping_service is None:
        _zone_mapping_service = ZoneMappingService()
    return _zone_mapping_service

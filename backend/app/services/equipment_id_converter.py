"""Equipment ID Converter - Convert legacy BMS IDs to SENTINEL v2.0 standard.

Converts equipment identifiers from various BMS formats to the standardized
SENTINEL v2.0 naming convention: {site}-{type}-{floor}-{zone}

Examples:
  "CH-1" → "S002-CHILLER-B1-001"
  "VAV-L1-05" → "S002-VAV-L1-E"
  "AHU-G-01" → "S002-AHU-G-001"
  "FCU-L2-A" → "S002-FCU-L2-A"
"""

import logging
import json
from typing import Dict, Optional, Tuple
from pathlib import Path
import re

logger = logging.getLogger(__name__)

# Equipment type mappings from various BMS formats to SENTINEL types
EQUIPMENT_TYPE_MAPPINGS = {
    # Chillers
    "ch": "CHILLER",
    "chiller": "CHILLER",
    "chill": "CHILLER",
    "chw": "CHILLER",
    # Air Handling Units
    "ahu": "AHU",
    "ah": "AHU",
    "air_handler": "AHU",
    # Fan Coil Units
    "fcu": "FCU",
    "fc": "FCU",
    "fan_coil": "FCU",
    # Variable Air Volume
    "vav": "VAV",
    "va": "VAV",
    # Cooling Tower
    "ct": "CT",
    "cooling_tower": "CT",
    "ctower": "CT",
    # CRAC / CRAH
    "crac": "CRAC",
    "crah": "CRAC",
    # Generators
    "gen": "GEN",
    "generator": "GEN",
    # Transformers
    "tx": "TX",
    "transformer": "TX",
    "trans": "TX",
    # UPS
    "ups": "UPS",
    # ATS
    "ats": "ATS",
    # Main Switchboard
    "msb": "MSB",
    "switchboard": "MSB",
    "main_board": "MSB",
    # Meter
    "mtr": "MTR",
    "meter": "MTR",
    # Power Factor Correction
    "pfc": "PFC",
    # Feeder
    "fdr": "FDR",
    "feeder": "FDR",
    # Medium Voltage
    "mv": "MV",
    "medium_voltage": "MV",
    # Distribution Board
    "db": "DB",
    "distribution": "DB",
    # DALI Lighting
    "dali": "DALI",
    # Luminaire
    "lum": "LUM",
    "light": "LUM",
    "luminaire": "LUM",
    # Fire
    "fire": "FIRE",
    "fire_system": "FIRE",
    # Access Control
    "acc": "ACC",
    "access": "ACC",
    "door": "ACC",
    # CCTV
    "cctv": "CCTV",
    "camera": "CCTV",
    "video": "CCTV",
}

# Floor aliases mapping (normalize variations)
FLOOR_ALIASES = {
    "basement": "B",
    "b1": "B1",
    "b2": "B2",
    "ground": "G",
    "ground floor": "G",
    "gf": "G",
    "level": "L",
    "l1": "L1",
    "l2": "L2",
    "l3": "L3",
    "l4": "L4",
    "l5": "L5",
    "l10": "L10",
    "l11": "L11",
    "l12": "L12",
    "roof": "R",
    "r1": "R",
    "mezzanine": "M",
    "penthouse": "PH",
}


class EquipmentIDConverter:
    """Convert legacy BMS equipment IDs to SENTINEL v2.0 standard.

    v2.0 Format: {site}-{type}-{floor}-{zone_or_seq}
    Example: S002-CHILLER-B1-001

    Site codes: S### (3-digit zero-padded)
    Types: CHILLER, AHU, FCU, VAV, DALI, etc.
    Floors: B1/B2, G, L1-L12, R, M, PH
    Zones: A-Z (letters) or 001-999 (numeric)
    """

    def __init__(self):
        """Initialize converter with site zone mappings."""
        self.zone_mappings = self._load_zone_mappings()

    def _load_zone_mappings(self) -> Dict[str, Dict[str, str]]:
        """Load site-specific zone mappings from JSON file."""
        try:
            config_path = (
                Path(__file__).parent.parent / "data" / "niagara" / "site_zone_mappings.json"
            )
            if config_path.exists():
                with open(config_path) as f:
                    data = json.load(f)
                return data
        except Exception as e:
            logger.warning(f"Failed to load zone mappings: {e}")

        # Return default empty structure
        return {"default": {"zone_number_to_letter": {}}}

    def convert_bms_to_v2(
        self,
        bms_id: str,
        equipment_type: str,
        site_id: str,
        zone_mapping: Optional[Dict[str, str]] = None,
    ) -> str:
        """Convert BMS equipment ID to SENTINEL v2.0 standard.

        Args:
            bms_id: Original BMS equipment ID (e.g., "CH-1", "VAV-L1-05")
            equipment_type: Equipment type (e.g., "chiller", "vav", "fcu")
            site_id: Site identifier (e.g., "site-002")
            zone_mapping: Optional site-specific zone mappings

        Returns:
            v2.0 standard equipment ID (e.g., "S002-CHILLER-B1-001")
        """
        # Normalize inputs
        bms_id = bms_id.strip()
        equipment_type = equipment_type.strip().lower()

        # Extract site prefix (S###)
        site_prefix = self._extract_site_prefix(site_id)

        # Normalize equipment type
        normalized_type = self._normalize_equipment_type(equipment_type)
        if not normalized_type:
            logger.warning(f"Unknown equipment type: {equipment_type}")
            normalized_type = "UNKNOWN"

        # Parse floor and zone from BMS ID
        floor, zone = self.parse_floor_zone(bms_id)

        # Convert zone number to letter if needed
        if zone and zone.isdigit():
            zone = self.map_zone_number_to_letter(zone, site_id, zone_mapping)

        # Build v2.0 ID
        if not floor or not zone:
            # Fallback: use sequence number from BMS ID
            sequence = self._extract_sequence(bms_id)
            v2_id = f"{site_prefix}-{normalized_type}-B1-{sequence:03d}"
        else:
            # Clean zone: ensure it's a single character (A-Z) or numeric
            zone = zone.upper() if zone else "001"
            v2_id = f"{site_prefix}-{normalized_type}-{floor}-{zone}"

        logger.debug(
            f"Converted BMS ID '{bms_id}' (type={equipment_type}) "
            f"→ v2.0 ID '{v2_id}' (site={site_id})"
        )

        return v2_id

    def parse_floor_zone(self, bms_id: str) -> Tuple[str, str]:
        """Extract floor and zone from BMS equipment ID.

        Examples:
          "FCU-L2-A" → ("L2", "A")
          "VAV-L1-05" → ("L1", "05")
          "AHU-G-01" → ("G", "01")
          "CH-B1-01" → ("B1", "01")
          "CHILLER-001" → ("B1", "001")

        Returns:
            Tuple of (floor, zone) or ("B1", extracted_sequence) as fallback
        """
        bms_id = bms_id.upper().strip()

        # Try pattern: EQUIPMENT-FLOOR-ZONE (e.g., FCU-L2-A, VAV-L1-05)
        match = re.search(r"-(B\d|B|G|L\d+|M|R|PH)[-_]([A-Z]|0?\d{1,3})(?:$|[-_])", bms_id)
        if match:
            floor = match.group(1)
            zone = match.group(2)
            return (floor, zone)

        # Try pattern: FLOOR-ZONE separated by anything (e.g., AHU_L1_01)
        match = re.search(r"([BL]\d{1,2}|[BGR]|M|PH)[_-]([A-Z]|0?\d{1,3})", bms_id)
        if match:
            floor = match.group(1)
            zone = match.group(2)
            return (floor, zone)

        # Try to find just floor without zone
        match = re.search(r"(B\d|B|G|L\d{1,2}|M|R|PH)", bms_id)
        if match:
            floor = match.group(1)
            sequence = self._extract_sequence(bms_id)
            return (floor, f"{sequence:03d}")

        # Fallback
        logger.debug(f"Could not parse floor/zone from BMS ID: {bms_id}")
        sequence = self._extract_sequence(bms_id)
        return ("B1", f"{sequence:03d}")

    def map_zone_number_to_letter(
        self,
        zone_num: str,
        site_id: str,
        override_mapping: Optional[Dict[str, str]] = None,
    ) -> str:
        """Convert numeric zone to letter per site-specific mapping.

        Only converts if explicit mapping exists. Otherwise returns numeric
        zone in 3-digit format (001, 002, etc).

        Args:
            zone_num: Numeric zone (e.g., "01", "05", "20")
            site_id: Site identifier (e.g., "site-002")
            override_mapping: Optional override mapping dict

        Returns:
            Letter zone (A-Z) if mapping found, else 3-digit numeric (001, 002, etc)
        """
        # Use override if provided
        if override_mapping and zone_num in override_mapping:
            return override_mapping[zone_num]

        # Try site-specific mapping
        site_code = site_id.replace("site-", "").lstrip("0")  # "site-002" → "2"
        site_key = f"site-{site_code.zfill(3)}"  # "site-002"

        if site_key in self.zone_mappings:
            zone_to_letter = self.zone_mappings[site_key].get("zone_number_to_letter", {})
            if zone_num in zone_to_letter:
                return zone_to_letter[zone_num]

        # Try default mapping
        default_mapping = self.zone_mappings.get("default", {}).get("zone_number_to_letter", {})
        if zone_num in default_mapping:
            return default_mapping[zone_num]

        # Fallback: return as 3-digit numeric sequence
        try:
            num = int(zone_num.lstrip("0") or "0")
            return f"{num:03d}"  # Convert to 3-digit format (001, 002, etc)
        except ValueError:
            return zone_num  # Return as-is if not numeric

    def _normalize_equipment_type(self, equipment_type: str) -> str:
        """Normalize equipment type to SENTINEL standard.

        Args:
            equipment_type: Equipment type string (any case, variations)

        Returns:
            Normalized type (e.g., "CHILLER", "AHU", "FCU") or empty string if unknown
        """
        equipment_type = equipment_type.strip().lower()

        # Direct mapping
        if equipment_type in EQUIPMENT_TYPE_MAPPINGS:
            return EQUIPMENT_TYPE_MAPPINGS[equipment_type]

        # Try partial matches
        for key, value in EQUIPMENT_TYPE_MAPPINGS.items():
            if key in equipment_type or equipment_type in key:
                return value

        return ""

    def _extract_site_prefix(self, site_id: str) -> str:
        """Extract S### prefix from site ID.

        Args:
            site_id: Site identifier (e.g., "site-002", "S002", "002")

        Returns:
            S### format (e.g., "S002")
        """
        # Remove "site-" prefix if present
        site_id = site_id.replace("site-", "").replace("site_", "").strip()

        # Extract digits
        digits = re.findall(r"\d+", site_id)
        if digits:
            site_num = digits[0].zfill(3)  # Ensure 3 digits
            return f"S{site_num}"

        return "S000"  # Fallback

    def _extract_sequence(self, bms_id: str) -> int:
        """Extract numeric sequence from BMS ID for fallback naming.

        Args:
            bms_id: BMS equipment ID

        Returns:
            Sequence number (001-999)
        """
        # Find all numbers in the ID
        numbers = re.findall(r"\d+", bms_id)
        if numbers:
            # Use the last number as sequence
            seq = int(numbers[-1])
            return min(seq, 999)  # Cap at 999
        return 1

    def detect_bms_format(self, bms_id: str) -> str:
        """Detect the BMS ID format/pattern.

        Returns:
            Format description (e.g., "EQUIPMENT-FLOOR-ZONE", "LEGACY_SANDTON", etc.)
        """
        bms_id = bms_id.upper().strip()

        # Legacy Sandton format: 011-stc-ahu-001
        if re.match(r"^\d{3}-[a-z]{3}-[a-z]{2,4}-\d{3}$", bms_id, re.IGNORECASE):
            return "LEGACY_SANDTON"

        # Niagara format: EQUIPMENT-FLOOR-ZONE
        if re.search(r"-[BL]\d{1,2}[-_][A-Z0-9]{1,3}(?:$|[-_])", bms_id):
            return "EQUIPMENT-FLOOR-ZONE"

        # Simple equipment-number: CH-1, AHU-01
        if re.match(r"^[A-Z]{2,4}-\d{1,3}$", bms_id):
            return "EQUIPMENT-NUMBER"

        return "UNKNOWN"

"""Equipment ID Converter for BMS → SENTINEL v2.0 standard naming.

Converts legacy BMS equipment IDs to SENTINEL v2.0 standard format:
  Legacy: CH-1, VAV-L1-05, 011-stc-ahu-001
  v2.0:   S002-CHILLER-B1-001, S002-VAV-L1-E, S002-AHU-L0-01

This enables:
- Consistent naming across all equipment
- Automatic technician specialty assignment (based on equipment type)
- Zone-based optimization (HVAC zones for cross-system coordination)
- Fleet-wide analytics and comparisons
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class EquipmentIDConverter:
    """Converts legacy BMS equipment IDs to SENTINEL v2.0 standard."""

    # Type code mappings: legacy → v2.0 standard uppercase
    TYPE_MAPPINGS = {
        # HVAC
        "ch": "CHILLER",
        "chiller": "CHILLER",
        "ahu": "AHU",
        "fcu": "FCU",
        "vav": "VAV",
        "ac": "SPLIT",
        "split": "SPLIT",
        "ct": "CT",
        "cooling_tower": "CT",
        "crac": "CRAC",
        "pump": "PUMP",
        "boiler": "BOILER",
        "cold": "COLD",
        "kef": "KEF",
        # Lighting
        "dali": "DALI",
        "dali_zone": "DALI",
        "dali_controller": "DALI",
        "lum": "LUM",
        "luminaire": "LUM",
        "lighting": "LUM",
        "zone": "DALI",          # Niagara zone controller → DALI lighting
        "zone_controller": "DALI",
        # Energy
        "gen": "GEN",
        "generator": "GEN",
        "tx": "TX",
        "transformer": "TX",
        "ups": "UPS",
        "ats": "ATS",
        "msb": "MSB",
        "mtr": "MTR",
        "meter": "MTR",
        "pfc": "PFC",
        "fdr": "FDR",
        "mv": "MV",
        "db": "DB",
        # Transport / Vertical
        "lift": "LIFT",
        "elevator": "LIFT",
        # Medical
        "medgas": "MEDGAS",
        # Controllers
        "jace": "JACE",
        # Fuel
        "tank": "TANK",
        # Other
        "fire": "FIRE",
        "acc": "ACC",
        "cctv": "CCTV",
        "bms": "BMS",
        "pxc": "PXC",
    }

    # Default zone number to letter mappings
    DEFAULT_ZONE_MAP = {
        "01": "A",
        "02": "B",
        "03": "C",
        "04": "D",
        "05": "E",
        "06": "F",
        "07": "G",
        "08": "H",
        "09": "I",
        "10": "J",
        "11": "K",
        "12": "L",
        "13": "M",
        "14": "N",
        "15": "O",
        "16": "P",
        "17": "Q",
        "18": "R",
        "19": "S",
        "20": "T",
    }

    def __init__(self):
        """Initialize converter with site-specific zone mappings."""
        self.site_zone_mappings = self._load_site_zone_mappings()

    def _load_site_zone_mappings(self) -> dict[str, dict[str, Any]]:
        """Load site-specific zone mappings from config file."""
        config_path = Path(__file__).parent.parent / "data" / "niagara" / "site_zone_mappings.json"

        if config_path.exists():
            try:
                with open(config_path) as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load site zone mappings: {e}")

        return {"default": {"zone_number_to_letter": self.DEFAULT_ZONE_MAP}}

    def convert_bms_to_v2(
        self,
        bms_id: str,
        equipment_type: str,
        site_id: str,
        zone_mapping: dict[str, str] | None = None,
    ) -> str:
        """Convert BMS equipment ID to SENTINEL v2.0 standard.

        Args:
            bms_id: Original BMS equipment ID (e.g., "CH-1", "VAV-L1-05")
            equipment_type: Equipment type (e.g., "chiller", "vav")
            site_id: Site identifier (e.g., "site-002")
            zone_mapping: Optional site-specific zone number→letter mappings

        Returns:
            v2.0 formatted equipment ID (e.g., "S002-CHILLER-B1-001")

        Examples:
            convert_bms_to_v2("CH-1", "chiller", "site-002")
            → "S002-CHILLER-B1-001"

            convert_bms_to_v2("VAV-L1-05", "vav", "site-002", zone_mapping={"05": "E"})
            → "S002-VAV-L1-E"

            convert_bms_to_v2("011-stc-ahu-001", "ahu", "site-002")
            → "S002-AHU-L0-01"
        """
        logger.debug(f"Converting BMS ID '{bms_id}' (type: {equipment_type}, site: {site_id})")

        # Normalize equipment type
        normalized_type = self._normalize_equipment_type(equipment_type)
        if not normalized_type:
            logger.warning(f"Unknown equipment type: {equipment_type}, using as-is")
            normalized_type = equipment_type.upper()

        # Extract site prefix (S###)
        site_prefix = self._extract_site_prefix(site_id)

        # Parse floor and zone from BMS ID
        floor_zone = self.parse_floor_zone(bms_id)

        # If parsing fails, provide defaults
        if not floor_zone:
            floor = "B1"  # Default to basement
            zone_or_seq = "001"  # Default sequence
            logger.warning(f"Could not parse floor/zone from '{bms_id}', using defaults: {floor}/{zone_or_seq}")
        else:
            floor = floor_zone.get("floor", "B1")
            zone_value = floor_zone.get("zone", "001")

            # Convert zone number to letter if needed
            if zone_value.isdigit() and len(zone_value) <= 2:
                zone_number = zone_value.zfill(2)
                zone_mapping_dict = zone_mapping or self._get_zone_mappings_for_site(site_id)
                zone_or_seq = zone_mapping_dict.get(zone_number, zone_number.lstrip("0") or "A")
            else:
                zone_or_seq = zone_value

        # Build v2.0 format
        v2_id = f"{site_prefix}-{normalized_type}-{floor}-{zone_or_seq}"
        logger.info(f"Converted '{bms_id}' → '{v2_id}' (type: {normalized_type}, floor: {floor}, zone: {zone_or_seq})")

        return v2_id

    def parse_floor_zone(self, bms_id: str) -> dict[str, str] | None:
        """Extract floor and zone from BMS equipment ID.

        Args:
            bms_id: BMS equipment ID (e.g., "FCU-L2-A", "VAV-L12-03", "AHU-G-01")

        Returns:
            Dict with 'floor' and 'zone' keys, or None if parsing fails

        Examples:
            parse_floor_zone("FCU-L2-A") → {"floor": "L2", "zone": "A"}
            parse_floor_zone("VAV-L12-03") → {"floor": "L12", "zone": "03"}
            parse_floor_zone("AHU-G-01") → {"floor": "G", "zone": "01"}
            parse_floor_zone("CHILLER-001") → None (no floor info)
        """
        # Normalize input
        normalized = bms_id.upper().replace("_", "-")

        # Try various parsing patterns (most specific first)
        patterns = [
            # Pattern 1: TYPE-FLOOR-ZONE (e.g., FCU-L2-A)
            r"(?:FCU|VAV|AHU|DALI|LUM|TS|CO2|OCC|DLS|ACC|CCTV|SPLIT|CRAC)-([BGL]\d*|G|R)-([A-Z0-9]{1,3})",
            # Pattern 2: TYPE-FLOOR-ZONE with optional hyphen variations (e.g., CH-B1-01)
            r"(?:CH|GEN|TX|UPS|ATS|MSB|MTR|PFC|FDR|MV|DB|CT|FIRE|BMS)-([B][0-9]|G|[L][0-9]+|R)-([A-Z0-9]{1,3})",
            # Pattern 3: Simple floor code (e.g., AHU-G-01 or AHU-L12-1)
            r"([B][0-9]|G|[L][0-9]+|R)-([A-Z0-9]{1,3})$",
        ]

        for pattern in patterns:
            match = re.search(pattern, normalized)
            if match:
                floor = match.group(1)
                zone = match.group(2)

                # Normalize floor format
                floor = self._normalize_floor(floor)

                logger.debug(f"Parsed '{bms_id}': floor='{floor}', zone='{zone}'")
                return {"floor": floor, "zone": zone}

        # Pattern 4: Vendor-agnostic fallback — find floor code anywhere in a
        # hyphen/dot-separated ID. Handles Niagara (site-005-UMH-AHU-L3-ICU),
        # Desigo, Schneider, etc. Looks for L##, B##, G, R as a standalone segment.
        segments = re.split(r"[-.]", normalized)
        for i, seg in enumerate(segments):
            floor_match = re.match(r"^(L\d+|B\d+|G|R|PH|M)$", seg)
            if floor_match:
                floor = self._normalize_floor(floor_match.group(1))
                # Use next segment as zone/location if available
                zone = segments[i + 1] if i + 1 < len(segments) else "001"
                # Clean zone: strip trailing dot-parts (e.g., from "ICU.FAN")
                zone = re.sub(r"\..*", "", zone)
                if not zone or len(zone) > 10:
                    zone = "001"
                logger.debug(f"Parsed '{bms_id}' (vendor-agnostic): floor='{floor}', zone='{zone}'")
                return {"floor": floor, "zone": zone}

        logger.debug(f"Could not parse floor/zone from '{bms_id}'")
        return None

    def _normalize_equipment_type(self, equipment_type: str) -> str | None:
        """Normalize equipment type to v2.0 standard uppercase.

        Args:
            equipment_type: Equipment type (e.g., "chiller", "VAV", "ahu")

        Returns:
            Normalized uppercase type (e.g., "CHILLER") or None if not found
        """
        normalized = equipment_type.lower().replace(" ", "_").strip()
        return self.TYPE_MAPPINGS.get(normalized)

    def _normalize_floor(self, floor: str) -> str:
        """Normalize floor code to v2.0 format.

        Examples:
            B1 → B1
            b1 → B1
            Ground → G
            Level 1 → L1
            L12 → L12
        """
        floor = floor.upper().strip()

        # Already normalized
        if re.match(r"^(B\d+|G|L\d+|M|R|PH)$", floor):
            return floor

        # Expand aliases
        aliases = {
            "BASEMENT": "B",
            "GROUND": "G",
            "LEVEL": "L",
            "L0": "L0",
            "MEZZANINE": "M",
            "ROOF": "R",
            "PENTHOUSE": "PH",
        }

        for alias, code in aliases.items():
            if alias in floor:
                # Extract number if present (e.g., "LEVEL 12" → "L12")
                numbers = re.findall(r"\d+", floor)
                if numbers:
                    return f"{code}{numbers[0]}"
                return code

        # Default fallback
        logger.warning(f"Could not normalize floor '{floor}', using 'B1'")
        return "B1"

    def _extract_site_prefix(self, site_id: str) -> str:
        """Extract site prefix from site ID.

        Args:
            site_id: Site identifier (e.g., "site-002")

        Returns:
            Site prefix in v2.0 format (e.g., "S002")

        Examples:
            _extract_site_prefix("site-002") → "S002"
            _extract_site_prefix("S002") → "S002"
            _extract_site_prefix("02") → "S002"
        """
        # Extract numeric part
        numbers = re.findall(r"\d+", site_id)
        if not numbers:
            logger.warning(f"Could not extract site number from '{site_id}', using 'S001'")
            return "S001"

        site_num = numbers[0]
        # Zero-pad to 3 digits
        site_prefix = f"S{site_num.zfill(3)}"
        return site_prefix

    def _get_zone_mappings_for_site(self, site_id: str) -> dict[str, str]:
        """Get zone number→letter mappings for a specific site.

        Args:
            site_id: Site identifier (e.g., "site-002")

        Returns:
            Dict mapping zone numbers to letters (e.g., {"01": "A", "02": "B"})
        """
        # Extract site number
        site_num = re.findall(r"\d+", site_id)
        site_code = f"site-{site_num[0]}" if site_num else site_id

        # Check for site-specific mappings
        if site_code in self.site_zone_mappings:
            mappings = self.site_zone_mappings[site_code].get("zone_number_to_letter")
            if mappings:
                return mappings

        # Fall back to default
        return self.site_zone_mappings.get("default", {}).get("zone_number_to_letter", self.DEFAULT_ZONE_MAP)

    def map_zone_number_to_letter(self, zone_num: str, site_id: str) -> str:
        """Convert numeric zone to letter per site-specific mapping.

        Args:
            zone_num: Zone number (e.g., "01", "05")
            site_id: Site identifier (e.g., "site-002")

        Returns:
            Zone letter (e.g., "A", "E")

        Examples:
            map_zone_number_to_letter("01", "site-002") → "A"
            map_zone_number_to_letter("05", "site-002") → "E"
        """
        zone_num_padded = zone_num.zfill(2)
        mappings = self._get_zone_mappings_for_site(site_id)
        result = mappings.get(zone_num_padded, zone_num_padded.lstrip("0") or "A")
        logger.debug(f"Zone {zone_num} (site {site_id}) → {result}")
        return result


# Singleton instance
_converter: EquipmentIDConverter | None = None


def get_equipment_id_converter() -> EquipmentIDConverter:
    """Get the singleton equipment ID converter instance."""
    global _converter
    if _converter is None:
        _converter = EquipmentIDConverter()
    return _converter

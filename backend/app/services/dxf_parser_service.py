"""DXF Parser Service - Parse AutoCAD drawings for equipment extraction.

Handles DXF file parsing with layer-based equipment classification.
Extracts equipment positions, types, and floor/zone assignments from
professional CAD drawings using standardized layer conventions.

**Supported DXF Versions:** AutoCAD R12 through 2024

**Layer Conventions:**
- AR-WALL: Building walls and structure
- AE-HVAC: HVAC equipment (chillers, AHUs, FCUs, VAVs)
- EL-POWER: Electrical equipment (generators, transformers, UPS)
- FP-LIFE: Fire protection and life safety equipment
"""

import re
import logging
import tempfile
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from collections import defaultdict

import ezdxf
from ezdxf.document import Drawing

from app.services.geometry_utils import (
    BoundingBox,
    calculate_bounding_box,
    normalize_coordinates,
    infer_floor_from_z_coordinate,
)

logger = logging.getLogger(__name__)


@dataclass
class DXFEquipment:
    """Equipment extracted from DXF."""

    name: str
    equipment_type: str
    floor: str
    x: float
    y: float
    zone: str
    confidence: float = 0.95


class DXFParserService:
    """Parse DXF (AutoCAD) files to extract building equipment."""

    # Equipment type mappings for legacy name classification
    TYPE_MAPPINGS = {
        "ch-": "CHILLER",
        "chiller": "CHILLER",
        "ahu": "AHU",
        "fcu": "FCU",
        "vav": "VAV",
        "split": "SPLIT",
        "ct": "CT",  # Cooling tower
        "crac": "CRAC",
        "gen": "GEN",
        "tx": "TX",  # Transformer
        "ups": "UPS",
        "ats": "ATS",
        "msb": "MSB",
        "mtr": "MTR",  # Meter
        "pfc": "PFC",
        "fdr": "FDR",
        "mv": "MV",
        "db": "DB",
        "dali": "DALI",
        "lum": "LUM",
        "fire": "FIRE",
        "acc": "ACC",
        "cctv": "CCTV",
    }

    def __init__(self):
        """Initialize parser service."""
        pass

    async def parse_dxf_file(
        self,
        dxf_bytes: bytes,
        building_code: str,
        building_name: str,
    ) -> Dict[str, Any]:
        """
        Main entry point: parse DXF and return BuildingConfig format.

        Returns same structure as digital_twin_service.extract_from_image()
        for seamless API integration.

        Args:
            dxf_bytes: DXF file content (bytes)
            building_code: Building identifier (e.g., "site-002")
            building_name: Building name (e.g., "Sandton City")

        Returns:
            Dict with keys: equipment, floors, zones, extraction_metadata
        """
        try:
            # 1. Load DXF document
            doc = self._load_dxf(dxf_bytes)
            logger.info(f"✓ Loaded DXF: {doc.dxfversion}")

            # 2. Calculate bounding box for coordinate normalization
            bbox = self._calculate_floor_plan_bbox(doc)
            logger.info(f"✓ Floor plan bbox: {bbox.width:.1f}m x {bbox.height:.1f}m")

            # 3. Extract equipment from layers
            equipment = []
            equipment.extend(self._extract_hvac_equipment(doc, bbox, building_code))
            equipment.extend(self._extract_electrical_equipment(doc, bbox, building_code))
            equipment.extend(self._extract_fire_equipment(doc, bbox, building_code))

            logger.info(f"✓ Extracted {len(equipment)} equipment (HVAC, Electrical, Fire)")

            # 4. Infer floors from equipment positions
            floors = self._infer_floor_definitions(equipment)
            logger.info(f"✓ Inferred {len(floors)} floors: {[f['level'] for f in floors]}")

            # 5. Create zones from equipment clustering
            zones = self._create_zones_from_equipment(equipment)
            logger.info(f"✓ Created {len(zones)} zones")

            # 6. Return config
            return {
                "building_code": building_code,
                "building_name": building_name,
                "equipment": equipment,
                "floors": floors,
                "zones": zones,
                "extraction_metadata": {
                    "method": "dxf_parser",
                    "equipment_count": len(equipment),
                    "floor_count": len(floors),
                    "zone_count": len(zones),
                },
            }

        except Exception as e:
            logger.error(f"DXF parsing failed: {e}", exc_info=True)
            raise

    def _load_dxf(self, dxf_bytes: bytes) -> Drawing:
        """
        Load DXF from bytes.

        Args:
            dxf_bytes: DXF file content

        Returns:
            ezdxf Drawing object

        Raises:
            ValueError: If DXF is invalid or unsupported version
        """
        # Write to temporary file for ezdxf.readfile()
        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
            temp_path = f.name
            f.write(dxf_bytes)

        try:
            doc = ezdxf.readfile(temp_path)
            return doc
        except ezdxf.DXFStructureError as e:
            raise ValueError(f"Invalid DXF file structure: {e}")
        except ezdxf.DXFVersionError as e:
            raise ValueError(f"Unsupported DXF version: {e}")
        except Exception as e:
            raise ValueError(f"Failed to load DXF: {e}")
        finally:
            # Clean up temp file
            try:
                os.remove(temp_path)
            except Exception:
                pass

    def _calculate_floor_plan_bbox(self, doc: Drawing) -> BoundingBox:
        """
        Calculate bounding box from AR-WALL layer.

        Falls back to modelspace extents if AR-WALL not found.

        Args:
            doc: ezdxf Drawing

        Returns:
            BoundingBox covering floor plan walls
        """
        msp = doc.modelspace()

        # Try AR-WALL layer first (preferred)
        try:
            wall_entities = list(msp.query('*[layer=="AR-WALL"]'))
            if wall_entities:
                return calculate_bounding_box(wall_entities)
        except Exception as e:
            logger.debug(f"AR-WALL layer not found or error: {e}")

        # Fallback to all entities
        try:
            all_entities = list(msp.query("*"))
            if all_entities:
                return calculate_bounding_box(all_entities)
        except Exception as e:
            logger.debug(f"Could not calculate bbox from entities: {e}")

        # Last resort: return default
        logger.warning("Using default floor plan bbox")
        return BoundingBox(0, 0, 150, 120)

    def _extract_hvac_equipment(
        self,
        doc: Drawing,
        bbox: BoundingBox,
        building_code: str,
    ) -> List[Dict[str, Any]]:
        """
        Extract HVAC equipment from AE-HVAC layer.

        Extracts:
        - CHILLER (CH-*, CHILLER-*)
        - AHU (AHU-*)
        - FCU (FCU-*)
        - VAV (VAV-*)
        - SPLIT (SPLIT-*)
        - CT (CT-*, Cooling Tower)
        - CRAC (CRAC-*)

        Strategy:
        1. Query layer: AE-HVAC
        2. Filter entity types: INSERT (blocks), TEXT/MTEXT (labels)
        3. Extract equipment name from block name or text
        4. Extract position and classify type
        5. Normalize coordinates and infer floor/zone
        6. Convert to v2.0 format

        Args:
            doc: ezdxf Drawing
            bbox: Bounding box for coordinate normalization
            building_code: Site code (e.g., "site-002")

        Returns:
            List of equipment dicts
        """
        equipment = []
        msp = doc.modelspace()

        try:
            hvac_entities = list(msp.query('*[layer=="AE-HVAC"]'))
        except Exception as e:
            logger.debug(f"AE-HVAC query failed: {e}")
            hvac_entities = []

        logger.debug(f"Found {len(hvac_entities)} AE-HVAC entities")

        for entity in hvac_entities:
            try:
                eq_data = self._extract_equipment_from_entity(entity, bbox, building_code, "HVAC")
                if eq_data:
                    equipment.append(eq_data)
            except Exception as e:
                logger.debug(f"Error extracting HVAC equipment: {e}")
                continue

        return equipment

    def _extract_electrical_equipment(
        self,
        doc: Drawing,
        bbox: BoundingBox,
        building_code: str,
    ) -> List[Dict[str, Any]]:
        """
        Extract electrical equipment from EL-POWER layer.

        Extracts:
        - GEN (Generators)
        - TX (Transformers)
        - UPS (Uninterruptible Power Supply)
        - ATS (Automatic Transfer Switch)
        - MSB (Main Switchboard)
        - DB (Distribution Boards)
        - MTR (Meter)
        - PFC (Power Factor Correction)
        - FDR (Feeder)
        - MV (Medium Voltage)

        Args:
            doc: ezdxf Drawing
            bbox: Bounding box for coordinate normalization
            building_code: Site code

        Returns:
            List of equipment dicts
        """
        equipment = []
        msp = doc.modelspace()

        try:
            power_entities = list(msp.query('*[layer=="EL-POWER"]'))
        except Exception as e:
            logger.debug(f"EL-POWER query failed: {e}")
            power_entities = []

        logger.debug(f"Found {len(power_entities)} EL-POWER entities")

        for entity in power_entities:
            try:
                eq_data = self._extract_equipment_from_entity(entity, bbox, building_code, "Electrical")
                if eq_data:
                    equipment.append(eq_data)
            except Exception as e:
                logger.debug(f"Error extracting electrical equipment: {e}")
                continue

        return equipment

    def _extract_fire_equipment(
        self,
        doc: Drawing,
        bbox: BoundingBox,
        building_code: str,
    ) -> List[Dict[str, Any]]:
        """
        Extract fire/safety equipment from FP-LIFE layer.

        Extracts:
        - Fire detectors
        - Sprinklers
        - Fire panels
        - Life safety equipment

        Args:
            doc: ezdxf Drawing
            bbox: Bounding box for coordinate normalization
            building_code: Site code

        Returns:
            List of equipment dicts
        """
        equipment = []
        msp = doc.modelspace()

        try:
            fire_entities = list(msp.query('*[layer=="FP-LIFE"]'))
        except Exception as e:
            logger.debug(f"FP-LIFE query failed: {e}")
            fire_entities = []

        logger.debug(f"Found {len(fire_entities)} FP-LIFE entities")

        for entity in fire_entities:
            try:
                eq_data = self._extract_equipment_from_entity(entity, bbox, building_code, "Fire")
                if eq_data:
                    equipment.append(eq_data)
            except Exception as e:
                logger.debug(f"Error extracting fire equipment: {e}")
                continue

        return equipment

    def _extract_equipment_from_entity(
        self,
        entity,
        bbox: BoundingBox,
        building_code: str,
        layer_type: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Extract equipment from a single DXF entity.

        Handles INSERT blocks and TEXT labels.

        Args:
            entity: DXF entity (INSERT, TEXT, MTEXT, etc.)
            bbox: Bounding box for coordinate normalization
            building_code: Site code
            layer_type: Layer category (HVAC, Electrical, Fire)

        Returns:
            Equipment dict or None if extraction fails
        """
        # Get equipment name
        eq_name = None

        if entity.dxftype() == "INSERT":
            # Try block attributes first
            eq_name = self._extract_name_from_attributes(entity)

            # Fallback to block name
            if not eq_name and hasattr(entity.dxf, "name"):
                eq_name = entity.dxf.name

        elif entity.dxftype() in ["TEXT", "MTEXT"]:
            # Extract text content
            if hasattr(entity.dxf, "text"):
                eq_name = entity.dxf.text

        if not eq_name:
            return None

        # Classify equipment type
        eq_type = self._classify_equipment_type(eq_name)
        if eq_type == "UNKNOWN":
            logger.debug(f"Unknown equipment type: {eq_name}")
            return None

        # Extract position
        try:
            if hasattr(entity.dxf, "insert"):
                x, y, z = entity.dxf.insert
            elif hasattr(entity.dxf, "start"):
                x, y = entity.dxf.start[0], entity.dxf.start[1]
                z = 0
            elif hasattr(entity.dxf, "center"):
                x, y = entity.dxf.center[0], entity.dxf.center[1]
                z = 0
            else:
                return None
        except (AttributeError, IndexError, TypeError):
            return None

        # Normalize coordinates
        x_norm, y_norm = normalize_coordinates(x, y, bbox)

        # Infer floor
        floor = self._infer_floor(z, eq_name)

        # Infer zone
        zone = self._infer_zone(eq_name, x_norm, y_norm, floor)

        # Build v2.0 equipment ID
        equipment_id = self._build_v2_equipment_id(building_code, eq_type, floor, zone)

        return {
            "name": equipment_id,
            "equipment_type": eq_type.lower(),
            "floor": floor,
            "x": round(x_norm, 2),
            "y": round(y_norm, 2),
            "zone": zone,
            "confidence": 0.95,  # High confidence from CAD
        }

    def _extract_name_from_attributes(self, insert_entity) -> Optional[str]:
        """
        Extract equipment name from DXF block attributes.

        Checks for standard attribute tags:
        - EQUIPMENT_ID
        - TAG
        - NAME
        - LABEL

        Args:
            insert_entity: DXF INSERT entity with attributes

        Returns:
            Equipment name or None
        """
        try:
            if hasattr(insert_entity, "attribs"):
                for attrib in insert_entity.attribs:
                    if hasattr(attrib, "dxf") and hasattr(attrib.dxf, "tag"):
                        tag_name = attrib.dxf.tag
                        if tag_name.upper() in [
                            "EQUIPMENT_ID",
                            "TAG",
                            "NAME",
                            "LABEL",
                        ]:
                            if hasattr(attrib.dxf, "text"):
                                return attrib.dxf.text
        except Exception as e:
            logger.debug(f"Error extracting attributes: {e}")

        return None

    def _classify_equipment_type(self, equipment_name: str) -> str:
        """
        Classify equipment type from name.

        Uses TYPE_MAPPINGS for legacy name patterns:
        - "CH-1" → CHILLER
        - "AHU-L1" → AHU
        - "FCU-L2-A" → FCU

        Args:
            equipment_name: Equipment name from DXF

        Returns:
            Uppercase type (CHILLER, AHU, FCU, etc.) or "UNKNOWN"
        """
        name_lower = equipment_name.lower()

        # Check if name starts with known type prefix
        for prefix, eq_type in self.TYPE_MAPPINGS.items():
            if name_lower.startswith(prefix):
                return eq_type

        # Fuzzy match common patterns
        patterns = [
            ("chiller", "CHILLER"),
            ("ahu", "AHU"),
            ("fcu", "FCU"),
            ("vav", "VAV"),
            ("split", "SPLIT"),
            ("crac", "CRAC"),
            ("cooling.*tower", "CT"),
            ("generator", "GEN"),
            ("ups", "UPS"),
            ("transformer", "TX"),
            ("switchboard", "MSB"),
            ("meter", "MTR"),
            ("dali", "DALI"),
            ("lighting", "LUM"),
            ("fire.*detect", "FIRE"),
        ]

        for pattern, eq_type in patterns:
            if re.search(pattern, name_lower):
                return eq_type

        return "UNKNOWN"

    def _infer_floor(self, z_coord: float, equipment_name: str) -> str:
        """
        Infer floor code from Z-coordinate or equipment name.

        Priority:
        1. Parse from equipment name (e.g., "FCU-L2-A" → "L2")
        2. Infer from Z-coordinate using floor height

        Args:
            z_coord: Z-coordinate from DXF
            equipment_name: Equipment name

        Returns:
            Floor code: B1, G, L1, L2, etc.
        """
        # Try parsing from name first (more reliable)
        match = re.search(r"-(B\d|G|L\d{1,2}|R)-", equipment_name, re.IGNORECASE)
        if match:
            return match.group(1).upper()

        # Fallback to Z-coordinate
        return infer_floor_from_z_coordinate(z_coord)

    def _infer_zone(self, equipment_name: str, x: float, y: float, floor: str) -> str:
        """
        Infer zone assignment from equipment name or position.

        Priority:
        1. Parse from equipment name if it ends with letter (e.g., "FCU-L2-A" → "A")
        2. Position-based clustering for numeric suffixes or no suffix

        Args:
            equipment_name: Equipment name
            x, y: Normalized coordinates
            floor: Floor code

        Returns:
            Zone identifier (A-Z for zoned, 001+ for plant)
        """
        # Try parsing from name (only if it ends with a LETTER, not number)
        match = re.search(r"-([A-Z])$", equipment_name, re.IGNORECASE)
        if match:
            return match.group(1).upper()

        # Position-based clustering (divide floor into 5 zones)
        if x < 30:
            return "A"
        elif x < 60:
            return "B"
        elif x < 90:
            return "C"
        elif x < 120:
            return "D"
        else:
            return "E"

    def _build_v2_equipment_id(
        self,
        building_code: str,
        equipment_type: str,
        floor: str,
        zone: str,
    ) -> str:
        """
        Build v2.0 equipment ID.

        Format: {site}-{type}-{floor}-{zone}
        Example: S002-CHILLER-B1-001

        Args:
            building_code: Site code (e.g., "site-002")
            equipment_type: Equipment type (CHILLER, AHU, etc.)
            floor: Floor code (B1, G, L1, etc.)
            zone: Zone identifier (A-Z or 001+)

        Returns:
            v2.0 format equipment ID
        """
        # Extract site number from building_code
        site_match = re.search(r"(\d+)", building_code)
        site_code = f"S{site_match.group(1).zfill(3)}" if site_match else "S999"

        return f"{site_code}-{equipment_type}-{floor}-{zone}"

    def _infer_floor_definitions(self, equipment: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Infer floor definitions from equipment positions.

        Groups equipment by floor and estimates dimensions.

        Args:
            equipment: List of extracted equipment

        Returns:
            List of floor definitions
        """
        floors_dict = defaultdict(list)
        for eq in equipment:
            floors_dict[eq["floor"]].append(eq)

        floors = []
        floor_order = ["B2", "B1", "G", "L1", "L2", "L3", "L4", "L5", "R"]
        z_position = 0

        for floor_code in floor_order:
            if floor_code not in floors_dict:
                continue

            floor_equipment = floors_dict[floor_code]

            # Calculate floor dimensions from equipment positions
            x_coords = [eq["x"] for eq in floor_equipment]
            y_coords = [eq["y"] for eq in floor_equipment]

            width = max(x_coords) - min(x_coords) + 20
            depth = max(y_coords) - min(y_coords) + 20

            # Standard floor height
            height = 3.5 if floor_code in ["B1", "G"] else 3.2

            floors.append(
                {
                    "level": floor_code,
                    "height": height,
                    "width": max(width, 100),
                    "depth": max(depth, 80),
                    "z_position": z_position,
                }
            )

            z_position += height

        return floors

    def _create_zones_from_equipment(self, equipment: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Create zone definitions from equipment clustering.

        Groups equipment by floor-zone combination.

        Args:
            equipment: List of extracted equipment

        Returns:
            List of zone definitions
        """
        zones_dict = defaultdict(lambda: {"equipment": [], "floor": "", "zone_type": "open_office"})

        for eq in equipment:
            zone_key = f"Zone-{eq['floor']}-{eq['zone']}"
            zones_dict[zone_key]["equipment"].append(eq["name"])
            zones_dict[zone_key]["floor"] = eq["floor"]

            # Infer zone type from equipment
            if eq["equipment_type"] in ["chiller", "ahu", "gen", "ups", "ct"]:
                zones_dict[zone_key]["zone_type"] = "mechanical"

        zones = []
        for zone_id, zone_data in zones_dict.items():
            zones.append(
                {
                    "zone_id": zone_id,
                    "floor": zone_data["floor"],
                    "zone_type": zone_data["zone_type"],
                    "equipment": zone_data["equipment"],
                }
            )

        return zones


# Singleton factory
_parser_service = None


def get_dxf_parser_service() -> DXFParserService:
    """Get or create singleton parser service."""
    global _parser_service
    if _parser_service is None:
        _parser_service = DXFParserService()
    return _parser_service

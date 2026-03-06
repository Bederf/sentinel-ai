"""Building 3D Configuration Service.

Handles validation, processing, and transformation of building structure
and equipment placement data for 3D visualization.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.database.repositories.site_3d_config_repository import (
    get_site_3d_config_repository,
)
from app.services.zone_mapping_service import get_zone_mapping_service

logger = logging.getLogger(__name__)

# Validation bounds
MIN_FLOOR_HEIGHT = 2.0  # Minimum 2 meters
MAX_FLOOR_HEIGHT = 20.0  # Maximum 20 meters
MIN_FLOOR_DIMENSION = 5.0  # Minimum 5m width/depth
MAX_FLOOR_DIMENSION = 1000.0  # Maximum 1000m
MIN_EQUIPMENT_SPACING = 0.5  # Minimum 0.5m between equipment centers


class Site3DConfigService:
    """Service for building 3D configuration operations."""

    def __init__(self):
        """Initialize service with dependencies."""
        self.repository = get_site_3d_config_repository()
        self.zone_service = get_zone_mapping_service()

    def validate_building_structure(self, structure: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate building structure definition.

        Args:
            structure: Building structure dict with name, code, numberOfFloors, floors

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Validate required fields
        if not structure.get("name"):
            return False, "Building name is required"

        if not isinstance(structure.get("numberOfFloors"), int):
            return False, "Number of floors must be an integer"

        if structure["numberOfFloors"] < 1 or structure["numberOfFloors"] > 50:
            return False, "Number of floors must be between 1 and 50"

        floors = structure.get("floors", [])
        if len(floors) != structure["numberOfFloors"]:
            return False, f"Expected {structure['numberOfFloors']} floors, got {len(floors)}"

        # Validate each floor
        seen_levels = set()
        for i, floor in enumerate(floors):
            is_valid, error = self._validate_floor(floor)
            if not is_valid:
                return False, f"Floor {i + 1}: {error}"

            if floor.get("level") in seen_levels:
                return False, f"Duplicate floor level: {floor.get('level')}"

            seen_levels.add(floor.get("level"))

        return True, None

    def validate_equipment_positions(
        self,
        positions: List[Dict[str, Any]],
        structure: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """Validate equipment positions against building structure.

        Args:
            positions: List of equipment positions
            structure: Building structure definition

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Build floor lookup for bounds checking
        floor_lookup = {f["level"]: f for f in structure.get("floors", [])}

        for i, pos in enumerate(positions):
            is_valid, error = self._validate_position(pos, floor_lookup)
            if not is_valid:
                return False, f"Position {i + 1} ({pos.get('equipment_id')}): {error}"

        # Check for equipment collisions
        collision_error = self._check_equipment_collisions(positions)
        if collision_error:
            return False, collision_error

        return True, None

    def _validate_floor(self, floor: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate single floor definition.

        Args:
            floor: Floor dict with level, height, width, depth, label

        Returns:
            Tuple of (is_valid, error_message)
        """
        required_fields = ["level", "height", "width", "depth", "label"]
        for field in required_fields:
            if field not in floor:
                return False, f"Missing required field: {field}"

        # Validate level
        if not isinstance(floor["level"], str) or len(floor["level"]) == 0:
            return False, "Level must be non-empty string (e.g., B1, G, L1)"

        # Validate dimensions
        try:
            height = float(floor["height"])
            width = float(floor["width"])
            depth = float(floor["depth"])
        except (ValueError, TypeError):
            return False, "Height, width, depth must be numeric"

        if not (MIN_FLOOR_HEIGHT <= height <= MAX_FLOOR_HEIGHT):
            return False, f"Height must be between {MIN_FLOOR_HEIGHT} and {MAX_FLOOR_HEIGHT}m"

        if not (MIN_FLOOR_DIMENSION <= width <= MAX_FLOOR_DIMENSION):
            return False, f"Width must be between {MIN_FLOOR_DIMENSION} and {MAX_FLOOR_DIMENSION}m"

        if not (MIN_FLOOR_DIMENSION <= depth <= MAX_FLOOR_DIMENSION):
            return False, f"Depth must be between {MIN_FLOOR_DIMENSION} and {MAX_FLOOR_DIMENSION}m"

        # Validate label
        if not isinstance(floor["label"], str) or len(floor["label"]) == 0:
            return False, "Label must be non-empty string"

        return True, None

    def _validate_position(
        self,
        position: Dict[str, Any],
        floor_lookup: Dict[str, Dict[str, Any]],
    ) -> Tuple[bool, Optional[str]]:
        """Validate single equipment position.

        Args:
            position: Position dict with equipment_id, floor, x, y
            floor_lookup: Map of floor levels to floor definitions

        Returns:
            Tuple of (is_valid, error_message)
        """
        required_fields = ["equipment_id", "floor", "x", "y"]
        for field in required_fields:
            if field not in position:
                return False, f"Missing required field: {field}"

        # Validate floor exists
        floor_level = position.get("floor")
        if floor_level not in floor_lookup:
            return False, f"Floor level '{floor_level}' not found in building structure"

        # Validate coordinates
        try:
            x = float(position["x"])
            y = float(position["y"])
        except (ValueError, TypeError):
            return False, "Coordinates x, y must be numeric"

        floor = floor_lookup[floor_level]
        width = float(floor["width"])
        depth = float(floor["depth"])

        # Check bounds (with small margin for edge placement)
        margin = 0.5  # 0.5m margin
        if not (0 - margin <= x <= width + margin):
            return False, f"X coordinate {x}m outside floor width bounds [0, {width}m]"

        if not (0 - margin <= y <= depth + margin):
            return False, f"Y coordinate {y}m outside floor depth bounds [0, {depth}m]"

        if x < 0 or y < 0 or x > width or y > depth:
            logger.warning(f"Equipment {position['equipment_id']} slightly outside bounds: ({x}, {y})")

        return True, None

    def _check_equipment_collisions(
        self,
        positions: List[Dict[str, Any]],
    ) -> Optional[str]:
        """Check for equipment spacing violations.

        Args:
            positions: List of equipment positions

        Returns:
            Error message if collision found, None otherwise
        """
        # Group by floor
        by_floor: Dict[str, List[Dict[str, Any]]] = {}
        for pos in positions:
            floor = pos.get("floor")
            if floor not in by_floor:
                by_floor[floor] = []
            by_floor[floor].append(pos)

        # Check spacing on each floor
        for floor, floor_positions in by_floor.items():
            for i, pos1 in enumerate(floor_positions):
                for pos2 in floor_positions[i + 1 :]:
                    distance = self._calculate_distance(
                        (pos1["x"], pos1["y"]),
                        (pos2["x"], pos2["y"]),
                    )

                    if distance < MIN_EQUIPMENT_SPACING:
                        return (
                            f"Equipment {pos1['equipment_id']} and {pos2['equipment_id']} "
                            f"on floor {floor} are too close (distance: {distance:.2f}m, "
                            f"minimum: {MIN_EQUIPMENT_SPACING}m)"
                        )

        return None

    @staticmethod
    def _calculate_distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
        """Calculate Euclidean distance between two points.

        Args:
            p1: Point 1 as (x, y)
            p2: Point 2 as (x, y)

        Returns:
            Distance in meters
        """
        dx = p1[0] - p2[0]
        dy = p1[1] - p2[1]
        return (dx**2 + dy**2) ** 0.5

    def infer_zones_from_positions(
        self,
        positions: List[Dict[str, Any]],
        equipment_map: Dict[str, Dict[str, Any]],
        site_id: str,
    ) -> List[Dict[str, Any]]:
        """Auto-infer zones from equipment positions.

        Groups equipment by floor, then infers zones using ZoneMappingService.

        Args:
            positions: Equipment positions
            equipment_map: Map of equipment_id to equipment data
            site_id: Site identifier

        Returns:
            List of zone definitions
        """
        zones = []

        # Group equipment by floor
        by_floor: Dict[str, List[str]] = {}
        for pos in positions:
            floor = pos.get("floor")
            equipment_id = pos.get("equipment_id")

            if floor not in by_floor:
                by_floor[floor] = []
            by_floor[floor].append(equipment_id)

        # Create zone definitions per floor
        for floor, equipment_ids in by_floor.items():
            zone_id = f"Zone-{floor}"
            zone_def = {
                "zone_id": zone_id,
                "floor": floor,
                "equipment_ids": equipment_ids,
                "type": "open_office",  # Default type; can be customized
                "site_id": site_id,
            }
            zones.append(zone_def)

        logger.info(f"Inferred {len(zones)} zones from equipment positions")
        return zones

    def generate_viewer_data(
        self,
        site_id: str,
        structure: Dict[str, Any],
        positions: List[Dict[str, Any]],
        equipment_map: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Generate data formatted for 3D viewer display.

        Args:
            site_id: Building ID
            structure: Building structure
            positions: Equipment positions
            equipment_map: Map of equipment to metadata

        Returns:
            Viewer-ready data structure
        """
        # Group equipment by floor
        equipment_by_floor: Dict[str, List[Dict[str, Any]]] = {}
        for pos in positions:
            floor = pos.get("floor")
            equipment_id = pos.get("equipment_id")

            if floor not in equipment_by_floor:
                equipment_by_floor[floor] = []

            equipment = equipment_map.get(equipment_id, {})
            equipment_by_floor[floor].append(
                {
                    "equipment_id": equipment_id,
                    "code": equipment.get("code", equipment_id),
                    "type": equipment.get("type", "unknown"),
                    "position": {"x": pos.get("x"), "y": pos.get("y")},
                    "status": equipment.get("status", "unknown"),
                }
            )

        # Build floor data
        floors = []
        for floor_def in structure.get("floors", []):
            floor_data = {
                "level": floor_def.get("level"),
                "label": floor_def.get("label"),
                "dimensions": {
                    "height": floor_def.get("height"),
                    "width": floor_def.get("width"),
                    "depth": floor_def.get("depth"),
                },
                "equipment": equipment_by_floor.get(floor_def.get("level"), []),
            }
            floors.append(floor_data)

        return {
            "site_id": site_id,
            "site_name": structure.get("name"),
            "floors": floors,
            "metadata": {
                "generated_at": "2026-02-09T00:00:00Z",
                "equipment_count": len(positions),
                "floor_count": len(floors),
            },
        }

    def export_config_for_import(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Export configuration in standardized format for import/sharing.

        Args:
            config: Configuration data

        Returns:
            Exportable config dict
        """
        return {
            "version": "1.0",
            "export_format": "building-3d-config",
            "site_name": config.get("name"),
            "site_code": config.get("code"),
            "floors": config.get("floors", []),
            "equipment_positions": config.get("equipment_positions", []),
            "zones": config.get("zones", []),
        }

    def import_config_from_dict(
        self,
        site_id: str,
        import_data: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """Import configuration from standardized format.

        Args:
            site_id: Building ID to import into
            import_data: Data to import

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Validate import data has required structure
            if import_data.get("export_format") != "building-3d-config":
                return False, "Invalid export format"

            structure = {
                "name": import_data.get("site_name"),
                "code": import_data.get("site_code"),
                "numberOfFloors": len(import_data.get("floors", [])),
                "floors": import_data.get("floors", []),
            }

            is_valid, error = self.validate_building_structure(structure)
            if not is_valid:
                return False, f"Structure validation failed: {error}"

            positions = import_data.get("equipment_positions", [])
            is_valid, error = self.validate_equipment_positions(positions, structure)
            if not is_valid:
                return False, f"Position validation failed: {error}"

            # All valid - save to repository
            self.repository.create(
                site_id=site_id,
                site_code=site_id,  # site_code same as site_id for imports
                name=structure["name"],
                code=structure["code"],
                floors=structure["floors"],
                equipment_positions=positions,
            )

            return True, None

        except Exception as e:
            return False, f"Import failed: {str(e)}"


# Singleton instance
_site_3d_config_service: Optional[Site3DConfigService] = None


def get_site_3d_config_service() -> Site3DConfigService:
    """Get or create singleton service instance.

    Returns:
        Site3DConfigService instance
    """
    global _site_3d_config_service

    if _site_3d_config_service is None:
        _site_3d_config_service = Site3DConfigService()

    return _site_3d_config_service

"""AI-assisted point classification for Niagara BACnet point discovery.

Uses Haystack/Brick ontology tags to classify BACnet points into
equipment types and point types, generating standardized names
following the Brick ontology schema.

Classification approach:
1. Regex matching against equipment patterns (chiller, AHU, FCU, etc.)
2. Keyword matching against point type tags (temperature, pressure, etc.)
3. Confidence scoring: high (exact match), medium (partial), low (guessed)
4. Standardized name generation using Brick ontology
"""

import json
import logging
import re
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Data directory for Haystack/Brick ontology tags
DATA_DIR = Path(__file__).parent.parent.parent / "data" / "niagara"


class ConfidenceLevel(str, Enum):
    """Classification confidence levels."""
    HIGH = "high"      # Exact regex or keyword match
    MEDIUM = "medium"  # Partial match or inferred
    LOW = "low"        # Best guess, needs review
    UNKNOWN = "unknown"  # Could not classify


class PointType(str, Enum):
    """BMS point functional types."""
    SENSOR = "sensor"
    SETPOINT = "setpoint"
    COMMAND = "command"
    STATUS = "status"
    ALARM = "alarm"
    UNKNOWN = "unknown"


class ClassifiedPoint:
    """Result of classifying a BACnet point."""

    def __init__(
        self,
        original_name: str,
        original_description: str = "",
        equipment_type: str = "unknown",
        equipment_id: str = "",
        point_type: PointType = PointType.UNKNOWN,
        point_category: str = "unknown",
        brick_class: str = "",
        standardized_name: str = "",
        unit: str = "",
        confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN,
        tags: Optional[List[str]] = None,
        object_type: str = "",
        instance: int = 0,
        present_value: Any = None,
        writable: bool = False,
    ):
        self.original_name = original_name
        self.original_description = original_description
        self.equipment_type = equipment_type
        self.equipment_id = equipment_id
        self.point_type = point_type
        self.point_category = point_category
        self.brick_class = brick_class
        self.standardized_name = standardized_name
        self.unit = unit
        self.confidence = confidence
        self.tags = tags or []
        self.object_type = object_type
        self.instance = instance
        self.present_value = present_value
        self.writable = writable

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_name": self.original_name,
            "original_description": self.original_description,
            "equipment_type": self.equipment_type,
            "equipment_id": self.equipment_id,
            "point_type": self.point_type.value,
            "point_category": self.point_category,
            "brick_class": self.brick_class,
            "standardized_name": self.standardized_name,
            "unit": self.unit,
            "confidence": self.confidence.value,
            "tags": self.tags,
            "object_type": self.object_type,
            "instance": self.instance,
            "present_value": self.present_value,
            "writable": self.writable,
        }


class PointClassifier:
    """Classifies BACnet points using Haystack/Brick ontology.

    Loads tag definitions from haystack_tags.json and uses regex pattern
    matching and keyword search to identify equipment types and point
    categories with confidence scoring.

    Usage:
        classifier = PointClassifier()
        result = classifier.classify_point("CH-1_CHW_Supply_Temp", "Chiller 1 Supply")
        print(result.equipment_type)  # "chiller"
        print(result.confidence)  # "high"
    """

    def __init__(self, tags_path: Optional[str] = None):
        self._tags_path = tags_path or str(DATA_DIR / "haystack_tags.json")
        self._point_type_tags: Dict[str, Any] = {}
        self._equipment_patterns: Dict[str, Any] = {}
        self._unit_mappings: Dict[str, List[str]] = {}
        self._loaded = False

    def _load_tags(self) -> None:
        """Load Haystack/Brick tags from JSON file."""
        if self._loaded:
            return

        try:
            with open(self._tags_path) as f:
                data = json.load(f)

            self._point_type_tags = data.get("point_type_tags", {})
            self._equipment_patterns = data.get("equipment_patterns", {})
            self._unit_mappings = data.get("unit_mappings", {})
            self._loaded = True
            logger.info(
                "Loaded %d point type tags, %d equipment patterns",
                len(self._point_type_tags),
                len(self._equipment_patterns),
            )
        except FileNotFoundError:
            logger.error("Haystack tags file not found: %s", self._tags_path)
            self._loaded = True  # Prevent repeated attempts
        except json.JSONDecodeError as e:
            logger.error("Failed to parse haystack tags JSON: %s", e)
            self._loaded = True

    def classify_point(
        self,
        point_name: str,
        point_description: str = "",
        object_type: str = "",
        instance: int = 0,
        units: str = "",
        present_value: Any = None,
        writable: bool = False,
    ) -> ClassifiedPoint:
        """Classify a single BACnet point.

        Uses a multi-step approach:
        1. Extract equipment ID from name prefix
        2. Match equipment type using regex patterns
        3. Match point category using keyword tags
        4. Infer point type from object type and keywords
        5. Generate standardized Brick name
        6. Calculate confidence score

        Args:
            point_name: BACnet point name (e.g., "CH-1_CHW_Supply_Temp")
            point_description: Point description text
            object_type: BACnet object type (e.g., "analogInput")
            instance: BACnet object instance number
            units: Engineering units string
            present_value: Current point value
            writable: Whether the point is writable

        Returns:
            ClassifiedPoint with equipment type, point type, and confidence
        """
        self._load_tags()

        # Combine name and description for matching
        search_text = f"{point_name} {point_description}".lower()

        # Step 1: Extract equipment ID from name prefix
        equipment_id = self._extract_equipment_id(point_name)

        # Step 2: Match equipment type
        equipment_type, equip_confidence = self._match_equipment_type(search_text)

        # Step 3: Match point category (temperature, pressure, etc.)
        point_category, category_brick, category_unit, cat_confidence = (
            self._match_point_category(search_text)
        )

        # Step 4: Infer point type
        point_type = self._infer_point_type(
            search_text, object_type, writable, point_category
        )

        # Step 5: Resolve units
        resolved_unit = self._resolve_unit(units, category_unit)

        # Step 6: Generate standardized name
        standardized_name = self._generate_standardized_name(
            equipment_id, equipment_type, point_category, point_type
        )

        # Step 7: Calculate overall confidence
        confidence = self._calculate_confidence(
            equip_confidence, cat_confidence, equipment_type, point_category
        )

        # Build tags list
        tags = self._build_tags(equipment_type, point_category, point_type)

        # Get Brick class
        brick_class = category_brick
        if not brick_class and equipment_type != "unknown":
            equip_data = self._equipment_patterns.get(equipment_type, {})
            brick_class = equip_data.get("brick_class", "")

        return ClassifiedPoint(
            original_name=point_name,
            original_description=point_description,
            equipment_type=equipment_type,
            equipment_id=equipment_id,
            point_type=point_type,
            point_category=point_category,
            brick_class=brick_class,
            standardized_name=standardized_name,
            unit=resolved_unit,
            confidence=confidence,
            tags=tags,
            object_type=object_type,
            instance=instance,
            present_value=present_value,
            writable=writable,
        )

    def classify_points(
        self,
        points: List[Dict[str, Any]],
    ) -> List[ClassifiedPoint]:
        """Classify multiple points in batch.

        Args:
            points: List of dicts with keys: name, description, object_type,
                    instance, units, present_value, writable

        Returns:
            List of ClassifiedPoint results
        """
        results = []
        for p in points:
            result = self.classify_point(
                point_name=p.get("name", ""),
                point_description=p.get("description", ""),
                object_type=p.get("object_type", ""),
                instance=p.get("instance", 0),
                units=p.get("units", ""),
                present_value=p.get("present_value"),
                writable=p.get("writable", False),
            )
            results.append(result)
        return results

    def get_classification_summary(
        self, classified_points: List[ClassifiedPoint]
    ) -> Dict[str, Any]:
        """Generate a summary of classification results.

        Args:
            classified_points: List of classified points

        Returns:
            Summary with counts by equipment type, confidence, and point type
        """
        equipment_counts: Dict[str, int] = {}
        confidence_counts: Dict[str, int] = {}
        point_type_counts: Dict[str, int] = {}
        equipment_ids: Dict[str, List[str]] = {}

        for cp in classified_points:
            # Equipment type counts
            equipment_counts[cp.equipment_type] = (
                equipment_counts.get(cp.equipment_type, 0) + 1
            )
            # Confidence counts
            confidence_counts[cp.confidence.value] = (
                confidence_counts.get(cp.confidence.value, 0) + 1
            )
            # Point type counts
            point_type_counts[cp.point_type.value] = (
                point_type_counts.get(cp.point_type.value, 0) + 1
            )
            # Track unique equipment IDs
            if cp.equipment_id:
                if cp.equipment_type not in equipment_ids:
                    equipment_ids[cp.equipment_type] = []
                if cp.equipment_id not in equipment_ids[cp.equipment_type]:
                    equipment_ids[cp.equipment_type].append(cp.equipment_id)

        return {
            "total_points": len(classified_points),
            "equipment_type_counts": equipment_counts,
            "confidence_counts": confidence_counts,
            "point_type_counts": point_type_counts,
            "unique_equipment": {
                eq_type: len(ids)
                for eq_type, ids in equipment_ids.items()
            },
            "equipment_ids": equipment_ids,
            "needs_review": confidence_counts.get("low", 0)
            + confidence_counts.get("unknown", 0),
        }

    # ------------------------------------------------------------------
    # Internal classification methods
    # ------------------------------------------------------------------

    def _extract_equipment_id(self, point_name: str) -> str:
        """Extract equipment identifier from point name prefix.

        Common patterns:
        - "CH-1_CHW_Supply_Temp" -> "CH-1"
        - "AHU-1_Supply_Air_Temp" -> "AHU-1"
        - "VAV-L1-A_Zone_Temp" -> "VAV-L1-A"
        - "FCU-L1-A_Room_Temp" -> "FCU-L1-A"
        - "PUMP-CW-1_Status" -> "PUMP-CW-1"
        - "MTR-MAIN_kW" -> "MTR-MAIN"
        - "GEN-1_Status" -> "GEN-1"
        - "ZONE-L1_CO2" -> "ZONE-L1"
        """
        # Equipment prefix pattern: letters+digits connected by dashes
        # Stops at the first underscore that separates the prefix from the point name
        # Uses [A-Za-z0-9] (no underscore) in dash-groups to prevent matching past dashes
        match = re.match(
            r'^([A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*)_',
            point_name,
        )
        if match:
            return match.group(1)

        # Fallback: split on first underscore
        parts = point_name.split("_", 1)
        if len(parts) > 1 and len(parts[0]) <= 20:
            return parts[0]

        return ""

    def _match_equipment_type(
        self, search_text: str
    ) -> Tuple[str, ConfidenceLevel]:
        """Match equipment type using regex patterns.

        Returns:
            Tuple of (equipment_type, confidence_level)
        """
        best_match = "unknown"
        best_confidence = ConfidenceLevel.UNKNOWN

        for eq_type, eq_data in self._equipment_patterns.items():
            pattern = eq_data.get("regex", "")
            if not pattern:
                continue

            try:
                if re.search(pattern, search_text, re.IGNORECASE):
                    # Check for exact vs partial match
                    # If the equipment abbreviation appears at the start or
                    # as a prefix, it's a high confidence match
                    if re.match(
                        rf"^{pattern}", search_text.split()[0], re.IGNORECASE
                    ):
                        best_match = eq_type
                        best_confidence = ConfidenceLevel.HIGH
                        break  # Exact match, no need to continue
                    else:
                        # Found in text but not as prefix
                        if best_confidence != ConfidenceLevel.HIGH:
                            best_match = eq_type
                            best_confidence = ConfidenceLevel.MEDIUM
            except re.error:
                logger.warning("Invalid regex for equipment %s: %s", eq_type, pattern)

        return best_match, best_confidence

    def _match_point_category(
        self, search_text: str
    ) -> Tuple[str, str, str, ConfidenceLevel]:
        """Match point category using keyword tags.

        Returns:
            Tuple of (category, brick_class, unit, confidence)
        """
        best_category = "unknown"
        best_brick = ""
        best_unit = ""
        best_confidence = ConfidenceLevel.UNKNOWN
        best_match_count = 0

        for category, cat_data in self._point_type_tags.items():
            keywords = cat_data.get("keywords", [])
            match_count = 0

            for keyword in keywords:
                if keyword in search_text:
                    match_count += 1

            if match_count > best_match_count:
                best_match_count = match_count
                best_category = category
                best_brick = cat_data.get("brick_class", "")
                best_unit = cat_data.get("unit", "")

                if match_count >= 2:
                    best_confidence = ConfidenceLevel.HIGH
                elif match_count == 1:
                    best_confidence = ConfidenceLevel.MEDIUM

        return best_category, best_brick, best_unit, best_confidence

    def _infer_point_type(
        self,
        search_text: str,
        object_type: str,
        writable: bool,
        point_category: str,
    ) -> PointType:
        """Infer the functional point type.

        Uses a combination of BACnet object type, writeability,
        and category to determine if a point is a sensor, setpoint,
        command, status, or alarm.
        """
        # Check category-based type first (from tag definitions)
        for _category, cat_data in self._point_type_tags.items():
            if _category == point_category:
                cat_point_type = cat_data.get("point_type", "")
                if cat_point_type:
                    try:
                        return PointType(cat_point_type)
                    except ValueError:
                        pass

        # Infer from BACnet object type
        if object_type in ("binaryInput",):
            # Binary inputs are typically status or alarm
            if any(kw in search_text for kw in ["alarm", "fault", "trip", "fail"]):
                return PointType.ALARM
            return PointType.STATUS

        if object_type in ("binaryOutput", "binaryValue"):
            if any(kw in search_text for kw in ["command", "cmd", "enable", "start"]):
                return PointType.COMMAND
            return PointType.COMMAND if writable else PointType.STATUS

        if object_type in ("analogValue",):
            if any(kw in search_text for kw in ["setpoint", "sp", "stpt", "set_point"]):
                return PointType.SETPOINT
            return PointType.SETPOINT if writable else PointType.SENSOR

        if object_type in ("analogOutput",):
            if any(kw in search_text for kw in ["setpoint", "sp"]):
                return PointType.SETPOINT
            return PointType.COMMAND

        if object_type in ("analogInput",):
            return PointType.SENSOR

        # Default: writable means command, otherwise sensor
        if writable:
            return PointType.COMMAND

        return PointType.UNKNOWN

    def _resolve_unit(self, raw_units: str, category_unit: str) -> str:
        """Resolve engineering units from raw string or category default.

        Args:
            raw_units: Units string from BACnet point
            category_unit: Default unit from category tags

        Returns:
            Standardized unit string
        """
        if not raw_units:
            return category_unit

        raw_lower = raw_units.lower().strip()

        # Try to match against unit mappings
        for standard_unit, aliases in self._unit_mappings.items():
            if raw_lower in aliases or raw_lower == standard_unit.lower():
                return standard_unit

        # Return raw units if no mapping found
        return raw_units

    def _generate_standardized_name(
        self,
        equipment_id: str,
        equipment_type: str,
        point_category: str,
        point_type: PointType,
    ) -> str:
        """Generate a standardized Brick-style point name.

        Format: {equipment_id}/{point_category}_{point_type}
        Example: CH-1/temperature_sensor
        """
        if not equipment_id:
            equipment_id = equipment_type or "unknown"

        if point_category == "unknown" and point_type == PointType.UNKNOWN:
            return f"{equipment_id}/unclassified"

        parts = [equipment_id]
        name_parts = []

        if point_category != "unknown":
            name_parts.append(point_category)
        if point_type != PointType.UNKNOWN:
            name_parts.append(point_type.value)

        if name_parts:
            parts.append("_".join(name_parts))

        return "/".join(parts)

    def _calculate_confidence(
        self,
        equip_confidence: ConfidenceLevel,
        cat_confidence: ConfidenceLevel,
        equipment_type: str,
        point_category: str,
    ) -> ConfidenceLevel:
        """Calculate overall classification confidence.

        Both equipment type and point category need to be identified
        for high confidence. Unknown in either reduces confidence.
        """
        if equipment_type == "unknown" and point_category == "unknown":
            return ConfidenceLevel.UNKNOWN

        if equipment_type == "unknown" or point_category == "unknown":
            # If at least one dimension is confidently identified,
            # treat as medium to reduce excessive "low" classifications.
            if equip_confidence in [ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM] \
                    or cat_confidence in [ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM]:
                return ConfidenceLevel.MEDIUM
            return ConfidenceLevel.LOW

        # Both identified - use the lower confidence
        confidence_order = {
            ConfidenceLevel.HIGH: 3,
            ConfidenceLevel.MEDIUM: 2,
            ConfidenceLevel.LOW: 1,
            ConfidenceLevel.UNKNOWN: 0,
        }

        min_level = min(
            confidence_order[equip_confidence],
            confidence_order[cat_confidence],
        )

        for level, order in confidence_order.items():
            if order == min_level:
                return level

        return ConfidenceLevel.MEDIUM

    def _build_tags(
        self,
        equipment_type: str,
        point_category: str,
        point_type: PointType,
    ) -> List[str]:
        """Build a list of Haystack-style tags for the point."""
        tags = []

        if equipment_type != "unknown":
            tags.append(equipment_type)
            # Add Brick class tag
            equip_data = self._equipment_patterns.get(equipment_type, {})
            if equip_data.get("brick_class"):
                tags.append(equip_data["brick_class"])

        if point_category != "unknown":
            tags.append(point_category)

        if point_type != PointType.UNKNOWN:
            tags.append(point_type.value)

        # Add common Haystack tags
        tags.append("point")
        if point_type == PointType.SENSOR:
            tags.append("cur")  # current value
        elif point_type == PointType.SETPOINT:
            tags.append("writable")
        elif point_type == PointType.COMMAND:
            tags.append("writable")

        return tags


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_classifier_instance: Optional[PointClassifier] = None


def get_point_classifier() -> PointClassifier:
    """Get or create the singleton PointClassifier instance."""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = PointClassifier()
    return _classifier_instance

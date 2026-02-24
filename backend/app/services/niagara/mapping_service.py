"""Point-to-equipment mapping service for Niagara commissioning.

Groups classified BACnet points into equipment entities, generates
equipment model configurations, and provides validation, dual-write
storage, and manual correction support.

Workflow:
1. Group classified points by equipment ID prefix
2. Infer equipment type from majority classification
3. Generate equipment model with point mappings
4. Validate for orphans, duplicates, and completeness
5. Store mappings with dual-write (JSON + optional Supabase)
"""

import json
import logging
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.niagara.point_classifier import (
    ClassifiedPoint,
    ConfidenceLevel,
)

logger = logging.getLogger(__name__)

# Data directory for mapping storage
DATA_DIR = Path(__file__).parent.parent.parent / "data" / "niagara"
BUILDINGS_DIR = Path(__file__).parent.parent.parent / "data" / "buildings"


class EquipmentMapping:
    """An auto-generated equipment model from classified points."""

    def __init__(
        self,
        equipment_id: str,
        equipment_type: str,
        equipment_name: str = "",
        site_id: str = "",
        points: Optional[List[Dict[str, Any]]] = None,
        confidence: str = "medium",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.equipment_id = equipment_id
        self.equipment_type = equipment_type
        self.equipment_name = equipment_name or f"{equipment_type.upper()} {equipment_id}"
        self.site_id = site_id
        self.points = points or []
        self.confidence = confidence
        self.metadata = metadata or {}
        self.created_at = datetime.utcnow().isoformat()
        self.approved = False
        self.approved_at: Optional[str] = None
        self.approved_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "equipment_id": self.equipment_id,
            "equipment_type": self.equipment_type,
            "equipment_name": self.equipment_name,
            "site_id": self.site_id,
            "points": self.points,
            "point_count": len(self.points),
            "confidence": self.confidence,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "approved": self.approved,
            "approved_at": self.approved_at,
            "approved_by": self.approved_by,
        }


class MappingValidationResult:
    """Result of validating a point mapping set."""

    def __init__(self):
        self.valid = True
        self.orphan_points: List[str] = []
        self.duplicate_points: List[str] = []
        self.missing_typical_points: Dict[str, List[str]] = {}
        self.low_confidence_points: List[str] = []
        self.warnings: List[str] = []
        self.errors: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "orphan_points": self.orphan_points,
            "duplicate_points": self.duplicate_points,
            "missing_typical_points": self.missing_typical_points,
            "low_confidence_count": len(self.low_confidence_points),
            "low_confidence_points": self.low_confidence_points[:20],
            "warnings": self.warnings,
            "errors": self.errors,
        }


class PointMappingService:
    """Service for mapping classified points to equipment entities.

    Handles the full mapping workflow:
    1. Group points by equipment prefix
    2. Generate equipment models from point groups
    3. Validate mappings for completeness
    4. Store with dual-write (JSON + Supabase)
    5. Support manual corrections and approvals

    Usage:
        service = PointMappingService()
        mappings = service.map_points_to_equipment(classified_points, "site-002")
        validation = service.validate_mappings(mappings)
        service.save_mappings("discovery-123", mappings)
    """

    def __init__(self):
        self._mapping_cache: Dict[str, Dict[str, EquipmentMapping]] = {}
        self._mapping_history: Dict[str, List[Dict[str, Any]]] = {}

    def map_points_to_equipment(
        self,
        classified_points: List[ClassifiedPoint],
        site_id: str,
    ) -> Dict[str, EquipmentMapping]:
        """Group classified points into equipment entities with v2.0 naming conversion.

        Uses equipment_id extracted during classification to group points.
        For each group, infers the equipment type from majority vote of
        point classifications. Converts BMS IDs to v2.0 standard format.

        Args:
            classified_points: Points from PointClassifier
            site_id: SENTINEL site ID for the equipment

        Returns:
            Dict mapping v2.0_equipment_id -> EquipmentMapping
        """
        from app.services.equipment_id_converter import EquipmentIDConverter
        from app.services.zone_mapping_service import get_zone_mapping_service

        converter = EquipmentIDConverter()
        zone_service = get_zone_mapping_service()

        # Step 1: Group points by equipment ID
        groups: Dict[str, List[ClassifiedPoint]] = {}
        orphans: List[ClassifiedPoint] = []

        for cp in classified_points:
            if cp.equipment_id:
                if cp.equipment_id not in groups:
                    groups[cp.equipment_id] = []
                groups[cp.equipment_id].append(cp)
            else:
                orphans.append(cp)

        logger.info(
            "Grouped %d points into %d equipment entities (%d orphans)",
            len(classified_points),
            len(groups),
            len(orphans),
        )

        # Step 2: Generate equipment mappings with v2.0 naming conversion
        mappings: Dict[str, EquipmentMapping] = {}

        for bms_equip_id, points in groups.items():
            # Infer equipment type from majority vote
            type_counts = Counter(p.equipment_type for p in points if p.equipment_type != "unknown")
            equipment_type = type_counts.most_common(1)[0][0] if type_counts else "unknown"

            # Convert BMS ID to v2.0 format
            v2_equipment_id = converter.convert_bms_to_v2(
                bms_id=bms_equip_id,
                equipment_type=equipment_type,
                site_id=site_id,
            )

            # Infer zone from v2.0 equipment ID
            zone_info = zone_service.infer_zone_from_equipment_id(v2_equipment_id, site_id)

            # Generate equipment mapping
            mapping = self._generate_equipment_mapping(v2_equipment_id, points, site_id)

            # Store original BMS ID and zone info in metadata
            mapping.metadata["bms_original_id"] = bms_equip_id
            if zone_info:
                mapping.metadata["zone"] = zone_info

            mappings[v2_equipment_id] = mapping

            logger.debug(
                f"Converted BMS ID '{bms_equip_id}' → v2.0 '{v2_equipment_id}' "
                f"with zone {zone_info.get('zone_letter') if zone_info else 'N/A'}"
            )

        # Step 3: Handle orphan points - group under "UNASSIGNED"
        if orphans:
            orphan_mapping = self._generate_equipment_mapping("UNASSIGNED", orphans, site_id)
            orphan_mapping.confidence = "low"
            mappings["UNASSIGNED"] = orphan_mapping

        return mappings

    def _generate_equipment_mapping(
        self,
        equipment_id: str,
        points: List[ClassifiedPoint],
        site_id: str,
    ) -> EquipmentMapping:
        """Generate an equipment mapping from a group of classified points.

        Uses majority voting on equipment_type to determine the
        overall equipment type for the group.
        """
        # Majority vote on equipment type
        type_counts = Counter(p.equipment_type for p in points if p.equipment_type != "unknown")
        if type_counts:
            equipment_type = type_counts.most_common(1)[0][0]
        else:
            equipment_type = "unknown"

        # Calculate group confidence
        confidence_values = {
            ConfidenceLevel.HIGH: 3,
            ConfidenceLevel.MEDIUM: 2,
            ConfidenceLevel.LOW: 1,
            ConfidenceLevel.UNKNOWN: 0,
        }
        avg_confidence = sum(confidence_values.get(p.confidence, 0) for p in points) / len(points) if points else 0

        if avg_confidence >= 2.5:
            group_confidence = "high"
        elif avg_confidence >= 1.5:
            group_confidence = "medium"
        else:
            group_confidence = "low"

        # Generate friendly name
        equipment_name = self._generate_equipment_name(equipment_id, equipment_type)

        # Build point list for the mapping
        point_list = []
        for p in points:
            point_list.append(
                {
                    "original_name": p.original_name,
                    "standardized_name": p.standardized_name,
                    "point_type": p.point_type.value,
                    "point_category": p.point_category,
                    "unit": p.unit,
                    "confidence": p.confidence.value,
                    "object_type": p.object_type,
                    "instance": p.instance,
                    "present_value": p.present_value,
                    "writable": p.writable,
                }
            )

        return EquipmentMapping(
            equipment_id=equipment_id,
            equipment_type=equipment_type,
            equipment_name=equipment_name,
            site_id=site_id,
            points=point_list,
            confidence=group_confidence,
            metadata={
                "type_vote_counts": dict(type_counts),
                "avg_confidence_score": round(avg_confidence, 2),
            },
        )

    def _generate_equipment_name(self, equipment_id: str, equipment_type: str) -> str:
        """Generate a human-friendly equipment name."""
        type_names = {
            "chiller": "Chiller",
            "ahu": "Air Handling Unit",
            "fcu": "Fan Coil Unit",
            "vav": "Variable Air Volume Box",
            "pump": "Pump",
            "boiler": "Boiler",
            "cooling_tower": "Cooling Tower",
            "ct": "Cooling Tower",
            "generator": "Generator",
            "gen": "Generator",
            "ups": "UPS",
            "transformer": "Transformer",
            "dali_controller": "DALI Lighting Controller",
            "dali": "DALI Lighting Controller",
            "meter": "Power Meter",
            "split": "Split Unit",
            "crac": "CRAC Unit",
            "fire": "Fire Panel",
            "msb": "Main Switchboard",
            "db": "Distribution Board",
            "cold": "Cold Room",
            "lift": "Lift",
            "jace": "JACE Controller",
            "kef": "Kitchen Extract Fan",
            "medgas": "Medical Gas System",
            "acc": "Access Control",
            "cctv": "CCTV Camera",
            "ats": "Auto Transfer Switch",
            "pfc": "Power Factor Correction",
            "fdr": "Feeder",
            "mv": "Medium Voltage",
            "mtr": "Meter",
            "lum": "Luminaire",
        }

        type_label = type_names.get(equipment_type, equipment_type.replace("_", " ").title())
        return f"{type_label} ({equipment_id})"

    def generate_equipment_model(self, mapping: EquipmentMapping) -> Dict[str, Any]:
        """Generate a DeviceInterface-compatible equipment configuration.

        Creates a JSON structure that can be loaded by the device manager
        to create a new equipment entry in SENTINEL.

        Args:
            mapping: Equipment mapping to convert

        Returns:
            Dict with equipment configuration for device_manager
        """
        # Build point definitions
        point_defs = {}
        for p in mapping.points:
            point_name = p.get("point_category", "unknown")
            if point_name in point_defs:
                # Disambiguate duplicate categories
                point_name = f"{point_name}_{p.get('point_type', 'value')}"

            point_defs[point_name] = {
                "bacnet_ref": p.get("original_name", ""),
                "object_type": p.get("object_type", ""),
                "instance": p.get("instance", 0),
                "unit": p.get("unit", ""),
                "writable": p.get("writable", False),
                "point_type": p.get("point_type", "unknown"),
                "default_value": p.get("present_value"),
            }

        # Map equipment type to device type
        device_type_map = {
            "chiller": "hvac",
            "ahu": "hvac",
            "fcu": "hvac",
            "vav": "hvac",
            "pump": "hvac",
            "boiler": "hvac",
            "cooling_tower": "hvac",
            "ct": "hvac",
            "split": "hvac",
            "crac": "hvac",
            "cold": "hvac",
            "generator": "power",
            "gen": "power",
            "ups": "power",
            "transformer": "power",
            "msb": "power",
            "db": "power",
            "ats": "power",
            "pfc": "power",
            "fdr": "power",
            "mv": "power",
            "mtr": "power",
            "meter": "power",
            "dali_controller": "lighting",
            "dali": "lighting",
            "lum": "lighting",
            "fire": "fire_safety",
            "lift": "transport",
            "jace": "controller",
            "kef": "hvac",
            "medgas": "medical",
            "acc": "security",
            "cctv": "security",
        }

        return {
            "id": mapping.equipment_id,  # Already v2.0 format (S###-TYPE-FLOOR-ZONE)
            "name": mapping.equipment_name,
            "device_type": device_type_map.get(mapping.equipment_type, "other"),
            "equipment_type": mapping.equipment_type,
            "site_id": mapping.site_id,
            "protocol": "bacnet",
            "points": point_defs,
            "metadata": {
                "source": "niagara_auto_discovery",
                "discovery_confidence": mapping.confidence,
                "auto_generated": True,
                "created_at": mapping.created_at,
            },
        }

    def validate_mappings(
        self,
        mappings: Dict[str, EquipmentMapping],
        haystack_tags: Optional[Dict[str, Any]] = None,
    ) -> MappingValidationResult:
        """Validate point mappings for completeness and correctness.

        Checks for:
        - Orphan points (no equipment association)
        - Duplicate point names across equipment
        - Missing typical points for equipment type
        - Low confidence classifications

        Args:
            mappings: Equipment mappings to validate
            haystack_tags: Optional Haystack tag data for typical point checks

        Returns:
            MappingValidationResult with issues found
        """
        result = MappingValidationResult()

        # Load haystack tags for typical point checking
        if haystack_tags is None:
            haystack_tags = self._load_haystack_tags()

        equipment_patterns = haystack_tags.get("equipment_patterns", {})

        # Track all point names for duplicate detection
        all_point_names: Dict[str, str] = {}  # name -> equipment_id

        for equip_id, mapping in mappings.items():
            # Check for UNASSIGNED (orphan) group
            if equip_id == "UNASSIGNED":
                for p in mapping.points:
                    result.orphan_points.append(p.get("original_name", ""))
                if mapping.points:
                    result.warnings.append(f"{len(mapping.points)} orphan points not assigned to any equipment")

            # Check for duplicates
            for p in mapping.points:
                name = p.get("original_name", "")
                if name in all_point_names:
                    result.duplicate_points.append(name)
                    result.warnings.append(
                        f"Duplicate point '{name}' in both '{all_point_names[name]}' and '{equip_id}'"
                    )
                else:
                    all_point_names[name] = equip_id

            # Check for low confidence
            for p in mapping.points:
                if p.get("confidence") in ("low", "unknown"):
                    result.low_confidence_points.append(p.get("original_name", ""))

            # Check for missing typical points
            if mapping.equipment_type in equipment_patterns:
                typical = equipment_patterns[mapping.equipment_type].get("typical_points", [])
                mapped_categories = {p.get("point_category") for p in mapping.points}

                missing = []
                for tp in typical:
                    # Check if any mapped point category matches the typical point
                    tp_lower = tp.lower()
                    found = any(cat and tp_lower in cat.lower() for cat in mapped_categories)
                    if not found:
                        missing.append(tp)

                if missing:
                    result.missing_typical_points[equip_id] = missing
                    result.warnings.append(
                        f"{equip_id} ({mapping.equipment_type}): missing typical points: {', '.join(missing)}"
                    )

        # Set validity
        if result.errors:
            result.valid = False
        if result.orphan_points and len(result.orphan_points) > len(all_point_names) * 0.2:
            result.warnings.append("More than 20% of points are orphaned - check discovery quality")

        return result

    def save_mappings(
        self,
        discovery_id: str,
        mappings: Dict[str, EquipmentMapping],
        site_id: str = "",
    ) -> Dict[str, Any]:
        """Save mappings with dual-write (JSON primary, Supabase optional).

        Args:
            discovery_id: Discovery ID to associate mappings with
            mappings: Equipment mappings to save
            site_id: Site ID for file organization

        Returns:
            Dict with save status
        """
        # Cache in memory
        self._mapping_cache[discovery_id] = mappings

        # Save to JSON
        json_result = self._save_to_json(discovery_id, mappings, site_id)

        # Record in history
        history_entry = {
            "action": "save",
            "discovery_id": discovery_id,
            "timestamp": datetime.utcnow().isoformat(),
            "equipment_count": len(mappings),
            "total_points": sum(len(m.points) for m in mappings.values()),
        }
        if discovery_id not in self._mapping_history:
            self._mapping_history[discovery_id] = []
        self._mapping_history[discovery_id].append(history_entry)

        # Attempt Supabase write (best-effort)
        supabase_result = self._save_to_supabase(discovery_id, mappings)

        return {
            "success": json_result.get("success", False),
            "json_saved": json_result.get("success", False),
            "supabase_saved": supabase_result.get("success", False),
            "file_path": json_result.get("file_path", ""),
            "equipment_count": len(mappings),
        }

    def _save_to_json(
        self,
        discovery_id: str,
        mappings: Dict[str, EquipmentMapping],
        site_id: str,
    ) -> Dict[str, Any]:
        """Save mappings to JSON file."""
        try:
            save_dir = DATA_DIR / "mappings"
            save_dir.mkdir(parents=True, exist_ok=True)

            filepath = save_dir / f"mapping_{discovery_id}.json"

            data = {
                "discovery_id": discovery_id,
                "site_id": site_id,
                "created_at": datetime.utcnow().isoformat(),
                "equipment_count": len(mappings),
                "total_points": sum(len(m.points) for m in mappings.values()),
                "equipment": {eid: m.to_dict() for eid, m in mappings.items()},
            }

            with open(filepath, "w") as f:
                json.dump(data, f, indent=2, default=str)

            logger.info("Saved mapping %s to %s", discovery_id, filepath)
            return {"success": True, "file_path": str(filepath)}

        except Exception as e:
            logger.error("Failed to save mapping to JSON: %s", e)
            return {"success": False, "error": str(e)}

    def _save_to_supabase(
        self,
        discovery_id: str,
        mappings: Dict[str, EquipmentMapping],
    ) -> Dict[str, Any]:
        """Save equipment to Supabase buildings and equipment tables.

        Creates or finds the building record, then creates equipment records
        for all approved mappings.
        """
        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()

            if client is None:
                return {"success": False, "reason": "Supabase not configured"}

            # Get site_id from first mapping
            site_id = next((m.site_id for m in mappings.values() if m.site_id), "")
            if not site_id:
                return {"success": False, "reason": "No site_id in mappings"}

            # 1. Get or create building record
            building_result = client.table("buildings").select("id").eq("code", site_id).execute()

            if building_result.data:
                building_id = building_result.data[0]["id"]
            else:
                # Load building.json and create record
                building_json = self._load_building_json(site_id)
                if not building_json:
                    return {"success": False, "reason": f"building.json not found for {site_id}"}

                metadata = building_json.get("metadata", {})
                insert_result = (
                    client.table("buildings")
                    .insert(
                        {
                            "code": site_id,
                            "name": building_json.get("name", site_id),
                            "address": building_json.get("address", ""),
                            "type": metadata.get("type", "office"),
                            "region": "South Africa",  # Default region
                            "sqm": metadata.get("sqm", 0),
                            "floors": metadata.get("total_floors", 1),
                        }
                    )
                    .execute()
                )
                building_id = insert_result.data[0]["id"]
                logger.info("Created building record in Supabase: %s -> %s", site_id, building_id)

            # 2. Insert equipment records
            equipment_created = 0
            for eid, mapping in mappings.items():
                if eid == "UNASSIGNED":
                    continue

                # Check if equipment already exists
                existing = client.table("equipment").select("id").eq("code", mapping.equipment_id).execute()
                if existing.data:
                    continue  # Skip existing

                try:
                    client.table("equipment").insert(
                        {
                            "building_id": building_id,
                            "code": mapping.equipment_id,
                            "name": mapping.equipment_name,
                            "equipment_type": mapping.equipment_type,
                            "status": "normal",
                            "metadata": {
                                "source": "niagara_discovery",
                                "discovery_id": discovery_id,
                                "confidence": mapping.confidence,
                                "point_count": len(mapping.points),
                            },
                        }
                    ).execute()
                    equipment_created += 1
                except Exception as e:
                    logger.warning("Failed to create equipment %s in Supabase: %s", mapping.equipment_id, e)

            logger.info(
                "Saved %d equipment records to Supabase for discovery %s",
                equipment_created,
                discovery_id,
            )
            return {"success": True, "equipment_created": equipment_created}

        except Exception as e:
            logger.error("Supabase save failed: %s", e)
            return {"success": False, "reason": str(e)}

    def _load_building_json(self, site_id: str) -> Optional[Dict[str, Any]]:
        """Load building.json for a site."""
        try:
            filepath = BUILDINGS_DIR / site_id / "building.json"
            if not filepath.exists():
                return None
            with open(filepath) as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to load building.json for %s: %s", site_id, e)
            return None

    def get_mappings(self, discovery_id: str) -> Optional[Dict[str, EquipmentMapping]]:
        """Get cached mappings for a discovery."""
        if discovery_id in self._mapping_cache:
            return self._mapping_cache[discovery_id]

        # Try loading from JSON
        return self._load_from_json(discovery_id)

    def _load_from_json(self, discovery_id: str) -> Optional[Dict[str, EquipmentMapping]]:
        """Load mappings from JSON file."""
        try:
            filepath = DATA_DIR / "mappings" / f"mapping_{discovery_id}.json"
            if not filepath.exists():
                return None

            with open(filepath) as f:
                data = json.load(f)

            mappings: Dict[str, EquipmentMapping] = {}
            for eid, edata in data.get("equipment", {}).items():
                mapping = EquipmentMapping(
                    equipment_id=edata.get("equipment_id", eid),
                    equipment_type=edata.get("equipment_type", "unknown"),
                    equipment_name=edata.get("equipment_name", ""),
                    site_id=edata.get("site_id", ""),
                    points=edata.get("points", []),
                    confidence=edata.get("confidence", "medium"),
                    metadata=edata.get("metadata", {}),
                )
                mapping.approved = edata.get("approved", False)
                mapping.approved_at = edata.get("approved_at")
                mapping.approved_by = edata.get("approved_by")
                mapping.created_at = edata.get("created_at", "")
                mappings[eid] = mapping

            self._mapping_cache[discovery_id] = mappings
            return mappings

        except Exception as e:
            logger.warning("Failed to load mapping %s: %s", discovery_id, e)
            return None

    def correct_point(
        self,
        discovery_id: str,
        point_name: str,
        new_equipment_id: Optional[str] = None,
        new_point_type: Optional[str] = None,
        new_equipment_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Apply manual correction to a point classification.

        Args:
            discovery_id: Discovery ID containing the point
            point_name: Original point name to correct
            new_equipment_id: New equipment to assign point to
            new_point_type: Corrected point type
            new_equipment_type: Corrected equipment type

        Returns:
            Dict with correction status
        """
        mappings = self.get_mappings(discovery_id)
        if mappings is None:
            return {"success": False, "error": f"Discovery {discovery_id} not found"}

        # Find the point
        found = False
        source_equip = None
        point_data = None

        for eid, mapping in mappings.items():
            for p in mapping.points:
                if p.get("original_name") == point_name:
                    found = True
                    source_equip = eid
                    point_data = p
                    break
            if found:
                break

        if not found:
            return {"success": False, "error": f"Point '{point_name}' not found"}

        corrections_applied = []

        # Apply corrections
        if new_point_type:
            point_data["point_type"] = new_point_type
            corrections_applied.append(f"point_type -> {new_point_type}")

        if new_equipment_type:
            # Update the equipment mapping type
            if source_equip and source_equip in mappings:
                mappings[source_equip].equipment_type = new_equipment_type
                corrections_applied.append(f"equipment_type -> {new_equipment_type}")

        if new_equipment_id and new_equipment_id != source_equip:
            # Move point to different equipment
            if source_equip and source_equip in mappings:
                mappings[source_equip].points.remove(point_data)

            if new_equipment_id not in mappings:
                # Create new equipment mapping
                mappings[new_equipment_id] = EquipmentMapping(
                    equipment_id=new_equipment_id,
                    equipment_type=new_equipment_type or "unknown",
                    site_id=mappings.get(source_equip, EquipmentMapping("", "")).site_id,
                    confidence="manual",
                )

            mappings[new_equipment_id].points.append(point_data)
            corrections_applied.append(f"moved from {source_equip} to {new_equipment_id}")

        # Mark confidence as manually verified
        point_data["confidence"] = "manual"

        # Record correction in history
        history_entry = {
            "action": "correct",
            "point_name": point_name,
            "corrections": corrections_applied,
            "timestamp": datetime.utcnow().isoformat(),
        }
        if discovery_id not in self._mapping_history:
            self._mapping_history[discovery_id] = []
        self._mapping_history[discovery_id].append(history_entry)

        # Re-save
        site_id = next((m.site_id for m in mappings.values() if m.site_id), "")
        self.save_mappings(discovery_id, mappings, site_id)

        return {
            "success": True,
            "corrections": corrections_applied,
            "point_name": point_name,
        }

    def approve_mappings(
        self,
        discovery_id: str,
        approved_by: str = "system",
    ) -> Dict[str, Any]:
        """Approve all equipment mappings for activation.

        Args:
            discovery_id: Discovery ID to approve
            approved_by: Name of approver

        Returns:
            Dict with approval status and equipment models
        """
        mappings = self.get_mappings(discovery_id)
        if mappings is None:
            return {"success": False, "error": f"Discovery {discovery_id} not found"}

        now = datetime.utcnow().isoformat()
        equipment_models = []

        for eid, mapping in mappings.items():
            if eid == "UNASSIGNED":
                continue  # Skip orphan group

            mapping.approved = True
            mapping.approved_at = now
            mapping.approved_by = approved_by

            # Generate equipment model
            model = self.generate_equipment_model(mapping)
            equipment_models.append(model)

        # Re-save with approval status
        site_id = next((m.site_id for m in mappings.values() if m.site_id), "")
        self.save_mappings(discovery_id, mappings, site_id)

        # Save equipment models to buildings directory
        models_saved = self._save_equipment_models(equipment_models, site_id)

        # NEW: Generate zones file from equipment
        zones_result = self.generate_zones_file(equipment_models, site_id)

        # Record in history
        history_entry = {
            "action": "approve",
            "approved_by": approved_by,
            "timestamp": now,
            "equipment_count": len(equipment_models),
            "zones_generated": zones_result.get("zones_count", 0),
        }
        if discovery_id not in self._mapping_history:
            self._mapping_history[discovery_id] = []
        self._mapping_history[discovery_id].append(history_entry)

        return {
            "success": True,
            "equipment_created": len(equipment_models),
            "equipment_models": equipment_models,
            "models_saved": models_saved,
            "zones_generated": zones_result.get("success", False),
            "zones_count": zones_result.get("zones_count", 0),
        }

    def _save_equipment_models(
        self,
        models: List[Dict[str, Any]],
        site_id: str,
    ) -> bool:
        """Save equipment models to the buildings directory."""
        if not site_id:
            return False

        try:
            equip_dir = BUILDINGS_DIR / site_id / "equipment"
            equip_dir.mkdir(parents=True, exist_ok=True)

            for model in models:
                model_id = model.get("id", "unknown")
                filepath = equip_dir / f"{model_id}.json"
                with open(filepath, "w") as f:
                    json.dump(model, f, indent=2, default=str)

            logger.info("Saved %d equipment models to %s", len(models), equip_dir)
            return True

        except Exception as e:
            logger.error("Failed to save equipment models: %s", e)
            return False

    def generate_zones_file(
        self,
        equipment_models: List[Dict[str, Any]],
        site_id: str,
    ) -> Dict[str, Any]:
        """Auto-generate zones.json from discovered equipment.

        Parses equipment location metadata and creates zone definitions
        based on floor and zone assignments.

        Args:
            equipment_models: List of generated equipment models
            site_id: Site ID for zone file location

        Returns:
            Dict with zone generation status
        """
        try:
            from app.services.zone_mapping_service import get_zone_mapping_service

            zone_service = get_zone_mapping_service()

            # Extract equipment list from models for zone inference
            equipment_list = [{"equipment_id": m.get("id", "")} for m in equipment_models]

            # Auto-generate zones
            zones = zone_service.create_zones_from_equipment(equipment_list, site_id)

            # Save zones.json
            zones_dir = BUILDINGS_DIR / site_id
            zones_dir.mkdir(parents=True, exist_ok=True)
            zones_file = zones_dir / "zones.json"

            zones_data = {
                "site_id": site_id,
                "generated_at": datetime.utcnow().isoformat(),
                "auto_generated": True,
                "zones": zones,
            }

            with open(zones_file, "w") as f:
                json.dump(zones_data, f, indent=2)

            logger.info(f"Generated {len(zones)} zones for {site_id}")
            return {
                "success": True,
                "zones_count": len(zones),
                "file_path": str(zones_file),
            }

        except Exception as e:
            logger.error(f"Failed to generate zones file: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def get_mapping_history(self, discovery_id: str) -> List[Dict[str, Any]]:
        """Get the change history for a mapping set."""
        return self._mapping_history.get(discovery_id, [])

    def _load_haystack_tags(self) -> Dict[str, Any]:
        """Load Haystack tags for validation."""
        try:
            with open(DATA_DIR / "haystack_tags.json") as f:
                return json.load(f)
        except Exception:
            return {}


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_mapping_service: Optional[PointMappingService] = None


def get_mapping_service() -> PointMappingService:
    """Get or create the singleton PointMappingService instance."""
    global _mapping_service
    if _mapping_service is None:
        _mapping_service = PointMappingService()
    return _mapping_service

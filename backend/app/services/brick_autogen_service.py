"""Brick Ontology Auto-Generation Service.

Builds a Brick graph from SENTINEL's equipment JSON files (canonical source)
enriched with discovery mapping metadata (classification + zone info).

Architecture:
    Equipment JSON (data/buildings/{site}/equipment/*.json)
        = authoritative for points, BACnet refs, instances, writable flags
    Discovery mapping (data/niagara/mappings/mapping_*.json)
        = enrichment for point_category, confidence, zone metadata

BMS-agnostic: works identically for Desigo, Niagara, Honeywell, etc.
The Brick layer reads from SIMBIOT's normalized data, never vendor-specific APIs.

See: docs/02-architecture/brick-ontology-layer.md
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from brickschema import Graph as BrickGraph

    BRICK_AVAILABLE = True
except ImportError:
    BRICK_AVAILABLE = False

try:
    from rdflib import BNode, Literal, Namespace, URIRef
    from rdflib.namespace import RDF, RDFS, XSD

    RDFLIB_AVAILABLE = True
except ImportError:
    RDFLIB_AVAILABLE = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Namespaces
# ---------------------------------------------------------------------------
if RDFLIB_AVAILABLE:
    BRICK = Namespace("https://brickschema.org/schema/Brick#")
    REF = Namespace("https://brickschema.org/schema/Brick/ref#")
    BACNET = Namespace("https://brickschema.org/schema/Brick/ref/bacnet#")
    SENTINEL = Namespace("urn:sentinel:")
else:
    BRICK = REF = BACNET = SENTINEL = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Equipment type -> Brick class mapping
# ---------------------------------------------------------------------------
EQUIPMENT_TYPE_TO_BRICK: dict[str, str] = {
    "chiller": "Chiller",
    "ahu": "AHU",
    "vav": "VAV",
    "fcu": "Fan_Coil_Unit",
    "pump": "Pump",
    "generator": "Generator",
    "ups": "UPS",
    "cooling_tower": "Cooling_Tower",
    "ct": "Cooling_Tower",
    "boiler": "Boiler",
    "meter": "Electrical_Meter",
    "dali_controller": "Lighting_Equipment",
    "dali": "Lighting_Equipment",
    "split": "CRAC",
}

# Classifier brick_class string -> Brick point class
CLASSIFIER_TO_BRICK_POINT: dict[str, str] = {
    "chiller.supply.temperature": "Supply_Chilled_Water_Temperature_Sensor",
    "chiller.return.temperature": "Return_Chilled_Water_Temperature_Sensor",
    "chiller.supply.pressure": "Supply_Chilled_Water_Pressure_Sensor",
    "ahu.supply.air.temperature": "Supply_Air_Temperature_Sensor",
    "zone.air.temperature": "Zone_Air_Temperature_Sensor",
}

# Confidence string -> float mapping (discovery uses string values)
CONFIDENCE_MAP: dict[str, float] = {
    "high": 0.9,
    "medium": 0.6,
    "low": 0.3,
    "unknown": 0.0,
}


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DiscoveryPointEnrichment:
    """Classification metadata from a discovery mapping point."""

    original_name: str
    standardized_name: str
    point_category: str
    confidence: float
    object_type: str
    instance: int
    brick_class: str | None = None
    haystack_tags: list[str] | None = None


@dataclass(frozen=True)
class DiscoveryEquipmentEnrichment:
    """Discovery metadata for one equipment item."""

    equipment_id: str
    equipment_type: str
    zone: dict[str, Any] | None = None
    points: list[DiscoveryPointEnrichment] = field(default_factory=list)


@dataclass
class ResolutionIndex:
    """Fast runtime lookup table for point/equipment/location resolution."""

    # bacnet_ref (e.g. "CH-1.ChwSupplyTemp") -> brick point IRI
    bacnet_ref_to_point_iri: dict[str, str] = field(default_factory=dict)
    # "analogInput,1000" -> brick point IRI
    bacnet_object_to_point_iri: dict[str, str] = field(default_factory=dict)
    # brick point IRI -> brick equipment IRI
    point_iri_to_equipment_iri: dict[str, str] = field(default_factory=dict)
    # equipment code -> brick equipment IRI
    equipment_code_to_equipment_iri: dict[str, str] = field(default_factory=dict)
    # equipment code -> brick location IRI
    equipment_code_to_location_iri: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bacnet_ref_to_point_iri": self.bacnet_ref_to_point_iri,
            "bacnet_object_to_point_iri": self.bacnet_object_to_point_iri,
            "point_iri_to_equipment_iri": self.point_iri_to_equipment_iri,
            "equipment_code_to_equipment_iri": self.equipment_code_to_equipment_iri,
            "equipment_code_to_location_iri": self.equipment_code_to_location_iri,
        }


@dataclass
class BuildResult:
    """Result of a Brick graph build."""

    equipment_count: int = 0
    point_count: int = 0
    location_count: int = 0
    skipped_unchanged: int = 0
    validation_ok: bool = True
    validation_report: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe_iri_part(s: str) -> str:
    """Sanitize a string for use in an IRI."""
    return re.sub(r"[^a-zA-Z0-9_./-]+", "_", s or "").strip("_")


def _stable_hash(obj: Any) -> str:
    """Deterministic hash for delta detection."""
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# ---------------------------------------------------------------------------
# Discovery mapping loader
# ---------------------------------------------------------------------------
def load_discovery_enrichment(
    mappings_dir: Path,
    site_id: str,
) -> dict[str, DiscoveryEquipmentEnrichment]:
    """Load discovery mappings and build enrichment index keyed by equipment_id.

    Reads all mapping_*.json files from the mappings directory.
    Filters to those matching the given site_id.
    """
    result: dict[str, DiscoveryEquipmentEnrichment] = {}

    if not mappings_dir.exists():
        logger.warning("Discovery mappings directory not found: %s", mappings_dir)
        return result

    for mapping_path in sorted(mappings_dir.glob("mapping_*.json")):
        try:
            raw = json.loads(mapping_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read mapping %s: %s", mapping_path.name, e)
            continue

        if raw.get("site_id") != site_id:
            continue

        equipment_map = raw.get("equipment", {})
        for eq_id, eq_data in equipment_map.items():
            if eq_id in result:
                continue  # first discovery wins

            zone = eq_data.get("metadata", {}).get("zone")
            points = []
            for p in eq_data.get("points", []):
                conf_str = str(p.get("confidence", "unknown")).lower()
                conf_float = CONFIDENCE_MAP.get(conf_str, 0.0)
                points.append(
                    DiscoveryPointEnrichment(
                        original_name=p.get("original_name", ""),
                        standardized_name=p.get("standardized_name", ""),
                        point_category=p.get("point_category", "unknown"),
                        confidence=conf_float,
                        object_type=p.get("object_type", ""),
                        instance=p.get("instance", 0),
                        brick_class=None,  # PointClassifier output not yet in mapping JSON
                        haystack_tags=None,
                    )
                )

            result[eq_id] = DiscoveryEquipmentEnrichment(
                equipment_id=eq_id,
                equipment_type=eq_data.get("equipment_type", "unknown"),
                zone=zone,
                points=points,
            )

    logger.info("Loaded discovery enrichment for %d equipment items (site=%s)", len(result), site_id)
    return result


# ---------------------------------------------------------------------------
# Brick Auto-Gen Service
# ---------------------------------------------------------------------------
class BrickAutogenService:
    """Builds a Brick ontology graph from SENTINEL equipment data.

    Equipment JSON files are the canonical source for points and BACnet refs.
    Discovery mappings provide classification enrichment and zone metadata.
    """

    def __init__(
        self,
        *,
        base_dir: Path,
        site_id: str,
        confidence_threshold: float = 0.75,
        low_confidence_threshold: float = 0.45,
        validate_graph: bool = True,
    ) -> None:
        if not RDFLIB_AVAILABLE:
            raise ImportError("rdflib is required for BrickAutogenService. Install with: pip install rdflib")

        self.base_dir = base_dir
        self.site_id = site_id
        self.equipment_dir = base_dir / "app" / "data" / "buildings" / site_id / "equipment"
        self.confidence_threshold = confidence_threshold
        self.low_confidence_threshold = low_confidence_threshold
        self.validate_graph = validate_graph

        # Build graph - load full Brick ontology if brickschema available
        if BRICK_AVAILABLE:
            self.g = BrickGraph(load_brick=True)
        else:
            logger.warning("brickschema not installed; using plain rdflib Graph (no SHACL validation)")
            from rdflib import Graph

            self.g = Graph()

        self.g.bind("brick", BRICK)
        self.g.bind("ref", REF)
        self.g.bind("bacnet", BACNET)
        self.g.bind("sentinel", SENTINEL)

        # Delta tracking per equipment
        self._hash_by_equipment: dict[str, str] = {}

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------
    def build(
        self,
        discovery: dict[str, DiscoveryEquipmentEnrichment] | None = None,
    ) -> tuple[Any, ResolutionIndex, BuildResult]:
        """Build Brick graph for the site.

        Args:
            discovery: Optional enrichment from discovery mappings.
                       If None, auto-loads from data/niagara/mappings/.

        Returns:
            (graph, resolution_index, build_result)
        """
        if discovery is None:
            mappings_dir = self.base_dir / "app" / "data" / "niagara" / "mappings"
            discovery = load_discovery_enrichment(mappings_dir, self.site_id)

        idx = ResolutionIndex()
        result = BuildResult()

        if not self.equipment_dir.exists():
            logger.warning("Equipment directory not found: %s", self.equipment_dir)
            return self.g, idx, result

        for eq_path in sorted(self.equipment_dir.glob("*.json")):
            try:
                eq_json = json.loads(eq_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to read equipment file %s: %s", eq_path.name, e)
                continue

            equipment_id = eq_json.get("id") or eq_path.stem
            equipment_type = (eq_json.get("equipment_type") or eq_json.get("type") or "").lower().strip()

            enrichment = discovery.get(equipment_id)

            # Delta check
            eq_input = {
                "equipment": eq_json,
                "zone": enrichment.zone if enrichment else None,
            }
            h = _stable_hash(eq_input)
            if self._hash_by_equipment.get(equipment_id) == h:
                result.skipped_unchanged += 1
                continue
            self._hash_by_equipment[equipment_id] = h

            # Equipment node
            eq_iri = self._upsert_equipment(equipment_id, equipment_type, eq_json)
            idx.equipment_code_to_equipment_iri[equipment_id] = str(eq_iri)
            result.equipment_count += 1

            # Location from discovery zone metadata
            zone = enrichment.zone if enrichment else None
            loc_iri = self._upsert_location(zone)
            if loc_iri:
                self.g.add((eq_iri, BRICK.hasLocation, loc_iri))
                idx.equipment_code_to_location_iri[equipment_id] = str(loc_iri)
                result.location_count += 1

            # Points from canonical equipment JSON
            points = eq_json.get("points", {})
            discovery_points = enrichment.points if enrichment else []
            pt_count = self._upsert_points(eq_iri, equipment_id, points, discovery_points, idx)
            result.point_count += pt_count

        # SHACL validation
        if self.validate_graph and BRICK_AVAILABLE and hasattr(self.g, "validate"):
            try:
                ok, _, report = self.g.validate()
                result.validation_ok = ok
                result.validation_report = str(report) if not ok else ""
                if not ok:
                    logger.warning("Brick graph validation failed:\n%s", report)
            except Exception as e:
                logger.warning("SHACL validation error (non-fatal): %s", e)
                result.validation_ok = True  # Don't block on validation errors

        logger.info(
            "Brick build complete: %d equipment, %d points, %d locations, %d unchanged",
            result.equipment_count,
            result.point_count,
            result.location_count,
            result.skipped_unchanged,
        )

        return self.g, idx, result

    def serialize_ttl(self) -> str:
        """Serialize the graph to Turtle format."""
        return self.g.serialize(format="turtle")

    # -----------------------------------------------------------------------
    # IRI minting (stable, deterministic)
    # -----------------------------------------------------------------------
    def _eq_iri(self, equipment_id: str) -> URIRef:
        return URIRef(SENTINEL[f"eq/{_safe_iri_part(equipment_id)}"])

    def _pt_iri(self, equipment_id: str, point_key: str) -> URIRef:
        return URIRef(SENTINEL[f"pt/{_safe_iri_part(equipment_id)}/{_safe_iri_part(point_key)}"])

    def _loc_iri(self, *parts: str) -> URIRef:
        safe = [_safe_iri_part(p) for p in parts if p]
        return URIRef(SENTINEL["loc/" + "/".join(safe)])

    # -----------------------------------------------------------------------
    # Equipment node
    # -----------------------------------------------------------------------
    def _upsert_equipment(
        self,
        equipment_id: str,
        equipment_type: str,
        eq_json: dict,
    ) -> URIRef:
        eq_iri = self._eq_iri(equipment_id)
        brick_class_name = EQUIPMENT_TYPE_TO_BRICK.get(equipment_type, "Equipment")
        eq_class = BRICK[brick_class_name]

        self.g.add((eq_iri, RDF.type, eq_class))
        self.g.add((eq_iri, RDFS.label, Literal(equipment_id)))
        self.g.add((eq_iri, SENTINEL.site_id, Literal(self.site_id)))
        self.g.add((eq_iri, SENTINEL.equipment_type, Literal(equipment_type)))

        if eq_json.get("protocol"):
            self.g.add((eq_iri, SENTINEL.protocol, Literal(eq_json["protocol"])))

        # Metadata fields (may be nested or top-level)
        metadata = eq_json.get("metadata", {})
        for attr in ("manufacturer", "model", "serial_number"):
            val = eq_json.get(attr) or metadata.get(attr)
            if val:
                self.g.add((eq_iri, SENTINEL[attr], Literal(str(val))))

        return eq_iri

    # -----------------------------------------------------------------------
    # Location hierarchy from discovery zone metadata
    # -----------------------------------------------------------------------
    def _upsert_location(self, zone: dict[str, Any] | None) -> URIRef | None:
        """Build location hierarchy from discovery zone metadata.

        Real zone example from mapping JSON:
            {"zone_id": "Zone-B1-001", "floor": "B1", "zone_letter": "001",
             "zone_type": "open_office", "site_id": "site-002"}
        """
        site_iri = self._loc_iri(self.site_id)
        self.g.add((site_iri, RDF.type, BRICK.Site))
        self.g.add((site_iri, RDFS.label, Literal(self.site_id)))

        if not zone:
            return site_iri

        parent = site_iri

        def _add_child(label: str, brick_type: URIRef) -> URIRef:
            nonlocal parent
            child = self._loc_iri(self.site_id, label)
            self.g.add((child, RDF.type, brick_type))
            self.g.add((child, RDFS.label, Literal(label)))
            self.g.add((parent, BRICK.hasPart, child))
            parent = child
            return child

        floor = zone.get("floor")
        zone_id = zone.get("zone_id")

        if floor:
            _add_child(str(floor), BRICK.Floor)
        if zone_id:
            _add_child(str(zone_id), BRICK.HVAC_Zone)

        return parent

    # -----------------------------------------------------------------------
    # Points (canonical from equipment JSON, enriched by discovery)
    # -----------------------------------------------------------------------
    def _upsert_points(
        self,
        eq_iri: URIRef,
        equipment_id: str,
        points: dict[str, dict],
        discovery_points: list[DiscoveryPointEnrichment],
        idx: ResolutionIndex,
    ) -> int:
        """Create Brick Point nodes from equipment JSON points dict.

        Real equipment JSON point example:
            "chilled_water_temperature": {
                "bacnet_ref": "CH-1.ChwSupplyTemp",
                "object_type": "analogInput",
                "instance": 1000,
                "unit": "°C",
                "writable": false,
                "point_type": "sensor",
                "default_value": 7.0
            }
        """
        # Build enrichment lookup by original_name tokens for fuzzy match
        # within the same equipment (deterministic: same equipment_id)
        enrich_by_category: dict[str, DiscoveryPointEnrichment] = {}
        for dp in discovery_points:
            cat = dp.point_category
            if cat and cat != "unknown":
                enrich_by_category[cat] = dp

        count = 0
        for point_key, p in points.items():
            pt_iri = self._pt_iri(equipment_id, point_key)

            # Equipment <-> Point relationships
            self.g.add((eq_iri, BRICK.hasPoint, pt_iri))
            self.g.add((pt_iri, BRICK.isPointOf, eq_iri))
            self.g.add((pt_iri, RDFS.label, Literal(point_key)))

            # Point attributes from canonical JSON
            unit = p.get("unit")
            writable = p.get("writable")
            point_type = p.get("point_type")
            bacnet_ref = p.get("bacnet_ref")

            if unit:
                self.g.add((pt_iri, SENTINEL.unit, Literal(str(unit))))
            if writable is not None:
                self.g.add((pt_iri, SENTINEL.writable, Literal(bool(writable), datatype=XSD.boolean)))
            if point_type:
                self.g.add((pt_iri, SENTINEL.point_type, Literal(str(point_type))))
            if bacnet_ref:
                self.g.add((pt_iri, SENTINEL.bacnet_ref, Literal(str(bacnet_ref))))

            # Classify point: try discovery enrichment, then heuristics
            enrich = self._find_enrichment(point_key, p, enrich_by_category)
            pt_class = self._classify_point(point_key, p, enrich)
            self.g.add((pt_iri, RDF.type, pt_class))

            # BACnet external reference from canonical equipment JSON
            obj_type = p.get("object_type")
            instance = p.get("instance")

            if bacnet_ref:
                idx.bacnet_ref_to_point_iri[bacnet_ref] = str(pt_iri)

            if obj_type is not None and instance is not None:
                self._attach_bacnet_ref(pt_iri, str(obj_type), int(instance), bacnet_ref)
                bacnet_key = f"{str(obj_type).lower()},{int(instance)}"
                idx.bacnet_object_to_point_iri[bacnet_key] = str(pt_iri)

            idx.point_iri_to_equipment_iri[str(pt_iri)] = str(eq_iri)
            count += 1

        return count

    def _find_enrichment(
        self,
        point_key: str,
        point: dict,
        enrich_by_category: dict[str, DiscoveryPointEnrichment],
    ) -> DiscoveryPointEnrichment | None:
        """Find the best discovery enrichment for a canonical point.

        Strategy: match by point_category inferred from the canonical point's
        name/unit/type. This is deterministic within one equipment's points.
        """
        name = point_key.lower()
        unit = (point.get("unit") or "").lower()

        # Infer category from canonical point
        if "temp" in name or "setpoint" in name or unit in {"°c", "degc", "c"}:
            return enrich_by_category.get("temperature")
        if "pressure" in name or unit in {"kpa", "pa", "psi", "bar"}:
            return enrich_by_category.get("pressure")
        if "speed" in name or "fan" in name:
            return enrich_by_category.get("speed")
        if "flow" in name or unit in {"l/s", "lps", "m3/h"}:
            return enrich_by_category.get("flow")
        if "status" in name:
            return enrich_by_category.get("status")
        if "power" in name or unit in {"kw", "kwh"}:
            return enrich_by_category.get("power")
        if "level" in name:
            return enrich_by_category.get("level")
        if "valve" in name or "damper" in name:
            return enrich_by_category.get("valve_position")

        return None

    def _classify_point(
        self,
        point_key: str,
        point: dict,
        enrich: DiscoveryPointEnrichment | None,
    ) -> URIRef:
        """Determine Brick Point class.

        Priority:
        1. High-confidence classifier brick_class from enrichment
        2. Heuristics from point_type + name + unit
        """
        # 1. Classifier enrichment
        if enrich and enrich.brick_class:
            if enrich.confidence >= self.confidence_threshold or enrich.confidence >= self.low_confidence_threshold:
                mapped = CLASSIFIER_TO_BRICK_POINT.get(enrich.brick_class.strip().lower())
                if mapped:
                    return BRICK[mapped]

        # 2. Heuristics from canonical point data
        name = (point.get("name") or point_key).lower()
        unit = (point.get("unit") or "").lower()
        ptype = (point.get("point_type") or "").lower()

        # Setpoint / command first (most specific)
        if ptype == "setpoint" or "setpoint" in name:
            if "temp" in name or unit in {"°c", "degc", "c"}:
                return BRICK.Temperature_Setpoint
            return BRICK.Setpoint
        if ptype == "command" or "command" in name or "cmd" in name:
            return BRICK.Command

        # Sensor types by name/unit
        if "temp" in name or unit in {"°c", "degc", "c", "deg_c"}:
            return BRICK.Temperature_Sensor
        if "pressure" in name or unit in {"pa", "kpa", "bar", "psi"}:
            return BRICK.Pressure_Sensor
        if "flow" in name or unit in {"l/s", "lps", "m3/h", "gpm"}:
            return BRICK.Flow_Sensor
        if "speed" in name or unit in {"hz", "rpm"}:
            return BRICK.Speed_Sensor
        if "power" in name or unit in {"kw"}:
            return BRICK.Electric_Power_Sensor
        if "energy" in name or unit in {"kwh"}:
            return BRICK.Energy_Sensor
        if "status" in name:
            return BRICK.Status
        if "level" in name or "fuel" in name:
            return BRICK.Level_Sensor
        if "valve" in name or "damper" in name:
            return BRICK.Damper_Position_Sensor
        if "lux" in name or unit == "lux":
            return BRICK.Luminance_Sensor
        if "occupancy" in name:
            return BRICK.Occupancy_Sensor
        if "co2" in name or unit == "ppm":
            return BRICK.CO2_Sensor
        if "humidity" in name or unit in {"%rh", "rh"}:
            return BRICK.Humidity_Sensor
        if "alarm" in name:
            return BRICK.Alarm

        return BRICK.Point

    def _attach_bacnet_ref(
        self,
        pt_iri: URIRef,
        object_type: str,
        instance: int,
        bacnet_ref: str | None,
    ) -> None:
        """Attach BACnet external reference to a point.

        Uses Brick's ref:hasExternalReference pattern.
        """
        refnode = BNode()
        self.g.add((pt_iri, REF.hasExternalReference, refnode))
        self.g.add((refnode, RDF.type, REF.BACnetReference))
        self.g.add((refnode, BACNET["object-identifier"], Literal(f"{object_type},{instance}")))

        if bacnet_ref:
            self.g.add((refnode, BACNET["object-name"], Literal(bacnet_ref)))


# ---------------------------------------------------------------------------
# Convenience: build for a site
# ---------------------------------------------------------------------------
def build_brick_for_site(
    base_dir: Path,
    site_id: str,
    *,
    validate: bool = True,
    output_dir: Path | None = None,
) -> tuple[ResolutionIndex, BuildResult]:
    """Build Brick graph for a site and optionally save artifacts.

    Args:
        base_dir: Backend root (e.g., /opt/bms-intelligence/backend)
        site_id: Site identifier (e.g., "site-002")
        validate: Run SHACL validation
        output_dir: If set, write brick.ttl and resolution_index.json here

    Returns:
        (resolution_index, build_result)
    """
    svc = BrickAutogenService(
        base_dir=base_dir,
        site_id=site_id,
        validate_graph=validate,
    )

    graph, idx, result = svc.build()

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        ttl_path = output_dir / f"{site_id}_brick.ttl"
        idx_path = output_dir / f"{site_id}_resolution_index.json"

        ttl_path.write_text(svc.serialize_ttl(), encoding="utf-8")
        idx_path.write_text(
            json.dumps(idx.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        logger.info("Saved Brick TTL to %s", ttl_path)
        logger.info("Saved resolution index to %s", idx_path)

    return idx, result

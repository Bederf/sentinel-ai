"""Automated point discovery service for Niagara BACnet integration.

Scans BACnet devices to discover all objects/points, retrieves metadata
(name, description, units, present_value), and feeds them through the
AI-assisted classifier for automatic equipment mapping.

Handles large point lists incrementally (1000+ points) and caches
results to avoid repeated scanning.
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.database.supabase_client import get_supabase_client
from app.services.niagara.bacnet_client import (
    BACnetException,
    NiagaraBACnetClient,
    get_bacnet_client,
)
from app.services.niagara.point_classifier import (
    ClassifiedPoint,
    PointClassifier,
    get_point_classifier,
)

logger = logging.getLogger(__name__)

# Data directory for cached discovery results
DATA_DIR = Path(__file__).parent.parent.parent / "data" / "niagara"

# BACnet object types to scan for during discovery
DISCOVERY_OBJECT_TYPES = [
    "analogInput",
    "analogOutput",
    "analogValue",
    "binaryInput",
    "binaryOutput",
    "binaryValue",
]

# Maximum points to read details for in a single batch
BATCH_SIZE = 50


def _infer_object_type(sensor_type: str) -> str:
    """Infer BACnet object type from sensor type string.

    Args:
        sensor_type: Sensor type name (e.g., 'temperature', 'setpoint', 'command')

    Returns:
        BACnet object type string (analogInput, analogValue, binaryOutput, binaryInput)
    """
    st = sensor_type.lower()
    if "setpoint" in st or "target" in st:
        return "analogValue"
    if "command" in st or "enable" in st or "mode" in st:
        return "binaryOutput"
    if "status" in st or "alarm" in st or "fault" in st:
        return "binaryInput"
    return "analogInput"


def _infer_point_type(sensor_type: str) -> str:
    """Infer point type category from sensor type string.

    Args:
        sensor_type: Sensor type name (e.g., 'temperature', 'setpoint', 'command')

    Returns:
        Point type string (sensor, setpoint, command, status)
    """
    st = sensor_type.lower()
    if "setpoint" in st or "target" in st:
        return "setpoint"
    if "command" in st or "enable" in st:
        return "command"
    if "status" in st or "alarm" in st or "fault" in st:
        return "status"
    return "sensor"


class DiscoveryResult:
    """Container for a complete point discovery and classification result."""

    def __init__(
        self,
        discovery_id: str,
        device_ip: str,
        site_id: str,
        device_id: Optional[int] = None,
    ):
        self.discovery_id = discovery_id
        self.device_ip = device_ip
        self.site_id = site_id
        self.device_id = device_id
        self.status = "pending"  # pending, discovering, classifying, complete, error
        self.started_at = datetime.utcnow().isoformat()
        self.completed_at: Optional[str] = None
        self.raw_points: List[Dict[str, Any]] = []
        self.classified_points: List[Dict[str, Any]] = []
        self.summary: Dict[str, Any] = {}
        self.error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "discovery_id": self.discovery_id,
            "device_ip": self.device_ip,
            "site_id": self.site_id,
            "device_id": self.device_id,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "points_count": len(self.raw_points),
            "classified_count": len(self.classified_points),
            "summary": self.summary,
            "error": self.error,
        }


class PointDiscoveryService:
    """Service for discovering and classifying BACnet points.

    Orchestrates the full discovery workflow:
    1. Connect to BACnet device
    2. Scan for all point objects
    3. Read point metadata (name, description, units, value)
    4. Classify points using Haystack/Brick ontology
    5. Cache results for review

    Usage:
        service = PointDiscoveryService()
        result = await service.discover_and_classify("192.168.1.100", "site-002")
        print(result.summary)  # Equipment counts, confidence breakdown
    """

    def __init__(
        self,
        bacnet_client: Optional[NiagaraBACnetClient] = None,
        classifier: Optional[PointClassifier] = None,
    ):
        self._bacnet_client = bacnet_client
        self._classifier = classifier or get_point_classifier()
        self._discovery_cache: Dict[str, DiscoveryResult] = {}

    def _get_bacnet_client(self) -> NiagaraBACnetClient:
        """Get the BACnet client, creating if needed."""
        if self._bacnet_client is None:
            self._bacnet_client = get_bacnet_client()
        return self._bacnet_client

    async def discover_and_classify(
        self,
        device_ip: str,
        site_id: str,
        device_bacnet_id: Optional[int] = None,
        bms_vendor: Optional[str] = None,
    ) -> DiscoveryResult:
        """Run full point discovery and classification workflow.

        Routes: BACnet (live device) -> Simulation (Supabase) -> JSON fallback.

        Args:
            device_ip: IP address of the BACnet device, or 'simulation' for simulation data
            site_id: SENTINEL site ID for mapping (the NEW site being created)
            device_bacnet_id: Optional BACnet device instance ID
            bms_vendor: Optional BMS vendor identifier

        Returns:
            DiscoveryResult with classified points and summary
        """
        discovery_id = str(uuid.uuid4())[:8]
        result = DiscoveryResult(
            discovery_id=discovery_id,
            device_ip=device_ip,
            site_id=site_id,
            device_id=device_bacnet_id,
        )

        logger.info(
            "Starting point discovery %s for device %s (site %s)",
            discovery_id,
            device_ip,
            site_id,
        )

        try:
            # Phase 1: Discover points (BACnet -> Simulation -> JSON fallback)
            result.status = "discovering"
            raw_points = await self._discover_points(device_ip, site_id, device_bacnet_id)
            result.raw_points = [p if isinstance(p, dict) else p.to_dict() for p in raw_points]

            logger.info(
                "Discovery %s: found %d points on %s",
                discovery_id,
                len(raw_points),
                device_ip,
            )

            # Phase 2: Classify points
            result.status = "classifying"
            classified = self._classify_discovered_points(raw_points)
            result.classified_points = [cp.to_dict() for cp in classified]

            # Phase 3: Generate summary
            result.summary = self._classifier.get_classification_summary(classified)
            result.status = "complete"
            result.completed_at = datetime.utcnow().isoformat()

            logger.info(
                "Discovery %s complete: %d points classified (%d equipment types)",
                discovery_id,
                len(classified),
                len(result.summary.get("unique_equipment", {})),
            )

        except Exception as e:
            result.status = "error"
            result.error = str(e)
            logger.error("Discovery %s failed: %s", discovery_id, e)

        # Cache result
        self._discovery_cache[discovery_id] = result
        self._save_discovery_result(result)

        return result

    async def _discover_points(
        self,
        device_ip: str,
        site_id: str,
        device_bacnet_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Discover points using 3-tier routing: BACnet -> Simulation -> JSON fallback.

        Args:
            device_ip: Device IP address (or 'simulation' for simulation-only)
            site_id: SENTINEL site ID for simulation/fallback lookup
            device_bacnet_id: BACnet device ID (if provided, tries BACnet first)

        Returns:
            List of point dicts with name, description, object_type, etc.
        """
        # Tier 1: Try BACnet discovery first (if device_bacnet_id provided)
        if device_bacnet_id is not None:
            client = self._get_bacnet_client()
            if not client.is_running:
                try:
                    logger.info("Auto-starting BACnet client for discovery...")
                    await client.start()
                except BACnetException as e:
                    logger.warning(
                        "BACnet auto-start failed: %s. Falling back to simulation data.",
                        e,
                    )

            if client.is_running:
                try:
                    return await self._discover_from_bacnet(client, device_bacnet_id)
                except BACnetException as e:
                    logger.warning(
                        "BACnet discovery failed for device %d: %s. Falling back to simulation data.",
                        device_bacnet_id,
                        e,
                    )

        # Tier 2: Try simulation data from Supabase
        sim_points = self._load_simulation_points(site_id)
        if sim_points:
            logger.info(
                "Loaded %d points from simulation data for site %s",
                len(sim_points),
                site_id,
            )
            return sim_points

        # Tier 3: Fall back to static JSON files
        json_points = self._load_demo_points(site_id)
        if json_points:
            logger.info(
                "Loaded %d points from JSON fallback for site %s",
                len(json_points),
                site_id,
            )
            return json_points

        raise BACnetException(f"No points found for {device_ip} (site {site_id}): all tiers exhausted")

    async def _discover_from_bacnet(
        self,
        client: NiagaraBACnetClient,
        device_id: int,
    ) -> List[Dict[str, Any]]:
        """Discover points from a live BACnet device.

        Handles large point lists by reading metadata in batches.
        """
        # Get raw point list
        raw_points = await client.read_point_list(
            device_id,
            object_types=DISCOVERY_OBJECT_TYPES,
            use_cache=False,
        )

        logger.info(
            "Found %d points on device %d, reading metadata...",
            len(raw_points),
            device_id,
        )

        # Read detailed metadata in batches
        detailed_points: List[Dict[str, Any]] = []

        for i in range(0, len(raw_points), BATCH_SIZE):
            batch = raw_points[i : i + BATCH_SIZE]
            logger.info(
                "Reading batch %d-%d of %d...",
                i,
                min(i + BATCH_SIZE, len(raw_points)),
                len(raw_points),
            )

            for point in batch:
                try:
                    # Read additional properties
                    name = await client.read_point(
                        device_id,
                        point.object_type,
                        point.instance,
                        property_name="objectName",
                    )
                    description = ""
                    try:
                        description = await client.read_point(
                            device_id,
                            point.object_type,
                            point.instance,
                            property_name="description",
                        )
                    except Exception:
                        pass  # Description is optional

                    units = ""
                    try:
                        units = await client.read_point(
                            device_id,
                            point.object_type,
                            point.instance,
                            property_name="units",
                        )
                    except Exception:
                        pass

                    value = None
                    try:
                        value = await client.read_point(
                            device_id,
                            point.object_type,
                            point.instance,
                            property_name="presentValue",
                        )
                    except Exception:
                        pass

                    detailed_points.append(
                        {
                            "name": str(name) if name else f"{point.object_type}_{point.instance}",
                            "description": str(description) if description else "",
                            "object_type": point.object_type,
                            "instance": point.instance,
                            "units": str(units) if units else "",
                            "present_value": value,
                            "writable": point.writable,
                        }
                    )

                except BACnetException as e:
                    logger.warning(
                        "Failed to read metadata for %s:%d: %s",
                        point.object_type,
                        point.instance,
                        e,
                    )
                    # Add with minimal info
                    detailed_points.append(
                        {
                            "name": f"{point.object_type}_{point.instance}",
                            "description": "",
                            "object_type": point.object_type,
                            "instance": point.instance,
                            "units": "",
                            "present_value": None,
                            "writable": point.writable,
                        }
                    )

        return detailed_points

    def _load_demo_points(self, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Load points from static JSON equipment files (Tier 3 fallback).

        Args:
            site_id: Site ID to load equipment files from (e.g., 'site-002').
                     If None, falls back to haystack_tags.json demo points.

        Returns:
            List of point dicts with name, description, object_type, etc.
        """
        # If site_id is provided, load from that building's equipment files
        if site_id:
            equipment_dir = DATA_DIR.parent / "buildings" / site_id / "equipment"

            if equipment_dir.exists():
                points = self._load_points_from_equipment_dir(equipment_dir, site_id)
                if points:
                    logger.info(
                        "Loaded %d JSON fallback points from %s equipment files",
                        len(points),
                        site_id,
                    )
                    return points
                else:
                    logger.warning(
                        "Site %s has no equipment files, falling back to haystack_tags.json",
                        site_id,
                    )
            else:
                logger.warning(
                    "Site %s equipment directory not found: %s, falling back to haystack_tags.json",
                    site_id,
                    equipment_dir,
                )

        # Fallback to haystack_tags.json
        return self._load_from_haystack_tags()

    def _load_points_from_equipment_dir(self, equipment_dir: Path, demo_building_id: str) -> List[Dict[str, Any]]:
        """Extract demo points from a building's equipment files.

        Args:
            equipment_dir: Path to equipment directory
            demo_building_id: ID of the demo building for logging

        Returns:
            List of point dicts ready for classification
        """
        points = []
        instance_counter = 1000

        for eq_file in sorted(equipment_dir.glob("*.json")):
            try:
                with open(eq_file) as f:
                    equipment = json.load(f)

                eq_id = equipment.get("id", eq_file.stem)
                eq_name = equipment.get("name", eq_id)
                eq_type = equipment.get("equipment_type", "unknown")
                eq_points = equipment.get("points", {})

                for point_name, point_def in eq_points.items():
                    # Determine object type based on point definition
                    obj_type = point_def.get("object_type", "analogInput")

                    points.append(
                        {
                            "name": f"{eq_id}.{point_name}",
                            "description": f"{eq_name} - {point_name.replace('_', ' ').title()}",
                            "object_type": obj_type,
                            "instance": instance_counter,
                            "units": point_def.get("unit", ""),
                            "present_value": point_def.get("default_value", 0),
                            "writable": point_def.get("writable", False),
                            # Extra fields to help classification
                            "_equipment_id": eq_id,
                            "_equipment_type": eq_type,
                            "_point_type": point_def.get("point_type", "sensor"),
                        }
                    )
                    instance_counter += 1

            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Failed to parse equipment file %s: %s", eq_file.name, e)
                continue

        return points

    def _load_from_haystack_tags(self) -> List[Dict[str, Any]]:
        """Load demo points from haystack_tags.json (legacy fallback)."""
        try:
            tags_path = DATA_DIR / "haystack_tags.json"
            with open(tags_path) as f:
                data = json.load(f)
            demo_points = data.get("demo_points", [])
            logger.info("Loaded %d demo points from haystack_tags.json", len(demo_points))
            return demo_points
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error("Failed to load demo points from haystack_tags.json: %s", e)
            return []

    def _load_simulation_points(self, site_id: str) -> List[Dict[str, Any]]:
        """Load points from Supabase equipment + sensor readings (simulation data).

        Queries the equipment table for equipment belonging to the site, then
        fetches latest sensor readings from equipment_sensor_readings. Formats
        results as point dicts matching the classifier's expected input format.

        Args:
            site_id: SENTINEL site ID (e.g., 'site-002')

        Returns:
            List of point dicts, or empty list if Supabase unavailable or no data.
        """
        try:
            client = get_supabase_client()
        except Exception as e:
            logger.warning("Supabase client unavailable for simulation points: %s", e)
            return []

        try:
            # Try to find equipment via buildings table first
            equipment_rows = []
            try:
                buildings_resp = (
                    client.table("buildings").select("id").or_(f"code.eq.{site_id},site_id.eq.{site_id}").execute()
                )
                building_ids = [b["id"] for b in (buildings_resp.data or [])]

                if building_ids:
                    equip_resp = (
                        client.table("equipment")
                        .select("code,name,type,status,health_score")
                        .in_("building_id", building_ids)
                        .execute()
                    )
                    equipment_rows = equip_resp.data or []
            except Exception as e:
                logger.debug("Buildings-based equipment lookup failed: %s", e)

            # Fallback: match by equipment code prefix (e.g., S002-)
            if not equipment_rows:
                prefix = site_id.upper().replace("SITE-", "S")
                try:
                    equip_resp = (
                        client.table("equipment")
                        .select("code,name,type,status,health_score")
                        .like("code", f"{prefix}-%")
                        .execute()
                    )
                    equipment_rows = equip_resp.data or []
                except Exception as e:
                    logger.debug("Prefix-based equipment lookup failed: %s", e)

            if not equipment_rows:
                logger.info("No simulation equipment found for site %s", site_id)
                return []

            # Fetch sensor readings for each equipment and build point dicts
            points: List[Dict[str, Any]] = []
            instance_counter = 2000  # Offset from JSON fallback range (1000+)

            for equip in equipment_rows:
                eq_code = equip.get("code", "")
                eq_name = equip.get("name", eq_code)
                eq_type = equip.get("type", "unknown")

                try:
                    readings_resp = (
                        client.table("equipment_sensor_readings")
                        .select("sensor_type,value,unit")
                        .eq("equipment_id", eq_code)
                        .order("recorded_at", desc=True)
                        .limit(50)
                    ).execute()
                    readings = readings_resp.data or []
                except Exception as e:
                    logger.debug("Sensor readings query failed for %s: %s", eq_code, e)
                    readings = []

                # Deduplicate by sensor_type (keep first = most recent)
                seen_types: set = set()
                for reading in readings:
                    sensor_type = reading.get("sensor_type", "")
                    if not sensor_type or sensor_type in seen_types:
                        continue
                    seen_types.add(sensor_type)

                    points.append(
                        {
                            "name": f"{eq_code}.{sensor_type}",
                            "description": f"{eq_name} - {sensor_type.replace('_', ' ').title()}",
                            "object_type": _infer_object_type(sensor_type),
                            "instance": instance_counter,
                            "units": reading.get("unit", ""),
                            "present_value": reading.get("value"),
                            "writable": sensor_type in ("setpoint", "command", "mode"),
                            "_equipment_id": eq_code,
                            "_equipment_type": eq_type,
                            "_point_type": _infer_point_type(sensor_type),
                        }
                    )
                    instance_counter += 1

            logger.info(
                "Loaded %d simulation points from %d equipment for site %s",
                len(points),
                len(equipment_rows),
                site_id,
            )
            return points

        except Exception as e:
            logger.warning("Failed to load simulation points for %s: %s", site_id, e)
            return []

    def _classify_discovered_points(self, points: List[Dict[str, Any]]) -> List[ClassifiedPoint]:
        """Classify all discovered points using the point classifier."""
        return self._classifier.classify_points(points)

    def get_discovery_result(self, discovery_id: str) -> Optional[DiscoveryResult]:
        """Get a cached discovery result by ID.

        Args:
            discovery_id: Discovery identifier

        Returns:
            DiscoveryResult if found, None otherwise
        """
        # Check in-memory cache
        if discovery_id in self._discovery_cache:
            return self._discovery_cache[discovery_id]

        # Try loading from file
        return self._load_discovery_result(discovery_id)

    def list_discoveries(self) -> List[Dict[str, Any]]:
        """List all cached discovery results (metadata only)."""
        results = []
        for result in self._discovery_cache.values():
            results.append(result.to_dict())
        return results

    def _save_discovery_result(self, result: DiscoveryResult) -> None:
        """Save discovery result to JSON file for persistence."""
        try:
            save_dir = DATA_DIR / "discoveries"
            save_dir.mkdir(parents=True, exist_ok=True)

            filepath = save_dir / f"discovery_{result.discovery_id}.json"
            with open(filepath, "w") as f:
                json.dump(
                    {
                        "metadata": result.to_dict(),
                        "classified_points": result.classified_points,
                        "raw_points": result.raw_points,
                    },
                    f,
                    indent=2,
                    default=str,
                )
            logger.debug("Saved discovery %s to %s", result.discovery_id, filepath)
        except Exception as e:
            logger.warning("Failed to save discovery result: %s", e)

    def _load_discovery_result(self, discovery_id: str) -> Optional[DiscoveryResult]:
        """Load a discovery result from JSON file."""
        try:
            filepath = DATA_DIR / "discoveries" / f"discovery_{discovery_id}.json"
            if not filepath.exists():
                return None

            with open(filepath) as f:
                data = json.load(f)

            metadata = data.get("metadata", {})
            result = DiscoveryResult(
                discovery_id=metadata.get("discovery_id", discovery_id),
                device_ip=metadata.get("device_ip", ""),
                site_id=metadata.get("site_id", ""),
                device_id=metadata.get("device_id"),
            )
            result.status = metadata.get("status", "complete")
            result.started_at = metadata.get("started_at", "")
            result.completed_at = metadata.get("completed_at")
            result.summary = metadata.get("summary", {})
            result.error = metadata.get("error")
            result.classified_points = data.get("classified_points", [])
            result.raw_points = data.get("raw_points", [])

            # Cache for future lookups
            self._discovery_cache[discovery_id] = result
            return result

        except Exception as e:
            logger.warning("Failed to load discovery %s: %s", discovery_id, e)
            return None


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_discovery_service: Optional[PointDiscoveryService] = None


def get_point_discovery_service() -> PointDiscoveryService:
    """Get or create the singleton PointDiscoveryService instance."""
    global _discovery_service
    if _discovery_service is None:
        _discovery_service = PointDiscoveryService()
    return _discovery_service

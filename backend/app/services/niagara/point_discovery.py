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
        self._demo_mode = True  # Use demo data when BACnet not available

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
        use_demo: bool = True,
        demo_building_id: Optional[str] = None,
        bms_vendor: Optional[str] = None,
    ) -> DiscoveryResult:
        """Run full point discovery and classification workflow.

        Args:
            device_ip: IP address of the BACnet device (JACE/Supervisor)
            site_id: SENTINEL site ID for mapping (the NEW site being created)
            device_bacnet_id: Optional BACnet device instance ID
            use_demo: If True, use demo points when BACnet unavailable
            demo_building_id: Demo building ID to load data from (e.g., 'site-004')

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
            "Starting point discovery %s for device %s (site %s, demo_building=%s)",
            discovery_id, device_ip, site_id, demo_building_id,
        )

        try:
            # Phase 1: Discover points
            result.status = "discovering"
            raw_points = await self._discover_points(
                device_ip, device_bacnet_id, use_demo, demo_building_id
            )
            result.raw_points = [p if isinstance(p, dict) else p.to_dict() for p in raw_points]

            logger.info(
                "Discovery %s: found %d points on %s",
                discovery_id, len(raw_points), device_ip,
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
        device_bacnet_id: Optional[int],
        use_demo: bool,
        demo_building_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Discover points from BACnet device or demo data.

        Auto-starts the BACnet client if BAC0 is installed and a real
        device_bacnet_id is provided.

        Args:
            device_ip: Device IP address
            device_bacnet_id: BACnet device ID
            use_demo: Fall back to demo data if BACnet unavailable
            demo_building_id: Demo building ID to load data from (e.g., 'site-004')

        Returns:
            List of point dicts with name, description, object_type, etc.
        """
        # Try BACnet discovery first
        client = self._get_bacnet_client()

        if device_bacnet_id is not None:
            # Auto-start if not running and BAC0 is available
            if not client.is_running:
                try:
                    logger.info("Auto-starting BACnet client for discovery...")
                    await client.start()
                except BACnetException as e:
                    logger.warning(
                        "BACnet auto-start failed: %s. %s",
                        e,
                        "Falling back to demo data." if use_demo else "No fallback.",
                    )
                    if not use_demo:
                        raise

            if client.is_running:
                try:
                    return await self._discover_from_bacnet(client, device_bacnet_id)
                except BACnetException as e:
                    logger.warning(
                        "BACnet discovery failed for device %d: %s. %s",
                        device_bacnet_id, e,
                        "Falling back to demo data." if use_demo else "No fallback.",
                    )
                    if not use_demo:
                        raise

        # Fall back to demo data
        if use_demo or self._demo_mode:
            return self._load_demo_points(demo_building_id)

        raise BACnetException(
            f"BACnet client not running and demo mode disabled for {device_ip}"
        )

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
            len(raw_points), device_id,
        )

        # Read detailed metadata in batches
        detailed_points: List[Dict[str, Any]] = []

        for i in range(0, len(raw_points), BATCH_SIZE):
            batch = raw_points[i:i + BATCH_SIZE]
            logger.info(
                "Reading batch %d-%d of %d...",
                i, min(i + BATCH_SIZE, len(raw_points)), len(raw_points),
            )

            for point in batch:
                try:
                    # Read additional properties
                    name = await client.read_point(
                        device_id, point.object_type, point.instance,
                        property_name="objectName",
                    )
                    description = ""
                    try:
                        description = await client.read_point(
                            device_id, point.object_type, point.instance,
                            property_name="description",
                        )
                    except Exception:
                        pass  # Description is optional

                    units = ""
                    try:
                        units = await client.read_point(
                            device_id, point.object_type, point.instance,
                            property_name="units",
                        )
                    except Exception:
                        pass

                    value = None
                    try:
                        value = await client.read_point(
                            device_id, point.object_type, point.instance,
                            property_name="presentValue",
                        )
                    except Exception:
                        pass

                    detailed_points.append({
                        "name": str(name) if name else f"{point.object_type}_{point.instance}",
                        "description": str(description) if description else "",
                        "object_type": point.object_type,
                        "instance": point.instance,
                        "units": str(units) if units else "",
                        "present_value": value,
                        "writable": point.writable,
                    })

                except BACnetException as e:
                    logger.warning(
                        "Failed to read metadata for %s:%d: %s",
                        point.object_type, point.instance, e,
                    )
                    # Add with minimal info
                    detailed_points.append({
                        "name": f"{point.object_type}_{point.instance}",
                        "description": "",
                        "object_type": point.object_type,
                        "instance": point.instance,
                        "units": "",
                        "present_value": None,
                        "writable": point.writable,
                    })

        return detailed_points

    def _load_demo_points(self, demo_building_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Load demo points from a demo building's equipment files.

        Args:
            demo_building_id: ID of demo building to load data from (e.g., 'site-004').
                            If None, falls back to haystack_tags.json demo points.

        Returns:
            List of point dicts with name, description, object_type, etc.
        """
        # If demo_building_id is provided, load from that building's equipment files
        if demo_building_id:
            equipment_dir = DATA_DIR.parent / "buildings" / demo_building_id / "equipment"

            if equipment_dir.exists():
                points = self._load_points_from_equipment_dir(equipment_dir, demo_building_id)
                if points:
                    logger.info(
                        "Loaded %d demo points from %s equipment files",
                        len(points), demo_building_id,
                    )
                    return points
                else:
                    logger.warning(
                        "Demo building %s has no equipment files, falling back to haystack_tags.json",
                        demo_building_id,
                    )
            else:
                logger.warning(
                    "Demo building %s equipment directory not found: %s, falling back to haystack_tags.json",
                    demo_building_id, equipment_dir,
                )

        # Fallback to haystack_tags.json
        return self._load_from_haystack_tags()

    def _load_points_from_equipment_dir(
        self, equipment_dir: Path, demo_building_id: str
    ) -> List[Dict[str, Any]]:
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

                    points.append({
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
                    })
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

    def _classify_discovered_points(
        self, points: List[Dict[str, Any]]
    ) -> List[ClassifiedPoint]:
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

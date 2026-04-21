"""Automated point discovery service for Niagara BACnet integration.

Scans BACnet devices to discover all objects/points, retrieves metadata
(name, description, units, present_value), and feeds them through the
AI-assisted classifier for automatic equipment mapping.

Handles large point lists incrementally (1000+ points) and caches
results to avoid repeated scanning.
"""

import contextlib
import csv
import io
import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

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
from app.services.simbiot import (
    BmsConnectionConfig,
    BmsDeviceDescriptor,
    BmsPointDescriptor,
    BmsPointValue,
    create_bms_adapter,
    filter_classified_points_for_site,
    resolve_bms_adapter_type,
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
        device_id: int | None = None,
    ):
        self.discovery_id = discovery_id
        self.device_ip = device_ip
        self.site_id = site_id
        self.device_id = device_id
        self.status = "pending"  # pending, discovering, classifying, complete, error
        self.started_at = datetime.utcnow().isoformat()
        self.completed_at: str | None = None
        self.raw_points: list[dict[str, Any]] = []
        self.classified_points: list[dict[str, Any]] = []
        self.summary: dict[str, Any] = {}
        self.error: str | None = None

    def to_dict(self) -> dict[str, Any]:
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
        bacnet_client: NiagaraBACnetClient | None = None,
        classifier: PointClassifier | None = None,
    ):
        self._bacnet_client = bacnet_client
        self._classifier = classifier or get_point_classifier()
        self._discovery_cache: dict[str, DiscoveryResult] = {}

    def _get_bacnet_client(self) -> NiagaraBACnetClient:
        """Get the BACnet client, creating if needed."""
        if self._bacnet_client is None:
            self._bacnet_client = get_bacnet_client()
        return self._bacnet_client

    async def discover_and_classify(
        self,
        device_ip: str,
        site_id: str,
        device_bacnet_id: int | None = None,
        bms_vendor: str | None = None,
        adapter_type: str | None = None,
    ) -> DiscoveryResult:
        """Run full point discovery and classification workflow.

        Routes: BACnet (live device) -> Simulation adapter -> JSON fallback.

        Args:
            device_ip: IP address of the BACnet device, or 'simulation' for simulation data
            site_id: SENTINEL site ID for mapping (the NEW site being created)
            device_bacnet_id: Optional BACnet device instance ID
            bms_vendor: Optional BMS vendor identifier
            adapter_type: Explicit adapter selection ('bacnet', 'simulation')

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
            # Phase 1: Discover points (adapter route -> JSON fallback)
            result.status = "discovering"
            raw_points = await self._discover_points(device_ip, site_id, device_bacnet_id, adapter_type, bms_vendor)
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
            raw_points, classified, dropped_points = self._apply_module_policy(site_id, raw_points, classified)
            result.raw_points = [p if isinstance(p, dict) else p.to_dict() for p in raw_points]
            result.classified_points = [cp.to_dict() for cp in classified]

            # Phase 3: Generate summary
            result.summary = self._classifier.get_classification_summary(classified)
            if dropped_points:
                result.summary["module_filtered_points"] = dropped_points
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

    def discover_from_csv(
        self,
        csv_content: str,
        site_id: str,
        source_label: str = "desigo-export",
    ) -> DiscoveryResult:
        """Discover and classify points from a BMS CSV export.

        Accepts the standard Desigo/Niagara CSV format:
            name,object_type,instance,units,present_value,description,min_value,max_value,writable

        Also handles the hierarchical Desigo naming convention:
            STC/{LEVEL}/{EQUIP-ID}/{PointName}  e.g. STC/L1/DALI-01/Lum01_ActivePower

        The equipment ID is extracted from the path hierarchy and passed
        to the classifier as metadata for high-confidence classification.

        Args:
            csv_content: CSV string content (with header row)
            site_id: SENTINEL site ID for mapping
            source_label: Label for the export source (e.g., 'desigo-export')

        Returns:
            DiscoveryResult with classified points and summary
        """
        self._load_tags_via_classifier()

        discovery_id = f"csv-{str(uuid.uuid4())[:8]}"
        result = DiscoveryResult(
            discovery_id=discovery_id,
            device_ip=source_label,
            site_id=site_id,
        )

        logger.info(
            "Starting CSV discovery %s for site %s (source: %s)",
            discovery_id,
            site_id,
            source_label,
        )

        try:
            # Phase 1: Parse CSV
            result.status = "discovering"
            raw_points = self._parse_csv_export(csv_content)
            result.raw_points = raw_points

            logger.info(
                "CSV discovery %s: parsed %d points from %s",
                discovery_id,
                len(raw_points),
                source_label,
            )

            # Phase 2: Classify points
            result.status = "classifying"
            classified = self._classifier.classify_points(raw_points)
            raw_points, classified, dropped_points = self._apply_module_policy(site_id, raw_points, classified)
            result.raw_points = raw_points
            result.classified_points = [cp.to_dict() for cp in classified]

            # Phase 3: Generate summary
            result.summary = self._classifier.get_classification_summary(classified)
            if dropped_points:
                result.summary["module_filtered_points"] = dropped_points

            # Add lighting-specific summary
            result.summary["lighting_points"] = self._extract_lighting_summary(classified)

            result.status = "complete"
            result.completed_at = datetime.utcnow().isoformat()

            logger.info(
                "CSV discovery %s complete: %d points classified (%d equipment types, %d lighting points)",
                discovery_id,
                len(classified),
                len(result.summary.get("unique_equipment", {})),
                result.summary["lighting_points"]["total"],
            )

        except Exception as e:
            result.status = "error"
            result.error = str(e)
            logger.error("CSV discovery %s failed: %s", discovery_id, e)

        # Cache and persist
        self._discovery_cache[discovery_id] = result
        self._save_discovery_result(result)

        return result

    def _parse_csv_export(self, csv_content: str) -> list[dict[str, Any]]:
        """Parse a Desigo/Niagara BACnet CSV export into point dicts.

        Handles the standard format:
            name,object_type,instance,units,present_value,description,min_value,max_value,writable

        Extracts equipment ID from hierarchical names:
            STC/L1/DALI-01/Lum01_ActivePower → equipment_id = DALI-01

        Returns:
            List of point dicts ready for classification
        """
        points = []
        reader = csv.DictReader(io.StringIO(csv_content))

        for row in reader:
            name = row.get("name", "").strip()
            if not name:
                continue

            # Parse writable field
            writable_raw = row.get("writable", "False").strip()
            writable = writable_raw.lower() in ("true", "1", "yes")

            # Parse numeric fields safely
            present_value = row.get("present_value", "")
            try:
                present_value = float(present_value) if present_value else None
            except (ValueError, TypeError):
                present_value = present_value if present_value else None

            instance = 0
            with contextlib.suppress(ValueError, TypeError):
                instance = int(row.get("instance", 0))

            # Extract equipment ID from hierarchical name
            # STC/L1/DALI-01/Lum01_ActivePower → equipment_id = DALI-01
            equipment_id, _point_suffix = self._parse_hierarchical_name(name)

            point = {
                "name": name,
                "description": row.get("description", "").strip(),
                "object_type": row.get("object_type", "").strip(),
                "instance": instance,
                "units": row.get("units", "").strip(),
                "present_value": present_value,
                "writable": writable,
            }

            # Pass extracted equipment ID as metadata for classifier
            if equipment_id:
                point["_equipment_id"] = equipment_id

            points.append(point)

        return points

    @staticmethod
    def _parse_hierarchical_name(name: str) -> tuple:
        """Parse a hierarchical BACnet point name.

        Handles Desigo naming convention:
            STC/{LEVEL}/{EQUIP-ID}/{PointName}
            e.g. STC/L1/DALI-01/Lum01_ActivePower

        Also handles flat names:
            DALI-01_Lum01_ActivePower

        Returns:
            Tuple of (equipment_id, point_suffix)
            e.g. ("DALI-01", "Lum01_ActivePower")
        """
        # Hierarchical path: split on /
        parts = name.split("/")
        if len(parts) >= 3:
            # Last part is the point name, second-to-last is equipment ID
            # STC/L1/DALI-01/Lum01_ActivePower → equip=DALI-01, point=Lum01_ActivePower
            return parts[-2], parts[-1]

        # Flat name: extract equipment ID prefix
        # DALI-01_Lum01_ActivePower → equip=DALI-01, rest=Lum01_ActivePower
        match = re.match(r"^([A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*)_(.+)$", name)
        if match:
            return match.group(1), match.group(2)

        return "", name

    @staticmethod
    def _extract_lighting_summary(classified: list) -> dict[str, Any]:
        """Extract lighting-specific statistics from classified points.

        Returns:
            Dict with lighting point counts by category
        """
        lighting_types = {
            "dali_controller",
            "dali",
            "luminaire",
            "lum",
            "light_sensor",
            "emergency_luminaire",
        }
        lighting_categories = {
            "brightness",
            "lux",
            "color_temperature",
            "lamp_status",
            "scene",
            "lighting_power",
            "lighting_energy",
            "driver_temperature",
            "lamp_hours",
            "light_output",
            "emergency_battery",
            "emergency_test",
            "charge_status",
        }

        by_equipment = {}
        by_category = {}
        total = 0

        for cp in classified:
            eq_type = cp.equipment_type if hasattr(cp, "equipment_type") else cp.get("equipment_type", "")
            cat = cp.point_category if hasattr(cp, "point_category") else cp.get("point_category", "")

            is_lighting = eq_type in lighting_types or cat in lighting_categories
            if is_lighting:
                total += 1
                by_equipment[eq_type] = by_equipment.get(eq_type, 0) + 1
                by_category[cat] = by_category.get(cat, 0) + 1

        return {
            "total": total,
            "by_equipment_type": by_equipment,
            "by_category": by_category,
        }

    def _load_tags_via_classifier(self) -> None:
        """Ensure the classifier's tags are loaded."""
        self._classifier._load_tags()

    async def _discover_points(
        self,
        device_ip: str,
        site_id: str,
        device_bacnet_id: int | None = None,
        adapter_type: str | None = None,
        bms_vendor: str | None = None,
    ) -> list[dict[str, Any]]:
        """Discover points using adapter routing with JSON fallback.

        Args:
            device_ip: Device IP address
            site_id: SENTINEL site ID for fallback lookup
            device_bacnet_id: BACnet device ID (if provided, tries BACnet first)
            adapter_type: Explicit adapter selection ('bacnet', ...)
            bms_vendor: Optional vendor/source alias resolved by the adapter registry

        Returns:
            List of point dicts with name, description, object_type, etc.
        """
        selected_adapter = resolve_bms_adapter_type(
            adapter_type=adapter_type,
            bms_vendor=bms_vendor,
            device_ip=device_ip,
        )

        should_try_selected_adapter = adapter_type is not None or bms_vendor is not None or device_bacnet_id is not None

        # Tier 1: Try the selected adapter first when it was explicitly
        # requested or when sufficient live connection context is present.
        if should_try_selected_adapter:
            adapter_points = await self._load_adapter_points(
                adapter_type=selected_adapter,
                site_id=site_id,
                device_ip=device_ip,
                device_bacnet_id=device_bacnet_id,
                bms_vendor=bms_vendor,
            )
            if adapter_points:
                logger.info(
                    "Loaded %d points through %s adapter for site %s",
                    len(adapter_points),
                    selected_adapter,
                    site_id,
                )
                return adapter_points

        # Tier 2: Fall back to static JSON files
        json_points = self._load_seed_points(site_id)
        if json_points:
            logger.info(
                "Loaded %d points from JSON fallback for site %s",
                len(json_points),
                site_id,
            )
            return json_points

        raise BACnetException(f"No points found for {device_ip} (site {site_id}): adapter and fallback exhausted")

    async def _load_adapter_points(
        self,
        adapter_type: str,
        site_id: str,
        device_ip: str,
        device_bacnet_id: int | None = None,
        bms_vendor: str | None = None,
    ) -> list[dict[str, Any]]:
        """Load points through the canonical SIMBIOT adapter boundary."""
        adapter = create_bms_adapter(
            adapter_type=adapter_type,
            bms_vendor=bms_vendor,
            device_ip=device_ip,
        )
        config = BmsConnectionConfig(
            site_id=site_id,
            source_type=adapter_type,
            host=device_ip,
            metadata={
                "bms_vendor": bms_vendor,
                "commissioning": True,
            },
        )

        try:
            status = await adapter.connect(config)
            if not status.connected:
                logger.warning("Adapter %s did not connect for site %s: %s", adapter_type, site_id, status.message)
                return []

            devices = await adapter.discover_devices()
            target_devices = self._select_target_devices(
                adapter_type=adapter_type,
                devices=devices,
                device_ip=device_ip,
                device_bacnet_id=device_bacnet_id,
            )
            if not target_devices:
                logger.info("No %s adapter devices selected for site %s", adapter_type, site_id)
                return []

            points: list[dict[str, Any]] = []
            instance_counter = 2000
            for device in target_devices:
                device_points = await adapter.discover_points(device.device_id)
                reading_map = {}
                if device_points:
                    readings = await adapter.read_points(device.device_id, [point.point_id for point in device_points])
                    reading_map = {reading.point_id: reading for reading in readings}
                for point in device_points:
                    reading = reading_map.get(point.point_id)
                    if reading is None:
                        reading = await self._safe_adapter_read(adapter, device.device_id, point.point_id)
                    points.append(self._format_adapter_point(adapter_type, device, point, reading, instance_counter))
                    instance_counter += 1
            return points
        except Exception as e:
            logger.warning("Failed to load %s adapter points for %s: %s", adapter_type, site_id, e)
            return []
        finally:
            with contextlib.suppress(Exception):
                await adapter.disconnect()

    async def _discover_from_bacnet(
        self,
        client: NiagaraBACnetClient,
        device_id: int,
    ) -> list[dict[str, Any]]:
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
        detailed_points: list[dict[str, Any]] = []

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
                    with contextlib.suppress(Exception):
                        units = await client.read_point(
                            device_id,
                            point.object_type,
                            point.instance,
                            property_name="units",
                        )

                    value = None
                    with contextlib.suppress(Exception):
                        value = await client.read_point(
                            device_id,
                            point.object_type,
                            point.instance,
                            property_name="presentValue",
                        )

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

    def _load_seed_points(self, site_id: str | None = None) -> list[dict[str, Any]]:
        """Load points from static JSON equipment files (Tier 3 fallback).

        Args:
            site_id: Site ID to load equipment files from (e.g., 'site-002').
                     If None, falls back to haystack_tags.json seed points.

        Returns:
            List of point dicts with name, description, object_type, etc.
        """
        # If site_id is provided, load from that building's equipment files
        if site_id:
            equipment_dir = DATA_DIR.parent / "sites" / site_id / "equipment"

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

    def _load_points_from_equipment_dir(self, equipment_dir: Path, site_id: str) -> list[dict[str, Any]]:
        """Extract seed points from a building's equipment files.

        Args:
            equipment_dir: Path to equipment directory
            site_id: ID of the site for logging

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

    def _load_from_haystack_tags(self) -> list[dict[str, Any]]:
        """Load seed points from haystack_tags.json (legacy fallback)."""
        try:
            tags_path = DATA_DIR / "haystack_tags.json"
            with open(tags_path) as f:
                data = json.load(f)
            seed_points = data.get("seed_points", data.get("demo_points", []))
            logger.info("Loaded %d seed points from haystack_tags.json", len(seed_points))
            return seed_points
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error("Failed to load seed points from haystack_tags.json: %s", e)
            return []

    def _select_target_devices(
        self,
        adapter_type: str,
        devices: list[BmsDeviceDescriptor],
        device_ip: str,
        device_bacnet_id: int | None,
    ) -> list[BmsDeviceDescriptor]:
        """Select the device set to discover for an adapter invocation."""
        if device_bacnet_id is not None:
            matching = [device for device in devices if device.device_id == str(device_bacnet_id)]
            if matching:
                return matching
            return [
                BmsDeviceDescriptor(
                    device_id=str(device_bacnet_id),
                    display_name=f"BACnet Device {device_bacnet_id}",
                    protocol=adapter_type,
                    address=device_ip,
                )
            ]

        if device_ip:
            matching = [device for device in devices if self._device_matches_host(device, device_ip)]
            if matching:
                return matching

        if len(devices) == 1:
            return devices

        return []

    def _device_matches_host(self, device: BmsDeviceDescriptor, host: str) -> bool:
        address = (device.address or "").lower()
        normalized_host = host.lower()
        return address.startswith(normalized_host) or normalized_host in address

    async def _safe_adapter_read(self, adapter, device_id: str, point_id: str) -> BmsPointValue | None:
        try:
            return await adapter.read_point(device_id, point_id)
        except Exception:
            return None

    def _format_adapter_point(
        self,
        adapter_type: str,
        device: BmsDeviceDescriptor,
        point: BmsPointDescriptor,
        reading: BmsPointValue | None,
        instance_counter: int,
    ) -> dict[str, Any]:
        point_name = point.point_name or point.point_id
        description = (
            point.metadata.get("description") or f"{device.display_name} - {point_name.replace('_', ' ').title()}"
        )
        object_type = point.metadata.get("object_type") or _infer_object_type(point_name)
        instance = point.metadata.get("instance", instance_counter)
        value = reading.value if reading else None
        unit = point.unit or (reading.unit if reading else None) or ""
        name = point_name

        return {
            "name": name,
            "description": description,
            "object_type": object_type,
            "instance": instance,
            "units": unit,
            "present_value": value,
            "writable": point.writable,
            "_equipment_id": device.device_id,
            "_equipment_type": device.metadata.get("equipment_type", "unknown"),
            "_point_type": _infer_point_type(point_name),
        }

    def _classify_discovered_points(self, points: list[dict[str, Any]]) -> list[ClassifiedPoint]:
        """Classify all discovered points using the point classifier."""
        return self._classifier.classify_points(points)

    def _apply_module_policy(
        self,
        site_id: str,
        raw_points: list[dict[str, Any]],
        classified_points: list[ClassifiedPoint],
    ) -> tuple[list[dict[str, Any]], list[ClassifiedPoint], int]:
        """Filter discovered points against the site's explicit module policy."""
        filtered_classified, dropped_points = filter_classified_points_for_site(site_id, classified_points)
        if not dropped_points:
            return raw_points, filtered_classified, 0

        allowed_keys = {(point.original_name, point.instance) for point in filtered_classified}
        filtered_raw = [
            point for point in raw_points if (str(point.get("name", "")), int(point.get("instance", 0))) in allowed_keys
        ]
        return filtered_raw, filtered_classified, dropped_points

    def get_discovery_result(self, discovery_id: str) -> DiscoveryResult | None:
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

    def list_discoveries(self) -> list[dict[str, Any]]:
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

    def _load_discovery_result(self, discovery_id: str) -> DiscoveryResult | None:
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

_discovery_service: PointDiscoveryService | None = None


def get_point_discovery_service() -> PointDiscoveryService:
    """Get or create the singleton PointDiscoveryService instance."""
    global _discovery_service
    if _discovery_service is None:
        _discovery_service = PointDiscoveryService()
    return _discovery_service

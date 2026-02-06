"""Device API endpoints.

Provides REST API for device discovery, monitoring, and control.
Integrates with the device abstraction layer for protocol-agnostic
device management.
"""

import json
import logging
import re
from pathlib import Path
from typing import List, Optional, Union

from fastapi import APIRouter, HTTPException, Query, Body, Request
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.services.device_abstraction import device_manager

limiter = Limiter(key_func=get_remote_address)

logger = logging.getLogger(__name__)
router = APIRouter()

# ---- Pydantic validation models for device control (Phase 58-04 M-1) ----

# Whitelist of allowed control actions
_ALLOWED_ACTIONS = {
    "set_temperature", "set_brightness", "set_mode", "set_speed",
    "set_setpoint", "set_schedule", "set_value",
    "start", "stop", "enable", "disable", "reset",
    "override", "release_override",
}


class DeviceControlRequest(BaseModel):
    """Validated request body for device control commands.

    Enforces action whitelist, numeric bounds, and string length limits
    to prevent injection and out-of-range values before they reach the
    safety engine.
    """
    point: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Point name to control",
    )
    value: Union[float, int, bool, str] = Field(
        ...,
        description="Value to write",
    )
    priority: int = Field(
        default=8,
        ge=1,
        le=16,
        description="Write priority (1-16, default: 8)",
    )

    @field_validator("point")
    @classmethod
    def validate_point_name(cls, v: str) -> str:
        """Reject point names with shell/SQL metacharacters."""
        if not re.match(r"^[a-zA-Z0-9_\-./]+$", v):
            raise ValueError(
                "Point name may only contain alphanumerics, underscores, hyphens, dots, and slashes"
            )
        return v

    @field_validator("value")
    @classmethod
    def validate_value(cls, v: Union[float, int, bool, str]) -> Union[float, int, bool, str]:
        """Enforce sensible bounds on numeric values and string length."""
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            if v < -1000 or v > 10000:
                raise ValueError("Numeric value must be between -1000 and 10000")
            return v
        if isinstance(v, str):
            if len(v) > 200:
                raise ValueError("String value must be 200 characters or fewer")
            # Reject shell metacharacters in string values
            if re.search(r'[;&|`$(){}[\]<>!#]', v):
                raise ValueError("Value contains disallowed characters")
            return v
        return v


# Data directory for mock devices
DATA_DIR = Path(__file__).parent.parent / "data"
BUILDINGS_DIR = DATA_DIR / "buildings"


async def load_mock_devices() -> List[dict]:
    """Load mock devices from JSON file."""
    filepath = DATA_DIR / "mock_devices.json"
    if filepath.exists():
        with open(filepath) as f:
            return json.load(f)
    return []


async def load_controllable_equipment_from_buildings() -> List[dict]:
    """Load controllable equipment from building directories.

    Scans all building equipment directories and returns equipment
    that has at least one writable point (controllable).
    """
    controllable_devices = []

    # Get active buildings from registry
    registry_path = BUILDINGS_DIR / "_registry.json"
    if not registry_path.exists():
        logger.warning("Building registry not found")
        return []

    with open(registry_path) as f:
        registry = json.load(f)

    active_buildings = registry.get("active_buildings", [])

    for building_id in active_buildings:
        equipment_dir = BUILDINGS_DIR / building_id / "equipment"
        if not equipment_dir.exists():
            continue

        for eq_file in equipment_dir.glob("*.json"):
            try:
                with open(eq_file) as f:
                    eq_data = json.load(f)

                # Check if equipment has any writable points
                points = eq_data.get("points", {})
                has_writable = any(
                    p.get("writable", False) for p in points.values()
                )

                if not has_writable:
                    continue

                # Transform equipment format to device format
                device_data = _transform_equipment_to_device(eq_data)
                if device_data:
                    controllable_devices.append(device_data)

            except Exception as e:
                logger.warning(f"Failed to load equipment {eq_file}: {e}")

    logger.info(f"Loaded {len(controllable_devices)} controllable devices from building directories")
    return controllable_devices


def _transform_equipment_to_device(eq_data: dict) -> Optional[dict]:
    """Transform equipment JSON format to device manager format."""
    try:
        device_id = eq_data.get("id")
        if not device_id:
            return None

        # Transform points to device format
        transformed_points = {}
        for point_name, point_data in eq_data.get("points", {}).items():
            transformed_points[point_name] = {
                "name": point_name,
                "point_type": _map_point_type(point_data.get("object_type", "analogValue")),
                "description": point_data.get("description", f"{point_name} point"),
                "unit": point_data.get("unit", ""),
                "default_value": point_data.get("default_value"),
                "writable": point_data.get("writable", False),
                "min_value": point_data.get("min_value"),
                "max_value": point_data.get("max_value"),
            }

        # Build device data structure
        device_data = {
            "id": device_id,
            "name": eq_data.get("name", device_id),
            "device_type": eq_data.get("device_type", "hvac"),
            "protocol": eq_data.get("protocol", "bacnet"),
            "site_id": eq_data.get("site_id"),
            "points": transformed_points,
            "metadata": {
                **eq_data.get("metadata", {}),
                "equipment_type": eq_data.get("equipment_type"),
                "source": "building_equipment",
            }
        }

        # Add hvac_type if applicable
        eq_type = eq_data.get("equipment_type", "").lower()
        if eq_type in ["ahu", "chiller", "cooling_tower", "boiler", "fcu", "vav", "pump"]:
            device_data["hvac_type"] = eq_type

        return device_data

    except Exception as e:
        logger.warning(f"Failed to transform equipment: {e}")
        return None


def _map_point_type(bacnet_type: str) -> str:
    """Map BACnet object type to device point type."""
    type_map = {
        "analogValue": "analog_value",
        "analogInput": "analog_input",
        "analogOutput": "analog_output",
        "binaryValue": "binary_value",
        "binaryInput": "binary_input",
        "binaryOutput": "binary_output",
        "multistateValue": "multistate_value",
        "multistateInput": "multistate_input",
        "multistateOutput": "multistate_output",
    }
    return type_map.get(bacnet_type, "analog_value")


async def startup_event():
    """Initialize device manager on startup.

    Called from main.py startup event.
    Loads mock devices + controllable equipment from building directories.
    """
    try:
        print("[DEVICES] Starting device manager initialization...")

        # Load mock devices for demo
        devices_data = await load_mock_devices()
        mock_count = len(devices_data)
        print(f"[DEVICES] Loaded {mock_count} mock devices")

        # Load controllable equipment from building directories
        building_devices = await load_controllable_equipment_from_buildings()
        print(f"[DEVICES] Loaded {len(building_devices)} controllable building equipment")

        # Get existing device IDs to avoid duplicates
        existing_ids = {d["id"] for d in devices_data}

        # Add building devices that don't already exist in mock_devices
        added_count = 0
        for device in building_devices:
            if device["id"] not in existing_ids:
                devices_data.append(device)
                existing_ids.add(device["id"])
                added_count += 1

        print(f"[DEVICES] Added {added_count} building devices (after dedup)")

        await device_manager.initialize(devices_data)
        print(f"[DEVICES] Device manager initialized with {len(devices_data)} total devices")
        logger.info(
            f"Device manager initialized with {mock_count} mock devices + "
            f"{added_count} building equipment = {len(devices_data)} total"
        )
    except Exception as e:
        print(f"[DEVICES] ERROR: Failed to initialize device manager: {e}")
        logger.error(f"Failed to initialize device manager: {e}")
        import traceback
        traceback.print_exc()
        # Initialize empty manager if loading fails
        await device_manager.initialize([])


@router.on_event("shutdown")
async def shutdown_event():
    """Shutdown device manager on shutdown."""
    try:
        await device_manager.shutdown()
        logger.info("Device manager shutdown complete")
    except Exception as e:
        logger.error(f"Error shutting down device manager: {e}")


@router.get("/devices", response_model=List[dict])
async def get_devices(
    site_id: Optional[str] = Query(None, description="Filter by site ID"),
    device_type: Optional[str] = Query(None, description="Filter by device type"),
    protocol: Optional[str] = Query(None, description="Filter by protocol")
) -> List[dict]:
    """Get all devices with optional filtering."""
    try:
        devices = await device_manager.list_devices()

        # Apply filters
        if site_id:
            devices = [d for d in devices if d.site_id == site_id]
        if device_type:
            devices = [d for d in devices if d.device_type.value == device_type]
        if protocol:
            devices = [d for d in devices if d.protocol.value == protocol]

        # Convert to dictionaries for response
        return [device.to_dict() for device in devices]
    except Exception as e:
        logger.error(f"Error getting devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _enrich_device_with_current_values(device_id: str, device_dict: dict) -> dict:
    """Add current point values from adapter state to device dict."""
    try:
        adapter = await device_manager.get_adapter(device_id)
        if adapter and hasattr(adapter, 'get_state'):
            state = adapter.get_state()
            for point_name, point_data in device_dict.get("points", {}).items():
                if point_name in state:
                    point_data["current_value"] = state[point_name]
    except Exception as e:
        logger.warning(f"Could not enrich device {device_id} with current values: {e}")
    return device_dict


@router.get("/devices/{device_id}", response_model=dict)
async def get_device(device_id: str) -> dict:
    """Get a specific device by ID."""
    try:
        device = await device_manager.get_device(device_id)
        if not device:
            raise HTTPException(status_code=404, detail=f"Device {device_id} not found")

        device_dict = device.to_dict()
        # Add current point values from adapter state
        device_dict = await _enrich_device_with_current_values(device_id, device_dict)
        return device_dict
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting device {device_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/devices/{device_id}/points", response_model=dict)
async def get_device_points(device_id: str) -> dict:
    """Get all points for a device."""
    try:
        device = await device_manager.get_device(device_id)
        if not device:
            raise HTTPException(status_code=404, detail=f"Device {device_id} not found")

        adapter = await device_manager.get_adapter(device_id)
        if not adapter:
            raise HTTPException(status_code=503, detail=f"Device {device_id} not connected")

        points = await adapter.get_points()
        return {
            "device_id": device_id,
            "device_name": device.name,
            "points": {name: point.__dict__ for name, point in points.items()}
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting points for device {device_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/devices/{device_id}/points/{point_name}", response_model=dict)
async def read_device_point(
    device_id: str,
    point_name: str
) -> dict:
    """Read a value from a device point."""
    try:
        device_value = await device_manager.read_device_value(device_id, point_name)
        return {
            "device_id": device_id,
            "point_name": point_name,
            "value": device_value.value,
            "unit": device_value.unit,
            "timestamp": device_value.timestamp,
            "quality": device_value.quality
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Error reading point {point_name} from device {device_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/devices/{device_id}/control", response_model=dict)
@limiter.limit("10/minute")
async def control_device(
    request: Request,
    device_id: str,
    body: DeviceControlRequest = Body(...),
) -> dict:
    """Write a value to a device point (control command).

    Request body is validated via DeviceControlRequest (Phase 58-04 M-1):
    - point: alphanumeric + _ - . / only, max 100 chars
    - value: numeric -1000..10000, bool, or string max 200 chars
    - priority: 1-16 (default 8)
    """
    try:
        # Extract user from headers (demo: hardcoded, production: from auth)
        user = request.headers.get("X-User-Id", "system")

        success = await device_manager.write_device_value(
            device_id, body.point, body.value, body.priority, user
        )

        if success:
            return {
                "success": True,
                "message": f"Successfully wrote {body.value} to {body.point} on device {device_id}",
                "device_id": device_id,
                "point": body.point,
                "value": body.value,
                "priority": body.priority,
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to write value to {body.point} on device {device_id}",
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error controlling device {device_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/devices/{device_id}/status", response_model=dict)
async def get_device_status(device_id: str) -> dict:
    """Get device operational status."""
    try:
        device = await device_manager.get_device(device_id)
        if not device:
            raise HTTPException(status_code=404, detail=f"Device {device_id} not found")

        status = await device_manager.get_device_status(device_id)
        return {
            "device_id": device_id,
            "device_name": device.name,
            "status": status.value,
            "last_seen": device.last_seen,
            "protocol": device.protocol.value
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting status for device {device_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/devices/{device_id}/safety-status", response_model=dict)
async def get_device_safety_status(device_id: str) -> dict:
    """Get device safety status."""
    try:
        device = await device_manager.get_device(device_id)
        if not device:
            raise HTTPException(status_code=404, detail=f"Device {device_id} not found")

        safety_status = await device_manager.get_device_safety_status(device_id)
        return safety_status
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting safety status for device {device_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/devices/{device_id}/scan", response_model=dict)
async def scan_device_points(device_id: str) -> dict:
    """Scan device for available points."""
    try:
        device = await device_manager.get_device(device_id)
        if not device:
            raise HTTPException(status_code=404, detail=f"Device {device_id} not found")

        points = await device_manager.scan_device_points(device_id)
        return {
            "device_id": device_id,
            "device_name": device.name,
            "points_found": len(points),
            "points": {name: point.__dict__ for name, point in points.items()}
        }
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Error scanning device {device_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/devices/{device_id}/connect", response_model=dict)
async def connect_device(device_id: str) -> dict:
    """Connect to a device."""
    try:
        device = await device_manager.get_device(device_id)
        if not device:
            raise HTTPException(status_code=404, detail=f"Device {device_id} not found")

        success = await device_manager.connect_device(device_id)
        return {
            "success": success,
            "device_id": device_id,
            "device_name": device.name,
            "message": f"Device {'connected' if success else 'failed to connect'}"
        }
    except Exception as e:
        logger.error(f"Error connecting to device {device_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/devices/{device_id}/disconnect", response_model=dict)
async def disconnect_device(device_id: str) -> dict:
    """Disconnect from a device."""
    try:
        device = await device_manager.get_device(device_id)
        if not device:
            raise HTTPException(status_code=404, detail=f"Device {device_id} not found")

        await device_manager.disconnect_device(device_id)
        return {
            "success": True,
            "device_id": device_id,
            "device_name": device.name,
            "message": "Device disconnected"
        }
    except Exception as e:
        logger.error(f"Error disconnecting from device {device_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sites/{site_id}/devices", response_model=List[dict])
async def get_site_devices(site_id: str) -> List[dict]:
    """Get all devices at a specific site."""
    try:
        devices = await device_manager.list_devices_by_site(site_id)
        return [device.to_dict() for device in devices]
    except Exception as e:
        logger.error(f"Error getting devices for site {site_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
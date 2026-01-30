"""Device API endpoints.

Provides REST API for device discovery, monitoring, and control.
Integrates with the device abstraction layer for protocol-agnostic
device management.
"""

import json
import logging
from pathlib import Path
from typing import List, Optional, Any, Union

from fastapi import APIRouter, HTTPException, Query, Body, Request

from app.models.device import Device, DeviceValue
from app.services.device_abstraction import device_manager

logger = logging.getLogger(__name__)
router = APIRouter()

# Data directory for mock devices
DATA_DIR = Path(__file__).parent.parent / "data"


async def load_mock_devices() -> List[dict]:
    """Load mock devices from JSON file."""
    filepath = DATA_DIR / "mock_devices.json"
    if filepath.exists():
        with open(filepath) as f:
            return json.load(f)
    return []


@router.on_event("startup")
async def startup_event():
    """Initialize device manager on startup."""
    try:
        # Load mock devices for demo
        devices_data = await load_mock_devices()
        await device_manager.initialize(devices_data)
        logger.info(f"Device manager initialized with {len(devices_data)} mock devices")
    except Exception as e:
        logger.error(f"Failed to initialize device manager: {e}")
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
async def control_device(
    request: Request,
    device_id: str,
    point: str = Body(..., embed=True, description="Point name to control"),
    value: Union[float, int, bool, str] = Body(..., embed=True, description="Value to write"),
    priority: int = Body(8, embed=True, description="Write priority (1-16, default: 8)")
) -> dict:
    """Write a value to a device point (control command)."""
    try:
        # Validate priority range
        if priority < 1 or priority > 16:
            raise HTTPException(status_code=400, detail="Priority must be between 1 and 16")

        # Extract user from headers (demo: hardcoded, production: from auth)
        user = request.headers.get("X-User-Id", "system")

        success = await device_manager.write_device_value(device_id, point, value, priority, user)

        if success:
            return {
                "success": True,
                "message": f"Successfully wrote {value} to {point} on device {device_id}",
                "device_id": device_id,
                "point": point,
                "value": value,
                "priority": priority
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to write {value} to {point} on device {device_id}"
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
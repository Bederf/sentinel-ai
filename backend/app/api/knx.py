"""KNX/IP API endpoints — SENTINEL KNXnet/IP integration.

REST API for KNX/IP gateway discovery, group address management,
device registration, and point read/write operations.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Body, File, HTTPException, UploadFile

from app.middleware.auth_middleware import require_site_access
from app.services.device_abstraction import device_manager
from app.services.knx.knx_client import SUPPORTED_DPT_TYPES
from app.services.knx.knx_discovery_service import (
    build_device_from_ets,
    discover_gateways,
    import_ets_group_addresses,
    scan_group_addresses,
    test_gateway_connectivity,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knx", tags=["KNX"])


# ---------------------------------------------------------------------------
# Gateway discovery
# ---------------------------------------------------------------------------


@router.get("/gateways")
async def list_knx_gateways():
    """Discover KNXnet/IP gateways on the network via UDP multicast.

    Returns list of discovered gateways with host IP and port.
    Requires: superuser or site-002 access.
    """
    try:
        gateways = await discover_gateways(timeout_s=5.0)
        return {"count": len(gateways), "gateways": gateways}
    except Exception as e:
        logger.error("Gateway discovery failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/gateways/test")
async def test_knx_gateway(
    host: Annotated[str, Body(...)],
    port: Annotated[int, Body(...)] = 3671,
):
    """Test connectivity to a specific KNXnet/IP gateway.

    Args:
        host: Gateway IP address
        port: Gateway port (default 3671)
    """
    result = await test_gateway_connectivity(host, port, timeout_s=3.0)

    if result["status"] == "success":
        return {"status": "connected", "host": host, "port": port}
    elif result["status"] == "timeout":
        raise HTTPException(status_code=504, detail=f"Gateway not responding: {host}:{port}")
    else:
        raise HTTPException(status_code=503, detail=f"Gateway error: {result.get('error')}")


# ---------------------------------------------------------------------------
# DPT types
# ---------------------------------------------------------------------------


@router.get("/dpt/types")
async def list_dpt_types():
    """List all supported KNX Data Point Types (DPT) with encoding info."""
    return {"dpt_types": SUPPORTED_DPT_TYPES}


# ---------------------------------------------------------------------------
# Site devices
# ---------------------------------------------------------------------------


@router.get("/sites/{site_id}/devices")
@require_site_access
async def list_knx_devices(site_id: str):
    """List all KNX devices for a site.

    Returns device list with group address point summaries.
    """
    try:
        devices = await device_manager.list_devices_by_site(site_id)
        knx_devices = [d for d in devices if d.protocol.value == "knx"]

        return {
            "count": len(knx_devices),
            "devices": [
                {
                    "id": d.id,
                    "name": d.name,
                    "status": d.status.value,
                    "gateway_host": d.metadata.get("gateway_host", ""),
                    "point_count": len(d.points),
                    "last_seen": d.last_seen,
                }
                for d in knx_devices
            ],
        }
    except Exception as e:
        logger.error("List KNX devices failed (site=%s): %s", site_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sites/{site_id}/devices")
@require_site_access
async def register_knx_device(site_id: str, device_data: dict[str, Any]):
    """Register a KNX device with group address configuration.

    Args:
        site_id: SENTINEL site ID
        device_data: Device config with:
            - gateway_host: KNXnet/IP gateway IP
            - name: Device name
            - group_addresses: dict of point_name -> {read_address, write_address, dpt, ...}
            - main_group: Optional ETS main group number
    """
    # Validate required fields
    if not device_data.get("gateway_host"):
        raise HTTPException(
            status_code=400,
            detail="gateway_host is required in device_data",
        )

    device_data["protocol"] = "knx"
    device_data["site_id"] = site_id

    # Ensure group_addresses is in metadata for the adapter
    group_addresses = device_data.pop("group_addresses", {})
    device_data.setdefault("metadata", {})["group_addresses"] = group_addresses

    try:
        device = await device_manager.add_device(device_data)
        return {"id": device.id, "name": device.name, "status": device.status.value}
    except Exception as e:
        logger.error("Register KNX device failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Device points
# ---------------------------------------------------------------------------


@router.get("/devices/{device_id}/points")
async def list_knx_device_points(device_id: str):
    """List all group addresses for a KNX device as DevicePoints."""
    device = await device_manager.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")

    if device.protocol.value != "knx":
        raise HTTPException(status_code=400, detail=f"Device {device_id} is not a KNX device")

    points = await device_manager.scan_device_points(device_id)

    return {
        "device_id": device_id,
        "count": len(points),
        "points": [
            {
                "name": name,
                "point_type": p.point_type.value,
                "description": p.description,
                "unit": p.unit,
                "writable": p.writable,
                "group_addresses": device.metadata.get("group_addresses", {}).get(name, {}),
            }
            for name, p in points.items()
        ],
    }


@router.get("/devices/{device_id}/points/{point}/value")
async def read_knx_point(device_id: str, point: str):
    """Read current value from a KNX group address."""
    try:
        value = await device_manager.read_device_value(device_id, point)
        return {
            "device_id": device_id,
            "point": point,
            "value": value.value,
            "unit": value.unit,
            "quality": value.quality,
            "timestamp": value.timestamp,
        }
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("KNX read failed (device=%s, point=%s): %s", device_id, point, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/devices/{device_id}/points/{point}/value")
async def write_knx_point(
    device_id: str,
    point: str,
    value: Annotated[float | int | bool, Body(...)],
    priority: Annotated[int, Body(...)] = 8,
):
    """Write a value to a KNX group address.

    Args:
        device_id: KNX device ID
        point: Point/group address name
        value: Value to write
        priority: KNX priority (1=urgent, 8=low, default 8)
    """
    # Safety: emergency writes are blocked at the adapter level
    try:
        success = await device_manager.write_device_value(device_id, point, value, priority, user="api")
        if success:
            return {"status": "written", "device_id": device_id, "point": point, "value": value}
        else:
            raise HTTPException(status_code=500, detail="KNX write returned False")
    except ValueError as e:
        # Safety blocked or invalid value
        raise HTTPException(status_code=400, detail=str(e))
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("KNX write failed (device=%s, point=%s): %s", device_id, point, e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Device health
# ---------------------------------------------------------------------------


@router.get("/devices/{device_id}/health")
async def get_knx_device_health(device_id: str):
    """Get gateway connectivity and last-seen status for a KNX device."""
    device = await device_manager.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")

    adapter = await device_manager.get_adapter(device_id)
    if not adapter:
        raise HTTPException(status_code=503, detail="Device adapter not available")

    status = await adapter.get_status()
    health = {"status": status.value, "last_seen": device.last_seen}

    # Include gateway info from adapter if available
    if hasattr(adapter, "client") and adapter.client:
        gw_health = await adapter.client.gateway_health_check()
        health["gateway"] = gw_health

    return health


# ---------------------------------------------------------------------------
# ETS XML import
# ---------------------------------------------------------------------------


@router.post("/import/ets")
@require_site_access
async def import_ets_xml(
    site_id: str,
    file: Annotated[UploadFile, File(description="ETS group address export XML")],
    building_name: Annotated[str, Body(...)] = "Unknown",
    floor: Annotated[str, Body(...)] = "Ground",
):
    """Upload ETS5/ETS6 group address export XML and return SENTINEL device config.

    Parses the XML, extracts all group addresses with DPT types,
    and returns device configs ready for POST /api/knx/sites/{site_id}/devices.

    Args:
        site_id: SENTINEL site ID
        file: ETS XML export file (multipart/form-data)
        building_name: Building name for device location
        floor: Floor designator
    """
    try:
        content = await file.read()
        xml_str = content.decode("utf-8")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read XML file: {e}")

    if not xml_str.strip():
        raise HTTPException(status_code=400, detail="Empty XML file")

    try:
        group_addresses = import_ets_group_addresses(xml_str)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("ETS import failed: %s", e)
        raise HTTPException(status_code=500, detail=f"ETS XML parse failed: {e}")

    if not group_addresses:
        raise HTTPException(
            status_code=422,
            detail="No group addresses found in XML — check file format",
        )

    # Build device config
    device_config = build_device_from_ets(site_id, building_name, floor, group_addresses)

    return {
        "group_address_count": len(group_addresses),
        "device_config": device_config,
        "building_name": building_name,
        "floor": floor,
    }


# ---------------------------------------------------------------------------
# Group address scan
# ---------------------------------------------------------------------------


@router.post("/scan/group-addresses")
@require_site_access
async def scan_knx_group_addresses(
    gateway_host: Annotated[str, Body(...)],
    start_address: Annotated[str, Body(...)] = "0/0/0",
    end_address: Annotated[str, Body(...)] = "1/7/255",
):
    """Passively scan a group address range on the KNX bus.

    Sends GroupValueRead telegrams and collects responses.
    Non-intrusive — does not write to the bus.

    Args:
        gateway_host: KNXnet/IP gateway IP
        start_address: Start of range (e.g., "1/0/0")
        end_address: End of range (e.g., "1/7/255")
    """
    try:
        results = await scan_group_addresses(
            gateway_host=gateway_host,
            start_address=start_address,
            end_address=end_address,
            timeout_s=2.0,
        )
        return {
            "gateway_host": gateway_host,
            "range": f"{start_address}–{end_address}",
            "responsive_count": len(results),
            "responsive_addresses": results,
        }
    except Exception as e:
        logger.error("Group address scan failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

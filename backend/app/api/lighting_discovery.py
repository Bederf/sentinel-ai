"""Lighting Discovery API - Endpoints for discovering lighting device information."""

import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.lighting_discovery_service import (
    LightingDiscoveryService,
    SimulatedLightingDiscovery,
)
from app.database.repositories.equipment_metadata_repository import EquipmentMetadataRepository

router = APIRouter()


class DiscoverDeviceRequest(BaseModel):
    """Request to discover a specific lighting device."""

    equipment_code: str = Field(..., description="Equipment code (e.g., S002-DALI-L1-A)")
    gateway_ip: Optional[str] = Field(None, description="DALI gateway IP (uses env default if not provided)")
    gateway_type: str = Field("tridonic", description="Gateway type: tridonic, philips, helvar, generic")
    dali_line: int = Field(1, ge=1, le=4, description="DALI line number (1-4)")
    dali_address: Optional[int] = Field(None, ge=0, le=63, description="DALI short address (0-63)")
    username: Optional[str] = Field(None, description="Gateway auth username")
    password: Optional[str] = Field(None, description="Gateway auth password")


class DiscoverLineRequest(BaseModel):
    """Request to discover all devices on a lighting bus/line."""

    gateway_ip: Optional[str] = Field(None, description="DALI gateway IP")
    gateway_type: str = Field("tridonic", description="Gateway type")
    dali_line: int = Field(1, ge=1, le=4, description="DALI line number")
    username: Optional[str] = None
    password: Optional[str] = None


class SimulatedDiscoveryRequest(BaseModel):
    """Request for simulated discovery (demo mode)."""

    equipment_code: str = Field(..., description="Equipment code to update")
    device_type: str = Field("led_panel", description="Device type: led_panel, led_downlight, emergency")
    dali_address: int = Field(1, ge=0, le=63, description="Simulated DALI address")
    save_to_db: bool = Field(True, description="Save to equipment metadata")


def _get_gateway_ip(provided_ip: Optional[str]) -> str:
    """Get gateway IP from parameter or environment."""
    if provided_ip:
        return provided_ip

    env_ip = os.getenv("DALI_GATEWAY_IP")
    if env_ip:
        return env_ip

    raise HTTPException(status_code=400, detail="No gateway IP provided and DALI_GATEWAY_IP not set in environment")


@router.get("/lighting/gateway/info")
async def get_gateway_info(
    gateway_ip: Optional[str] = Query(None, description="Gateway IP address"),
    gateway_type: str = Query("tridonic", description="Gateway type"),
) -> dict:
    """Get DALI gateway/controller information.

    Queries the gateway for system info including firmware version,
    MAC address, and device counts.

    Args:
        gateway_ip: IP address of DALI gateway
        gateway_type: Type of gateway (tridonic, philips, helvar, generic)

    Returns:
        Gateway information
    """
    try:
        ip = _get_gateway_ip(gateway_ip)
    except HTTPException:
        # Return demo data if no gateway configured
        return {
            "status": "demo_mode",
            "message": "No DALI gateway configured. Showing demo data.",
            "gateway": {
                "ip_address": "192.168.10.50",
                "mac_address": "00:1A:2B:3C:4D:5E",
                "firmware_version": "2.4.1",
                "model": "Scenecom Pro",
                "manufacturer": "Tridonic",
                "dali_lines": 2,
                "total_devices": 48,
                "online": True,
            },
        }

    service = LightingDiscoveryService(
        gateway_ip=ip,
        gateway_type=gateway_type,
        username=os.getenv("DALI_GATEWAY_USERNAME"),
        password=os.getenv("DALI_GATEWAY_PASSWORD"),
    )

    gateway = await service.get_gateway_info()

    if not gateway:
        raise HTTPException(status_code=503, detail="Could not connect to DALI gateway")

    return {"status": "success" if gateway.online else "offline", "gateway": gateway.to_dict()}


@router.post("/lighting/discover/device")
async def discover_device(request: DiscoverDeviceRequest) -> dict:
    """Discover and save DALI device information.

    Queries the DALI gateway for device information and saves
    it to the equipment metadata in the database.

    Args:
        request: Discovery request with equipment code and gateway details

    Returns:
        Discovery result with device info
    """
    try:
        ip = _get_gateway_ip(request.gateway_ip)
    except HTTPException:
        # Fall back to simulated discovery
        return await _simulated_discovery(
            request.equipment_code, "led_panel", request.dali_address or 1, save_to_db=True
        )

    service = LightingDiscoveryService(
        gateway_ip=ip,
        gateway_type=request.gateway_type,
        username=request.username or os.getenv("DALI_GATEWAY_USERNAME"),
        password=request.password or os.getenv("DALI_GATEWAY_PASSWORD"),
    )

    result = await service.discover_and_save(
        equipment_code=request.equipment_code,
        dali_line=request.dali_line,
        dali_address=request.dali_address,
    )

    if result["status"] == "gateway_offline":
        raise HTTPException(status_code=503, detail="DALI gateway is offline")

    if result["status"] == "device_not_found":
        raise HTTPException(
            status_code=404,
            detail=f"No DALI device found at line {request.dali_line}"
            + (f" address {request.dali_address}" if request.dali_address else ""),
        )

    return result


@router.post("/lighting/discover/line")
async def discover_line(request: DiscoverLineRequest) -> dict:
    """Discover all DALI devices on a line.

    Scans the specified DALI line and returns information about
    all devices found.

    Args:
        request: Discovery request with gateway and line details

    Returns:
        List of discovered devices
    """
    try:
        ip = _get_gateway_ip(request.gateway_ip)
    except HTTPException:
        # Return demo data
        return {
            "status": "demo_mode",
            "dali_line": request.dali_line,
            "message": "No DALI gateway configured. Showing demo data.",
            "devices": [
                {
                    "dali_address": i,
                    "device_type": 6,
                    "device_type_name": "LED Module",
                    "manufacturer": "Tridonic",
                    "actual_level": 200,
                    "lamp_failure": False,
                }
                for i in range(1, 9)
            ],
            "count": 8,
        }

    service = LightingDiscoveryService(
        gateway_ip=ip,
        gateway_type=request.gateway_type,
        username=request.username or os.getenv("DALI_GATEWAY_USERNAME"),
        password=request.password or os.getenv("DALI_GATEWAY_PASSWORD"),
    )

    devices = await service.discover_devices(request.dali_line)

    return {
        "status": "success",
        "dali_line": request.dali_line,
        "devices": [d.to_dict() for d in devices],
        "count": len(devices),
    }


@router.post("/lighting/discover/simulated")
async def discover_simulated(request: SimulatedDiscoveryRequest) -> dict:
    """Generate simulated DALI discovery data (for demo/testing).

    Creates realistic device metadata without requiring a physical
    DALI gateway. Useful for demos and development.

    Args:
        request: Simulated discovery parameters

    Returns:
        Generated device info
    """
    return await _simulated_discovery(
        request.equipment_code, request.device_type, request.dali_address, request.save_to_db
    )


async def _simulated_discovery(equipment_code: str, device_type: str, dali_address: int, save_to_db: bool) -> dict:
    """Internal simulated discovery helper."""
    data = SimulatedLightingDiscovery.generate_device_info(
        equipment_code=equipment_code, device_type=device_type, dali_address=dali_address
    )

    result = {
        "status": "simulated",
        "equipment_code": equipment_code,
        "message": "Using simulated data (no gateway connected)",
        "network_info": data["network_info"],
        "device_info": data["device_info"],
        "operating_data": data["operating_data"],
        "saved": False,
    }

    if save_to_db:
        try:
            repo = EquipmentMetadataRepository()
            repo.update_from_discovery(
                equipment_id=equipment_code,
                network_info=data["network_info"],
                device_info=data["device_info"],
                operating_data=data["operating_data"],
            )
            result["saved"] = True
        except Exception as e:
            result["save_error"] = str(e)

    return result


@router.post("/lighting/discover/bulk")
async def discover_bulk(
    equipment_codes: list[str],
    gateway_ip: Optional[str] = Query(None),
    gateway_type: str = Query("tridonic"),
    dali_line: int = Query(1, ge=1, le=4),
    use_simulated: bool = Query(False, description="Use simulated data if gateway unavailable"),
) -> dict:
    """Bulk discover multiple DALI devices.

    Discovers device info for multiple equipment codes and saves
    to database. Useful for commissioning multiple devices.

    Args:
        equipment_codes: List of equipment codes to discover
        gateway_ip: DALI gateway IP
        gateway_type: Gateway type
        dali_line: DALI line number
        use_simulated: Fall back to simulated data if gateway unavailable

    Returns:
        Results for each equipment code
    """
    results = []
    errors = []

    # Check if gateway is available
    gateway_available = False
    try:
        ip = _get_gateway_ip(gateway_ip)
        service = LightingDiscoveryService(gateway_ip=ip, gateway_type=gateway_type)
        gateway = await service.get_gateway_info()
        gateway_available = gateway and gateway.online
    except Exception:
        gateway_available = False

    for i, code in enumerate(equipment_codes):
        try:
            if gateway_available:
                result = await service.discover_and_save(
                    equipment_code=code,
                    dali_line=dali_line,
                    dali_address=i + 1,  # Assign sequential addresses
                )
            elif use_simulated:
                result = await _simulated_discovery(code, "led_panel", i + 1, save_to_db=True)
            else:
                result = {
                    "equipment_code": code,
                    "status": "skipped",
                    "reason": "Gateway unavailable and simulated mode disabled",
                }

            results.append(result)
        except Exception as e:
            errors.append({"equipment_code": code, "error": str(e)})

    return {
        "status": "completed",
        "gateway_available": gateway_available,
        "total": len(equipment_codes),
        "successful": len([r for r in results if r.get("saved") or r.get("status") == "success"]),
        "results": results,
        "errors": errors,
    }

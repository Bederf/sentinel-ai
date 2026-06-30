"""Equipment Discovery API - Unified discovery for all protocol types.

Supports:
- DALI lighting devices (DALI-2 protocol)
- BACnet HVAC equipment (BACnet/IP)
- Modbus electrical equipment (Modbus TCP/RTU)
- Generic network devices (ping/port scan)
"""

import os

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.bacnet_discovery_service import BACnetDiscoveryService
from app.services.lighting_discovery_service import LightingDiscoveryService
from app.services.modbus_discovery_service import ModbusDiscoveryService

router = APIRouter()


class UnifiedDiscoveryRequest(BaseModel):
    """Request to discover any equipment type."""

    equipment_code: str = Field(..., description="Equipment code (e.g., S002-CHILLER-B1-001)")
    protocol: str = Field(..., description="Protocol: dali, bacnet, modbus, or auto")
    equipment_type: str | None = Field(None, description="Equipment type for profile selection")

    # Network info
    ip_address: str | None = Field(None, description="Device/gateway IP address")
    port: int | None = Field(None, description="Port number")

    # DALI specific
    dali_line: int | None = Field(1, ge=1, le=4, description="DALI line number")
    dali_address: int | None = Field(None, ge=0, le=63, description="DALI short address")
    gateway_type: str | None = Field("tridonic", description="DALI gateway type")

    # BACnet specific
    bacnet_device_id: int | None = Field(None, description="BACnet device instance")

    # Modbus specific
    modbus_unit_id: int | None = Field(1, ge=1, le=247, description="Modbus unit/slave ID")

    # Options
    use_simulated: bool = Field(False, description="Deprecated. Simulated discovery is disabled in live mode.")


class BulkDiscoveryRequest(BaseModel):
    """Request for bulk discovery of multiple equipment."""

    equipment_list: list[dict] = Field(..., description="List of equipment with code and protocol info")
    use_simulated: bool = Field(False, description="Deprecated. Simulated discovery is disabled in live mode.")


@router.post("/equipment/discover")
async def discover_equipment(request: UnifiedDiscoveryRequest) -> dict:
    """Discover equipment information using appropriate protocol.

    Automatically selects the right discovery method based on protocol
    and equipment type. Does not fall back to simulated data.

    Args:
        request: Discovery request with equipment and protocol details

    Returns:
        Discovery result with network, device, and operating data
    """
    result = {
        "equipment_code": request.equipment_code,
        "protocol": request.protocol,
        "status": "pending",
        "network_info": None,
        "device_info": None,
        "operating_data": None,
        "saved": False,
    }

    protocol = request.protocol.lower()
    if request.use_simulated:
        raise HTTPException(status_code=400, detail="Simulated discovery is disabled; live site telemetry only.")

    # Auto-detect protocol from equipment code
    if protocol == "auto":
        protocol = _detect_protocol(request.equipment_code, request.equipment_type)
        result["protocol"] = protocol

    try:
        if protocol == "dali":
            data = await _discover_dali(request)
        elif protocol == "bacnet":
            data = await _discover_bacnet(request)
        elif protocol == "modbus":
            data = await _discover_modbus(request)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown protocol: {protocol}")

        if data:
            result.update(data)
            result["status"] = "success" if data.get("saved") else "discovered"
        else:
            result["status"] = "not_found"

    except HTTPException:
        raise
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    return result


@router.post("/equipment/discover/bulk")
async def bulk_discover_equipment(request: BulkDiscoveryRequest) -> dict:
    """Bulk discover multiple equipment items.

    Args:
        request: Bulk discovery request with equipment list

    Returns:
        Results for each equipment item
    """
    results = []
    success_count = 0
    error_count = 0

    for item in request.equipment_list:
        try:
            req = UnifiedDiscoveryRequest(
                equipment_code=item.get("equipment_code", item.get("code")),
                protocol=item.get("protocol", "auto"),
                equipment_type=item.get("equipment_type", item.get("type")),
                ip_address=item.get("ip_address"),
                dali_line=item.get("dali_line", 1),
                dali_address=item.get("dali_address"),
                bacnet_device_id=item.get("bacnet_device_id"),
                modbus_unit_id=item.get("modbus_unit_id", 1),
                use_simulated=request.use_simulated,
            )

            result = await discover_equipment(req)
            results.append(result)

            if result.get("saved"):
                success_count += 1
            elif result.get("status") == "error":
                error_count += 1

        except Exception as e:
            results.append(
                {"equipment_code": item.get("equipment_code", item.get("code")), "status": "error", "error": str(e)}
            )
            error_count += 1

    return {
        "status": "completed",
        "total": len(request.equipment_list),
        "successful": success_count,
        "errors": error_count,
        "results": results,
    }


@router.get("/equipment/{equipment_code}/discover")
async def auto_discover_equipment(
    equipment_code: str,
    use_simulated: bool = Query(False, description="Deprecated. Simulated discovery is disabled in live mode."),
) -> dict:
    """Auto-discover equipment by code.

    Determines the protocol from the equipment code pattern and
    attempts discovery.

    Args:
        equipment_code: Equipment code
        use_simulated: Deprecated. Simulated discovery is disabled.

    Returns:
        Discovery result
    """
    # Detect equipment type from code
    equipment_type = _detect_equipment_type(equipment_code)

    request = UnifiedDiscoveryRequest(
        equipment_code=equipment_code,
        protocol="auto",
        equipment_type=equipment_type,
        use_simulated=use_simulated,
    )

    return await discover_equipment(request)


def _detect_protocol(equipment_code: str, equipment_type: str | None) -> str:
    """Detect protocol from equipment code or type.

    Args:
        equipment_code: Equipment code
        equipment_type: Optional explicit type

    Returns:
        Protocol string: dali, bacnet, or modbus
    """
    code_upper = equipment_code.upper()
    _type_upper = (equipment_type or "").upper()

    # DALI - lighting equipment
    if any(x in code_upper for x in ["DALI", "LUM", "LIGHT"]):
        return "dali"

    # Modbus - electrical equipment
    if any(x in code_upper for x in ["GEN", "UPS", "ATS", "MTR", "METER", "MSB", "DB"]):
        return "modbus"

    # BACnet - HVAC and most other equipment
    if any(x in code_upper for x in ["CHILLER", "AHU", "FCU", "VAV", "CT", "PUMP", "BOILER"]):
        return "bacnet"

    # Default to BACnet
    return "bacnet"


def _detect_equipment_type(equipment_code: str) -> str:
    """Detect equipment type from code.

    Args:
        equipment_code: Equipment code

    Returns:
        Equipment type string
    """
    code_upper = equipment_code.upper()

    type_patterns = {
        "chiller": ["CHILLER", "CH-"],
        "ahu": ["AHU"],
        "fcu": ["FCU"],
        "vav": ["VAV"],
        "generator": ["GEN"],
        "ups": ["UPS"],
        "ats": ["ATS"],
        "meter": ["MTR", "METER"],
        "dali": ["DALI", "LUM"],
        "pump": ["PUMP"],
        "boiler": ["BOILER"],
        "ct": ["CT-", "COOLING"],
    }

    for eq_type, patterns in type_patterns.items():
        if any(p in code_upper for p in patterns):
            return eq_type

    return "unknown"


async def _discover_dali(request: UnifiedDiscoveryRequest) -> dict | None:
    """Attempt DALI discovery."""
    ip = request.ip_address or os.getenv("DALI_GATEWAY_IP")

    if not ip:
        return None

    service = LightingDiscoveryService(
        gateway_ip=ip,
        gateway_type=request.gateway_type or "tridonic",
    )

    result = await service.discover_and_save(
        equipment_code=request.equipment_code,
        dali_line=request.dali_line or 1,
        dali_address=request.dali_address,
    )

    if result.get("status") == "success":
        return {
            "network_info": result.get("gateway_info"),
            "device_info": result.get("device_info"),
            "saved": result.get("saved", False),
        }

    return None


async def _discover_bacnet(request: UnifiedDiscoveryRequest) -> dict | None:
    """Attempt BACnet discovery."""
    niagara_host = os.getenv("NIAGARA_OBIX_HOST")

    if not niagara_host and not request.ip_address:
        return None

    service = BACnetDiscoveryService(
        use_niagara=bool(niagara_host),
        niagara_host=niagara_host,
        niagara_username=os.getenv("NIAGARA_OBIX_USERNAME"),
        niagara_password=os.getenv("NIAGARA_OBIX_PASSWORD"),
    )

    if request.bacnet_device_id:
        result = await service.discover_and_save(
            equipment_code=request.equipment_code,
            device_id=request.bacnet_device_id,
            ip_address=request.ip_address,
        )

        if result.get("status") == "success":
            return {
                "network_info": result.get("device_info", {}).get("network_info"),
                "device_info": result.get("device_info"),
                "saved": result.get("saved", False),
            }

    return None


async def _discover_modbus(request: UnifiedDiscoveryRequest) -> dict | None:
    """Attempt Modbus discovery."""
    if not request.ip_address:
        return None

    service = ModbusDiscoveryService()

    result = await service.discover_and_save(
        equipment_code=request.equipment_code,
        ip_address=request.ip_address,
        unit_id=request.modbus_unit_id or 1,
        port=request.port,
    )

    if result.get("status") == "success":
        return {
            "network_info": result.get("device_info", {}).get("network_info"),
            "device_info": result.get("device_info"),
            "saved": result.get("saved", False),
        }

    return None

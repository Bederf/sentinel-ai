"""Equipment Metadata API - Endpoints for equipment notes and metadata management."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.database.repositories.equipment_metadata_repository import EquipmentMetadataRepository

router = APIRouter()


class NotesUpdateRequest(BaseModel):
    """Request to update equipment notes."""
    notes: str = Field(..., description="New notes content")
    changed_by: str = Field(..., description="User making the change")
    change_reason: Optional[str] = Field(None, description="Reason for change")


class NetworkInfoUpdateRequest(BaseModel):
    """Request to update network info."""
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    gateway_ip: Optional[str] = None
    dali_line: Optional[int] = None
    dali_address: Optional[int] = None
    bacnet_device_id: Optional[int] = None
    bacnet_network: Optional[int] = None
    modbus_address: Optional[int] = None
    merge: bool = Field(True, description="Merge with existing or replace")


class DeviceInfoUpdateRequest(BaseModel):
    """Request to update device info."""
    gtin: Optional[str] = Field(None, description="Global Trade Item Number")
    serial_number: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    firmware_version: Optional[str] = None
    hardware_version: Optional[str] = None
    device_type: Optional[str] = None
    merge: bool = Field(True, description="Merge with existing or replace")


class OperatingDataUpdateRequest(BaseModel):
    """Request to update operating data."""
    lamp_hours: Optional[int] = None
    power_cycles: Optional[int] = None
    total_runtime_hours: Optional[float] = None
    last_fault: Optional[str] = None
    fault_count: Optional[int] = None
    energy_kwh: Optional[float] = None
    merge: bool = Field(True, description="Merge with existing or replace")


class CommissioningInfoRequest(BaseModel):
    """Request to set commissioning info."""
    commissioning_date: Optional[str] = Field(None, description="Date commissioned (YYYY-MM-DD)")
    warranty_expiry: Optional[str] = Field(None, description="Warranty expiry (YYYY-MM-DD)")


@router.get("/equipment/{equipment_id}/metadata")
async def get_equipment_metadata(equipment_id: str) -> dict:
    """Get full metadata for equipment.

    Returns all metadata fields including notes, network info, device info,
    and operating data.

    Args:
        equipment_id: Equipment UUID or code (e.g., S002-DALI-L1-A)

    Returns:
        Equipment record with all metadata fields
    """
    repo = EquipmentMetadataRepository()
    equipment = repo.get_equipment_metadata(equipment_id)

    if not equipment:
        raise HTTPException(status_code=404, detail=f"Equipment {equipment_id} not found")

    return {
        "equipment": equipment,
        "has_notes": bool(equipment.get("notes")),
        "has_network_info": bool(equipment.get("network_info")),
        "has_device_info": bool(equipment.get("device_info")),
        "last_discovery": equipment.get("last_discovery"),
    }


@router.patch("/equipment/{equipment_id}/notes")
async def update_equipment_notes(
    equipment_id: str,
    request: NotesUpdateRequest
) -> dict:
    """Update equipment notes.

    Creates an audit trail entry for the change.

    Args:
        equipment_id: Equipment UUID or code
        request: Notes update with content, user, and optional reason

    Returns:
        Updated equipment record
    """
    repo = EquipmentMetadataRepository()

    try:
        equipment = repo.update_notes(
            equipment_id=equipment_id,
            notes=request.notes,
            changed_by=request.changed_by,
            change_reason=request.change_reason
        )
        return {
            "status": "success",
            "equipment": equipment,
            "message": "Notes updated successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/equipment/{equipment_id}/notes/history")
async def get_notes_history(
    equipment_id: str,
    limit: int = Query(20, ge=1, le=100, description="Max records to return")
) -> dict:
    """Get notes change history for equipment.

    Returns audit trail of all notes changes.

    Args:
        equipment_id: Equipment UUID or code
        limit: Maximum records to return (1-100)

    Returns:
        List of notes history records
    """
    repo = EquipmentMetadataRepository()
    history = repo.get_notes_history(equipment_id, limit=limit)

    return {
        "equipment_id": equipment_id,
        "history": history,
        "count": len(history)
    }


@router.patch("/equipment/{equipment_id}/network-info")
async def update_network_info(
    equipment_id: str,
    request: NetworkInfoUpdateRequest
) -> dict:
    """Update equipment network information.

    Args:
        equipment_id: Equipment UUID or code
        request: Network info fields to update

    Returns:
        Updated equipment record
    """
    repo = EquipmentMetadataRepository()

    # Build network_info dict from non-None fields
    network_info = {}
    for field in ['ip_address', 'mac_address', 'gateway_ip', 'dali_line',
                  'dali_address', 'bacnet_device_id', 'bacnet_network', 'modbus_address']:
        value = getattr(request, field, None)
        if value is not None:
            network_info[field] = value

    if not network_info:
        raise HTTPException(status_code=400, detail="No network info fields provided")

    try:
        equipment = repo.update_network_info(
            equipment_id=equipment_id,
            network_info=network_info,
            merge=request.merge
        )
        return {
            "status": "success",
            "equipment": equipment,
            "message": "Network info updated successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/equipment/{equipment_id}/device-info")
async def update_device_info(
    equipment_id: str,
    request: DeviceInfoUpdateRequest
) -> dict:
    """Update equipment device information.

    Args:
        equipment_id: Equipment UUID or code
        request: Device info fields to update

    Returns:
        Updated equipment record
    """
    repo = EquipmentMetadataRepository()

    # Build device_info dict from non-None fields
    device_info = {}
    for field in ['gtin', 'serial_number', 'manufacturer', 'model',
                  'firmware_version', 'hardware_version', 'device_type']:
        value = getattr(request, field, None)
        if value is not None:
            device_info[field] = value

    if not device_info:
        raise HTTPException(status_code=400, detail="No device info fields provided")

    try:
        equipment = repo.update_device_info(
            equipment_id=equipment_id,
            device_info=device_info,
            merge=request.merge
        )
        return {
            "status": "success",
            "equipment": equipment,
            "message": "Device info updated successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/equipment/{equipment_id}/operating-data")
async def update_operating_data(
    equipment_id: str,
    request: OperatingDataUpdateRequest
) -> dict:
    """Update equipment operating data.

    Args:
        equipment_id: Equipment UUID or code
        request: Operating data fields to update

    Returns:
        Updated equipment record
    """
    repo = EquipmentMetadataRepository()

    # Build operating_data dict from non-None fields
    operating_data = {}
    for field in ['lamp_hours', 'power_cycles', 'total_runtime_hours',
                  'last_fault', 'fault_count', 'energy_kwh']:
        value = getattr(request, field, None)
        if value is not None:
            operating_data[field] = value

    if not operating_data:
        raise HTTPException(status_code=400, detail="No operating data fields provided")

    try:
        equipment = repo.update_operating_data(
            equipment_id=equipment_id,
            operating_data=operating_data,
            merge=request.merge
        )
        return {
            "status": "success",
            "equipment": equipment,
            "message": "Operating data updated successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/equipment/{equipment_id}/commissioning")
async def set_commissioning_info(
    equipment_id: str,
    request: CommissioningInfoRequest
) -> dict:
    """Set equipment commissioning and warranty dates.

    Args:
        equipment_id: Equipment UUID or code
        request: Commissioning and warranty dates

    Returns:
        Updated equipment record
    """
    repo = EquipmentMetadataRepository()

    if not request.commissioning_date and not request.warranty_expiry:
        raise HTTPException(status_code=400, detail="At least one date must be provided")

    try:
        equipment = repo.set_commissioning_info(
            equipment_id=equipment_id,
            commissioning_date=request.commissioning_date,
            warranty_expiry=request.warranty_expiry
        )
        return {
            "status": "success",
            "equipment": equipment,
            "message": "Commissioning info updated successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/equipment/search/network")
async def search_by_network_info(
    key: str = Query(..., description="Network info key (e.g., ip_address, mac_address)"),
    value: str = Query(..., description="Value to search for")
) -> dict:
    """Search equipment by network info field.

    Args:
        key: Field name to search (ip_address, mac_address, dali_address, etc.)
        value: Value to match

    Returns:
        List of matching equipment
    """
    repo = EquipmentMetadataRepository()
    results = repo.search_by_network_info(key, value)

    return {
        "search_key": key,
        "search_value": value,
        "results": results,
        "count": len(results)
    }

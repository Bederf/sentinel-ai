"""Equipment Metadata API - Endpoints for equipment notes and metadata management."""


from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.database.repositories.equipment_metadata_repository import EquipmentMetadataRepository
from app.database.supabase_client import get_supabase_client

router = APIRouter()


class NotesUpdateRequest(BaseModel):
    """Request to update equipment notes."""

    notes: str = Field(..., description="New notes content")
    changed_by: str = Field(..., description="User making the change")
    change_reason: str | None = Field(None, description="Reason for change")


class NetworkInfoUpdateRequest(BaseModel):
    """Request to update network info."""

    ip_address: str | None = None
    mac_address: str | None = None
    gateway_ip: str | None = None
    dali_line: int | None = None
    dali_address: int | None = None
    bacnet_device_id: int | None = None
    bacnet_network: int | None = None
    modbus_address: int | None = None
    merge: bool = Field(True, description="Merge with existing or replace")


class DeviceInfoUpdateRequest(BaseModel):
    """Request to update device info."""

    gtin: str | None = Field(None, description="Global Trade Item Number")
    serial_number: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    firmware_version: str | None = None
    hardware_version: str | None = None
    device_type: str | None = None
    merge: bool = Field(True, description="Merge with existing or replace")


class OperatingDataUpdateRequest(BaseModel):
    """Request to update operating data."""

    lamp_hours: int | None = None
    power_cycles: int | None = None
    total_runtime_hours: float | None = None
    last_fault: str | None = None
    fault_count: int | None = None
    energy_kwh: float | None = None
    merge: bool = Field(True, description="Merge with existing or replace")


class CommissioningInfoRequest(BaseModel):
    """Request to set commissioning info."""

    commissioning_date: str | None = Field(None, description="Date commissioned (YYYY-MM-DD)")
    warranty_expiry: str | None = Field(None, description="Warranty expiry (YYYY-MM-DD)")


@router.get("/equipment/{equipment_id}/metadata")
async def get_equipment_metadata(equipment_id: str) -> dict:
    """Get full metadata for equipment.

    Returns all metadata fields including notes, network info, device info,
    and operating data. Falls back to the latest health snapshot if
    equipment.health_score is stale.

    Args:
        equipment_id: Equipment UUID or code (e.g., S002-DALI-L1-A)

    Returns:
        Equipment record with all metadata fields
    """
    repo = EquipmentMetadataRepository()
    equipment = repo.get_equipment_metadata(equipment_id)

    if not equipment:
        raise HTTPException(status_code=404, detail=f"Equipment {equipment_id} not found")

    # Fall back to latest health snapshot if equipment.health_score is stale
    eq_id = equipment.get("id")
    if eq_id and equipment.get("health_score") is None:
        try:
            supabase = get_supabase_client()
            snap = (
                supabase.table("asset_health_snapshots")
                .select("health_score, health_status")
                .eq("equipment_id", eq_id)
                .order("snapshot_at", desc=True)
                .limit(1)
                .execute()
            )
            if snap.data:
                equipment["health_score"] = snap.data[0]["health_score"]
                equipment["health_status"] = snap.data[0]["health_status"]
        except Exception:
            pass

    return {
        "equipment": equipment,
        "has_notes": bool(equipment.get("notes")),
        "has_network_info": bool(equipment.get("network_info")),
        "has_device_info": bool(equipment.get("device_info")),
        "last_discovery": equipment.get("last_discovery"),
    }


@router.patch("/equipment/{equipment_id}/notes")
async def update_equipment_notes(equipment_id: str, request: NotesUpdateRequest) -> dict:
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
            change_reason=request.change_reason,
        )
        return {"status": "success", "equipment": equipment, "message": "Notes updated successfully"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/equipment/{equipment_id}/notes/history")
async def get_notes_history(
    equipment_id: str, limit: int = Query(20, ge=1, le=100, description="Max records to return")
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

    return {"equipment_id": equipment_id, "history": history, "count": len(history)}


@router.patch("/equipment/{equipment_id}/network-info")
async def update_network_info(equipment_id: str, request: NetworkInfoUpdateRequest) -> dict:
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
    for field in [
        "ip_address",
        "mac_address",
        "gateway_ip",
        "dali_line",
        "dali_address",
        "bacnet_device_id",
        "bacnet_network",
        "modbus_address",
    ]:
        value = getattr(request, field, None)
        if value is not None:
            network_info[field] = value

    if not network_info:
        raise HTTPException(status_code=400, detail="No network info fields provided")

    try:
        equipment = repo.update_network_info(equipment_id=equipment_id, network_info=network_info, merge=request.merge)
        return {"status": "success", "equipment": equipment, "message": "Network info updated successfully"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/equipment/{equipment_id}/device-info")
async def update_device_info(equipment_id: str, request: DeviceInfoUpdateRequest) -> dict:
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
    for field in [
        "gtin",
        "serial_number",
        "manufacturer",
        "model",
        "firmware_version",
        "hardware_version",
        "device_type",
    ]:
        value = getattr(request, field, None)
        if value is not None:
            device_info[field] = value

    if not device_info:
        raise HTTPException(status_code=400, detail="No device info fields provided")

    try:
        equipment = repo.update_device_info(equipment_id=equipment_id, device_info=device_info, merge=request.merge)
        return {"status": "success", "equipment": equipment, "message": "Device info updated successfully"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/equipment/{equipment_id}/operating-data")
async def update_operating_data(equipment_id: str, request: OperatingDataUpdateRequest) -> dict:
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
    for field in ["lamp_hours", "power_cycles", "total_runtime_hours", "last_fault", "fault_count", "energy_kwh"]:
        value = getattr(request, field, None)
        if value is not None:
            operating_data[field] = value

    if not operating_data:
        raise HTTPException(status_code=400, detail="No operating data fields provided")

    try:
        equipment = repo.update_operating_data(
            equipment_id=equipment_id, operating_data=operating_data, merge=request.merge
        )
        return {"status": "success", "equipment": equipment, "message": "Operating data updated successfully"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/equipment/{equipment_id}/commissioning")
async def set_commissioning_info(equipment_id: str, request: CommissioningInfoRequest) -> dict:
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
            warranty_expiry=request.warranty_expiry,
        )
        return {"status": "success", "equipment": equipment, "message": "Commissioning info updated successfully"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/equipment/search/network")
async def search_by_network_info(
    key: str = Query(..., description="Network info key (e.g., ip_address, mac_address)"),
    value: str = Query(..., description="Value to search for"),
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

    return {"search_key": key, "search_value": value, "results": results, "count": len(results)}


class MarkReplacedRequest(BaseModel):
    """Request to mark equipment as replaced."""

    replaced_on: str = Field(..., description="Date equipment was replaced (YYYY-MM-DD)")
    replacement_notes: str | None = Field(None, description="Optional notes about replacement")


@router.patch("/equipment/{equipment_id}/mark-replaced")
async def mark_equipment_replaced(equipment_id: str, request: MarkReplacedRequest) -> dict:
    """Mark equipment as replaced.

    Resets health_score to NULL so the baseline capture task picks it up
    and recalculates from the new commissioning date. The old record stays
    in place with its historical health data for audit.
    """
    from datetime import datetime

    supabase = get_supabase_client()

    eq = supabase.table("equipment").select("id,code").eq("id", equipment_id).limit(1).execute()
    if not eq.data:
        raise HTTPException(status_code=404, detail=f"Equipment {equipment_id} not found")

    supabase.table("equipment").update({
        "replaced_on": request.replaced_on,
        "replacement_notes": request.replacement_notes or "",
        "health_score": None,
        "health_score_confidence": None,
        "baseline_sourced_from": "pending_replacement",
        "last_baseline_update": None,
    }).eq("id", equipment_id).execute()

    return {
        "status": "marked_replaced",
        "equipment_code": eq.data[0]["code"],
        "replaced_on": request.replaced_on,
    }

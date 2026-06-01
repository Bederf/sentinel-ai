"""API endpoints for spare parts catalog and inventory management."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database.repositories.spare_parts_repository import SparePartsRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/parts", tags=["spare-parts"])


class PartCreate(BaseModel):
    equipment_id: str | None = None
    equipment_type: str
    manufacturer: str | None = None
    model: str | None = None
    part_name: str
    part_number: str | None = None
    alternate_part_numbers: list[str] = []
    unit_cost_zar: float | None = None
    typical_replacement_interval_days: int | None = None
    criticality: str = "consumable"
    source: str = "manual"
    initial_stock: int = 0
    min_threshold: int = 2
    max_threshold: int = 10
    location: str | None = None


class PartUpdate(BaseModel):
    part_name: str | None = None
    part_number: str | None = None
    alternate_part_numbers: list[str] | None = None
    unit_cost_zar: float | None = None
    typical_replacement_interval_days: int | None = None
    criticality: str | None = None
    is_active: bool | None = None
    equipment_id: str | None = None


class InventoryUpdate(BaseModel):
    quantity_on_hand: int
    location: str | None = None


@router.get("/equipment/{code}")
async def get_parts_for_equipment(code: str) -> list[dict[str, Any]]:
    """Get spare parts for a specific equipment instance by its code."""
    from app.database.repositories.equipment_repository import EquipmentRepository

    eq = EquipmentRepository().get_by_id(code)
    if not eq:
        raise HTTPException(status_code=404, detail="Equipment not found")

    repo = SparePartsRepository()

    parts = repo.get_parts_for_equipment(eq["id"])
    if parts:
        return parts

    manufacturer = None
    device_info = eq.get("device_info") or {}
    if isinstance(device_info, dict):
        manufacturer = device_info.get("manufacturer")
        model_val = device_info.get("model")

    parts = repo.get_parts_for_type(
        equipment_type=eq.get("type", "").lower(),
        manufacturer=manufacturer,
        model=model_val,
    )
    return parts


@router.get("")
async def search_parts(
    query: str | None = None,
    type: str | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    low_stock: bool = False,
) -> list[dict[str, Any]]:
    """Search spare parts catalog with filters."""
    repo = SparePartsRepository()

    if low_stock:
        return repo.get_low_stock_parts()

    if query:
        return repo.search_parts(query)

    if type:
        return repo.get_parts_for_type(
            equipment_type=type,
            manufacturer=manufacturer,
            model=model,
        )

    return repo.search_parts("")


@router.get("/{part_id}")
async def get_part(part_id: str) -> dict[str, Any]:
    """Get a single spare part by ID with inventory."""
    repo = SparePartsRepository()
    part = repo.get_part_by_id(part_id)
    if not part:
        raise HTTPException(status_code=404, detail="Part not found")
    return part


@router.post("", status_code=201)
async def create_part(data: PartCreate) -> dict[str, Any]:
    """Create a new spare part entry with inventory record."""
    repo = SparePartsRepository()
    part = repo.create_part(data.model_dump())
    if not part:
        raise HTTPException(status_code=500, detail="Failed to create part")
    return part


@router.patch("/{part_id}")
async def update_part(part_id: str, data: PartUpdate) -> dict[str, Any]:
    """Update spare part fields."""
    repo = SparePartsRepository()
    existing = repo.get_part_by_id(part_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Part not found")
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data:
        return existing
    result = repo.update_part(part_id, update_data)
    return result or existing


@router.patch("/{part_id}/inventory")
async def update_inventory(part_id: str, data: InventoryUpdate) -> dict[str, Any]:
    """Update stock quantity for a spare part."""
    repo = SparePartsRepository()
    result = repo.update_inventory(part_id, data.quantity_on_hand, data.location)
    if not result:
        raise HTTPException(status_code=404, detail="Part or inventory not found")
    return result


@router.post("/{part_id}/decrement")
async def decrement_stock(part_id: str, quantity: int = 1) -> dict[str, Any]:
    """Decrement inventory after part used in work order."""
    repo = SparePartsRepository()
    result = repo.decrement_stock(part_id, quantity)
    if not result:
        raise HTTPException(status_code=404, detail="Part not found")
    return result


@router.post("/{part_id}/link/{equipment_code}")
async def link_part_to_equipment(part_id: str, equipment_code: str) -> dict[str, Any]:
    """Link a generic spare part to a specific equipment instance."""
    from app.database.repositories.equipment_repository import EquipmentRepository

    eq = EquipmentRepository().get_by_id(equipment_code)
    if not eq:
        raise HTTPException(status_code=404, detail="Equipment not found")

    repo = SparePartsRepository()
    result = repo.link_to_equipment(part_id, eq["id"])
    if not result:
        raise HTTPException(status_code=404, detail="Part not found")
    return result

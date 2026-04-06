"""
Technician Registry API
========================
CRUD for technicians, site assignments, and specialties.
Used by the Settings UI Technician Registry panel.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.middleware.auth_middleware import require_role
from app.models.auth import AuthContext, SentinelRole
from app.database.repositories.technician_repository import get_technician_repository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/technicians", tags=["technicians"])

# Available specialties — derived from equipment type mapping in technician_repository.py
AVAILABLE_SPECIALTIES = [
    {
        "id": "hvac",
        "label": "HVAC",
        "equipment_types": ["CHILLER", "AHU", "FCU", "VAV", "SPLIT", "CT", "CRAC", "PUMP", "BOILER"],
    },
    {
        "id": "electrical",
        "label": "Electrical",
        "equipment_types": ["GEN", "TX", "UPS", "ATS", "MSB", "MTR", "PFC", "FDR", "MV", "DB"],
    },
    {"id": "dali", "label": "Lighting (DALI)", "equipment_types": ["DALI", "LUM"]},
    {"id": "fire", "label": "Fire", "equipment_types": ["FIRE"]},
    {"id": "security", "label": "Security", "equipment_types": ["ACC", "CCTV"]},
    {"id": "plumbing", "label": "Plumbing", "equipment_types": ["TANK", "BORE"]},
    {"id": "general", "label": "General Maintenance", "equipment_types": []},
]


class TechnicianCreate(BaseModel):
    name: str
    email: str
    phone: str
    specialties: List[str] = ["general"]
    site_id: Optional[str] = None
    telegram_id: Optional[str] = None


class TechnicianUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    active: Optional[bool] = None
    telegram_id: Optional[str] = None
    specialties: Optional[List[str]] = None
    site_id: Optional[str] = None


@router.get("")
async def list_technicians(
    site_id: Optional[str] = None,
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN, SentinelRole.OPERATOR)),
) -> dict:
    """List all technicians with their site assignments and channels."""
    repo = get_technician_repository()
    technicians = await repo.get_technicians_with_assignments(site_id=site_id)
    return {"technicians": technicians, "count": len(technicians)}


@router.get("/specialties")
async def list_specialties() -> dict:
    """List available specialty disciplines with their equipment type mappings."""
    return {"specialties": AVAILABLE_SPECIALTIES}


@router.post("")
async def create_technician(
    body: TechnicianCreate,
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN)),
) -> dict:
    """Register a new technician with site assignment and notification channels."""
    repo = get_technician_repository()

    # Validate specialties
    valid_ids = {s["id"] for s in AVAILABLE_SPECIALTIES}
    for spec in body.specialties:
        if spec not in valid_ids:
            raise HTTPException(status_code=422, detail=f"Invalid specialty: {spec}. Valid: {sorted(valid_ids)}")

    from app.core.site_resolver import get_primary_site_code

    resolved_site_id = body.site_id or get_primary_site_code()
    if not resolved_site_id:
        raise HTTPException(status_code=422, detail="site_id is required when no registered primary site exists")

    tech = await repo.create_technician(
        name=body.name,
        email=body.email,
        phone=body.phone,
        specialties=body.specialties,
        site_id=resolved_site_id,
        telegram_id=body.telegram_id,
    )

    if not tech:
        raise HTTPException(status_code=500, detail="Failed to create technician")

    # Audit event
    try:
        from app.services.audit_service import emit_audit_event

        await emit_audit_event(
            event_type="CONFIG_CHANGE",
            entity_type="technician",
            entity_id=tech.get("id", ""),
            actor=auth.email if auth else "system",
            details={"action": "create", "name": body.name, "specialties": body.specialties},
        )
    except Exception:
        pass

    logger.info(f"Technician created: {body.name} ({body.specialties})")
    return {"status": "created", "technician": tech}


@router.put("/{tech_id}")
async def update_technician(
    tech_id: str,
    body: TechnicianUpdate,
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN)),
) -> dict:
    """Update technician details and/or specialties."""
    repo = get_technician_repository()

    # Update base fields
    updates = {k: v for k, v in body.model_dump().items() if v is not None and k not in {"specialties", "site_id"}}
    if updates:
        result = await repo.update_technician(tech_id, updates)
        if not result:
            raise HTTPException(status_code=404, detail=f"Technician '{tech_id}' not found")

    # Update specialties if provided
    if body.specialties is not None:
        valid_ids = {s["id"] for s in AVAILABLE_SPECIALTIES}
        for spec in body.specialties:
            if spec not in valid_ids:
                raise HTTPException(status_code=422, detail=f"Invalid specialty: {spec}")
        if not body.site_id:
            raise HTTPException(status_code=422, detail="site_id is required when updating specialties")
        await repo.update_specialties(tech_id, body.site_id, body.specialties)

    return {"status": "updated", "tech_id": tech_id}


@router.post("/{tech_id}/deactivate")
async def deactivate_technician(
    tech_id: str,
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN)),
) -> dict:
    """Deactivate a technician (preserves audit trail, removes from routing)."""
    repo = get_technician_repository()
    success = await repo.deactivate_technician(tech_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Technician '{tech_id}' not found")

    logger.info(f"Technician deactivated: {tech_id}")
    return {"status": "deactivated", "tech_id": tech_id}


@router.post("/{tech_id}/reactivate")
async def reactivate_technician(
    tech_id: str,
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN)),
) -> dict:
    """Reactivate a previously deactivated technician."""
    repo = get_technician_repository()
    success = await repo.reactivate_technician(tech_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Technician '{tech_id}' not found")

    logger.info(f"Technician reactivated: {tech_id}")
    return {"status": "reactivated", "tech_id": tech_id}

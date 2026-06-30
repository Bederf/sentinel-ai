"""REST API endpoints for meeting rooms CRUD.

GET    /api/space/rooms          — list all meeting rooms for a site
POST   /api/space/rooms          — create a new room
GET    /api/space/rooms/{id}     — get a single room
PUT    /api/space/rooms/{id}     — update a room
DELETE /api/space/rooms/{id}     — delete a room
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.site_resolver import require_any_site
from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/space/rooms", tags=["space-rooms"])


class CreateRoomRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Room name, e.g. 'Prayer Room'")
    floor: str = Field(default="L0", description="Floor, e.g. L0, L1, L2")
    capacity: int = Field(default=4, ge=1, description="Max occupancy")
    room_type: str | None = Field(default="meeting", description="Room type: meeting, focus, prayer, etc.")
    has_av: bool = Field(default=False, description="Has AV equipment")
    building_code: str | None = Field(default="FA2", description="Building code")
    keywords: list[str] | None = Field(default=None, description="Custom email routing keywords")


class UpdateRoomRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    floor: str | None = None
    capacity: int | None = Field(default=None, ge=1)
    room_type: str | None = None
    has_av: bool | None = None
    building_code: str | None = None
    keywords: list[str] | None = None


def _get_site_id(site_param: str | None, required_site: str) -> str:
    return site_param or required_site


@router.get("")
async def list_rooms(
    site_id: str = Depends(require_any_site),
) -> dict[str, Any]:
    """List all meeting rooms for a site."""
    sb = get_supabase_client()
    if not sb:
        raise HTTPException(status_code=503, detail="Supabase client unavailable")
    try:
        result = sb.table("meeting_rooms").select("*").eq("site_id", site_id).order("floor").order("name").execute()
        return {"rooms": result.data or []}
    except Exception as e:
        logger.error("Failed to list rooms: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list rooms") from e


@router.post("", status_code=201)
async def create_room(
    body: CreateRoomRequest,
    site_id: str = Depends(require_any_site),
) -> dict[str, Any]:
    """Create a new meeting room."""
    sb = get_supabase_client()
    if not sb:
        raise HTTPException(status_code=503, detail="Supabase client unavailable")
    try:
        payload = {
            "site_id": site_id,
            "name": body.name,
            "floor": body.floor,
            "capacity": body.capacity,
            "room_type": body.room_type or "meeting",
            "has_av": body.has_av,
            "building_code": body.building_code or "FA2",
            "keywords": body.keywords or [],
        }
        result = sb.table("meeting_rooms").insert(payload).execute()
        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create room")
        return {"room": result.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create room: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create room") from e


@router.get("/{room_id}")
async def get_room(room_id: str) -> dict[str, Any]:
    """Get a single meeting room by ID."""
    sb = get_supabase_client()
    if not sb:
        raise HTTPException(status_code=503, detail="Supabase client unavailable")
    try:
        result = sb.table("meeting_rooms").select("*").eq("id", room_id).limit(1).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Room not found")
        return {"room": result.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get room: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get room") from e


@router.put("/{room_id}")
async def update_room(room_id: str, body: UpdateRoomRequest) -> dict[str, Any]:
    """Update a meeting room."""
    sb = get_supabase_client()
    if not sb:
        raise HTTPException(status_code=503, detail="Supabase client unavailable")
    try:
        payload: dict[str, Any] = {}
        for field in ("name", "floor", "capacity", "room_type", "has_av", "building_code", "keywords"):
            value = getattr(body, field, None)
            if value is not None:
                payload[field] = value
        if not payload:
            raise HTTPException(status_code=400, detail="No fields to update")
        result = sb.table("meeting_rooms").update(payload).eq("id", room_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Room not found")
        return {"room": result.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update room: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update room") from e


@router.delete("/{room_id}")
async def delete_room(room_id: str) -> dict[str, Any]:
    """Delete a meeting room."""
    sb = get_supabase_client()
    if not sb:
        raise HTTPException(status_code=503, detail="Supabase client unavailable")
    try:
        result = sb.table("meeting_rooms").delete().eq("id", room_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Room not found")
        return {"success": True, "room_id": room_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete room: %s", e)
        raise HTTPException(status_code=500, detail="Failed to delete room") from e

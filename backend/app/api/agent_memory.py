"""Agent Memory API endpoints.

CRUD for persistent agent memory — building quirks, equipment notes,
operator preferences, seasonal patterns, and safety notes.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.database.repositories.agent_memory_repository import (
    get_agent_memory_repository,
    VALID_CONTEXT_TYPES,
    VALID_SOURCES,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent-memory")


# --------------------------------------------------------------------------
# Request / Response models
# --------------------------------------------------------------------------


class AgentMemoryCreate(BaseModel):
    site_id: str
    equipment_code: Optional[str] = None
    context_type: str = Field(
        ..., description="One of: building_quirk, equipment_note, operator_preference, seasonal, safety_note"
    )
    key: str = Field(..., min_length=1, max_length=200)
    value: str = Field(..., min_length=1)
    source: str = Field(default="system", description="One of: claude, sentry, simbiot, operator, system")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    expires_at: Optional[str] = None


class AgentMemoryUpdate(BaseModel):
    value: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    expires_at: Optional[str] = None
    context_type: Optional[str] = None
    source: Optional[str] = None


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------


@router.get("")
async def list_memories(
    site_id: str = Query(..., description="Site ID to fetch memories for"),
    context_type: Optional[str] = Query(None, description="Filter by context type"),
    limit: int = Query(50, ge=1, le=200),
):
    """List agent memories for a site."""
    if context_type and context_type not in VALID_CONTEXT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid context_type. Must be one of: {', '.join(sorted(VALID_CONTEXT_TYPES))}",
        )

    repo = get_agent_memory_repository()
    memories = repo.get_by_site(site_id, context_type=context_type, limit=limit)
    return {"memories": memories, "count": len(memories)}


@router.get("/equipment/{equipment_code}")
async def get_equipment_memories(
    equipment_code: str,
    limit: int = Query(20, ge=1, le=100),
):
    """Get memories for a specific piece of equipment."""
    repo = get_agent_memory_repository()
    memories = repo.get_by_equipment(equipment_code, limit=limit)
    return {"memories": memories, "count": len(memories)}


@router.get("/{memory_id}")
async def get_memory(memory_id: str):
    """Get a single memory by ID."""
    repo = get_agent_memory_repository()
    memory = repo.get_by_id(memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@router.post("", status_code=201)
async def create_memory(body: AgentMemoryCreate):
    """Create or upsert an agent memory."""
    if body.context_type not in VALID_CONTEXT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid context_type. Must be one of: {', '.join(sorted(VALID_CONTEXT_TYPES))}",
        )
    if body.source not in VALID_SOURCES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source. Must be one of: {', '.join(sorted(VALID_SOURCES))}",
        )

    repo = get_agent_memory_repository()
    memory = repo.upsert(body.model_dump(exclude_none=True))
    logger.info("Agent memory upserted: site=%s key=%s", body.site_id, body.key)
    return memory


@router.patch("/{memory_id}")
async def update_memory(memory_id: str, body: AgentMemoryUpdate):
    """Update an existing agent memory."""
    repo = get_agent_memory_repository()
    existing = repo.get_by_id(memory_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Memory not found")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    if "context_type" in updates and updates["context_type"] not in VALID_CONTEXT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid context_type")
    if "source" in updates and updates["source"] not in VALID_SOURCES:
        raise HTTPException(status_code=400, detail="Invalid source")

    existing.update(updates)
    result = repo.upsert(existing)
    return result


@router.delete("/{memory_id}")
async def delete_memory(memory_id: str):
    """Delete an agent memory."""
    repo = get_agent_memory_repository()
    deleted = repo.delete(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"deleted": True, "id": memory_id}

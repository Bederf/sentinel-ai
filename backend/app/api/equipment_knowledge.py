"""
Equipment Knowledge API — tech chat context for maintenance records.

GET /api/equipment/{asset_id}/knowledge
    Returns maintenance/knowledge records for the given equipment asset,
    looked up by DB type (not parsed from asset_id string).

Phase 182-03.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/equipment", tags=["equipment-knowledge"])


@router.get("/{asset_id}/knowledge")
async def get_equipment_knowledge(
    asset_id: str,
    knowledge_type: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """
    Retrieve equipment knowledge records for tech chat context.

    Answers: "when was last generator service" — returns maintenance records
    ordered by created_at DESC.

    The equipment_type is always looked up from the DB (equipment.id = asset_id),
    NOT parsed from the asset_id string. This ensures correct type resolution
    even when asset_id format changes.
    """
    db = get_supabase_client()

    # Step 1: Look up equipment to get the canonical DB type (e.g., "GENERATOR")
    equipment = db.table("equipment").select("code", "type").eq("id", asset_id).execute()
    if not equipment.data:
        return {"asset_id": asset_id, "knowledge": [], "total": 0}

    equipment_code = equipment.data[0]["code"]
    equipment_type = equipment.data[0]["type"]  # e.g., "GENERATOR"

    # Step 2: Fetch knowledge records for this equipment type
    query = db.table("equipment_knowledge").select("*").eq("equipment_type", equipment_type)
    if knowledge_type:
        query = query.eq("knowledge_type", knowledge_type)
    knowledge_records = query.order("created_at", desc=True).limit(min(limit, 50)).execute()

    # Step 3: Build source_url map (two-step fetch to avoid complex JOIN)
    doc_ids = [r["source_document_id"] for r in knowledge_records.data if r.get("source_document_id")]
    source_url_map: dict[str, str | None] = {}
    if doc_ids:
        docs = db.table("documents").select("id", "source_url").in_("id", doc_ids).execute()
        source_url_map = {d["id"]: d.get("source_url") for d in docs.data}

    # Step 4: Build response
    knowledge = []
    for record in knowledge_records.data:
        knowledge.append(
            {
                "id": record["id"],
                "knowledge_type": record["knowledge_type"],
                "title": record["title"],
                "description": record["description"],
                "source_document_id": record.get("source_document_id"),
                "source_url": source_url_map.get(record.get("source_document_id")),
                "confidence": record.get("confidence", "medium"),
                "created_at": record.get("created_at"),
            }
        )

    return {
        "asset_id": asset_id,
        "equipment_code": equipment_code,
        "equipment_type": equipment_type,
        "knowledge": knowledge,
        "total": len(knowledge),
    }

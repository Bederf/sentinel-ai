"""
Chat tool: get_equipment_service_history — maintenance/service record lookup.

Answers "when was last service" questions by querying equipment_knowledge
records for the given equipment asset.

Phase 183-01.
"""

from __future__ import annotations

import logging
from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


async def get_equipment_service_history(
    asset_id: str,
    knowledge_type: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """
    Retrieve service/maintenance history for an equipment asset.

    The equipment type is always looked up from the DB (equipment.id = asset_id),
    NOT parsed from the asset_id string. This ensures correct type resolution
    even when asset_id format changes.

    Args:
        asset_id: Equipment UUID (equipment.id from the database)
        knowledge_type: Optional filter on knowledge_type field (e.g. "service", "repair")
        limit: Maximum number of records to return (default 10, max 50)

    Returns:
        Dictionary with service history records ordered by created_at DESC.
        Returns {"success": False, "error": ...} on any failure.
    """
    try:
        client = get_supabase_client()

        # Step 1: Look up equipment to get the canonical DB type
        equipment = client.table("equipment").select("code", "type").eq("id", asset_id).execute()
        if not equipment.data:
            return {"success": False, "error": f"Equipment '{asset_id}' not found"}

        equipment_code = equipment.data[0]["code"]
        equipment_type = equipment.data[0]["type"]  # e.g. "GENERATOR", "CHILLER"

        # Step 2: Fetch knowledge records for this equipment type
        query = client.table("equipment_knowledge").select("*").eq("equipment_type", equipment_type)
        if knowledge_type:
            query = query.eq("knowledge_type", knowledge_type)
        knowledge_resp = query.order("created_at", desc=True).limit(min(limit, 50)).execute()
        knowledge_records = knowledge_resp.data if knowledge_resp.data else []

        # Step 3: Build source_url map (two-step fetch to avoid complex JOIN)
        doc_ids = [r["source_document_id"] for r in knowledge_records if r.get("source_document_id")]
        source_url_map: dict[str, str | None] = {}
        if doc_ids:
            docs = client.table("documents").select("id", "source_url").in_("id", doc_ids).execute()
            source_url_map = {d["id"]: d.get("source_url") for d in docs.data}

        # Step 4: Build history list
        history = []
        for record in knowledge_records:
            history.append(
                {
                    "id": record["id"],
                    "knowledge_type": record.get("knowledge_type"),
                    "title": record.get("title"),
                    "description": record.get("description"),
                    "source_document_id": record.get("source_document_id"),
                    "source_url": source_url_map.get(record.get("source_document_id")),
                    "confidence": record.get("confidence", "medium"),
                    "created_at": record.get("created_at"),
                }
            )

        return {
            "success": True,
            "asset_id": asset_id,
            "equipment_code": equipment_code,
            "equipment_type": equipment_type,
            "history": history,
            "total": len(history),
        }

    except Exception as e:
        logger.error(f"Error getting equipment service history for '{asset_id}': {e}")
        return {"success": False, "error": str(e)}

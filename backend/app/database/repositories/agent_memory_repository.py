"""Repository for agent memory operations."""

import logging
import uuid
from datetime import datetime
from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

VALID_CONTEXT_TYPES = {
    "building_quirk",
    "equipment_note",
    "operator_preference",
    "seasonal",
    "safety_note",
}

VALID_SOURCES = {"claude", "sentry", "simbiot", "operator", "system"}


class AgentMemoryRepository:
    """Repository for agent memory CRUD operations in the canonical DB store."""

    def __init__(self):
        self.client = get_supabase_client()

    def get_by_site(
        self,
        site_id: str,
        context_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get memories for a site, optionally filtered by context_type."""
        try:
            query = (
                self.client.table("agent_memory")
                .select("*")
                .eq("site_id", site_id)
                .order("updated_at", desc=True)
                .limit(limit)
            )
            if context_type:
                query = query.eq("context_type", context_type)
            response = query.execute()
            return response.data or []
        except Exception as e:
            logger.error("Canonical agent_memory read failed: %s", e)
            return []

    def get_by_equipment(
        self,
        equipment_code: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get memories for a specific piece of equipment."""
        try:
            response = (
                self.client.table("agent_memory")
                .select("*")
                .eq("equipment_code", equipment_code)
                .order("updated_at", desc=True)
                .limit(limit)
                .execute()
            )
            return response.data or []
        except Exception as e:
            logger.error("Canonical agent_memory equipment read failed: %s", e)
            return []

    def get_by_id(self, memory_id: str) -> dict[str, Any] | None:
        """Get a single memory by ID."""
        try:
            response = self.client.table("agent_memory").select("*").eq("id", memory_id).execute()
            data = response.data
            return data[0] if data else None
        except Exception as e:
            logger.error("Canonical agent_memory get_by_id failed: %s", e)
            return None

    def upsert(self, memory: dict[str, Any]) -> dict[str, Any]:
        """Create or update a memory (upsert on site_id + equipment_code + key)."""
        ctx = memory.get("context_type")
        if ctx and ctx not in VALID_CONTEXT_TYPES:
            raise ValueError(f"Invalid context_type: {ctx}")
        src = memory.get("source")
        if src and src not in VALID_SOURCES:
            raise ValueError(f"Invalid source: {src}")

        if "id" not in memory:
            memory["id"] = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        memory.setdefault("created_at", now)
        memory["updated_at"] = now
        memory.setdefault("confidence", 1.0)
        memory.setdefault("source", "system")

        existing_rows = (
            self.client.table("agent_memory")
            .select("id,equipment_code")
            .eq("site_id", memory.get("site_id"))
            .eq("key", memory.get("key"))
            .execute()
        ).data or []

        target_id = None
        for row in existing_rows:
            if row.get("equipment_code") == memory.get("equipment_code"):
                target_id = row.get("id")
                break

        if target_id:
            memory["id"] = target_id
            response = self.client.table("agent_memory").update(memory).eq("id", target_id).execute()
        else:
            response = self.client.table("agent_memory").insert(memory).execute()

        data = response.data
        return data[0] if data else memory

    def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        try:
            self.client.table("agent_memory").delete().eq("id", memory_id).execute()
            return True
        except Exception as e:
            logger.error("Canonical agent_memory delete failed: %s", e)
            return False


_agent_memory_repo: AgentMemoryRepository | None = None


def get_agent_memory_repository() -> AgentMemoryRepository:
    """Get singleton agent memory repository."""
    global _agent_memory_repo
    if _agent_memory_repo is None:
        _agent_memory_repo = AgentMemoryRepository()
    return _agent_memory_repo

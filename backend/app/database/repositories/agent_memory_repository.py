"""Repository for agent memory operations.

Persistent conversational memory for SENTINEL AI agents.
Follows the 3-tier fallback pattern: Supabase -> JSON fallback.
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"
JSON_PATH = DATA_DIR / "agent_memory.json"

VALID_CONTEXT_TYPES = {
    "building_quirk",
    "equipment_note",
    "operator_preference",
    "seasonal",
    "safety_note",
}

VALID_SOURCES = {"claude", "sentry", "simbiot", "operator", "system"}


class AgentMemoryRepository:
    """Repository for agent memory CRUD operations."""

    def __init__(self):
        self.client = get_supabase_client()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_by_site(
        self,
        site_id: str,
        context_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
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
            logger.warning("Supabase agent_memory read failed, using JSON: %s", e)
            return self._get_by_site_json(site_id, context_type, limit)

    def get_by_equipment(
        self,
        equipment_code: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
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
            logger.warning("Supabase agent_memory read failed, using JSON: %s", e)
            return self._get_by_equipment_json(equipment_code, limit)

    def get_by_id(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """Get a single memory by ID."""
        try:
            response = self.client.table("agent_memory").select("*").eq("id", memory_id).execute()
            data = response.data
            return data[0] if data else None
        except Exception as e:
            logger.warning("Supabase agent_memory get_by_id failed: %s", e)
            return self._get_by_id_json(memory_id)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def upsert(self, memory: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update a memory (upsert on site_id + equipment_code + key)."""
        # Validate
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

        try:
            response = (
                self.client.table("agent_memory")
                .upsert(
                    memory,
                    on_conflict="site_id,COALESCE(equipment_code,'__site__'),key",
                )
                .execute()
            )
            data = response.data
            return data[0] if data else memory
        except Exception as e:
            logger.warning("Supabase agent_memory upsert failed, using JSON: %s", e)
            return self._upsert_json(memory)

    def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        try:
            self.client.table("agent_memory").delete().eq("id", memory_id).execute()
            return True
        except Exception as e:
            logger.warning("Supabase agent_memory delete failed: %s", e)
            return self._delete_json(memory_id)

    # ------------------------------------------------------------------
    # JSON fallback
    # ------------------------------------------------------------------

    def _load_json(self) -> List[Dict[str, Any]]:
        if JSON_PATH.exists():
            with open(JSON_PATH) as f:
                return json.load(f)
        return []

    def _save_json(self, data: List[Dict[str, Any]]) -> None:
        JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(JSON_PATH, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def _get_by_site_json(self, site_id: str, context_type: Optional[str], limit: int) -> List[Dict[str, Any]]:
        memories = self._load_json()
        result = [m for m in memories if m.get("site_id") == site_id]
        if context_type:
            result = [m for m in result if m.get("context_type") == context_type]
        result.sort(key=lambda m: m.get("updated_at", ""), reverse=True)
        return result[:limit]

    def _get_by_equipment_json(self, equipment_code: str, limit: int) -> List[Dict[str, Any]]:
        memories = self._load_json()
        result = [m for m in memories if m.get("equipment_code") == equipment_code]
        result.sort(key=lambda m: m.get("updated_at", ""), reverse=True)
        return result[:limit]

    def _get_by_id_json(self, memory_id: str) -> Optional[Dict[str, Any]]:
        memories = self._load_json()
        for m in memories:
            if m.get("id") == memory_id:
                return m
        return None

    def _upsert_json(self, memory: Dict[str, Any]) -> Dict[str, Any]:
        memories = self._load_json()
        # Find existing by site_id + equipment_code + key
        site_id = memory.get("site_id")
        equip = memory.get("equipment_code")
        key = memory.get("key")
        for i, m in enumerate(memories):
            if m.get("site_id") == site_id and m.get("equipment_code") == equip and m.get("key") == key:
                memories[i] = memory
                self._save_json(memories)
                return memory
        memories.append(memory)
        self._save_json(memories)
        return memory

    def _delete_json(self, memory_id: str) -> bool:
        memories = self._load_json()
        before = len(memories)
        memories = [m for m in memories if m.get("id") != memory_id]
        if len(memories) < before:
            self._save_json(memories)
            return True
        return False


# Singleton
_agent_memory_repo: Optional[AgentMemoryRepository] = None


def get_agent_memory_repository() -> AgentMemoryRepository:
    """Get singleton agent memory repository."""
    global _agent_memory_repo
    if _agent_memory_repo is None:
        _agent_memory_repo = AgentMemoryRepository()
    return _agent_memory_repo

"""Room registry repository backed by the canonical Postgres store."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)
_JSON_FALLBACK_PATH = Path(__file__).resolve().parent / "data" / "room_registry.json"


class RoomRegistryRepository:
    """Repository for room registry operations."""

    def __init__(self) -> None:
        self.client = get_supabase_client()

    def _load_json_fallback(self) -> list[dict]:
        try:
            with _JSON_FALLBACK_PATH.open() as handle:
                return json.load(handle)
        except Exception as exc:
            logger.error("Room registry JSON fallback load failed: %s", exc)
            return []

    async def get_rooms_by_site(self, site_id: str) -> list[dict]:
        """Get all active rooms for a site from the canonical store."""
        if self.client is None:
            return [room for room in self._load_json_fallback() if room.get("site_id") == site_id]
        try:
            result = self.client.table("room_registry").select("*").eq("site_id", site_id).eq("active", True).execute()
            return result.data or []
        except Exception as exc:
            logger.error("Canonical room_registry get_rooms_by_site failed: %s", exc)
            return [room for room in self._load_json_fallback() if room.get("site_id") == site_id]

    async def get_room(self, room_id: str) -> Optional[dict]:
        """Get a single room by room_id from the canonical store."""
        if self.client is None:
            return next((room for room in self._load_json_fallback() if room.get("room_id") == room_id), None)
        try:
            result = self.client.table("room_registry").select("*").eq("room_id", room_id).limit(1).execute()
            if result.data:
                return result.data[0]
        except Exception as exc:
            logger.error("Canonical room_registry get_room failed: %s", exc)
        return next((room for room in self._load_json_fallback() if room.get("room_id") == room_id), None)

    async def validate_room_exists(self, room_id: str) -> bool:
        """Quick existence check for a room_id."""
        return await self.get_room(room_id) is not None


_repository: Optional[RoomRegistryRepository] = None


def get_room_registry_repository() -> RoomRegistryRepository:
    """Get singleton room registry repository."""
    global _repository
    if _repository is None:
        _repository = RoomRegistryRepository()
    return _repository

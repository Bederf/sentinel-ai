"""
Room Registry Repository — data access for room_registry table.

Follows 3-tier fallback pattern: Supabase -> JSON file.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

_JSON_FALLBACK_PATH = Path(__file__).resolve().parents[2] / "data" / "space" / "room_registry.json"


class RoomRegistryRepository:
    """Repository for room registry operations."""

    def __init__(self) -> None:
        self.client = get_supabase_client()

    def _load_json_fallback(self) -> list[dict]:
        """Load rooms from JSON fallback file."""
        try:
            with open(_JSON_FALLBACK_PATH) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load room registry JSON fallback: {e}")
            return []

    async def get_rooms_by_site(self, site_id: str) -> list[dict]:
        """Get all rooms for a site. Supabase first, JSON fallback."""
        if self.client:
            try:
                result = (
                    self.client.table("room_registry").select("*").eq("site_id", site_id).eq("active", True).execute()
                )
                if result.data is not None:
                    return result.data
            except Exception as e:
                logger.warning(f"Supabase room_registry query failed, falling back to JSON: {e}")

        # JSON fallback
        rooms = self._load_json_fallback()
        return [r for r in rooms if r.get("site_id") == site_id and r.get("active", True)]

    async def get_room(self, room_id: str) -> Optional[dict]:
        """Get a single room by room_id. Supabase first, JSON fallback."""
        if self.client:
            try:
                result = self.client.table("room_registry").select("*").eq("room_id", room_id).execute()
                if result.data and len(result.data) > 0:
                    return result.data[0]
                return None
            except Exception as e:
                logger.warning(f"Supabase room lookup failed, falling back to JSON: {e}")

        # JSON fallback
        rooms = self._load_json_fallback()
        for r in rooms:
            if r.get("room_id") == room_id:
                return r
        return None

    async def validate_room_exists(self, room_id: str) -> bool:
        """Quick existence check for a room_id."""
        room = await self.get_room(room_id)
        return room is not None


# Singleton instance
_repository: Optional[RoomRegistryRepository] = None


def get_room_registry_repository() -> RoomRegistryRepository:
    """Get singleton room registry repository."""
    global _repository
    if _repository is None:
        _repository = RoomRegistryRepository()
    return _repository

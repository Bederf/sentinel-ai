"""Room registry repository backed by the canonical Postgres store."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.database.supabase_client import get_supabase_client
from app.services.block_booking_detector.site_resolver import normalize_site_id

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

    def _site_id_candidates(self, site_id: str) -> list[str]:
        raw = str(site_id).strip()
        normalized = normalize_site_id(raw)

        candidates: list[str] = []
        for candidate in (raw, raw.lower(), raw.upper(), normalized):
            if candidate and candidate not in candidates:
                candidates.append(candidate)

        if normalized.startswith("site-"):
            suffix = normalized.split("site-", 1)[1]
            short_code = f"S{suffix}"
            for candidate in (short_code, short_code.lower(), short_code.upper()):
                if candidate not in candidates:
                    candidates.append(candidate)

        return candidates

    async def get_rooms_by_site(self, site_id: str) -> list[dict]:
        """Get all active rooms for a site from the canonical store."""
        site_candidates = self._site_id_candidates(site_id)

        if self.client is None:
            fallback = self._load_json_fallback()
            return [room for room in fallback if str(room.get("site_id", "")).strip() in site_candidates]
        try:
            result = (
                self.client.table("room_registry")
                .select("*")
                .in_("site_id", site_candidates)
                .eq("active", True)
                .execute()
            )
            return result.data or []
        except Exception as exc:
            logger.error("Canonical room_registry get_rooms_by_site failed: %s", exc)
            fallback = self._load_json_fallback()
            return [room for room in fallback if str(room.get("site_id", "")).strip() in site_candidates]

    async def get_room(self, room_id: str) -> dict | None:
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


_repository: RoomRegistryRepository | None = None


def get_room_registry_repository() -> RoomRegistryRepository:
    """Get singleton room registry repository."""
    global _repository
    if _repository is None:
        _repository = RoomRegistryRepository()
    return _repository

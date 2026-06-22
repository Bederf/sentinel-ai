"""Resolve booking email site context from room identity."""

from __future__ import annotations

import re
from functools import lru_cache

from app.database.supabase_client import get_supabase_client


def normalize_site_id(site_id: str | None) -> str:
    """Normalize site identifiers to repo style, e.g. S002 -> site-002."""
    if not site_id:
        return ""

    normalized = str(site_id).strip()
    if not normalized:
        return ""

    upper = normalized.upper()
    if upper.startswith("SITE-"):
        return upper.lower()
    if upper.startswith("S") and upper[1:].isdigit():
        return f"site-{upper[1:].zfill(3)}"
    return normalized.lower()


def _normalize_room_alias(value: str | None) -> str:
    if not value:
        return ""
    return str(value).strip().upper()


def _site_id_from_text(value: str | None) -> str:
    """Extract an explicit site reference from room text without using local JSON."""
    if not value:
        return ""
    text = str(value).strip().upper()
    match = re.search(r"\bS([0-9]{3})\b", text)
    if match:
        return f"site-{match.group(1)}"
    match = re.search(r"\bSITE[\s_-]*([0-9]{3})\b", text)
    if match:
        return f"site-{match.group(1)}"
    return ""


@lru_cache(maxsize=1)
def _load_room_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {}

    try:
        rooms = (
            get_supabase_client().table("room_registry").select("site_id, room_id, friendly_name").execute().data or []
        )
    except Exception:
        rooms = []
    for room in rooms:
        site_id = normalize_site_id(room.get("site_id"))
        if not site_id:
            continue
        for candidate in (room.get("room_id"), room.get("friendly_name")):
            alias = _normalize_room_alias(candidate)
            if alias:
                aliases[alias] = site_id

    return aliases


def resolve_site_id_for_room(*room_candidates: str | None, fallback_site_id: str | None = None) -> str:
    """Resolve a site id from a room id/name, falling back only if no match exists."""
    aliases = _load_room_aliases()
    for candidate in room_candidates:
        alias = _normalize_room_alias(candidate)
        if not alias:
            continue
        site_id = aliases.get(alias)
        if site_id:
            return site_id
        site_id = _site_id_from_text(candidate)
        if site_id:
            return site_id
    return normalize_site_id(fallback_site_id)

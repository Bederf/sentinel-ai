"""Resolve booking email site context from room identity."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.database.supabase_client import get_supabase_client

BUILDINGS_PATH = Path(__file__).resolve().parents[2] / "data" / "buildings"


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

    if BUILDINGS_PATH.exists():
        for site_dir in BUILDINGS_PATH.iterdir():
            if not site_dir.is_dir():
                continue
            site_id = normalize_site_id(site_dir.name)
            zones_path = site_dir / "zones.json"
            if not zones_path.exists():
                continue
            with open(zones_path) as handle:
                zones_payload = json.load(handle)
            zones = zones_payload.get("zones", []) if isinstance(zones_payload, dict) else []
            for zone in zones:
                if zone.get("zone_type") != "meeting_room":
                    continue
                for candidate in (
                    zone.get("zone_id"),
                    zone.get("room_name"),
                    zone.get("friendly_name"),
                    zone.get("booking_alias"),
                ):
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
    return normalize_site_id(fallback_site_id)

"""
Signal Emitter Base Utilities — Phase 159
===========================================
Shared utilities for all signal emitter bridges (email, booking, occupancy).
Pure functions — no class. Async-first via httpx.

Functions:
    _get_supabase_headers  — Auth headers for Supabase REST
    write_signal           — POST one signal row to Supabase
    write_entities         — Bulk-insert entity rows linked to a signal
    check_dedup            — In-memory deduplication within a time window
    extract_entities_from_text — Rule-based person/room/building extraction
    build_signal_row       — Construct a signal dict matching table schema
"""

import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory deduplication store
# ---------------------------------------------------------------------------
_recent_signals: dict[str, float] = {}


# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------


def _get_supabase_headers() -> dict:
    """Return auth headers for Supabase REST API."""
    return {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


async def write_signal(signal_row: dict) -> dict:
    """POST a single signal row to Supabase ``signal`` table.

    Returns the created row (Prefer: return=representation).
    On error: logs and re-raises so the caller can decide.
    """
    url = f"{settings.supabase_url}/rest/v1/signal"
    headers = _get_supabase_headers()

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, headers=headers, json=signal_row)
        resp.raise_for_status()
        created = resp.json()
        row = created[0] if isinstance(created, list) else created

        logger.info(
            "Signal written: id=%s source=%s type=%s",
            row.get("id"),
            row.get("source_module"),
            row.get("signal_type"),
        )
        return row


async def write_entities(entities: list[dict]) -> list[dict]:
    """Bulk-insert entity rows linked to a signal.

    Each entity dict should have: id, signal_id, entity_type, name, metadata.
    Returns created entity rows.
    """
    if not entities:
        return []

    url = f"{settings.supabase_url}/rest/v1/entity"
    headers = _get_supabase_headers()

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, headers=headers, json=entities)
        resp.raise_for_status()
        created = resp.json()
        rows = created if isinstance(created, list) else [created]

        logger.info("Entities written: %d rows for signal %s", len(rows), entities[0].get("signal_id"))
        return rows


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def check_dedup(
    source_module: str,
    signal_type: str,
    location_ref: str,
    window_seconds: int = 300,
) -> bool:
    """Return True if the same signal was seen within *window_seconds*.

    Uses a module-level dict — lightweight, no external deps.
    Expired entries are cleaned on each call.
    """
    now = time.monotonic()
    key = f"{source_module}:{signal_type}:{location_ref}"

    # Clean expired entries
    expired = [k for k, ts in _recent_signals.items() if now - ts > window_seconds]
    for k in expired:
        del _recent_signals[k]

    if key in _recent_signals and now - _recent_signals[key] <= window_seconds:
        return True

    _recent_signals[key] = now
    return False


def _reset_dedup() -> None:
    """Clear dedup cache — for testing only."""
    _recent_signals.clear()


# ---------------------------------------------------------------------------
# Entity extraction
# ---------------------------------------------------------------------------


def extract_entities_from_text(
    text: str,
    known_people: list[str] | None = None,
    known_rooms: list[str] | None = None,
) -> list[dict]:
    """Rule-based entity extraction from free text.

    Extracts:
    - Room codes: ``FA1-1Q4-MR10`` style
    - Building codes: ``FA1``, ``FA2``, ``S002``
    - Known people names (if provided)
    - Known room names (if provided)

    Returns list of entity dicts ready for ``write_entities()``.
    Each dict has: entity_type, name, metadata (signal_id/id added by caller).
    """
    entities: list[dict] = []
    seen: set[str] = set()

    # Room code pattern: {building}-{floor}Q{quadrant}-{type}{number}
    room_pattern = re.compile(r"\b(FA[12])-(\dQ\d)-([A-Z]{2})(\d+)\b", re.IGNORECASE)
    for m in room_pattern.finditer(text):
        code = f"{m.group(1).upper()}-{m.group(2).upper()}-{m.group(3).upper()}{m.group(4)}"
        if code not in seen:
            seen.add(code)
            entities.append(
                {
                    "entity_type": "room",
                    "name": code,
                    "metadata": {"raw_match": m.group(0)},
                }
            )

    # Building codes: FA1, FA2, S002
    building_pattern = re.compile(r"\b(FA[12]|S\d{3})\b", re.IGNORECASE)
    for m in building_pattern.finditer(text):
        bldg = m.group(1).upper()
        if bldg not in seen:
            seen.add(bldg)
            entities.append(
                {
                    "entity_type": "building",
                    "name": bldg,
                    "metadata": {},
                }
            )

    # Known people
    if known_people:
        text_lower = text.lower()
        for person in known_people:
            if person.lower() in text_lower and person not in seen:
                seen.add(person)
                entities.append(
                    {
                        "entity_type": "person",
                        "name": person,
                        "metadata": {},
                    }
                )

    # Known rooms (friendly names like "Springboks")
    if known_rooms:
        text_lower = text.lower()
        for room in known_rooms:
            if room.lower() in text_lower and room not in seen:
                seen.add(room)
                entities.append(
                    {
                        "entity_type": "room",
                        "name": room,
                        "metadata": {"source": "known_rooms"},
                    }
                )

    return entities


# ---------------------------------------------------------------------------
# Signal row builder
# ---------------------------------------------------------------------------


def build_signal_row(
    source_module: str,
    signal_type: str,
    severity: str,
    confidence: float,
    location_ref: str,
    raw_content: str,
    metadata: dict | None = None,
    site_id: Optional[str] = None,
    parent_signal_id: Optional[str] = None,
) -> dict:
    """Construct a signal dict matching the ``signal`` table schema.

    Generates UUID id, sets created_at to UTC now, truncates raw_content
    to 2000 chars.
    """
    signal_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    row: dict = {
        "id": signal_id,
        "source_module": source_module,
        "signal_type": signal_type,
        "severity": severity,
        "confidence": confidence,
        "location_ref": location_ref or "unknown",
        "resolution_state": "active",
        "raw_content": raw_content[:2000] if raw_content else "",
        "metadata": metadata or {},
        "created_at": now,
    }

    if site_id:
        row["site_id"] = site_id
    if parent_signal_id:
        row["parent_signal_id"] = parent_signal_id

    return row


# ---------------------------------------------------------------------------
# Location reference helpers
# ---------------------------------------------------------------------------


def room_code_to_location_ref(room_code: str) -> str:
    """Derive a hierarchical location reference from a room code.

    Handles Fairlands-style codes (``FA1-1Q4-MR10``) and generic site-zone
    codes (``S002-L2-B``).  Returns a ``/``-separated path.

    Examples::

        FA1-1Q4-MR10  → Fairlands/FA1/1Q4/MR10
        FA2-2Q1-BR03  → Fairlands/FA2/2Q1/BR03
        S002-L2-B     → S002/L2-B
        unknown       → unknown
    """
    if not room_code:
        return "unknown"

    # Fairlands pattern: FA{n}-{floor}Q{quad}-{type}{num}
    fa_match = re.match(r"^(FA[12])-(\dQ\d)-([A-Z]{2,4}\d*)$", room_code, re.IGNORECASE)
    if fa_match:
        bldg = fa_match.group(1).upper()
        fq = fa_match.group(2).upper()
        room = fa_match.group(3).upper()
        return f"Fairlands/{bldg}/{fq}/{room}"

    # Site-zone pattern: S00x-...
    site_match = re.match(r"^(S\d{3})-(.+)$", room_code, re.IGNORECASE)
    if site_match:
        site = site_match.group(1).upper()
        rest = site_match.group(2).upper()
        return f"{site}/{rest}"

    return room_code

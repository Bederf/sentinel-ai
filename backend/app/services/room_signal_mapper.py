"""
Room Signal Mapper — Phase 161-02
===================================
Maps signals to rooms by extracting room IDs from signal fields and
validating them against the room registry. Creates entity/relationship
links between signals and rooms.

Functions:
    extract_room_id         — regex extraction of room ID from free text
    map_signal_to_room      — find room_id for a signal across multiple fields
    link_signal_to_room     — create entity + relationship linking signal to room
"""

from __future__ import annotations

import logging
import re
import uuid

from app.services.signal_emitter_base import write_entities

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Room ID pattern — matches Fairlands-style room codes
# Examples: FA2-1Q1-MR-01, FA1-2Q3-PR-05, fa2-1q1-mr-06
# ---------------------------------------------------------------------------

ROOM_ID_PATTERN = re.compile(r"\b(FA[12]-\d+Q\d+-(?:MR|PR)-\d+)\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def extract_room_id(text: str) -> str | None:
    """Extract the first room ID match from any text.

    Returns the room ID uppercased, or None if no match found.
    """
    if not text:
        return None
    match = ROOM_ID_PATTERN.search(text)
    if match:
        return match.group(1).upper()
    return None


# ---------------------------------------------------------------------------
# Signal-to-room mapping
# ---------------------------------------------------------------------------


async def map_signal_to_room(room_repo, signal: dict) -> str | None:
    """Find room_id for a signal by checking fields in priority order.

    Checks (in order):
    1. ``location_ref`` field
    2. ``summary`` field
    3. ``metadata`` fields: ``room_id``, ``rooms_affected``, ``subject``

    Each candidate is validated against the room registry via
    ``room_repo.validate_room_exists()``.

    Args:
        room_repo: Room registry repository instance with
                   ``validate_room_exists(room_id) -> bool`` method.
        signal: Signal dict with optional keys: location_ref, summary, metadata.

    Returns:
        Validated room_id string, or None if no valid room found.
    """
    candidates: list[str] = []

    # 1. Check location_ref
    location_ref = signal.get("location_ref", "")
    if location_ref:
        room_id = extract_room_id(location_ref)
        if room_id:
            candidates.append(room_id)

    # 2. Check summary
    summary = signal.get("summary", "")
    if summary:
        room_id = extract_room_id(summary)
        if room_id and room_id not in candidates:
            candidates.append(room_id)

    # 3. Check metadata fields
    metadata = signal.get("metadata") or {}
    if isinstance(metadata, dict):
        # Direct room_id field
        meta_room = metadata.get("room_id", "")
        if meta_room:
            upper_room = meta_room.upper()
            if upper_room not in candidates:
                candidates.append(upper_room)

        # rooms_affected (could be a list or comma-separated string)
        rooms_affected = metadata.get("rooms_affected", "")
        if isinstance(rooms_affected, list):
            for r in rooms_affected:
                room_id = extract_room_id(str(r))
                if room_id and room_id not in candidates:
                    candidates.append(room_id)
        elif isinstance(rooms_affected, str) and rooms_affected:
            room_id = extract_room_id(rooms_affected)
            if room_id and room_id not in candidates:
                candidates.append(room_id)

        # subject field
        subject = metadata.get("subject", "")
        if subject:
            room_id = extract_room_id(subject)
            if room_id and room_id not in candidates:
                candidates.append(room_id)

    # Validate candidates against room registry
    for candidate in candidates:
        try:
            exists = await room_repo.validate_room_exists(candidate)
            if exists:
                return candidate
        except Exception as exc:
            logger.warning("Room validation failed for %s: %s", candidate, exc)

    return None


# ---------------------------------------------------------------------------
# Entity linking
# ---------------------------------------------------------------------------


async def link_signal_to_room(signal_id: str, room_id: str) -> None:
    """Create an entity (type='room') and relationship (edge_type='affects')
    linking a signal to a room.

    Uses ``signal_emitter_base.write_entities()`` for persistence.
    Follows the entity pattern from Phase 156.

    Args:
        signal_id: UUID of the signal to link.
        room_id: Room code to link (e.g. 'FA2-1Q1-MR-01').
    """
    entity_id = str(uuid.uuid4())
    entities = [
        {
            "id": entity_id,
            "signal_id": signal_id,
            "entity_type": "room",
            "name": room_id,
            "metadata": {
                "edge_type": "affects",
                "source": "room_signal_mapper",
            },
        }
    ]

    try:
        await write_entities(entities)
        logger.info(
            "Linked signal %s to room %s (entity %s)",
            signal_id,
            room_id,
            entity_id,
        )
    except Exception as exc:
        logger.warning(
            "Failed to link signal %s to room %s: %s",
            signal_id,
            room_id,
            exc,
        )

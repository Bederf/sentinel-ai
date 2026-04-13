"""Concierge user CRUD store backed by the canonical Postgres store."""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)
_lock = threading.Lock()


@dataclass
class ConciergeUser:
    """A concierge user who confirms room occupancy for ghost bookings."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    mobile: str = ""
    email: str = ""
    site_id: str = ""
    building_codes: list[str] = field(default_factory=list)
    floor_assignments: dict[str, list[int]] = field(default_factory=dict)
    active: bool = True
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


def _client():
    return get_supabase_client()


def _dict_to_concierge(d: dict) -> ConciergeUser:
    return ConciergeUser(
        id=d.get("id", str(uuid.uuid4())),
        name=d.get("name", ""),
        mobile=d.get("mobile", ""),
        email=d.get("email", ""),
        site_id=d.get("site_id", ""),
        building_codes=d.get("building_codes", []),
        floor_assignments=d.get("floor_assignments", {}),
        active=d.get("active", True),
        created_at=d.get("created_at", ""),
        updated_at=d.get("updated_at", ""),
    )


def list_concierges(site_id: str | None = None) -> list[ConciergeUser]:
    """List all concierge users, optionally filtered by site_id."""
    try:
        query = _client().table("space_concierges").select("*")
        if site_id:
            query = query.eq("site_id", site_id)
        response = query.execute()
        return [_dict_to_concierge(row) for row in (response.data or [])]
    except Exception as exc:
        logger.error("Canonical list_concierges failed: %s", exc)
        return []


def get_concierge(concierge_id: str) -> ConciergeUser | None:
    """Get a single concierge by ID."""
    try:
        response = _client().table("space_concierges").select("*").eq("id", concierge_id).limit(1).execute()
        rows = response.data or []
        return _dict_to_concierge(rows[0]) if rows else None
    except Exception as exc:
        logger.error("Canonical get_concierge failed: %s", exc)
        return None


def create_concierge(data: dict) -> ConciergeUser:
    """Create a new concierge user. Returns the created user."""
    now = datetime.utcnow().isoformat()
    concierge = ConciergeUser(
        id=str(uuid.uuid4()),
        name=data.get("name", ""),
        mobile=data.get("mobile", ""),
        email=data.get("email", ""),
        site_id=data.get("site_id", ""),
        building_codes=data.get("building_codes", []),
        floor_assignments=data.get("floor_assignments", {}),
        active=data.get("active", True),
        created_at=now,
        updated_at=now,
    )
    with _lock:
        try:
            _client().table("space_concierges").insert(concierge.__dict__).execute()
        except Exception as exc:
            logger.error("Canonical create_concierge failed: %s", exc)
            raise
    return concierge


def update_concierge(concierge_id: str, data: dict) -> ConciergeUser | None:
    """Update an existing concierge. Returns updated user or None if not found."""
    with _lock:
        concierge = get_concierge(concierge_id)
        if concierge is None:
            return None
        record = concierge.__dict__.copy()
        for key in ("name", "mobile", "email", "site_id", "building_codes", "floor_assignments", "active"):
            if key in data:
                record[key] = data[key]
        record["updated_at"] = datetime.utcnow().isoformat()
        try:
            _client().table("space_concierges").update(record).eq("id", concierge_id).execute()
            return _dict_to_concierge(record)
        except Exception as exc:
            logger.error("Canonical update_concierge failed: %s", exc)
            return None


def delete_concierge(concierge_id: str) -> bool:
    """Delete a concierge by ID. Returns True if found and deleted."""
    with _lock:
        try:
            response = _client().table("space_concierges").delete().eq("id", concierge_id).execute()
            return bool(response.data is not None)
        except Exception as exc:
            logger.error("Canonical delete_concierge failed: %s", exc)
            return False


def find_concierge_for_room(site_id: str, building_code: str, floor: int | None = None) -> ConciergeUser | None:
    """Find the best matching active concierge for a room location."""
    concierges = list_concierges(site_id=site_id)
    active = [c for c in concierges if c.active]

    if floor is not None:
        for concierge in active:
            if building_code in concierge.building_codes:
                if floor in concierge.floor_assignments.get(building_code, []):
                    return concierge

    for concierge in active:
        if building_code in concierge.building_codes:
            return concierge

    if active:
        return active[0]

    return None


def find_all_concierges_for_room(site_id: str, building_code: str) -> list[ConciergeUser]:
    """Return all active concierges assigned to a building, falling back to all site concierges.

    Used for multi-recipient ghost booking alerts — every concierge assigned to the
    building receives the notification, not just the first match.
    """
    concierges = list_concierges(site_id=site_id)
    active = [c for c in concierges if c.active]

    matched = [c for c in active if building_code in c.building_codes]
    return matched if matched else active

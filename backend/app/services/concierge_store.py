"""Concierge user CRUD store.

Manages concierge users who receive ghost booking notifications and
confirm room status. JSON file persistence at data/space/concierges.json.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "space"
_CONCIERGES_FILE = _DATA_DIR / "concierges.json"
_lock = threading.Lock()


@dataclass
class ConciergeUser:
    """A concierge user who confirms room occupancy for ghost bookings."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    mobile: str = ""  # WhatsApp number, E.164 format
    email: str = ""
    site_id: str = ""
    building_codes: list[str] = field(default_factory=list)
    floor_assignments: dict[str, list[int]] = field(default_factory=dict)  # building_code -> [floor_nums]
    active: bool = True
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


def _ensure_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_all() -> list[dict]:
    if not _CONCIERGES_FILE.exists():
        return []
    try:
        with open(_CONCIERGES_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_all(data: list[dict]) -> None:
    _ensure_dir()
    with open(_CONCIERGES_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


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


def list_concierges(site_id: Optional[str] = None) -> list[ConciergeUser]:
    """List all concierge users, optionally filtered by site_id."""
    with _lock:
        records = _load_all()
    concierges = [_dict_to_concierge(r) for r in records]
    if site_id:
        concierges = [c for c in concierges if c.site_id == site_id]
    return concierges


def get_concierge(concierge_id: str) -> Optional[ConciergeUser]:
    """Get a single concierge by ID."""
    with _lock:
        records = _load_all()
    for r in records:
        if r.get("id") == concierge_id:
            return _dict_to_concierge(r)
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
        records = _load_all()
        records.append(asdict(concierge))
        _save_all(records)
    return concierge


def update_concierge(concierge_id: str, data: dict) -> Optional[ConciergeUser]:
    """Update an existing concierge. Returns updated user or None if not found."""
    with _lock:
        records = _load_all()
        for i, r in enumerate(records):
            if r.get("id") == concierge_id:
                # Merge provided fields
                for key in ("name", "mobile", "email", "site_id", "building_codes", "floor_assignments", "active"):
                    if key in data:
                        r[key] = data[key]
                r["updated_at"] = datetime.utcnow().isoformat()
                records[i] = r
                _save_all(records)
                return _dict_to_concierge(r)
    return None


def delete_concierge(concierge_id: str) -> bool:
    """Delete a concierge by ID. Returns True if found and deleted."""
    with _lock:
        records = _load_all()
        new_records = [r for r in records if r.get("id") != concierge_id]
        if len(new_records) == len(records):
            return False
        _save_all(new_records)
    return True


def find_concierge_for_room(site_id: str, building_code: str, floor: Optional[int] = None) -> Optional[ConciergeUser]:
    """Find the best matching active concierge for a room location.

    Matches by site_id + building_code, optionally narrowing by floor.
    Returns the most specific match (floor-assigned first).
    """
    concierges = list_concierges(site_id=site_id)
    active = [c for c in concierges if c.active]

    # First pass: match building + floor
    if floor is not None:
        for c in active:
            if building_code in c.building_codes:
                floor_list = c.floor_assignments.get(building_code, [])
                if floor in floor_list:
                    return c

    # Second pass: match building (any floor)
    for c in active:
        if building_code in c.building_codes:
            return c

    # Third pass: match site (any building)
    if active:
        return active[0]

    return None

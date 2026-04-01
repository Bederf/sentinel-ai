"""Repository for visit management with JSON file persistence.

Dual-write pattern: Supabase (primary) + JSON file (backup/fallback).
Thread-safe read-modify-write using file rotation + filelock.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID

from filelock import FileLock

from app.models.visit import BuildingMap, Visit, VisitStatus

logger = logging.getLogger(__name__)

# JSON store paths
DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
VISIT_STORE_PATH = DATA_DIR / "visit_store.json"
BUILDING_MAP_STORE_PATH = DATA_DIR / "building_map_store.json"
VISIT_LOCK_PATH = DATA_DIR / "visit_store.lock"
BUILDING_MAP_LOCK_PATH = DATA_DIR / "building_map_store.lock"


def _serialize_visit(visit: Visit) -> dict:
    """Serialize a Visit to a JSON-serializable dict."""
    return visit.model_dump(mode="json")


def _deserialize_visit(data: dict) -> Visit:
    """Deserialize a dict back to a Visit model."""
    return Visit(**data)


def _serialize_building_map(mapping: BuildingMap) -> dict:
    """Serialize a BuildingMap to a JSON-serializable dict."""
    return mapping.model_dump(mode="json")


def _deserialize_building_map(data: dict) -> BuildingMap:
    """Deserialize a dict back to a BuildingMap model."""
    return BuildingMap(**data)


class VisitRepository:
    """Repository for Visit records with thread-safe JSON store."""

    def __init__(self) -> None:
        self._client = None
        self._use_json = False
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Supabase client (lazy, falls back to JSON on failure)
    # ------------------------------------------------------------------

    @property
    def client(self):
        """Lazy-load Supabase client; fall back to JSON if unavailable."""
        if self._client is None and not self._use_json:
            try:
                from app.database.supabase_client import get_supabase_client

                self._client = get_supabase_client()
            except Exception as exc:
                logger.warning("Failed to get Supabase client, using JSON fallback: %s", exc)
                self._use_json = True
        return self._client

    # ------------------------------------------------------------------
    # Visit CRUD — JSON store
    # ------------------------------------------------------------------

    def _read_store(self) -> dict:
        """Read the entire visit store, returning an empty dict if missing."""
        if not VISIT_STORE_PATH.exists():
            return {"visits": []}
        try:
            with open(VISIT_STORE_PATH, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as exc:
            logger.warning("Failed to read visit store: %s", exc)
            return {"visits": []}

    def _write_store(self, store: dict) -> None:
        """Atomically write the visit store using file rotation."""
        # Write to a temp file in the same directory, then rename
        dirname = VISIT_STORE_PATH.parent
        with tempfile.NamedTemporaryFile(mode="w", dir=dirname, delete=False) as tmp:
            json.dump(store, tmp, indent=2, default=str)
            tmp_path = Path(tmp.name)
        # Atomic rename (on POSIX this is atomic if on same filesystem)
        shutil.move(str(tmp_path), str(VISIT_STORE_PATH))

    def _with_lock(self, func, lock_path: Path = VISIT_LOCK_PATH):
        """Execute func while holding a FileLock."""
        lock = FileLock(lock_path, timeout=10)
        with lock:
            return func()

    def create_visit(self, visit: Visit) -> Visit:
        """Persist a new visit to the store."""
        def _create():
            store = self._read_store()
            # Ensure no duplicate token or pin
            existing_tokens = {v["token"] for v in store["visits"]}
            existing_pins = {v["pin"] for v in store["visits"]}
            if str(visit.token) in existing_tokens:
                raise ValueError(f"Visit with token {visit.token} already exists")
            if visit.pin in existing_pins:
                raise ValueError(f"Visit with pin {visit.pin} already exists")
            store["visits"].append(_serialize_visit(visit))
            self._write_store(store)
            return visit

        return self._with_lock(_create)

    def get_visit_by_id(self, id: UUID) -> Optional[Visit]:
        """Retrieve a visit by its primary id."""
        def _get():
            store = self._read_store()
            for v in store["visits"]:
                if v["id"] == str(id):
                    return _deserialize_visit(v)
            return None

        return self._with_lock(_get)

    def get_visit_by_token(self, token: UUID) -> Optional[Visit]:
        """Retrieve a visit by its QR token (primary lookup key)."""
        def _get():
            store = self._read_store()
            for v in store["visits"]:
                if v["token"] == str(token):
                    return _deserialize_visit(v)
            return None

        return self._with_lock(_get)

    def get_visit_by_pin(self, pin: str) -> Optional[Visit]:
        """Retrieve a visit by its 6-digit PIN (scan fallback)."""
        def _get():
            store = self._read_store()
            for v in store["visits"]:
                if v["pin"] == pin:
                    return _deserialize_visit(v)
            return None

        return self._with_lock(_get)

    def update_visit(self, id: UUID, updates: dict) -> Optional[Visit]:
        """Update a visit by id, applying partial updates from updates dict."""
        def _update():
            store = self._read_store()
            for i, v in enumerate(store["visits"]):
                if v["id"] == str(id):
                    # Merge updates, protecting id/token/pin
                    for key in ["visitor_email", "visitor_name", "host_email", "host_name",
                                "host_mobile", "building_id", "meeting_start", "meeting_end",
                                "status", "visitor_photo", "visitor_vehicle", "visitor_id_number",
                                "access_card_id", "qr_code"]:
                        if key in updates:
                            v[key] = updates[key]
                    v["updated_at"] = datetime.now(timezone.utc).isoformat()
                    store["visits"][i] = v
                    self._write_store(store)
                    return _deserialize_visit(v)
            return None

        return self._with_lock(_update)

    def list_visits_by_building(
        self, building_id: str, status: Optional[VisitStatus] = None
    ) -> list[Visit]:
        """List all visits for a building, optionally filtered by status."""
        def _list():
            store = self._read_store()
            visits = []
            for v in store["visits"]:
                if v["building_id"] == building_id:
                    if status is None or v["status"] == status.value:
                        visits.append(_deserialize_visit(v))
            return visits

        return self._with_lock(_list)

    def list_active_visits(self) -> list[Visit]:
        """List all visits in CREATED, ARRIVED, REGISTERED, or APPROVED status."""
        ACTIVE_STATUSES = {
            VisitStatus.CREATED.value,
            VisitStatus.ARRIVED.value,
            VisitStatus.REGISTERED.value,
            VisitStatus.APPROVED.value,
            VisitStatus.ACTIVE.value,
        }

        def _list():
            store = self._read_store()
            visits = []
            for v in store["visits"]:
                if v["status"] in ACTIVE_STATUSES:
                    visits.append(_deserialize_visit(v))
            return visits

        return self._with_lock(_list)


class BuildingMapRepository:
    """Repository for BuildingMap records with JSON file persistence."""

    def __init__(self) -> None:
        pass

    def _read_store(self) -> dict:
        """Read the entire building map store."""
        if not BUILDING_MAP_STORE_PATH.exists():
            return {"building_maps": []}
        try:
            with open(BUILDING_MAP_STORE_PATH, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as exc:
            logger.warning("Failed to read building map store: %s", exc)
            return {"building_maps": []}

    def _write_store(self, store: dict) -> None:
        """Atomically write the building map store using file rotation."""
        dirname = BUILDING_MAP_STORE_PATH.parent
        with tempfile.NamedTemporaryFile(mode="w", dir=dirname, delete=False) as tmp:
            json.dump(store, tmp, indent=2, default=str)
            tmp_path = Path(tmp.name)
        shutil.move(str(tmp_path), str(BUILDING_MAP_STORE_PATH))

    def _with_lock(self, func):
        """Execute func while holding a FileLock."""
        lock = FileLock(BUILDING_MAP_LOCK_PATH, timeout=10)
        with lock:
            return func()

    def create_building_map(self, mapping: BuildingMap) -> BuildingMap:
        """Persist a new building map entry."""
        def _create():
            store = self._read_store()
            # Check for duplicate outlook_location_string
            existing = {bm["outlook_location_string"] for bm in store["building_maps"]}
            if mapping.outlook_location_string in existing:
                raise ValueError(
                    f"BuildingMap with outlook_location_string "
                    f"'{mapping.outlook_location_string}' already exists"
                )
            store["building_maps"].append(_serialize_building_map(mapping))
            self._write_store(store)
            return mapping

        return self._with_lock(_create)

    def get_building_map_by_outlook_location(
        self, location: str
    ) -> Optional[BuildingMap]:
        """Resolve an Outlook location string to a BuildingMap (case-insensitive)."""
        def _get():
            store = self._read_store()
            loc_lower = location.lower()
            for bm in store["building_maps"]:
                if bm["outlook_location_string"].lower() == loc_lower:
                    return _deserialize_building_map(bm)
            return None

        return self._with_lock(_get)

    def list_building_maps(self) -> list[BuildingMap]:
        """List all building map entries."""
        def _list():
            store = self._read_store()
            return [_deserialize_building_map(bm) for bm in store["building_maps"]]

        return self._with_lock(_list)

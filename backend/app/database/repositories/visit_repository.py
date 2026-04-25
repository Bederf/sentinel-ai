"""Repository for visit management — Supabase primary store."""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from uuid import UUID

from filelock import FileLock

from app.models.visit import BuildingMap, Visit, VisitStatus

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"


def _serialize_visit(visit: Visit) -> dict:
    return visit.model_dump(mode="json")


def _deserialize_visit(data: dict) -> Visit:
    return Visit(**data)


def _serialize_building_map(mapping: BuildingMap) -> dict:
    return mapping.model_dump(mode="json")


def _deserialize_building_map(data: dict) -> BuildingMap:
    return BuildingMap(**data)


class VisitRepository:
    """Repository for Visit records — Supabase primary store."""

    def __init__(self) -> None:
        self._client = None

    @property
    def client(self):
        """Lazy-load Supabase client."""
        if self._client is None:
            from app.database.supabase_client import get_supabase_client

            self._client = get_supabase_client()
        return self._client

    def create_visit(self, visit: Visit) -> Visit:
        """Persist a new visit to Supabase."""
        payload = {
            "id": str(visit.id),
            "token": str(visit.token),
            "pin": visit.pin,
            "visitor_email": visit.visitor_email,
            "visitor_name": visit.visitor_name,
            "visitor_photo": visit.visitor_photo,
            "visitor_vehicle": visit.visitor_vehicle,
            "visitor_id_number": visit.visitor_id_number,
            "host_email": visit.host_email,
            "host_name": visit.host_name,
            "host_mobile": visit.host_mobile,
            "building_id": visit.building_id,
            "meeting_subject": visit.meeting_subject,
            "meeting_start": visit.meeting_start.isoformat(),
            "meeting_end": visit.meeting_end.isoformat(),
            "status": visit.status,
            "access_card_id": visit.access_card_id,
            "qr_code": visit.qr_code,
            "external_event_id": visit.external_event_id,
            "created_at": visit.created_at.isoformat(),
            "updated_at": visit.updated_at.isoformat(),
        }
        self.client.table("visits").insert(payload).execute()
        return visit

    def get_visit_by_id(self, id: UUID) -> Visit | None:
        result = self.client.table("visits").select("*").eq("id", str(id)).execute()
        if not result.data:
            return None
        return _deserialize_visit(result.data[0])

    def get_visit_by_token(self, token: UUID) -> Visit | None:
        result = self.client.table("visits").select("*").eq("token", str(token)).execute()
        if not result.data:
            return None
        return _deserialize_visit(result.data[0])

    def get_visit_by_pin(self, pin: str) -> Visit | None:
        result = self.client.table("visits").select("*").eq("pin", pin).execute()
        if not result.data:
            return None
        return _deserialize_visit(result.data[0])

    def get_visit_by_external_event_id(self, external_event_id: str) -> Visit | None:
        result = self.client.table("visits").select("*").eq("external_event_id", external_event_id).execute()
        if not result.data:
            return None
        return _deserialize_visit(result.data[0])

    def update_visit(self, id: UUID, updates: dict) -> Visit | None:
        # Serialize datetime fields
        serialized = {}
        for k, v in updates.items():
            if isinstance(v, datetime):
                serialized[k] = v.isoformat()
            else:
                serialized[k] = v

        result = self.client.table("visits").update(serialized).eq("id", str(id)).execute()
        if not result.data:
            return None
        return _deserialize_visit(result.data[0])

    def update_visit_by_external_event_id(self, external_event_id: str, updates: dict) -> Visit | None:
        serialized = {}
        for k, v in updates.items():
            if isinstance(v, datetime):
                serialized[k] = v.isoformat()
            else:
                serialized[k] = v

        result = self.client.table("visits").update(serialized).eq("external_event_id", external_event_id).execute()
        if not result.data:
            return None
        return _deserialize_visit(result.data[0])

    def list_visits_by_building(self, building_id: str, status: VisitStatus | None = None) -> list[Visit]:
        query = self.client.table("visits").select("*").eq("building_id", building_id)
        if status:
            query = query.eq("status", status.value)
        result = query.execute()
        return [_deserialize_visit(r) for r in result.data]

    def list_active_visits(self) -> list[Visit]:
        ACTIVE_STATUSES = {
            VisitStatus.CREATED.value,
            VisitStatus.ARRIVED.value,
            VisitStatus.REGISTERED.value,
            VisitStatus.APPROVED.value,
            VisitStatus.ACTIVE.value,
        }
        result = self.client.table("visits").select("*").in_("status", list(ACTIVE_STATUSES)).execute()
        return [_deserialize_visit(r) for r in result.data]


class BuildingMapRepository:
    """Repository for BuildingMap records — JSON file store."""

    def __init__(self) -> None:
        self._client = None
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def client(self):
        if self._client is None:
            from app.database.supabase_client import get_supabase_client

            self._client = get_supabase_client()
        return self._client

    def _read_store(self) -> dict:
        if not DATA_DIR.exists():
            return {"building_maps": []}
        try:
            with open(DATA_DIR / "building_map_store.json") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {"building_maps": []}

    def _write_store(self, store: dict) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path = DATA_DIR / "building_map_store.json"
        with tempfile.NamedTemporaryFile(mode="w", dir=str(DATA_DIR), delete=False) as tmp:
            json.dump(store, tmp, indent=2, default=str)
            tmp_path = Path(tmp.name)
        shutil.move(str(tmp_path), str(path))

    def _with_lock(self, func):
        lock = FileLock(DATA_DIR / "building_map_store.lock", timeout=10)
        with lock:
            return func()

    def create_building_map(self, mapping: BuildingMap) -> BuildingMap:
        def _create():
            store = self._read_store()
            existing = {bm["outlook_location_string"] for bm in store["building_maps"]}
            if mapping.outlook_location_string in existing:
                raise ValueError(f"BuildingMap '{mapping.outlook_location_string}' already exists")
            store["building_maps"].append(_serialize_building_map(mapping))
            self._write_store(store)
            return mapping

        return self._with_lock(_create)

    def get_building_map_by_outlook_location(self, location: str) -> BuildingMap | None:
        def _get():
            store = self._read_store()
            loc_lower = location.lower()
            for bm in store["building_maps"]:
                if bm["outlook_location_string"].lower() == loc_lower:
                    return _deserialize_building_map(bm)
            return None

        return self._with_lock(_get)

    def list_building_maps(self) -> list[BuildingMap]:
        def _list():
            store = self._read_store()
            return [_deserialize_building_map(bm) for bm in store["building_maps"]]

        return self._with_lock(_list)

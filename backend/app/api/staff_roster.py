"""Staff roster API for Sentry Staff bot onboarding.

The roster is the canonical staff identity source for Staff bot first-use
registration. Channel-specific IDs live in bot_users or future channel binding
tables after a staff member registers.
"""

from __future__ import annotations

import csv
import io
import logging
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.database.supabase_client import get_supabase_client
from app.middleware.auth_middleware import require_role
from app.models.auth import AuthContext, SentinelRole

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings/staff-roster", tags=["staff-roster"])

REQUIRED_CSV_COLUMNS = {"staff_number", "name", "email", "phone", "desk"}
CONNECTOR_KEY = "staff_roster_connector"


class StaffRosterCreate(BaseModel):
    staff_number: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    email: str = Field(..., min_length=1)
    phone: str = Field(..., min_length=1)
    desk: str = Field(..., min_length=1)
    site_id: str = "site-002"
    active: bool = True
    source: str = "manual"


class StaffRosterUpdate(BaseModel):
    staff_number: str | None = None
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    desk: str | None = None
    site_id: str | None = None
    active: bool | None = None
    source: str | None = None


class StaffRosterConnectorSettings(BaseModel):
    enabled: bool = False
    source_type: str = "csv"
    endpoint_url: str | None = None
    sync_cadence: str = "manual"
    last_sync_at: str | None = None
    notes: str | None = None


def _client():
    try:
        return get_supabase_client()
    except Exception as exc:
        logger.error("Supabase client unavailable for staff roster: %s", exc)
        raise HTTPException(status_code=503, detail="Database client unavailable") from exc


def _normalise_row(row: dict[str, Any], default_site_id: str, source: str) -> dict[str, Any]:
    active_raw = str(row.get("active", "true")).strip().lower()
    return {
        "staff_number": str(row.get("staff_number", "")).strip(),
        "name": str(row.get("name", "")).strip(),
        "email": str(row.get("email", "")).strip(),
        "phone": str(row.get("phone", "")).strip(),
        "desk": str(row.get("desk", "")).strip(),
        "site_id": str(row.get("site_id") or default_site_id).strip(),
        "active": active_raw not in {"0", "false", "no", "inactive"},
        "source": source,
    }


def _validate_record(record: dict[str, Any], row_number: int | None = None) -> str | None:
    missing = [field for field in REQUIRED_CSV_COLUMNS if not record.get(field)]
    if missing:
        prefix = f"row {row_number}: " if row_number else ""
        return f"{prefix}missing {', '.join(sorted(missing))}"
    return None


@router.get("")
async def list_staff_roster(
    site_id: str | None = None,
    include_inactive: bool = False,
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN, SentinelRole.OPERATOR)),
) -> dict[str, Any]:
    client = _client()
    query = client.table("staff_roster").select("*").order("name")
    if site_id:
        query = query.eq("site_id", site_id)
    if not include_inactive:
        query = query.eq("active", True)
    result = query.execute()
    members = result.data or []
    return {"members": members, "count": len(members)}


@router.post("")
async def upsert_staff_member(
    body: StaffRosterCreate,
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN)),
) -> dict[str, Any]:
    client = _client()
    record = _normalise_row(body.model_dump(), body.site_id, body.source)
    error = _validate_record(record)
    if error:
        raise HTTPException(status_code=422, detail=error)

    result = client.table("staff_roster").upsert(record, on_conflict="site_id,staff_number").execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to save staff member")
    return {"member": result.data[0], "success": True}


@router.put("/{member_id}")
async def update_staff_member(
    member_id: str,
    body: StaffRosterUpdate,
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN)),
) -> dict[str, Any]:
    client = _client()
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if not updates:
        result = client.table("staff_roster").select("*").eq("id", member_id).limit(1).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Staff member not found")
        return {"member": result.data[0], "success": True}

    result = client.table("staff_roster").update(updates).eq("id", member_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Staff member not found")
    return {"member": result.data[0], "success": True}


@router.delete("/{member_id}")
async def deactivate_staff_member(
    member_id: str,
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN)),
) -> dict[str, Any]:
    client = _client()
    result = client.table("staff_roster").update({"active": False}).eq("id", member_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Staff member not found")
    return {"success": True, "message": "Staff member deactivated"}


@router.post("/import")
async def import_staff_roster(
    site_id: str = "site-002",
    file: UploadFile = File(...),
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN)),
) -> dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a CSV file")

    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded") from exc

    reader = csv.DictReader(io.StringIO(text))
    headers = set(reader.fieldnames or [])
    missing_headers = REQUIRED_CSV_COLUMNS - headers
    if missing_headers:
        raise HTTPException(status_code=400, detail=f"Missing CSV columns: {', '.join(sorted(missing_headers))}")

    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for row_number, row in enumerate(reader, start=2):
        record = _normalise_row(row, site_id, "csv_import")
        error = _validate_record(record, row_number)
        if error:
            errors.append(error)
            continue
        rows.append(record)

    if not rows:
        return {"imported": 0, "skipped": len(errors), "errors": errors[:25]}

    client = _client()
    saved = client.table("staff_roster").upsert(rows, on_conflict="site_id,staff_number").execute()
    imported = len(saved.data or [])
    return {"imported": imported, "skipped": len(errors), "errors": errors[:25]}


@router.get("/connector/config")
async def get_connector_settings(
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN, SentinelRole.OPERATOR)),
) -> StaffRosterConnectorSettings:
    client = _client()
    result = client.table("system_settings").select("value").eq("key", CONNECTOR_KEY).limit(1).execute()
    if result.data:
        value = result.data[0].get("value") or {}
        if isinstance(value, dict):
            return StaffRosterConnectorSettings(**value)
    return StaffRosterConnectorSettings()


@router.put("/connector/config")
async def update_connector_settings(
    body: StaffRosterConnectorSettings,
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN)),
) -> StaffRosterConnectorSettings:
    client = _client()
    data = body.model_dump()
    client.table("system_settings").upsert(
        {
            "key": CONNECTOR_KEY,
            "value": data,
            "category": "staff",
            "description": "Staff roster connector settings for Sentry Staff bot onboarding",
            "data_type": "object",
            "is_public": False,
            "is_editable": True,
        },
        on_conflict="key",
    ).execute()
    return StaffRosterConnectorSettings(**data)

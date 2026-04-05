"""
Document sync API router — /api/documents/sync.

Triggers on-demand or scheduled sync for document source adapters.
Analogous to /api/maintenance/sync for maintenance adapters (Phase 178 pattern).

POST /sync — trigger sync for a specific adapter
GET /sync/status/{adapter} — get last sync state
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.middleware.auth_middleware import AuthLevel, require_auth
from app.models.document_source import SourceSystem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["document-sync"])


class SyncRequest(BaseModel):
    """Request body for POST /api/documents/sync."""

    adapter: str  # "manual_upload" | "concept_mri"
    site_id: str | None = None


class SyncResponse(BaseModel):
    """Response for sync operations."""

    synced: int = 0
    failed: int = 0
    errors: list[str] = []


class SyncStatusResponse(BaseModel):
    """Response for GET /api/documents/sync/status/{adapter}."""

    last_sync: datetime | None = None
    records: int = 0
    status: str = "ok"  # "ok" | "error"


def _load_adapter(adapter_name: str):
    """Load the appropriate document adapter by name."""
    if adapter_name == "concept_mri":
        from app.services.document_adapter_mri import ConceptMRIAdapter

        return ConceptMRIAdapter()
    elif adapter_name == "manual_upload":
        from app.services.document_adapter_manual import ManualUploadAdapter

        return ManualUploadAdapter()
    else:
        raise ValueError(f"Unknown adapter: {adapter_name}")


@router.post("/sync", response_model=SyncResponse)
async def trigger_sync(
    request: SyncRequest,
    auth=Depends(require_auth(AuthLevel.AUTHENTICATED)),
) -> SyncResponse:
    """
    Trigger a document sync for the specified adapter.

    Calls adapter.run_sync() and returns counts of synced/failed records.
    """
    try:
        adapter = _load_adapter(request.adapter)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        result = await adapter.run_sync(site_id=request.site_id)
        return SyncResponse(
            synced=result.get("ingested", 0),
            failed=result.get("errors", 0),
            errors=[],
        )
    except Exception as e:
        logger.exception("[document_sync] Sync failed for adapter=%s", request.adapter)
        return SyncResponse(synced=0, failed=1, errors=[str(e)])


@router.get("/sync/status/{adapter}", response_model=SyncStatusResponse)
async def sync_status(
    adapter: str,
    auth=Depends(require_auth(AuthLevel.AUTHENTICATED)),
) -> SyncStatusResponse:
    """
    Get the last sync state for the specified adapter.

    Returns last_sync datetime, record count, and status.
    """
    try:
        source = SourceSystem(adapter)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown adapter: {adapter}") from None

    from app.database.supabase_client import get_supabase_client

    db = get_supabase_client()
    result = db.table("document_connector_sync").select("*").eq("adapter_source", source.value).execute()

    if not result.data:
        return SyncStatusResponse(last_sync=None, records=0, status="ok")

    row = result.data[0]
    last_sync = None
    if row.get("last_successful_sync"):
        try:
            last_sync = datetime.fromisoformat(row["last_successful_sync"])
        except (ValueError, TypeError):
            pass

    return SyncStatusResponse(
        last_sync=last_sync,
        records=row.get("records_ingested", 0) + row.get("records_updated", 0),
        status="error" if row.get("errors", 0) > 0 else "ok",
    )

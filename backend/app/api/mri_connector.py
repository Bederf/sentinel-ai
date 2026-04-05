"""MRI Evolution connector API routes."""

from __future__ import annotations

import json
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, Field

from app.middleware.auth_middleware import AuthLevel, require_auth
from app.services.maintenance_adapter_mri import MRIEvolutionAdapter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


class SyncResponse(BaseModel):
    ingested: int = 0
    updated: int = 0
    errors: int = 0
    status: str = "completed"


class WebhookPayload(BaseModel):
    task_id: str = Field(..., description="MRI Evolution TaskId")
    event_type: str = Field(..., description="created | updated | closed")
    payload: dict = Field(default_factory=dict)


@router.post("/sync", response_model=SyncResponse)
async def trigger_sync(
    background_tasks: BackgroundTasks,
    site_id: str | None = None,
    auth=Depends(require_auth(AuthLevel.AUTHENTICATED)),
) -> SyncResponse:
    """Manually trigger a sync from MRI Evolution (auth required)."""
    service = MRIEvolutionAdapter()
    result = await service.run_sync(site_id=site_id)
    errors = result.get("errors", 0)
    status = "completed" if errors == 0 else "completed_with_errors"
    return SyncResponse(**result, status=status)


@router.post("/webhook")
async def receive_webhook(request: Request) -> dict:
    """
    Webhook receiver for MRI Evolution push events.

    Register URL with MRI Evolution when vendor confirms webhook support:
    POST https://{your-domain}/api/mri-connector/webhook

    No auth — MRI Evolution cannot send Bearer tokens.
    Replace basic JSON parse with actual signature verification
    once vendor provides HMAC key.
    """
    body = await request.body()

    try:
        data = json.loads(body)
    except Exception:
        return {"status": "error", "message": "Invalid JSON"}

    task_id = data.get("TaskId", "")
    event_type = data.get("event_type", "updated")

    service = MRIEvolutionAdapter()
    event = service.normalise(data)
    service._upsert(event)
    service._check_sla_breach(event)

    return {"status": "received", "task_id": task_id, "event_type": event_type}


@router.get("/status")
async def sync_status(
    site_id: str | None = None,
    auth=Depends(require_auth(AuthLevel.AUTHENTICATED)),
) -> dict:
    """Return last sync state for a site."""
    from app.database.supabase_client import get_supabase_client

    db = get_supabase_client()
    query = db.table("maintenance_connector_sync").select("*")
    if site_id:
        query = query.eq("site_id", site_id)
    result = query.execute()
    return {"sync_records": result.data}


# === APScheduler singleton (mirrors BackgroundSchedulerService pattern) ===
_scheduler: AsyncIOScheduler | None = None


def start_scheduler() -> None:
    """Start the MRI Evolution polling scheduler. Call from startup/events.py."""
    from app.config.settings import settings

    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        MRIEvolutionAdapter().run_sync,
        "interval",
        minutes=settings.mri_poll_interval_minutes,
        id="mri_evolution_poll",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("MRI Evolution polling scheduler started (every %d minutes)", settings.mri_poll_interval_minutes)


def stop_scheduler() -> None:
    """Stop the MRI Evolution polling scheduler. Call from shutdown/events.py."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("MRI Evolution polling scheduler stopped")

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from apscheduler.triggers.interval import IntervalTrigger

from app.services.background_scheduler import scheduler_service
from app.services.eskomsepush_service import EskomSePushService

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 1800  # 30 min — shared across all sites in same area


@dataclass
class AreaSchedule:
    area_id: str
    stage: int | None
    next_slot_start: datetime | None
    next_slot_end: datetime | None
    fetched_at: datetime
    is_stale: bool = False


# Shared cache: one entry per unique area_id, shared by all sites in that area
_area_cache: dict[str, AreaSchedule] = {}
_esp_service = EskomSePushService()


def get_area_schedule(area_id: str) -> AreaSchedule | None:
    return _area_cache.get(area_id)


async def validate_area_code(area_id: str) -> bool:
    """Return True if area_id exists in EskomSePush. Used during onboarding."""
    if not _esp_service.is_configured():
        return True  # can't validate without API key — allow and warn
    try:
        results = await _esp_service.search_areas(area_id)
        return any(r.get("id") == area_id for r in results)
    except Exception as exc:
        logger.warning("Area code validation failed for %s: %s", area_id, exc)
        return True  # fail-open during onboarding


def _fetch_area_sync(area_id: str) -> None:
    """Sync wrapper for APScheduler — fetches and caches one area's schedule."""
    import asyncio

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_fetch_area_async(area_id))
    finally:
        loop.close()


async def _fetch_area_async(area_id: str) -> None:
    if not _esp_service.is_configured():
        logger.debug("EskomSePush not configured — skipping area poll for %s", area_id)
        return

    try:
        data = await _esp_service.get_area_information(area_id)
        events = data.get("events", [])
        stage = data.get("info", {}).get("stage")

        next_start: datetime | None = None
        next_end: datetime | None = None
        if events:
            try:
                next_start = datetime.fromisoformat(events[0]["start"].replace("Z", "+00:00"))
                next_end = datetime.fromisoformat(events[0]["end"].replace("Z", "+00:00"))
            except (KeyError, ValueError):
                pass

        _area_cache[area_id] = AreaSchedule(
            area_id=area_id,
            stage=int(stage) if stage is not None else None,
            next_slot_start=next_start,
            next_slot_end=next_end,
            fetched_at=datetime.utcnow(),
            is_stale=False,
        )
        logger.debug("EskomSePush cache updated for %s — stage=%s", area_id, stage)

    except Exception as exc:
        logger.warning("EskomSePush fetch failed for %s: %s", area_id, exc)
        if area_id in _area_cache:
            _area_cache[area_id].is_stale = True
        else:
            # First fetch failed — create a null stale entry so callers know we tried
            _area_cache[area_id] = AreaSchedule(
                area_id=area_id,
                stage=None,
                next_slot_start=None,
                next_slot_end=None,
                fetched_at=datetime.utcnow(),
                is_stale=True,
            )


def register_area_poller(area_id: str) -> None:
    """Register a shared 30-min polling job for area_id. Idempotent."""
    if not area_id:
        return

    job_id = f"eskomsepush_poll_{area_id}"
    if scheduler_service.scheduler.get_job(job_id):
        return  # already registered

    scheduler_service.scheduler.add_job(
        func=_fetch_area_sync,
        args=[area_id],
        trigger=IntervalTrigger(seconds=_POLL_INTERVAL_SECONDS),
        id=job_id,
        name=f"EskomSePush poll — {area_id}",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.utcnow(),  # fetch immediately on registration
    )
    logger.info("Registered EskomSePush poller for area %s", area_id)


def unregister_area_poller_if_unused(area_id: str, remaining_site_ids: list[str]) -> None:
    """Remove area poller only if no active sites remain in that area."""
    if not area_id or remaining_site_ids:
        return
    job_id = f"eskomsepush_poll_{area_id}"
    if scheduler_service.scheduler.get_job(job_id):
        scheduler_service.scheduler.remove_job(job_id)
        _area_cache.pop(area_id, None)
        logger.info("Removed EskomSePush poller for area %s (no remaining sites)", area_id)

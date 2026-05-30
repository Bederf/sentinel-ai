from __future__ import annotations

import asyncio
import logging

from apscheduler.triggers.interval import IntervalTrigger

from app.adapters.residential.base import ResidentialEnergyAdapter
from app.services.background_scheduler import scheduler_service
from app.services.residential.cloud_mqtt_bridge import get_cloud_bridge

logger = logging.getLogger(__name__)

_JOB_ID_PREFIX = "residential_poll_"


def _make_job_id(site_id: str) -> str:
    return f"{_JOB_ID_PREFIX}{site_id}"


def _poll_site_sync(site_id: str) -> None:
    """Sync APScheduler wrapper — runs async poll in a fresh event loop per thread."""
    bridge = get_cloud_bridge()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(bridge.poll_site(site_id))
    finally:
        loop.close()


def add_residential_polling_job(
    site_id: str,
    adapter: ResidentialEnergyAdapter,
    interval_seconds: int = 300,
) -> None:
    """Register adapter and schedule periodic MQTT polling for a residential site."""
    bridge = get_cloud_bridge()
    bridge.register_site(site_id, adapter)

    job_id = _make_job_id(site_id)
    if scheduler_service.scheduler.get_job(job_id):
        scheduler_service.scheduler.remove_job(job_id)

    scheduler_service.scheduler.add_job(
        func=_poll_site_sync,
        args=[site_id],
        trigger=IntervalTrigger(seconds=interval_seconds),
        id=job_id,
        name=f"Residential MQTT poll — {site_id}",
        replace_existing=True,
        max_instances=1,  # prevent overlapping cycles; threading.Lock in adapter handles concurrent callers
        coalesce=True,    # skip missed fires rather than stacking them
    )
    logger.info("Scheduled residential polling for %s every %ds", site_id, interval_seconds)


def remove_residential_polling_job(site_id: str) -> None:
    """Remove polling job and unregister adapter for a deactivated site."""
    job_id = _make_job_id(site_id)
    if scheduler_service.scheduler.get_job(job_id):
        scheduler_service.scheduler.remove_job(job_id)

    get_cloud_bridge().unregister_site(site_id)
    logger.info("Removed residential polling for %s", site_id)

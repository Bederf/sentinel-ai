from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from app.adapters.residential.base import ResidentialEnergyAdapter
from app.services.background_scheduler import scheduler_service
from app.services.residential.cloud_mqtt_bridge import get_cloud_bridge

if TYPE_CHECKING:
    from app.gateways.home_assistant import HomeAssistantGateway

logger = logging.getLogger(__name__)

_JOB_ID_PREFIX = "residential_poll_"

# Active HA gateways — keyed by site_id
_ha_gateways: dict[str, HomeAssistantGateway] = {}


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
        max_instances=1,
        coalesce=True,
    )
    logger.info("Scheduled residential polling for %s every %ds", site_id, interval_seconds)


def remove_residential_polling_job(site_id: str) -> None:
    """Remove polling job and unregister adapter for a deactivated site."""
    job_id = _make_job_id(site_id)
    if scheduler_service.scheduler.get_job(job_id):
        scheduler_service.scheduler.remove_job(job_id)

    get_cloud_bridge().unregister_site(site_id)
    logger.info("Removed residential polling for %s", site_id)


# ── HA SIMBIOT Gateway management ────────────────────────────────────────────────


def start_ha_gateway(site_id: str, config: dict) -> HomeAssistantGateway:
    """
    Start a HomeAssistantGateway for a residential site.

    Called after HA site is onboarded. Creates the gateway,
    connects to Mosquitto, subscribes to HA entity topics.
    No APScheduler polling job is created — HA is an MQTT subscriber.
    """
    from app.gateways.home_assistant import HomeAssistantGateway

    # Stop existing gateway if re-onboarding
    if site_id in _ha_gateways:
        stop_ha_gateway(site_id)

    gateway = HomeAssistantGateway(site_id, config)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        connected = loop.run_until_complete(gateway.connect())
        if connected:
            loop.run_until_complete(gateway.subscribe())
            _ha_gateways[site_id] = gateway
            logger.info("HA gateway started for %s", site_id)
        else:
            logger.warning("HA gateway connect failed for %s", site_id)
    finally:
        loop.close()

    return gateway


def stop_ha_gateway(site_id: str) -> None:
    """Stop and clean up a HA gateway for a site."""
    gateway = _ha_gateways.pop(site_id, None)
    if gateway is None:
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(gateway.disconnect())
    except Exception as exc:
        logger.warning("HA gateway disconnect error for %s: %s", site_id, exc)
    finally:
        loop.close()

    logger.info("HA gateway stopped for %s", site_id)


def get_ha_gateway(site_id: str) -> HomeAssistantGateway | None:
    """Get the active HA gateway for a site, or None."""
    return _ha_gateways.get(site_id)


# ── Residential AI Recommendation Scheduler ────────────────────────────────────────

_REC_JOB_PREFIX = "res_rec_"


def _rec_job_id(site_id: str) -> str:
    return f"{_REC_JOB_PREFIX}{site_id}"


def _run_recommendation_sync(site_id: str) -> None:
    """Sync APScheduler wrapper — runs async recommendation cycle."""
    from app.services.residential.residential_recommendation_service import (
        ResidentialRecommendationService,
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        svc = ResidentialRecommendationService()
        loop.run_until_complete(svc.process_site(site_id))
    finally:
        loop.close()


def _get_recommendation_interval(
    site_id: str,
    soc: float | None,
    ls_stage: int,
    minutes_to_slot: int | None,
) -> int:
    """Return recommendation check interval in minutes.

    Rules:
    - SOC < 30% and loadshedding active: 30min
    - Within 2h of shed slot: 30min
    - Otherwise: 120min
    """
    if soc is not None and soc < 30 and ls_stage > 0:
        return 30
    if minutes_to_slot is not None and minutes_to_slot < 120:
        return 30
    return 120


def schedule_residential_recommendations(site_id: str) -> None:
    """Schedule or update the AI recommendation job for a residential site.

    Called when a residential site is activated. Uses dynamic interval
    based on battery SOC and loadshedding stage.
    Job_id is namespaced to avoid collision with polling jobs.
    """
    from app.services.residential.eskomsepush_client import get_area_schedule

    # Get current SOC and loadshedding to set initial interval
    try:
        supabase = __import__("app.database.supabase_client", fromlist=["get_supabase_client"]).get_supabase_client()
        row = supabase.table("residential_sites").select("eskom_area_code").eq("site_id", site_id).maybe_execute()
        area_code = row.data[0].get("eskom_area_code") if row.data else None
    except Exception:
        area_code = None

    soc = None
    ls_stage = 0
    minutes_to_slot = None

    if area_code:
        sched = get_area_schedule(area_code)
        if sched:
            ls_stage = sched.stage or 0
            if sched.next_slot_start:
                delta = (sched.next_slot_start - datetime.now(UTC)).total_seconds()
                minutes_to_slot = max(0, int(delta / 60))

    interval_minutes = _get_recommendation_interval(site_id, soc, ls_stage, minutes_to_slot)
    job_id = _rec_job_id(site_id)

    if scheduler_service.scheduler.get_job(job_id):
        scheduler_service.scheduler.remove_job(job_id)

    scheduler_service.scheduler.add_job(
        func=_run_recommendation_sync,
        args=[site_id],
        trigger=IntervalTrigger(minutes=interval_minutes),
        id=job_id,
        name=f"Residential AI recs — {site_id}",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    logger.info(
        "Scheduled residential recommendations for %s every %dmin",
        site_id,
        interval_minutes,
    )


def cancel_residential_recommendations(site_id: str) -> None:
    """Remove recommendation job for a deactivated site."""
    job_id = _rec_job_id(site_id)
    if scheduler_service.scheduler.get_job(job_id):
        scheduler_service.scheduler.remove_job(job_id)
        logger.info("Cancelled residential recommendations for %s", site_id)


# ── Morning Summary Scheduler ─────────────────────────────────────────────────

_MORNING_JOB_PREFIX = "morning:"


def _morning_job_id(site_id: str) -> str:
    return f"{_MORNING_JOB_PREFIX}{site_id}"


def _run_morning_summary_sync(site_id: str) -> None:
    from app.services.residential.morning_summary_service import MorningSummaryService

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        svc = MorningSummaryService()
        loop.run_until_complete(svc.send_summary(site_id))
    finally:
        loop.close()


def schedule_morning_summary(site_id: str) -> None:
    """Schedule daily 07:00 SAST morning summary for a residential site."""
    job_id = _morning_job_id(site_id)
    if scheduler_service.scheduler.get_job(job_id):
        scheduler_service.scheduler.remove_job(job_id)
    scheduler_service.scheduler.add_job(
        func=_run_morning_summary_sync,
        args=[site_id],
        trigger=CronTrigger(hour=7, minute=0, timezone="Africa/Johannesburg"),
        id=job_id,
        name=f"Morning summary — {site_id}",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    logger.info("Scheduled morning summary for %s at 07:00 SAST", site_id)


def cancel_morning_summary(site_id: str) -> None:
    job_id = _morning_job_id(site_id)
    if scheduler_service.scheduler.get_job(job_id):
        scheduler_service.scheduler.remove_job(job_id)
        logger.info("Cancelled morning summary for %s", site_id)

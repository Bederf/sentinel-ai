"""Debug endpoints for non-production environments."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException

from app.config.settings import settings

router = APIRouter()


@router.get("/debug/energy-accum")
async def get_energy_accumulator_state() -> dict:
    """Inspect ShadowModePollingService energy accumulator state.

    Only available in non-production environments.
    Useful for verifying accumulation is running after service restart
    and confirming when the next hourly flush will fire.
    """
    if settings.environment == "production":
        raise HTTPException(status_code=404, detail="Not found")

    try:
        from app.services.shadow_mode_polling import get_shadow_mode_polling_service

        svc = get_shadow_mode_polling_service()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service not initialized: {e}")

    now = datetime.now(UTC)
    next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    next_flush_in_minutes = round((next_hour - now).total_seconds() / 60, 1)

    return {
        "poll_count": svc._poll_count,
        "energy_accumulator": svc._energy_accumulator,
        "energy_accum_start": svc._energy_accum_start.isoformat() if svc._energy_accum_start else None,
        "energy_last_poll": svc._energy_last_poll.isoformat() if svc._energy_last_poll else None,
        "current_hour_utc": now.replace(minute=0, second=0, microsecond=0).isoformat(),
        "next_flush_in_minutes": next_flush_in_minutes,
        "object_catalog_size": len(svc._object_catalog),
        "trends_sensor_count": len(svc._trends_sensor_codes),
        "last_poll_result": getattr(svc, "_last_poll_result", None),
        "accumulated_kwh": round(sum(svc._energy_accumulator.values()), 3),
    }


@router.get("/debug/health-snapshot/status")
async def get_health_snapshot_status() -> dict:
    """Check APScheduler job status for equipment health snapshots."""
    if settings.environment == "production":
        raise HTTPException(status_code=404, detail="Not found")

    try:
        from app.services.background_scheduler import BackgroundSchedulerService
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Scheduler not initialized: {e}")

    svc = BackgroundSchedulerService()
    scheduler = svc.scheduler

    health_job = scheduler.get_job("equipment_health_snapshot")
    health_initial = scheduler.get_job("equipment_health_snapshot_initial")

    return {
        "equipment_health_snapshot": {
            "registered": health_job is not None,
            "next_run": health_job.next_run_time.isoformat() if health_job else None,
            "pending": health_job.pending if health_job else None,
        }
        if health_job
        else None,
        "equipment_health_snapshot_initial": {
            "registered": health_initial is not None,
            "next_run": health_initial.next_run_time.isoformat() if health_initial else None,
            "pending": health_initial.pending if health_initial else None,
        }
        if health_initial
        else None,
        "all_jobs": [
            {
                "id": j.id,
                "name": j.name,
                "next_run": j.next_run_time.isoformat() if j.next_run_time else None,
                "pending": j.pending,
            }
            for j in scheduler.get_jobs()
        ],
    }


@router.post("/debug/health-snapshot/trigger")
async def trigger_health_snapshot() -> dict:
    """Manually trigger equipment health snapshot recompute for all sites."""
    if settings.environment == "production":
        raise HTTPException(status_code=404, detail="Not found")

    try:
        import asyncio

        from app.services.background_scheduler import BackgroundSchedulerService
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Scheduler not initialized: {e}")

    svc = BackgroundSchedulerService()
    try:
        if svc._main_loop and svc._main_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                svc._run_equipment_health_snapshot_async(),
                svc._main_loop,
            )
            future.result(timeout=300)
        else:
            asyncio.run(svc._run_equipment_health_snapshot_async())
        return {"status": "triggered"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug/energy-accum/poll")
async def trigger_energy_poll() -> dict:
    """Trigger a shadow mode poll and return energy accumulator state after.

    Useful for forcing an immediate poll cycle to verify accumulation is working.
    """
    if settings.environment == "production":
        raise HTTPException(status_code=404, detail="Not found")

    try:

        from app.services.shadow_mode_polling import get_shadow_mode_polling_service

        svc = get_shadow_mode_polling_service()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service not initialized: {e}")

    result = await svc.poll()
    _ = result.get("errors", [])

    now = datetime.now(UTC)
    next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    next_flush_in_minutes = round((next_hour - now).total_seconds() / 60, 1)

    return {
        "poll_count": svc._poll_count,
        "energy_accumulator": svc._energy_accumulator,
        "energy_accum_start": svc._energy_accum_start.isoformat() if svc._energy_accum_start else None,
        "energy_last_poll": svc._energy_last_poll.isoformat() if svc._energy_last_poll else None,
        "current_hour_utc": now.replace(minute=0, second=0, microsecond=0).isoformat(),
        "next_flush_in_minutes": next_flush_in_minutes,
        "object_catalog_size": len(svc._object_catalog),
        "trends_sensor_count": len(svc._trends_sensor_codes),
        "last_poll_result": getattr(svc, "_last_poll_result", None),
        "accumulated_kwh": round(sum(svc._energy_accumulator.values()), 3),
    }

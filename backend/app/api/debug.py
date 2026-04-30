"""Debug endpoints for non-production environments."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException

from app.config.settings import settings
from app.services.shadow_mode_polling import get_shadow_mode_polling_service

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
    }

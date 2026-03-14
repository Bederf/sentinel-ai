"""
Building Operating Schedule API
================================
Configurable per-site operating hours, replacing hardcoded SiteSchedule defaults.
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.middleware.auth_middleware import require_site_access, require_role
from app.models.auth import AuthContext, SentinelRole

logger = logging.getLogger(__name__)
router = APIRouter(tags=["building-schedule"])

DATA_PATH = Path(__file__).parent.parent / "data" / "buildings"

# Default operating hours (Site 002 pattern)
DEFAULT_SCHEDULE = {
    "monday": {"start_time": "06:00", "end_time": "18:00", "pre_cool_minutes": 60, "is_operational": True},
    "tuesday": {"start_time": "06:00", "end_time": "18:00", "pre_cool_minutes": 60, "is_operational": True},
    "wednesday": {"start_time": "06:00", "end_time": "18:00", "pre_cool_minutes": 60, "is_operational": True},
    "thursday": {"start_time": "06:00", "end_time": "18:00", "pre_cool_minutes": 60, "is_operational": True},
    "friday": {"start_time": "06:00", "end_time": "18:00", "pre_cool_minutes": 60, "is_operational": True},
    "saturday": {"start_time": "00:00", "end_time": "00:00", "pre_cool_minutes": 0, "is_operational": False},
    "sunday": {"start_time": "00:00", "end_time": "00:00", "pre_cool_minutes": 0, "is_operational": False},
}


class DaySchedule(BaseModel):
    start_time: str = "06:00"  # HH:MM
    end_time: str = "18:00"
    pre_cool_minutes: int = 60
    is_operational: bool = True


class WeekSchedule(BaseModel):
    monday: DaySchedule = DaySchedule()
    tuesday: DaySchedule = DaySchedule()
    wednesday: DaySchedule = DaySchedule()
    thursday: DaySchedule = DaySchedule()
    friday: DaySchedule = DaySchedule()
    saturday: DaySchedule = DaySchedule(start_time="00:00", end_time="00:00", pre_cool_minutes=0, is_operational=False)
    sunday: DaySchedule = DaySchedule(start_time="00:00", end_time="00:00", pre_cool_minutes=0, is_operational=False)


def _load_building_json(site_id: str) -> dict:
    """Load building.json for a site."""
    path = DATA_PATH / site_id / "building.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Building '{site_id}' not found")
    with open(path) as f:
        return json.load(f)


def _save_building_json(site_id: str, data: dict) -> None:
    """Save building.json for a site."""
    path = DATA_PATH / site_id / "building.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


@router.get("/api/buildings/{site_id}/schedule")
async def get_operating_schedule(
    site_id: str,
    auth: AuthContext = Depends(require_site_access("site_id")),
) -> dict:
    """Get per-day-of-week operating hours for a site."""
    building = _load_building_json(site_id)
    schedule = building.get("operating_schedule", DEFAULT_SCHEDULE)
    return {"site_id": site_id, "schedule": schedule}


@router.put("/api/buildings/{site_id}/schedule")
async def update_operating_schedule(
    site_id: str,
    schedule: WeekSchedule,
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN)),
) -> dict:
    """Update operating hours for each day of the week."""
    building = _load_building_json(site_id)
    schedule_dict = schedule.model_dump()
    building["operating_schedule"] = schedule_dict
    _save_building_json(site_id, building)

    # Emit audit event
    try:
        from app.services.audit_service import emit_audit_event

        await emit_audit_event(
            event_type="CONFIG_CHANGE",
            entity_type="building_schedule",
            entity_id=site_id,
            actor=auth.email if auth else "system",
            details={"schedule": schedule_dict},
        )
    except Exception as e:
        logger.warning(f"Failed to emit audit event: {e}")

    logger.info(f"Operating schedule updated for {site_id}")
    return {"status": "updated", "site_id": site_id, "schedule": schedule_dict}

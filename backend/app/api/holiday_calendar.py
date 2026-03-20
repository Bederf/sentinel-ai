"""
Holiday Calendar API
=====================
Manages public holidays and custom holidays per site.
Pre-seeded with SA public holidays.
"""

import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.middleware.auth_middleware import require_site_access, require_role
from app.models.auth import AuthContext, SentinelRole
from app.services.site_holiday_service import DATA_PATH, SA_PUBLIC_HOLIDAYS, get_site_holiday_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["holiday-calendar"])


class HolidayCreate(BaseModel):
    date: str  # YYYY-MM-DD for custom, MM-DD for recurring
    name: str
    recurring: bool = False


def _load_holidays(site_id: str) -> list:
    """Load holidays from building.json."""
    path = DATA_PATH / site_id / "building.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Building '{site_id}' not found")
    with open(path) as f:
        data = json.load(f)
    return data.get("holidays", [])


def _save_holidays(site_id: str, holidays: list) -> None:
    """Save holidays to building.json."""
    path = DATA_PATH / site_id / "building.json"
    with open(path) as f:
        data = json.load(f)
    data["holidays"] = holidays
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


@router.get("/api/buildings/{site_id}/holidays")
async def list_holidays(
    site_id: str,
    year: Optional[int] = None,
    auth: AuthContext = Depends(require_site_access("site_id")),
) -> dict:
    """List holidays for a site. Returns SA public holidays + custom holidays."""
    effective_holidays = get_site_holiday_service().list_holidays(site_id)

    # Build combined list
    all_holidays = []

    # Add SA public holidays with year prefix
    for h in SA_PUBLIC_HOLIDAYS:
        entry = {
            "id": f"sa-{h['date']}",
            "date": h["date"],
            "name": h["name"],
            "type": "public",
            "recurring": True,
            "editable": False,
        }
        all_holidays.append(entry)

    # Add custom holidays
    for h in effective_holidays:
        if h in SA_PUBLIC_HOLIDAYS:
            continue
        entry = {
            "id": h.get("id", str(uuid.uuid4())),
            "date": h["date"],
            "name": h["name"],
            "type": h.get("type", "custom"),
            "recurring": h.get("recurring", False),
            "editable": True,
        }
        all_holidays.append(entry)

    return {"site_id": site_id, "holidays": all_holidays, "count": len(all_holidays)}


@router.post("/api/buildings/{site_id}/holidays")
async def add_holiday(
    site_id: str,
    holiday: HolidayCreate,
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN)),
) -> dict:
    """Add a custom holiday."""
    custom_holidays = _load_holidays(site_id)

    new_holiday = {
        "id": str(uuid.uuid4()),
        "date": holiday.date,
        "name": holiday.name,
        "type": "custom",
        "recurring": holiday.recurring,
    }
    custom_holidays.append(new_holiday)
    _save_holidays(site_id, custom_holidays)

    logger.info(f"Added custom holiday for {site_id}: {holiday.name} on {holiday.date}")
    return {"status": "created", "holiday": new_holiday}


@router.delete("/api/buildings/{site_id}/holidays/{holiday_id}")
async def remove_holiday(
    site_id: str,
    holiday_id: str,
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN)),
) -> dict:
    """Remove a custom holiday. Cannot remove SA public holidays."""
    if holiday_id.startswith("sa-"):
        raise HTTPException(status_code=400, detail="Cannot remove SA public holidays")

    custom_holidays = _load_holidays(site_id)
    original_len = len(custom_holidays)
    custom_holidays = [h for h in custom_holidays if h.get("id") != holiday_id]

    if len(custom_holidays) == original_len:
        raise HTTPException(status_code=404, detail=f"Holiday '{holiday_id}' not found")

    _save_holidays(site_id, custom_holidays)
    logger.info(f"Removed holiday {holiday_id} from {site_id}")
    return {"status": "deleted", "holiday_id": holiday_id}

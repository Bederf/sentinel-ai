"""
Holiday Calendar API
=====================
Manages public holidays and custom holidays per site.
Pre-seeded with SA public holidays.
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.middleware.auth_middleware import require_site_access, require_role
from app.models.auth import AuthContext, SentinelRole

logger = logging.getLogger(__name__)
router = APIRouter(tags=["holiday-calendar"])

DATA_PATH = Path(__file__).parent.parent / "data" / "buildings"

# South African public holidays (recurring annually)
SA_PUBLIC_HOLIDAYS = [
    {"date": "01-01", "name": "New Year's Day", "type": "public", "recurring": True},
    {"date": "03-21", "name": "Human Rights Day", "type": "public", "recurring": True},
    {"date": "04-18", "name": "Good Friday", "type": "public", "recurring": True},
    {"date": "04-21", "name": "Family Day", "type": "public", "recurring": True},
    {"date": "04-27", "name": "Freedom Day", "type": "public", "recurring": True},
    {"date": "05-01", "name": "Workers' Day", "type": "public", "recurring": True},
    {"date": "06-16", "name": "Youth Day", "type": "public", "recurring": True},
    {"date": "08-09", "name": "National Women's Day", "type": "public", "recurring": True},
    {"date": "09-24", "name": "Heritage Day", "type": "public", "recurring": True},
    {"date": "12-16", "name": "Day of Reconciliation", "type": "public", "recurring": True},
    {"date": "12-25", "name": "Christmas Day", "type": "public", "recurring": True},
    {"date": "12-26", "name": "Day of Goodwill", "type": "public", "recurring": True},
]


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
    custom_holidays = _load_holidays(site_id)

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
    for h in custom_holidays:
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

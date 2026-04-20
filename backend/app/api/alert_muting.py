"""
Alert Muting API
=================
Per-equipment muting — suppress alerts for a given duration with reason tracking.
"""

import json
import logging
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.middleware.auth_middleware import require_role
from app.models.auth import AuthContext, SentinelRole

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/alert-muting", tags=["alert-muting"])

DATA_PATH = Path(__file__).parent.parent / "data"
MUTES_FILE = DATA_PATH / "alert_mutes.json"


class MuteCreate(BaseModel):
    reason: str
    duration_hours: int = 24  # Default 24h mute


def _load_mutes() -> list:
    if not MUTES_FILE.exists():
        return []
    try:
        with open(MUTES_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def _save_mutes(mutes: list) -> None:
    MUTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MUTES_FILE, "w") as f:
        json.dump(mutes, f, indent=2)


def _prune_expired(mutes: list) -> list:
    """Remove expired mutes."""
    now = datetime.utcnow().isoformat()
    return [m for m in mutes if m.get("muted_until", "") > now]


@router.get("")
async def list_active_mutes(
    site_id: str | None = None,
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN, SentinelRole.OPERATOR)),
) -> dict:
    """List all active (non-expired) equipment mutes."""
    mutes = _load_mutes()
    active = _prune_expired(mutes)
    if site_id:
        site_token = site_id.upper().replace("SITE-", "S")
        digits_match = re.search(r"(\d+)$", site_token)
        site_code = f"S{int(digits_match.group(1)):03d}" if digits_match else site_token
        active = [m for m in active if str(m.get("equipment_code", "")).upper().startswith(f"{site_code}-")]
    if len(active) != len(mutes):
        _save_mutes(_prune_expired(mutes))
    return {"mutes": active, "count": len(active)}


@router.post("/{equipment_code}")
async def mute_equipment(
    equipment_code: str,
    mute: MuteCreate,
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN)),
) -> dict:
    """Mute alerts for an equipment item."""
    mutes = _load_mutes()
    mutes = _prune_expired(mutes)

    # Check if already muted
    for m in mutes:
        if m["equipment_code"] == equipment_code:
            raise HTTPException(
                status_code=409,
                detail=f"Equipment '{equipment_code}' is already muted until {m['muted_until']}",
            )

    muted_until = (datetime.utcnow() + timedelta(hours=mute.duration_hours)).isoformat() + "Z"
    new_mute = {
        "id": str(uuid.uuid4()),
        "equipment_code": equipment_code,
        "reason": mute.reason,
        "duration_hours": mute.duration_hours,
        "muted_at": datetime.utcnow().isoformat() + "Z",
        "muted_until": muted_until,
        "muted_by": auth.email if auth else "system",
    }
    mutes.append(new_mute)
    _save_mutes(mutes)

    logger.info(f"Muted equipment {equipment_code} for {mute.duration_hours}h: {mute.reason}")
    return {"status": "muted", "mute": new_mute}


@router.delete("/{equipment_code}")
async def unmute_equipment(
    equipment_code: str,
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN)),
) -> dict:
    """Unmute an equipment item."""
    mutes = _load_mutes()
    original_len = len(mutes)
    mutes = [m for m in mutes if m["equipment_code"] != equipment_code]

    if len(mutes) == original_len:
        raise HTTPException(status_code=404, detail=f"No active mute for '{equipment_code}'")

    _save_mutes(mutes)
    logger.info(f"Unmuted equipment {equipment_code}")
    return {"status": "unmuted", "equipment_code": equipment_code}


def is_equipment_muted(equipment_code: str) -> bool:
    """Check if equipment is currently muted. Used by notification router."""
    mutes = _load_mutes()
    now = datetime.utcnow().isoformat()
    for m in mutes:
        if m["equipment_code"] == equipment_code and m.get("muted_until", "") > now:
            return True
    return False

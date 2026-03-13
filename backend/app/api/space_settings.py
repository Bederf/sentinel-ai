"""Space Optimization Settings API.

Endpoints for grace period configuration and concierge user CRUD.
Grace periods power the ghost booking detector and monitor.
Concierge users receive ghost booking notifications and confirm room status.

Security: GET endpoints require AUDITOR (level 1), mutations require ADMIN (level 4).
Phase 155: CONFIG_CHANGE audit events on all PUT/POST/DELETE endpoints.
"""

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.config.settings import settings as app_settings
from app.models.auth import AuthContext
from app.security.audit_events import audit_config_change
from app.security.pipeline import require_role
from app.services.concierge_store import (
    create_concierge,
    delete_concierge,
    list_concierges,
    update_concierge,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Path to space settings data file
DATA_DIR = Path(__file__).parent.parent / "data"
SPACE_SETTINGS_FILE = DATA_DIR / "space" / "space_settings.json"

# Default grace period settings (from config/settings.py)
DEFAULT_SPACE_SETTINGS: Dict[str, Any] = {
    "ghost_booking_grace_minutes": 15,
    "concierge_response_window_minutes": 15,
    "sensor_silence_threshold_minutes": 30,
    "right_sizing_grace_minutes": 20,
    "early_vacate_threshold_minutes": 90,
    "sporadic_use_threshold_pct": 25,
    "brief_occupation_threshold_min": 30,
}

# Valid setting keys and their allowed ranges
_SETTING_RANGES: Dict[str, tuple] = {
    "ghost_booking_grace_minutes": (1, 120),
    "concierge_response_window_minutes": (1, 120),
    "sensor_silence_threshold_minutes": (5, 240),
    "right_sizing_grace_minutes": (5, 120),
    "early_vacate_threshold_minutes": (15, 480),
    "sporadic_use_threshold_pct": (5, 95),
    "brief_occupation_threshold_min": (5, 180),
}


def _load_space_settings() -> Dict[str, Any]:
    """Load space settings from JSON file, falling back to defaults."""
    if SPACE_SETTINGS_FILE.exists():
        try:
            with open(SPACE_SETTINGS_FILE) as f:
                saved = json.load(f)
            # Merge with defaults (saved values take priority)
            result = {**DEFAULT_SPACE_SETTINGS, **saved}
            return result
        except (json.JSONDecodeError, OSError):
            pass

    # Fall back to app config values
    return {
        "ghost_booking_grace_minutes": app_settings.ghost_booking_grace_minutes,
        "concierge_response_window_minutes": app_settings.concierge_response_window_minutes,
        "sensor_silence_threshold_minutes": app_settings.sensor_silence_threshold_minutes,
        "right_sizing_grace_minutes": app_settings.right_sizing_grace_minutes,
        "early_vacate_threshold_minutes": app_settings.early_vacate_threshold_minutes,
        "sporadic_use_threshold_pct": app_settings.sporadic_use_threshold_pct,
        "brief_occupation_threshold_min": app_settings.brief_occupation_threshold_min,
    }


def _save_space_settings(data: Dict[str, Any]) -> None:
    """Save space settings to JSON file."""
    SPACE_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SPACE_SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_space_setting(key: str) -> Any:
    """Public helper: get a single space setting value for use by services."""
    loaded = _load_space_settings()
    return loaded.get(key, DEFAULT_SPACE_SETTINGS.get(key))


# ---------------------------------------------------------------------------
# Grace Period Settings
# ---------------------------------------------------------------------------


@router.get("/settings/space")
async def get_space_settings(auth: AuthContext = Depends(require_role(1))) -> Dict[str, Any]:
    """Get all space optimization settings including concierge list.

    Requires AUDITOR (level 1).
    """
    settings_data = _load_space_settings()
    concierges = list_concierges()
    settings_data["concierges"] = [asdict(c) for c in concierges]
    return settings_data


@router.put("/settings/space")
async def update_space_settings(
    body: Dict[str, Any],
    request: Request,
    auth: AuthContext = Depends(require_role(4)),
) -> Dict[str, Any]:
    """Update grace period settings. Requires ADMIN (level 4).

    Only accepts known grace period keys. Concierge data is managed
    via the dedicated concierge CRUD endpoints.
    """
    # Validate: only known setting keys
    for key in body:
        if key not in _SETTING_RANGES:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown setting: {key}. Valid keys: {', '.join(sorted(_SETTING_RANGES))}",
            )

    # Validate: values must be integers in allowed range
    for key, value in body.items():
        if not isinstance(value, (int, float)):
            raise HTTPException(status_code=400, detail=f"{key} must be a number")
        min_val, max_val = _SETTING_RANGES[key]
        if not (min_val <= value <= max_val):
            raise HTTPException(status_code=400, detail=f"{key} must be between {min_val} and {max_val}")

    # Merge with existing
    current = _load_space_settings()
    current.update(body)

    # Remove concierges key if present (managed separately)
    current.pop("concierges", None)

    _save_space_settings(current)

    # Audit
    source_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)
    audit_config_change("settings.space", user=auth.user_id, source_ip=source_ip)

    # Return full settings with concierges
    concierges = list_concierges()
    current["concierges"] = [asdict(c) for c in concierges]
    return current


# ---------------------------------------------------------------------------
# Concierge CRUD
# ---------------------------------------------------------------------------


@router.get("/settings/space/concierges")
async def list_concierges_endpoint(
    site_id: Optional[str] = Query(None, description="Filter by site ID"),
    auth: AuthContext = Depends(require_role(1)),
) -> List[Dict[str, Any]]:
    """List all concierge users. Requires AUDITOR (level 1)."""
    concierges = list_concierges(site_id=site_id)
    return [asdict(c) for c in concierges]


@router.post("/settings/space/concierges", status_code=201)
async def create_concierge_endpoint(
    body: Dict[str, Any],
    request: Request,
    auth: AuthContext = Depends(require_role(4)),
) -> Dict[str, Any]:
    """Create a new concierge user. Requires ADMIN (level 4)."""
    # Validate required fields
    if not body.get("name"):
        raise HTTPException(status_code=400, detail="name is required")
    if not body.get("site_id"):
        raise HTTPException(status_code=400, detail="site_id is required")

    concierge = create_concierge(body)

    # Audit
    source_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)
    audit_config_change("settings.space.concierge.create", user=auth.user_id, source_ip=source_ip)

    return asdict(concierge)


@router.put("/settings/space/concierges/{concierge_id}")
async def update_concierge_endpoint(
    concierge_id: str,
    body: Dict[str, Any],
    request: Request,
    auth: AuthContext = Depends(require_role(4)),
) -> Dict[str, Any]:
    """Update an existing concierge user. Requires ADMIN (level 4)."""
    updated = update_concierge(concierge_id, body)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Concierge {concierge_id} not found")

    # Audit
    source_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)
    audit_config_change("settings.space.concierge.update", user=auth.user_id, source_ip=source_ip)

    return asdict(updated)


@router.delete("/settings/space/concierges/{concierge_id}")
async def delete_concierge_endpoint(
    concierge_id: str,
    request: Request,
    auth: AuthContext = Depends(require_role(4)),
) -> Dict[str, str]:
    """Delete a concierge user. Requires ADMIN (level 4)."""
    deleted = delete_concierge(concierge_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Concierge {concierge_id} not found")

    # Audit
    source_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)
    audit_config_change("settings.space.concierge.delete", user=auth.user_id, source_ip=source_ip)

    return {"status": "deleted", "id": concierge_id}


# ---------------------------------------------------------------------------
# Site / Building / Floor Structure
# ---------------------------------------------------------------------------

SITE_STRUCTURE_FILE = DATA_DIR / "space" / "site_structure.json"


def _load_site_structure() -> List[Dict[str, Any]]:
    """Load site/building/floor structure from JSON config file."""
    if not SITE_STRUCTURE_FILE.exists():
        return []
    try:
        with open(SITE_STRUCTURE_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


@router.get("/settings/space/sites")
async def get_site_structure(
    auth: AuthContext = Depends(require_role(1)),
) -> List[Dict[str, Any]]:
    """Return site/building/floor structure for concierge assignment dropdowns.

    Requires AUDITOR (level 1).
    """
    return _load_site_structure()

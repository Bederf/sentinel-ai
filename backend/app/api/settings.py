"""Settings API - Global system configuration.

Security: GET endpoints require AUDITOR (level 1), PUT endpoints require ADMIN (level 4).
"""

import json
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.models.auth import AuthContext
from app.security.pipeline import require_role

router = APIRouter()

# Path to settings data file
DATA_DIR = Path(__file__).parent.parent / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"


def load_settings() -> Dict[str, Any]:
    """Load settings from JSON file."""
    if not SETTINGS_FILE.exists():
        # Create default settings if file doesn't exist
        default_settings = {
            "healthThresholds": {"healthy": 90, "warning": 70, "critical": 0},
            "notifications": {},
            "display": {},
        }
        save_settings(default_settings)
        return default_settings

    try:
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load settings: {str(e)}")


def save_settings(settings_data: Dict[str, Any]) -> None:
    """Save settings to JSON file."""
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings_data, f, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save settings: {str(e)}")


@router.get("/settings")
async def get_all_settings(auth: AuthContext = Depends(require_role(1))) -> Dict[str, Any]:
    """Get all settings. Requires AUDITOR (level 1)."""
    return load_settings()


@router.put("/settings")
async def update_all_settings(
    settings_data: Dict[str, Any],
    auth: AuthContext = Depends(require_role(4)),
) -> Dict[str, Any]:
    """Update all settings. Requires ADMIN (level 4)."""
    # Validate settings structure
    if "healthThresholds" in settings_data:
        thresholds = settings_data["healthThresholds"]
        if not isinstance(thresholds, dict):
            raise HTTPException(status_code=400, detail="healthThresholds must be an object")

        # Validate threshold values
        if "healthy" in thresholds and not isinstance(thresholds["healthy"], (int, float)):
            raise HTTPException(status_code=400, detail="healthy threshold must be a number")
        if "warning" in thresholds and not isinstance(thresholds["warning"], (int, float)):
            raise HTTPException(status_code=400, detail="warning threshold must be a number")
        if "critical" in thresholds and not isinstance(thresholds["critical"], (int, float)):
            raise HTTPException(status_code=400, detail="critical threshold must be a number")

        # Validate threshold ranges (0-100)
        for key in ["healthy", "warning", "critical"]:
            if key in thresholds:
                value = thresholds[key]
                if not (0 <= value <= 100):
                    raise HTTPException(status_code=400, detail=f"{key} threshold must be between 0 and 100")

        # Validate threshold ordering (healthy > warning > critical)
        if "healthy" in thresholds and "warning" in thresholds:
            if thresholds["healthy"] <= thresholds["warning"]:
                raise HTTPException(status_code=400, detail="healthy threshold must be greater than warning threshold")

    # Merge with existing settings
    current_settings = load_settings()
    current_settings.update(settings_data)

    # Save to file
    save_settings(current_settings)

    return current_settings


# Default notification settings (used when not configured)
DEFAULT_NOTIFICATION_SETTINGS = {
    "alertCommands": {
        "reset": {"enabled": True, "label": "Remote reset"},
        "info": {"enabled": True, "label": "More info"},
        "note": {"enabled": True, "label": "Add note"},
        "wo": {"enabled": True, "label": "Create work order"},
    },
    "alertCooldownMinutes": 5,
    "resetBlockedTypes": ["FIRE", "GEN"],
}

VALID_ALERT_COMMANDS = {"reset", "info", "note", "wo"}


@router.get("/settings/notifications")
async def get_notification_settings(auth: AuthContext = Depends(require_role(1))) -> Dict[str, Any]:
    """Get notification settings including alert command config. Requires AUDITOR (level 1)."""
    settings_data = load_settings()
    return settings_data.get("notifications", DEFAULT_NOTIFICATION_SETTINGS)


@router.put("/settings/notifications")
async def update_notification_settings(
    notifications: Dict[str, Any],
    auth: AuthContext = Depends(require_role(4)),
) -> Dict[str, Any]:
    """Update notification settings. Requires ADMIN (level 4).

    Validates alertCommands structure: each command must have 'enabled' (bool)
    and 'label' (str). Only known command keys are accepted.
    """
    # Validate alertCommands if provided
    if "alertCommands" in notifications:
        commands = notifications["alertCommands"]
        if not isinstance(commands, dict):
            raise HTTPException(status_code=400, detail="alertCommands must be an object")

        for key, config in commands.items():
            if key not in VALID_ALERT_COMMANDS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown alert command: {key}. Valid: {', '.join(sorted(VALID_ALERT_COMMANDS))}",
                )
            if not isinstance(config, dict):
                raise HTTPException(status_code=400, detail=f"alertCommands.{key} must be an object")
            if "enabled" in config and not isinstance(config["enabled"], bool):
                raise HTTPException(status_code=400, detail=f"alertCommands.{key}.enabled must be a boolean")
            if "label" in config and not isinstance(config["label"], str):
                raise HTTPException(status_code=400, detail=f"alertCommands.{key}.label must be a string")

    # Validate alertCooldownMinutes if provided
    if "alertCooldownMinutes" in notifications:
        cooldown = notifications["alertCooldownMinutes"]
        if not isinstance(cooldown, (int, float)) or cooldown < 1 or cooldown > 60:
            raise HTTPException(status_code=400, detail="alertCooldownMinutes must be a number between 1 and 60")

    # Validate resetBlockedTypes if provided
    if "resetBlockedTypes" in notifications:
        blocked = notifications["resetBlockedTypes"]
        if not isinstance(blocked, list) or not all(isinstance(t, str) for t in blocked):
            raise HTTPException(status_code=400, detail="resetBlockedTypes must be an array of strings")

    # Merge with existing settings
    current_settings = load_settings()
    current_notifications = current_settings.get("notifications", {})

    # Deep merge alertCommands
    if "alertCommands" in notifications and "alertCommands" in current_notifications:
        for key, config in notifications["alertCommands"].items():
            if key in current_notifications["alertCommands"]:
                current_notifications["alertCommands"][key].update(config)
            else:
                current_notifications["alertCommands"][key] = config
        notifications["alertCommands"] = current_notifications["alertCommands"]

    current_notifications.update(notifications)
    current_settings["notifications"] = current_notifications
    save_settings(current_settings)

    return current_notifications


@router.get("/settings/health-thresholds")
async def get_health_thresholds(auth: AuthContext = Depends(require_role(1))) -> Dict[str, int]:
    """Get health score thresholds. Requires AUDITOR (level 1)."""
    settings_data = load_settings()
    return settings_data.get("healthThresholds", {"healthy": 90, "warning": 70, "critical": 0})


@router.put("/settings/health-thresholds")
async def update_health_thresholds(
    thresholds: Dict[str, int],
    auth: AuthContext = Depends(require_role(4)),
) -> Dict[str, int]:
    """Update health score thresholds. Requires ADMIN (level 4)."""
    # Validate required fields
    required_fields = ["healthy", "warning", "critical"]
    for field in required_fields:
        if field not in thresholds:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    # Validate threshold values are numbers
    for field in required_fields:
        if not isinstance(thresholds[field], (int, float)):
            raise HTTPException(status_code=400, detail=f"{field} must be a number")

    # Validate threshold ranges (0-100)
    for field in required_fields:
        value = thresholds[field]
        if not (0 <= value <= 100):
            raise HTTPException(status_code=400, detail=f"{field} must be between 0 and 100")

    # Validate threshold ordering (healthy > warning > critical)
    if thresholds["healthy"] <= thresholds["warning"]:
        raise HTTPException(status_code=400, detail="healthy threshold must be greater than warning threshold")

    if thresholds["warning"] <= thresholds["critical"]:
        raise HTTPException(status_code=400, detail="warning threshold must be greater than critical threshold")

    # Load current settings and update thresholds
    current_settings = load_settings()
    current_settings["healthThresholds"] = thresholds

    # Save to file
    save_settings(current_settings)

    return thresholds

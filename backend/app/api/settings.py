"""Settings API - Global system configuration."""

import json
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

router = APIRouter()

# Path to settings data file
DATA_DIR = Path(__file__).parent.parent / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"


def load_settings() -> Dict[str, Any]:
    """Load settings from JSON file."""
    if not SETTINGS_FILE.exists():
        # Create default settings if file doesn't exist
        default_settings = {
            "healthThresholds": {
                "healthy": 90,
                "warning": 70,
                "critical": 0
            },
            "notifications": {},
            "display": {}
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
async def get_all_settings() -> Dict[str, Any]:
    """Get all settings."""
    return load_settings()


@router.put("/settings")
async def update_all_settings(settings_data: Dict[str, Any]) -> Dict[str, Any]:
    """Update all settings."""
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
                    raise HTTPException(
                        status_code=400,
                        detail=f"{key} threshold must be between 0 and 100"
                    )

        # Validate threshold ordering (healthy > warning > critical)
        if "healthy" in thresholds and "warning" in thresholds:
            if thresholds["healthy"] <= thresholds["warning"]:
                raise HTTPException(
                    status_code=400,
                    detail="healthy threshold must be greater than warning threshold"
                )

    # Merge with existing settings
    current_settings = load_settings()
    current_settings.update(settings_data)

    # Save to file
    save_settings(current_settings)

    return current_settings


@router.get("/settings/health-thresholds")
async def get_health_thresholds() -> Dict[str, int]:
    """Get health score thresholds."""
    settings_data = load_settings()
    return settings_data.get("healthThresholds", {
        "healthy": 90,
        "warning": 70,
        "critical": 0
    })


@router.put("/settings/health-thresholds")
async def update_health_thresholds(thresholds: Dict[str, int]) -> Dict[str, int]:
    """Update health score thresholds."""
    # Validate required fields
    required_fields = ["healthy", "warning", "critical"]
    for field in required_fields:
        if field not in thresholds:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required field: {field}"
            )

    # Validate threshold values are numbers
    for field in required_fields:
        if not isinstance(thresholds[field], (int, float)):
            raise HTTPException(
                status_code=400,
                detail=f"{field} must be a number"
            )

    # Validate threshold ranges (0-100)
    for field in required_fields:
        value = thresholds[field]
        if not (0 <= value <= 100):
            raise HTTPException(
                status_code=400,
                detail=f"{field} must be between 0 and 100"
            )

    # Validate threshold ordering (healthy > warning > critical)
    if thresholds["healthy"] <= thresholds["warning"]:
        raise HTTPException(
            status_code=400,
            detail="healthy threshold must be greater than warning threshold"
        )

    if thresholds["warning"] <= thresholds["critical"]:
        raise HTTPException(
            status_code=400,
            detail="warning threshold must be greater than critical threshold"
        )

    # Load current settings and update thresholds
    current_settings = load_settings()
    current_settings["healthThresholds"] = thresholds

    # Save to file
    save_settings(current_settings)

    return thresholds

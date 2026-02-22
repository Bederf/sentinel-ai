"""Settings API - Global system configuration from Supabase."""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import get_supabase_client

router = APIRouter()
logger = logging.getLogger(__name__)


class HealthThresholdsUpdate(BaseModel):
    """Health threshold update model."""

    healthy: int
    warning: int
    critical: int


class SettingUpdate(BaseModel):
    """Generic setting update model."""

    value: Dict[str, Any]
    category: Optional[str] = None
    description: Optional[str] = None


@router.get("/settings")
async def get_all_settings() -> Dict[str, Any]:
    """Get all system settings from Supabase.

    Returns both public and private settings (admin only in production).
    """
    try:
        supabase = get_supabase_client()
        result = supabase.table("system_settings").select("*").execute()

        settings = {}
        for setting in result.data:
            # Convert to key-value format (with metadata)
            settings[setting["key"]] = {
                "value": setting["value"],
                "category": setting.get("category"),
                "description": setting.get("description"),
                "dataType": setting.get("data_type"),
                "isPublic": setting.get("is_public", False),
                "isEditable": setting.get("is_editable", True),
                "updatedAt": setting.get("updated_at"),
            }

        return settings

    except Exception as e:
        logger.error(f"Error loading settings: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load settings from database: {str(e)}")


@router.get("/settings/public")
async def get_public_settings() -> Dict[str, Any]:
    """Get public settings (accessible to all users).

    Returns only settings where is_public = TRUE.
    """
    try:
        supabase = get_supabase_client()
        result = supabase.table("public_settings").select("*").execute()

        settings = {}
        for setting in result.data:
            # Return just key-value for public settings
            settings[setting["key"]] = setting["value"]

        return settings

    except Exception as e:
        logger.error(f"Error loading public settings: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load public settings: {str(e)}")


@router.get("/settings/health-thresholds")
async def get_health_thresholds() -> Dict[str, int]:
    """Get health score thresholds from database.

    Returns: {healthy: 90, warning: 70, critical: 50}
    """
    try:
        supabase = get_supabase_client()

        # Try to get from database first
        result = supabase.table("system_settings").select("value").eq("key", "health_thresholds").execute()

        if result.data:
            return result.data[0]["value"]
        else:
            # Return defaults if not found in database
            logger.warning("Health thresholds not found in database, using defaults")
            return {"healthy": 90, "warning": 70, "critical": 50}

    except Exception as e:
        logger.error(f"Error loading health thresholds: {e}")
        # Return defaults on error
        return {"healthy": 90, "warning": 70, "critical": 50}


@router.put("/settings/health-thresholds")
async def update_health_thresholds(thresholds: HealthThresholdsUpdate) -> Dict[str, int]:
    """Update health score thresholds in database.

    Validates:
    - All values between 0-100
    - healthy > warning > critical
    """
    # Validate threshold ranges (0-100)
    for field in ["healthy", "warning", "critical"]:
        value = getattr(thresholds, field)
        if not (0 <= value <= 100):
            raise HTTPException(status_code=400, detail=f"{field} must be between 0 and 100, got {value}")

    # Validate threshold ordering (healthy > warning > critical)
    if thresholds.healthy <= thresholds.warning:
        raise HTTPException(
            status_code=400,
            detail=(
                f"healthy threshold ({thresholds.healthy}) must be greater "
                f"than warning threshold ({thresholds.warning})"
            ),
        )

    if thresholds.warning <= thresholds.critical:
        raise HTTPException(
            status_code=400,
            detail=(
                f"warning threshold ({thresholds.warning}) must be greater "
                f"than critical threshold ({thresholds.critical})"
            ),
        )

    try:
        supabase = get_supabase_client()

        # Update in database
        (
            supabase.table("system_settings")
            .upsert(
                {
                    "key": "health_thresholds",
                    "value": {
                        "healthy": thresholds.healthy,
                        "warning": thresholds.warning,
                        "critical": thresholds.critical,
                    },
                    "category": "health",
                    "description": "Health score thresholds for equipment classification (0-100 scale)",
                    "data_type": "object",
                    "is_public": True,
                },
                on_conflict="key",
            )
            .execute()
        )

        logger.info(f"Updated health thresholds: {thresholds.dict()}")

        return {"healthy": thresholds.healthy, "warning": thresholds.warning, "critical": thresholds.critical}

    except Exception as e:
        logger.error(f"Error updating health thresholds: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update health thresholds: {str(e)}")


@router.get("/settings/alert-intervals")
async def get_alert_intervals() -> Dict[str, int]:
    """Get alert throttling intervals from database.

    Returns: {critical: 30, warning: 60, info: 1440}
    Values are in minutes (how often to repeat alerts).
    """
    try:
        supabase = get_supabase_client()

        result = supabase.table("system_settings").select("value").eq("key", "alert_intervals").execute()

        if result.data:
            return result.data[0]["value"]
        else:
            # Return defaults if not found
            return {"critical": 30, "warning": 60, "info": 1440}

    except Exception as e:
        logger.error(f"Error loading alert intervals: {e}")
        return {"critical": 30, "warning": 60, "info": 1440}


@router.put("/settings/alert-intervals")
async def update_alert_intervals(intervals: Dict[str, int]) -> Dict[str, int]:
    """Update alert throttling intervals in database.

    Args:
        intervals: {critical: minutes, warning: minutes, info: minutes}

    Example:
        {"critical": 15, "warning": 30, "info": 60}
    """
    # Validate intervals are positive
    for key, value in intervals.items():
        if not isinstance(value, int) or value < 1:
            raise HTTPException(
                status_code=400, detail=f"{key} interval must be a positive integer (minutes), got {value}"
            )

    try:
        supabase = get_supabase_client()

        (
            supabase.table("system_settings")
            .upsert(
                {
                    "key": "alert_intervals",
                    "value": intervals,
                    "category": "alerts",
                    "description": "Alert throttling intervals in minutes",
                    "data_type": "object",
                    "is_public": False,
                },
                on_conflict="key",
            )
            .execute()
        )

        logger.info(f"Updated alert intervals: {intervals}")

        return intervals

    except Exception as e:
        logger.error(f"Error updating alert intervals: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update alert intervals: {str(e)}")


@router.get("/settings/{key}")
async def get_setting(key: str) -> Dict[str, Any]:
    """Get a specific setting by key.

    Args:
        key: Setting key (e.g., "health_thresholds", "alert_intervals")
    """
    try:
        supabase = get_supabase_client()

        result = supabase.table("system_settings").select("*").eq("key", key).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")

        setting = result.data[0]

        # Check if user has access (for non-public settings)
        # TODO: Add proper authentication check here

        return {
            "key": setting["key"],
            "value": setting["value"],
            "category": setting.get("category"),
            "description": setting.get("description"),
            "dataType": setting.get("data_type"),
            "isEditable": setting.get("is_editable", True),
            "updatedAt": setting.get("updated_at"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting setting '{key}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get setting: {str(e)}")


@router.put("/settings/{key}")
async def update_setting(key: str, update: SettingUpdate) -> Dict[str, Any]:
    """Update a specific setting by key.

    Args:
        key: Setting key to update
        update: {value: ..., category: ..., description: ...}
    """
    try:
        supabase = get_supabase_client()

        # Check if setting exists and is editable
        existing = supabase.table("system_settings").select("is_editable").eq("key", key).execute()

        if existing.data:
            if not existing.data[0].get("is_editable", True):
                raise HTTPException(status_code=403, detail=f"Setting '{key}' is not editable")

        # Build update data
        update_data = {
            "key": key,
            "value": update.value,
            "data_type": "object" if isinstance(update.value, dict) else "string",
        }

        if update.category:
            update_data["category"] = update.category
        if update.description:
            update_data["description"] = update.description

        # Update in database
        supabase.table("system_settings").upsert(update_data, on_conflict="key").execute()

        logger.info(f"Updated setting '{key}': {update.value}")

        return {
            "key": key,
            "value": update.value,
            "category": update.get("category"),
            "description": update.get("description"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating setting '{key}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update setting: {str(e)}")

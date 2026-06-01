"""Settings API - Global system configuration from Supabase."""

import logging
from typing import Any

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
    site_id: str | None = None


class RiskThresholdsUpdate(BaseModel):
    """Risk threshold update model."""

    medium: int
    high: int
    critical: int
    site_id: str | None = None


class SettingUpdate(BaseModel):
    """Generic setting update model."""

    value: dict[str, Any]
    category: str | None = None
    description: str | None = None
    site_id: str | None = None


@router.get("/settings")
async def get_all_settings() -> dict[str, Any]:
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
        raise HTTPException(status_code=500, detail=f"Failed to load settings from database: {e!s}")


@router.get("/settings/public")
async def get_public_settings() -> dict[str, Any]:
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
        raise HTTPException(status_code=500, detail=f"Failed to load public settings: {e!s}")


@router.get("/settings/health-thresholds")
async def get_health_thresholds(site_id: str | None = None) -> dict[str, int]:
    """Get health score thresholds from database.

    Args:
        site_id: Optional site identifier for per-site thresholds.
                 Falls back to global settings if no site-specific entry exists.

    Returns: {healthy: 90, warning: 70, critical: 50}
    """
    try:
        supabase = get_supabase_client()

        # Try site-specific first, then fall back to global
        if site_id:
            result = (
                supabase.table("system_settings")
                .select("value")
                .eq("key", "health_thresholds")
                .eq("site_id", site_id)
                .execute()
            )
            if result.data:
                return result.data[0]["value"]

        # Fall back to global
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
async def update_health_thresholds(thresholds: HealthThresholdsUpdate) -> dict[str, int]:
    """Update health score thresholds in database.

    Validates:
    - All values between 0-100
    - healthy > warning > critical
    - site_id for per-site settings
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

        # Build upsert payload
        payload = {
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
            "site_id": thresholds.site_id,
        }

        # Update in database with composite key (key, site_id)
        (supabase.table("system_settings").upsert(payload, on_conflict="key,site_id").execute())

        logger.info(f"Updated health thresholds: site_id={thresholds.site_id}, values={thresholds.dict()}")

        return {"healthy": thresholds.healthy, "warning": thresholds.warning, "critical": thresholds.critical}

    except Exception as e:
        logger.error(f"Error updating health thresholds: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update health thresholds: {e!s}")


@router.get("/settings/risk-thresholds")
async def get_risk_thresholds(site_id: str | None = None) -> dict[str, int]:
    """Get risk score thresholds from database.

    Args:
        site_id: Optional site identifier for per-site thresholds.

    Returns: {medium: 31, high: 61, critical: 81}
    """
    try:
        supabase = get_supabase_client()

        if site_id:
            result = (
                supabase.table("system_settings")
                .select("value")
                .eq("key", "risk_thresholds")
                .eq("site_id", site_id)
                .execute()
            )
            if result.data:
                return result.data[0]["value"]

        result = supabase.table("system_settings").select("value").eq("key", "risk_thresholds").execute()

        if result.data:
            return result.data[0]["value"]

        logger.warning("Risk thresholds not found in database, using defaults")
        return {"medium": 31, "high": 61, "critical": 81}

    except Exception as e:
        logger.error(f"Error loading risk thresholds: {e}")
        return {"medium": 31, "high": 61, "critical": 81}


@router.put("/settings/risk-thresholds")
async def update_risk_thresholds(thresholds: RiskThresholdsUpdate) -> dict[str, int]:
    """Update risk score thresholds in database.

    Validates:
    - All values between 0-100
    - medium < high < critical
    - site_id for per-site settings
    """
    for field in ["medium", "high", "critical"]:
        value = getattr(thresholds, field)
        if not (0 <= value <= 100):
            raise HTTPException(status_code=400, detail=f"{field} must be between 0 and 100, got {value}")

    if thresholds.high <= thresholds.medium:
        raise HTTPException(
            status_code=400,
            detail=f"high threshold ({thresholds.high}) must be greater than medium threshold ({thresholds.medium})",
        )

    if thresholds.critical <= thresholds.high:
        raise HTTPException(
            status_code=400,
            detail=(
                f"critical threshold ({thresholds.critical}) must be greater than high threshold ({thresholds.high})"
            ),
        )

    try:
        supabase = get_supabase_client()

        (
            supabase.table("system_settings")
            .upsert(
                {
                    "key": "risk_thresholds",
                    "value": {
                        "medium": thresholds.medium,
                        "high": thresholds.high,
                        "critical": thresholds.critical,
                    },
                    "category": "risk",
                    "description": "Risk score thresholds for cockpit severity interpretation (0-100 scale)",
                    "data_type": "object",
                    "is_public": True,
                    "site_id": thresholds.site_id,
                },
                on_conflict="key,site_id",
            )
            .execute()
        )

        logger.info(f"Updated risk thresholds: site_id={thresholds.site_id}, values={thresholds.dict()}")
        return {"medium": thresholds.medium, "high": thresholds.high, "critical": thresholds.critical}

    except Exception as e:
        logger.error(f"Error updating risk thresholds: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update risk thresholds: {e!s}")


@router.get("/settings/alert-intervals")
async def get_alert_intervals(site_id: str | None = None) -> dict[str, int]:
    """Get alert throttling intervals from database.

    Args:
        site_id: Optional site identifier for per-site thresholds.

    Returns: {critical: 30, warning: 60, info: 1440}
    Values are in minutes (how often to repeat alerts).
    """
    try:
        supabase = get_supabase_client()

        if site_id:
            result = (
                supabase.table("system_settings")
                .select("value")
                .eq("key", "alert_intervals")
                .eq("site_id", site_id)
                .execute()
            )
            if result.data:
                return result.data[0]["value"]

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
async def update_alert_intervals(intervals: dict[str, int], site_id: str | None = None) -> dict[str, int]:
    """Update alert throttling intervals in database.

    Args:
        intervals: {critical: minutes, warning: minutes, info: minutes}
        site_id: Optional site identifier for per-site settings.

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
                    "site_id": site_id,
                },
                on_conflict="key,site_id",
            )
            .execute()
        )

        logger.info(f"Updated alert intervals: site_id={site_id}, intervals={intervals}")

        return intervals

    except Exception as e:
        logger.error(f"Error updating alert intervals: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update alert intervals: {e!s}")


@router.get("/settings/{key}")
async def get_setting(key: str, site_id: str | None = None) -> dict[str, Any]:
    """Get a specific setting by key.

    Args:
        key: Setting key (e.g., "health_thresholds", "alert_intervals")
        site_id: Optional site identifier for per-site settings
    """
    try:
        supabase = get_supabase_client()

        # Try site-specific first
        if site_id:
            result = supabase.table("system_settings").select("*").eq("key", key).eq("site_id", site_id).execute()
            if result.data:
                setting = result.data[0]
                return {
                    "key": setting["key"],
                    "value": setting["value"],
                    "category": setting.get("category"),
                    "description": setting.get("description"),
                    "dataType": setting.get("data_type"),
                    "isEditable": setting.get("is_editable", True),
                    "updatedAt": setting.get("updated_at"),
                    "site_id": setting.get("site_id"),
                }

        result = supabase.table("system_settings").select("*").eq("key", key).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")

        setting = result.data[0]

        return {
            "key": setting["key"],
            "value": setting["value"],
            "category": setting.get("category"),
            "description": setting.get("description"),
            "dataType": setting.get("data_type"),
            "isEditable": setting.get("is_editable", True),
            "updatedAt": setting.get("updated_at"),
            "site_id": setting.get("site_id"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting setting '{key}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get setting: {e!s}")


@router.put("/settings/{key}")
async def update_setting(key: str, update: SettingUpdate, site_id: str | None = None) -> dict[str, Any]:
    """Update a specific setting by key.

    Args:
        key: Setting key to update
        update: {value: ..., category: ..., description: ...}
        site_id: Optional site identifier for per-site settings
    """
    try:
        supabase = get_supabase_client()

        # Build update data
        update_data = {
            "key": key,
            "value": update.value,
            "data_type": "object" if isinstance(update.value, dict) else "string",
            "site_id": site_id,
        }

        if update.category:
            update_data["category"] = update.category
        if update.description:
            update_data["description"] = update.description

        # Check if setting exists and is editable
        existing = supabase.table("system_settings").select("is_editable").eq("key", key).execute()

        if existing.data and not existing.data[0].get("is_editable", True):
            raise HTTPException(status_code=403, detail=f"Setting '{key}' is not editable")

        # Update in database with composite key (key, site_id)
        supabase.table("system_settings").upsert(update_data, on_conflict="key,site_id").execute()

        logger.info(f"Updated setting '{key}': site_id={site_id}, value={update.value}")

        return {
            "key": key,
            "value": update.value,
            "category": update.category,
            "description": update.description,
            "site_id": site_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating setting '{key}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update setting: {e!s}")

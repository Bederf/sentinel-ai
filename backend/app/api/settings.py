"""Settings API - Global system configuration.

Security: GET endpoints require AUDITOR (level 1), PUT endpoints require ADMIN (level 4).
Phase 137-09: CONFIG_CHANGE audit events on all PUT endpoints.
"""

import json
import logging
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.middleware.auth_middleware import require_site_access
from app.models.auth import AuthContext
from app.security.audit_events import audit_config_change
from app.security.pipeline import require_role
from app.services.site_ai_policy_service import get_site_ai_policy, set_site_ai_policy

logger = logging.getLogger(__name__)

router = APIRouter()


class SiteAiPolicyUpdate(BaseModel):
    """Site-scoped AI policy update payload."""

    chat_local_ai_only: bool
    allow_tool_calling: bool
    show_recommendations_in_shadow: bool


# Path to settings data file
DATA_DIR = Path(__file__).parent.parent / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"


def load_settings() -> dict[str, Any]:
    """Load settings from JSON file."""
    if not SETTINGS_FILE.exists():
        # Create default settings if file doesn't exist
        default_settings = {
            "healthThresholds": {"healthy": 90, "warning": 70, "critical": 0},
            "riskThresholds": {"medium": 31, "high": 61, "critical": 81},
            "notifications": {},
            "display": {},
        }
        save_settings(default_settings)
        return default_settings

    try:
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load settings: {e!s}")


def save_settings(settings_data: dict[str, Any]) -> None:
    """Save settings to JSON file."""
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings_data, f, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save settings: {e!s}")


# Path to onboarding phase state file (mirrors sites.py _ONBOARDING_PHASE_FILE)
_ONBOARDING_PHASE_FILE = Path(__file__).parent.parent / "data" / "onboarding_phase_state.json"


def _save_phase_state_for_site(site_id: str, stage: str) -> None:
    """Update onboarding phase in the JSON state file so get_sites_from_supabase picks it up."""
    try:
        if _ONBOARDING_PHASE_FILE.exists():
            state = json.loads(_ONBOARDING_PHASE_FILE.read_text())
        else:
            state = {}
        state[site_id] = stage
        _ONBOARDING_PHASE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        logger.warning("Failed to write onboarding phase state for %s: %s", site_id, e)


@router.get("/settings")
async def get_all_settings(auth: AuthContext = Depends(require_role(1))) -> dict[str, Any]:
    """Get all settings. Requires AUDITOR (level 1)."""
    return load_settings()


@router.put("/settings")
async def update_all_settings(
    settings_data: dict[str, Any],
    request: Request,
    auth: AuthContext = Depends(require_role(4)),
) -> dict[str, Any]:
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

    if "riskThresholds" in settings_data:
        thresholds = settings_data["riskThresholds"]
        if not isinstance(thresholds, dict):
            raise HTTPException(status_code=400, detail="riskThresholds must be an object")

        for key in ["medium", "high", "critical"]:
            if key in thresholds and not isinstance(thresholds[key], (int, float)):
                raise HTTPException(status_code=400, detail=f"{key} risk threshold must be a number")

        for key in ["medium", "high", "critical"]:
            if key in thresholds:
                value = thresholds[key]
                if not (0 <= value <= 100):
                    raise HTTPException(status_code=400, detail=f"{key} risk threshold must be between 0 and 100")

        if "high" in thresholds and "medium" in thresholds and thresholds["high"] <= thresholds["medium"]:
            raise HTTPException(status_code=400, detail="high risk threshold must be greater than medium threshold")

        if "critical" in thresholds and "high" in thresholds and thresholds["critical"] <= thresholds["high"]:
            raise HTTPException(status_code=400, detail="critical risk threshold must be greater than high threshold")

    # Merge with existing settings
    current_settings = load_settings()
    current_settings.update(settings_data)

    # Save to file
    save_settings(current_settings)

    # Audit: CONFIG_CHANGE
    source_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)
    audit_config_change("settings.all", user=auth.user_id, source_ip=source_ip)

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
async def get_notification_settings(auth: AuthContext = Depends(require_role(1))) -> dict[str, Any]:
    """Get notification settings including alert command config. Requires AUDITOR (level 1)."""
    settings_data = load_settings()
    return settings_data.get("notifications", DEFAULT_NOTIFICATION_SETTINGS)


@router.put("/settings/notifications")
async def update_notification_settings(
    notifications: dict[str, Any],
    request: Request,
    auth: AuthContext = Depends(require_role(4)),
) -> dict[str, Any]:
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

    # Audit: CONFIG_CHANGE
    source_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)
    audit_config_change("settings.notifications", user=auth.user_id, source_ip=source_ip)

    return current_notifications


@router.get("/settings/health-thresholds")
async def get_health_thresholds(auth: AuthContext = Depends(require_role(1))) -> dict[str, int]:
    """Get health score thresholds. Requires AUDITOR (level 1)."""
    settings_data = load_settings()
    return settings_data.get("healthThresholds", {"healthy": 90, "warning": 70, "critical": 0})


@router.put("/settings/health-thresholds")
async def update_health_thresholds(
    thresholds: dict[str, int],
    request: Request,
    auth: AuthContext = Depends(require_role(4)),
) -> dict[str, int]:
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

    # Audit: CONFIG_CHANGE
    source_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)
    audit_config_change("settings.health-thresholds", user=auth.user_id, source_ip=source_ip)

    return thresholds


@router.get("/settings/risk-thresholds")
async def get_risk_thresholds(auth: AuthContext = Depends(require_role(1))) -> dict[str, int]:
    """Get risk score thresholds. Requires AUDITOR (level 1)."""
    settings_data = load_settings()
    return settings_data.get("riskThresholds", {"medium": 31, "high": 61, "critical": 81})


@router.put("/settings/risk-thresholds")
async def update_risk_thresholds(
    thresholds: dict[str, int],
    request: Request,
    auth: AuthContext = Depends(require_role(4)),
) -> dict[str, int]:
    """Update risk score thresholds. Requires ADMIN (level 4)."""
    required_fields = ["medium", "high", "critical"]
    for field in required_fields:
        if field not in thresholds:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    for field in required_fields:
        if not isinstance(thresholds[field], (int, float)):
            raise HTTPException(status_code=400, detail=f"{field} must be a number")

    for field in required_fields:
        value = thresholds[field]
        if not (0 <= value <= 100):
            raise HTTPException(status_code=400, detail=f"{field} must be between 0 and 100")

    if thresholds["high"] <= thresholds["medium"]:
        raise HTTPException(status_code=400, detail="high threshold must be greater than medium threshold")

    if thresholds["critical"] <= thresholds["high"]:
        raise HTTPException(status_code=400, detail="critical threshold must be greater than high threshold")

    current_settings = load_settings()
    current_settings["riskThresholds"] = thresholds
    save_settings(current_settings)

    source_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)
    audit_config_change("settings.risk-thresholds", user=auth.user_id, source_ip=source_ip)

    return thresholds


@router.get("/settings/ml-training")
async def get_ml_training_status(auth: AuthContext = Depends(require_role(1))) -> dict[str, Any]:
    """Get ML background training status."""
    from app.config.settings import settings as app_settings

    settings_data = load_settings()
    return {
        "enabled": settings_data.get("mlBackgroundTraining", app_settings.ml_background_training_enabled),
        "env_default": app_settings.ml_background_training_enabled,
    }


@router.put("/settings/ml-training")
async def toggle_ml_training(
    body: dict[str, bool],
    request: Request,
    auth: AuthContext = Depends(require_role(4)),
) -> dict[str, Any]:
    """Toggle ML background training. Requires ADMIN. Takes effect on next restart."""
    enabled = body.get("enabled", False)

    current_settings = load_settings()
    current_settings["mlBackgroundTraining"] = enabled
    save_settings(current_settings)

    source_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)
    audit_config_change("settings.ml-training", user=auth.user_id, source_ip=source_ip)

    return {
        "enabled": enabled,
        "message": "ML background training will be "
        + ("enabled" if enabled else "disabled")
        + " on next service restart.",
    }


@router.get("/settings/ai-policy/{site_id}")
async def get_site_ai_policy_settings(
    site_id: str,
    auth: AuthContext = Depends(require_site_access("site_id")),
) -> dict[str, Any]:
    """Get site-scoped AI runtime policy. Requires site access."""
    return get_site_ai_policy(site_id)


@router.put("/settings/ai-policy/{site_id}")
async def update_site_ai_policy_settings(
    site_id: str,
    payload: SiteAiPolicyUpdate,
    request: Request,
    auth: AuthContext = Depends(require_role(4)),
) -> dict[str, Any]:
    """Update site-scoped AI runtime policy. Requires ADMIN."""
    stored = set_site_ai_policy(site_id, payload.model_dump())
    source_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)
    audit_config_change(f"settings.ai-policy.{site_id}", user=auth.user_id, source_ip=source_ip)
    return stored


# Valid site deployment stages
VALID_DEPLOYMENT_STAGES = {"shadow", "advisory", "supervised", "commissioning"}


class SiteModeUpdate(BaseModel):
    stage: str


@router.get("/settings/site-mode/{site_id}")
async def get_site_mode(
    site_id: str,
    auth: AuthContext = Depends(require_role(1)),
) -> dict[str, Any]:
    """Get current deployment stage for a site. Requires AUDITOR (level 1)."""
    from app.services.site_mode_policy_service import SiteModePolicyService

    svc = SiteModePolicyService()
    try:
        state = svc._load_state(site_id, svc.load_policy(site_id))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"No mode policy found for {site_id}")
    return {
        "site_id": site_id,
        "current_stage": state.get("current_stage"),
        "candidate_stage": state.get("candidate_stage"),
        "candidate_since": state.get("candidate_since"),
        "last_evaluated_at": state.get("last_evaluated_at"),
    }


@router.patch("/settings/site-mode/{site_id}")
async def set_site_mode(
    site_id: str,
    payload: SiteModeUpdate,
    request: Request,
    auth: AuthContext = Depends(require_role(4)),
) -> dict[str, Any]:
    """Force-set deployment stage for a site. Requires ADMIN (level 4).

    Use this to manually override the mode without going through the
    automatic promotion/demotion evaluation cycle.
    """
    from app.services.site_mode_policy_service import SiteModePolicyService

    if payload.stage not in VALID_DEPLOYMENT_STAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid stage '{payload.stage}'. Valid: {', '.join(sorted(VALID_DEPLOYMENT_STAGES))}",
        )

    # Normalise frontend stage names (shadow → shadow_live, auto → automatic)
    from app.models.onboarding_phase import normalise_stage
    canonical_stage = normalise_stage(payload.stage)

    svc = SiteModePolicyService()
    try:
        state = svc._load_state(site_id, svc.load_policy(site_id))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"No mode policy found for {site_id}")

    state["current_stage"] = canonical_stage
    state["candidate_stage"] = None
    state["candidate_since"] = None
    state["violation_stage"] = None
    state["violation_since"] = None
    state["last_evaluated_at"] = datetime.now(UTC).isoformat()
    svc._save_state(site_id, state)

    # Also persist to onboarding_phase_state.json so get_sites_from_supabase picks it up
    _save_phase_state_for_site(site_id, canonical_stage)

    # Sync stage to Supabase so mode gates and downstream services stay in sync
    try:
        from app.models.onboarding_phase import sync_site_phase_to_supabase
        await sync_site_phase_to_supabase(site_id, canonical_stage)
    except Exception as e:
        logger.error("Failed to sync site mode to Supabase for %s: %s", site_id, e)

    source_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)
    audit_config_change(f"settings.site-mode.{site_id}", user=auth.user_id, source_ip=source_ip)

    return {"site_id": site_id, "current_stage": canonical_stage}

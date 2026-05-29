"""Settings API - Global system configuration.

Security: GET endpoints require AUDITOR (level 1), PUT endpoints require ADMIN (level 4).
Phase 137-09: CONFIG_CHANGE audit events on all PUT endpoints.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.database.supabase_client import get_supabase_client
from app.middleware.auth_middleware import require_site_access
from app.models.auth import AuthContext
from app.security.audit_events import audit_config_change
from app.security.pipeline import require_role
from app.services.site_ai_policy_service import get_site_ai_policy, set_site_ai_policy

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_role(1))])


DEFAULT_SETTINGS = {
    "healthThresholds": {"healthy": 90, "warning": 70, "critical": 0},
    "riskThresholds": {"medium": 31, "high": 61, "critical": 81},
    "notifications": {},
    "display": {},
    "siteAiPolicies": {},
}


def _load_all() -> dict[str, Any]:
    """Load settings from Supabase system_settings table, merged with defaults."""
    try:
        supabase = get_supabase_client()
        result = supabase.table("system_settings").select("key, value").execute()
        merged = dict(DEFAULT_SETTINGS)
        for row in result.data or []:
            merged[row["key"]] = row["value"]
        return merged
    except Exception as e:
        logger.warning(f"Failed to load settings from Supabase: {e}")
        return dict(DEFAULT_SETTINGS)


def _get_setting(key: str) -> Any:
    """Get a single setting by key from Supabase."""
    try:
        supabase = get_supabase_client()
        result = supabase.table("system_settings").select("value").eq("key", key).limit(1).execute()
        if result.data:
            return result.data[0]["value"]
    except Exception:
        pass
    return DEFAULT_SETTINGS.get(key)


def _upsert_setting(key: str, value: Any) -> None:
    """Upsert a setting into Supabase system_settings table."""
    try:
        supabase = get_supabase_client()
        existing = supabase.table("system_settings").select("id").eq("key", key).limit(1).execute()
        now = datetime.utcnow().isoformat()
        if existing.data:
            supabase.table("system_settings").update({"value": value, "updated_at": now}).eq("key", key).execute()
        else:
            supabase.table("system_settings").insert({
                "key": key,
                "value": value,
                "category": key,
                "data_type": "object",
                "created_at": now,
                "updated_at": now,
            }).execute()
    except Exception as e:
        logger.error(f"Failed to save setting '{key}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save setting: {e!s}")


# Public alias for external consumers (cockpit_policy_resolution, etc.)
load_settings = _load_all


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
    try:
        return _load_all()
    except Exception as e:
        import traceback
        logger.error(f"settings/all error: {e}\n{traceback.format_exc()}")
        raise


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

    # Upsert each key to Supabase
    for key, value in settings_data.items():
        _upsert_setting(key, value)

    # Audit: CONFIG_CHANGE
    source_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)
    audit_config_change("settings.all", user=auth.user_id, source_ip=source_ip)

    return _load_all()


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
    return _get_setting("notifications") or DEFAULT_NOTIFICATION_SETTINGS


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

    # Merge with existing
    current = _get_setting("notifications") or {}
    if "alertCommands" in notifications and "alertCommands" in current:
        for key, config in notifications["alertCommands"].items():
            if key in current["alertCommands"]:
                current["alertCommands"][key].update(config)
            else:
                current["alertCommands"][key] = config
        notifications["alertCommands"] = current["alertCommands"]

    current.update(notifications)
    _upsert_setting("notifications", current)

    # Audit: CONFIG_CHANGE
    source_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)
    audit_config_change("settings.notifications", user=auth.user_id, source_ip=source_ip)

    return current


@router.get("/settings/health-thresholds")
async def get_health_thresholds(
    site_id: str | None = Query(None, description="Site code for per-site thresholds"),
    auth: AuthContext = Depends(require_role(1)),
) -> dict[str, int]:
    """Get health score thresholds. Requires AUDITOR (level 1).

    If site_id is provided, returns site-specific thresholds if they exist,
    falling back to global defaults.
    """
    key = f"healthThresholds_{site_id}" if site_id else "healthThresholds"
    try:
        return _get_setting(key) or {"healthy": 90, "warning": 70, "critical": 0}
    except Exception as e:
        import traceback
        logger.error(f"settings/health-thresholds error: {e}\n{traceback.format_exc()}")
        raise


@router.put("/settings/health-thresholds")
async def update_health_thresholds(
    thresholds: dict[str, int],
    request: Request,
    site_id: str | None = Query(None, description="Site code for per-site thresholds"),
    auth: AuthContext = Depends(require_role(4)),
) -> dict[str, int]:
    """Update health score thresholds. Requires ADMIN (level 4)."""
    required_fields = ["healthy", "warning", "critical"]
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

    if thresholds["healthy"] <= thresholds["warning"]:
        raise HTTPException(status_code=400, detail="healthy threshold must be greater than warning threshold")

    if thresholds["warning"] <= thresholds["critical"]:
        raise HTTPException(status_code=400, detail="warning threshold must be greater than critical threshold")

    key = f"healthThresholds_{site_id}" if site_id else "healthThresholds"
    _upsert_setting(key, thresholds)

    source_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)
    audit_config_change("settings.health-thresholds", user=auth.user_id, source_ip=source_ip)

    return thresholds


@router.get("/settings/risk-thresholds")
async def get_risk_thresholds(
    site_id: str | None = Query(None, description="Site code for per-site thresholds"),
    auth: AuthContext = Depends(require_role(1)),
) -> dict[str, int]:
    """Get risk score thresholds. Requires AUDITOR (level 1)."""
    key = f"riskThresholds_{site_id}" if site_id else "riskThresholds"
    result = _get_setting(key)
    if result:
        return result
    # Per-site falls back to global when no custom thresholds exist
    if site_id:
        global_result = _get_setting("riskThresholds")
        if global_result:
            return global_result
    return {"medium": 31, "high": 61, "critical": 81}


@router.put("/settings/risk-thresholds")
async def update_risk_thresholds(
    thresholds: dict[str, int],
    request: Request,
    site_id: str | None = Query(None, description="Site code for per-site thresholds"),
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

    key = f"riskThresholds_{site_id}" if site_id else "riskThresholds"
    _upsert_setting(key, thresholds)

    # When saving global, also update legacy key;
    # when saving per-site, do NOT clobber global defaults.
    if not site_id:
        _upsert_setting("riskThresholds", thresholds)

    source_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)
    audit_config_change("settings.risk-thresholds", user=auth.user_id, source_ip=source_ip)

    return thresholds


@router.get("/settings/ml-training")
async def get_ml_training_status(auth: AuthContext = Depends(require_role(1))) -> dict[str, Any]:
    """Get ML background training status."""
    from app.config.settings import settings as app_settings

    stored = _get_setting("mlBackgroundTraining")
    enabled = stored if isinstance(stored, bool) else app_settings.ml_background_training_enabled
    return {"enabled": enabled, "env_default": app_settings.ml_background_training_enabled}


@router.put("/settings/ml-training")
async def toggle_ml_training(
    body: dict[str, bool],
    request: Request,
    auth: AuthContext = Depends(require_role(4)),
) -> dict[str, Any]:
    """Toggle ML background training. Requires ADMIN. Takes effect on next restart."""
    enabled = body.get("enabled", False)
    _upsert_setting("mlBackgroundTraining", enabled)

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


class SiteAiPolicyUpdate(BaseModel):
    """Site-scoped AI policy update payload."""

    chat_local_ai_only: bool = False
    allow_tool_calling: bool = True
    show_recommendations_in_shadow: bool = False


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
        state = {}
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

    current_stage = state.get("current_stage", "commissioning")

    # Evaluate promotion gates — don't allow write if gates fail
    eval_result = await svc.evaluate_site(site_id)
    decision = eval_result.get("decision", "hold")
    reasons = eval_result.get("reasons", [])

    if decision == "hold" and canonical_stage != current_stage:
        gate_target = canonical_stage
        raise HTTPException(
            status_code=400,
            detail=f"Cannot promote to '{gate_target}'. "
                   f"Current: {current_stage}. Promotion gates not met: {'; '.join(reasons)}",
        )

    state["current_stage"] = canonical_stage
    state["candidate_stage"] = None
    state["candidate_since"] = None
    state["violation_stage"] = None
    state["violation_since"] = None
    state["last_evaluated_at"] = datetime.now(timezone.utc).isoformat()
    svc._save_state(site_id, state)

    # Audit phase transition in phase_transition_log
    try:
        supabase = get_supabase_client()
        supabase.table("phase_transition_log").insert({
            "site_id": site_id,
            "from_phase": state.get("current_stage", "unknown"),
            "to_phase": canonical_stage,
            "changed_by": auth.user_id or "system",
            "reason": f"Manual phase change via settings API: {canonical_stage}",
            "created_at": datetime.utcnow().isoformat(),
        }).execute()
    except Exception as e:
        logger.warning("Failed to log phase transition for %s: %s", site_id, e)

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

    # Sync bridge policy stage when phase is changed manually
    try:
        import httpx
        import os
        bridge_url = f"http://10.99.0.1:8080/api/sites/{site_id}/ipmvp/policy-state"
        bridge_token = os.getenv("BRIDGE_API_TOKEN_SITE002") or os.getenv("BRIDGE_API_TOKEN", "")
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.put(
                bridge_url,
                json={"policy_stage": canonical_stage},
                headers={"Authorization": f"Bearer {bridge_token}"},
            )
            if resp.is_success:
                logger.info("Bridge policy stage synced to %s for %s", canonical_stage, site_id)
            else:
                logger.warning("Bridge policy sync returned %s: %s", resp.status_code, resp.text[:200])
    except Exception as e:
        logger.warning("Failed to sync bridge policy stage for %s: %s", site_id, e)

    return {"site_id": site_id, "current_stage": canonical_stage}


# =============================================================================
# AEGIS BESS Writer Settings
# =============================================================================


class AegisWriterSettings(BaseModel):
    """AEGIS BESS writer enable/disable payload."""

    aegis_bess_writer_enabled: bool = False


@router.get("/settings/aegis/{site_id}")
async def get_aegis_settings(
    site_id: str,
    auth: AuthContext = Depends(require_role(1)),
) -> dict[str, Any]:
    """Get AEGIS BESS writer settings for a site. Requires AUDITOR (level 1)."""
    from app.config.settings import settings

    # Check site mode — only supervised or automatic allow execution
    from app.services.site_mode_policy_service import SiteModePolicyService

    svc = SiteModePolicyService()
    try:
        state = svc._load_state(site_id, svc.load_policy(site_id))
    except FileNotFoundError:
        state = {}

    current_stage = state.get("current_stage", "commissioning")
    execution_allowed = current_stage in ("supervised", "automatic")

    return {
        "site_id": site_id,
        "aegis_bess_writer_enabled": settings.aegis_bess_writer_enabled,
        "current_stage": current_stage,
        "execution_allowed": execution_allowed,
        "gate_status": "open" if (settings.aegis_bess_writer_enabled and execution_allowed) else "closed",
    }


@router.put("/settings/aegis/{site_id}")
async def update_aegis_settings(
    site_id: str,
    payload: AegisWriterSettings,
    request: Request,
    auth: AuthContext = Depends(require_role(4)),
) -> dict[str, Any]:
    """Update AEGIS BESS writer enable flag. Requires ADMIN (level 4).

    Safety gates:
    - Flag is persisted to backend config at runtime (not in Supabase)
    - Actual writes also require site to be in supervised or automatic mode
    - All state changes are audit-logged via CONFIG_CHANGE events
    """
    from app.config.settings import settings

    # Check site mode — warn if enabling while not in supervised/automatic
    from app.services.site_mode_policy_service import SiteModePolicyService

    svc = SiteModePolicyService()
    try:
        state = svc._load_state(site_id, svc.load_policy(site_id))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"No mode policy found for {site_id}")

    current_stage = state.get("current_stage", "commissioning")
    execution_allowed = current_stage in ("supervised", "automatic")

    # Update runtime setting (this affects the running backend process)
    settings.aegis_bess_writer_enabled = payload.aegis_bess_writer_enabled

    source_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)
    audit_config_change(
        f"settings.aegis.{site_id}.aegis_bess_writer_enabled",
        user=auth.user_id,
        source_ip=source_ip,
        old_value=not payload.aegis_bess_writer_enabled,
        new_value=payload.aegis_bess_writer_enabled,
    )

    return {
        "site_id": site_id,
        "aegis_bess_writer_enabled": settings.aegis_bess_writer_enabled,
        "current_stage": current_stage,
        "execution_allowed": execution_allowed,
        "gate_status": "open" if (settings.aegis_bess_writer_enabled and execution_allowed) else "closed",
        "warning": None if execution_allowed else f"execution_blocked: site is in '{current_stage}' mode (requires supervised or automatic)",
    }

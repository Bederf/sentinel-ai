"""Site-scoped AI policy settings backed by settings.json."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"

DEFAULT_SITE_AI_POLICY: dict[str, Any] = {
    "chat_local_ai_only": False,
    "allow_tool_calling": True,
    "show_recommendations_in_shadow": False,
    "monthly_budget_zar": 0.0,
    "hard_cap_enforced": False,
}


def _load_settings() -> dict[str, Any]:
    if not SETTINGS_FILE.exists():
        return {}
    try:
        return json.loads(SETTINGS_FILE.read_text())
    except Exception as exc:
        logger.warning("Failed to load settings file for site AI policy: %s", exc)
        return {}


def _save_settings(payload: dict[str, Any]) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(payload, indent=2))


def _normalize_policy(candidate: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(DEFAULT_SITE_AI_POLICY)
    if not isinstance(candidate, dict):
        return normalized

    if "chat_local_ai_only" in candidate:
        normalized["chat_local_ai_only"] = bool(candidate["chat_local_ai_only"])
    if "allow_tool_calling" in candidate:
        normalized["allow_tool_calling"] = bool(candidate["allow_tool_calling"])
    if "show_recommendations_in_shadow" in candidate:
        normalized["show_recommendations_in_shadow"] = bool(candidate["show_recommendations_in_shadow"])
    if "monthly_budget_zar" in candidate:
        try:
            normalized["monthly_budget_zar"] = max(0.0, float(candidate["monthly_budget_zar"]))
        except (TypeError, ValueError):
            normalized["monthly_budget_zar"] = 0.0
    if "hard_cap_enforced" in candidate:
        normalized["hard_cap_enforced"] = bool(candidate["hard_cap_enforced"])
    return normalized


def get_site_ai_policy(site_id: str | None) -> dict[str, Any]:
    """Return effective AI policy for a site."""
    if not site_id:
        return dict(DEFAULT_SITE_AI_POLICY)
    settings_data = _load_settings()
    site_policies = settings_data.get("siteAiPolicies", {})
    return _normalize_policy(site_policies.get(site_id))


def set_site_ai_policy(site_id: str, policy: dict[str, Any]) -> dict[str, Any]:
    """Persist AI policy for a specific site and return stored value."""
    settings_data = _load_settings()
    site_policies = settings_data.get("siteAiPolicies", {})
    if not isinstance(site_policies, dict):
        site_policies = {}
    normalized = _normalize_policy(policy)
    site_policies[site_id] = normalized
    settings_data["siteAiPolicies"] = site_policies
    _save_settings(settings_data)
    return normalized

"""Site-scoped AI policy settings backed by Supabase system_settings."""

from __future__ import annotations

import logging
from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

DEFAULT_SITE_AI_POLICY: dict[str, Any] = {
    "chat_local_ai_only": False,
    "allow_tool_calling": True,
    "show_recommendations_in_shadow": False,
    "monthly_budget_zar": 0.0,
    "hard_cap_enforced": False,
}


def _get_site_ai_policies() -> dict[str, Any]:
    try:
        supabase = get_supabase_client()
        result = supabase.table("system_settings").select("value").eq("key", "siteAiPolicies").limit(1).execute()
        if result.data:
            return result.data[0]["value"] or {}
    except Exception as e:
        logger.warning("Failed to load site AI policies from Supabase: %s", e)
    return {}


def _save_site_ai_policies(policies: dict[str, Any]) -> None:
    try:
        supabase = get_supabase_client()
        existing = supabase.table("system_settings").select("id").eq("key", "siteAiPolicies").limit(1).execute()
        if existing.data:
            supabase.table("system_settings").update({"value": policies}).eq("key", "siteAiPolicies").execute()
        else:
            supabase.table("system_settings").insert({
                "key": "siteAiPolicies",
                "value": policies,
                "category": "siteAiPolicies",
                "data_type": "object",
            }).execute()
    except Exception as e:
        logger.error("Failed to save site AI policies: %s", e)


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
    policies = _get_site_ai_policies()
    return _normalize_policy(policies.get(site_id))


def set_site_ai_policy(site_id: str, policy: dict[str, Any]) -> dict[str, Any]:
    """Persist AI policy for a specific site and return stored value."""
    policies = _get_site_ai_policies()
    if not isinstance(policies, dict):
        policies = {}
    normalized = _normalize_policy(policy)
    policies[site_id] = normalized
    _save_site_ai_policies(policies)
    return normalized

"""
Onboarding Phase — SENTINEL trust-building model.

A site progresses through four phases as it earns operator trust:
  shadow     → SENTINEL watches and learns, nothing surfaced to users
  advisory   → recommendations and notifications visible, no control writes
  supervised → approve/reject controls enabled, humans approve each action
  auto       → SENTINEL acts within defined safety limits automatically

The phase gates are enforced at:
  - Backend: background_scheduler (notifications), optimizer (auto-apply),
             correlation (email signal routing), API responses (recs)
  - Frontend: SiteCard, SiteDetail, ControlPanel visibility

All gates use phase_allows() — single source of truth.
"""

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class OnboardingPhase(str, Enum):
    SHADOW = "shadow"
    ADVISORY = "advisory"
    SUPERVISED = "supervised"
    AUTO = "auto"


_PHASE_ORDER = ["shadow", "advisory", "supervised", "auto"]

_FEATURE_GATES: dict[str, str] = {
    "recommendations_ui": "advisory",
    "sentry_notifications": "advisory",
    "approve_reject": "supervised",
    "auto_apply": "auto",
    "concierge_dashboard": "advisory",
    "email_signal_routing": "advisory",
    "emit_signal": "advisory",
}


def phase_allows(phase: str | None, feature: str, module_type: str | None = None) -> bool:
    """Return True if the site's onboarding phase permits the given feature.

    Args:
        phase:       The site's current onboarding_phase value. None treated as 'shadow'.
        feature:     One of: recommendations_ui, sentry_notifications,
                     approve_reject, auto_apply, concierge_dashboard,
                     email_signal_routing.
        module_type: Optional — informational only. The caller is responsible for
                     passing the correct resolved phase (via effective_phase()) when
                     module-level overrides are required. This parameter is accepted
                     for forward-compatibility but does not alter the gate logic here.

    Returns:
        True if phase >= the feature's minimum required phase.
        False for unknown feature names (fail-safe deny).
    """
    p = phase or "shadow"
    required = _FEATURE_GATES.get(feature)
    if required is None:
        return False  # unknown feature → deny
    try:
        return _PHASE_ORDER.index(p) >= _PHASE_ORDER.index(required)
    except ValueError:
        return False  # unknown phase value → deny


PHASE_LABELS: dict[str, str] = {
    "shadow": "Shadow",
    "advisory": "Advisory",
    "supervised": "Supervised",
    "auto": "Auto",
}

PHASE_DESCRIPTIONS: dict[str, str] = {
    "shadow": "SENTINEL monitors and learns. Nothing surfaced to users.",
    "advisory": "Recommendations and notifications visible. No control writes.",
    "supervised": "Controls enabled. Humans approve each action before it executes.",
    "auto": "SENTINEL acts automatically within defined safety limits.",
}


async def effective_phase(site_id: str, module_type: str | None = None) -> str:
    """Return the effective onboarding phase for a site, optionally for a specific module.

    Resolution order:
      1. site_modules.phase_override for (site_id, module_type) — if set and module_type provided
      2. sites.onboarding_phase — site-level phase
      3. "shadow" — safe default

    Args:
        site_id:     Site code (e.g. 'S001').
        module_type: Optional module type key (e.g. 'occupancy_control'). When provided,
                     a per-module phase_override is checked first.

    Returns:
        One of: 'shadow', 'advisory', 'supervised', 'auto'.
        Falls back to 'shadow' on any error or missing value.
    """
    try:
        from app.database.supabase_client import get_supabase_client

        sb = get_supabase_client()
        if module_type:
            mod_result = (
                sb.table("site_modules")
                .select("phase_override")
                .eq("site_id", site_id)
                .eq("module_type", module_type)
                .execute()
            )
            if mod_result.data and mod_result.data[0].get("phase_override"):
                return mod_result.data[0]["phase_override"]
        # Fall through to site-level
        site_result = sb.table("sites").select("onboarding_phase").eq("code", site_id).execute()
        if site_result.data:
            return site_result.data[0].get("onboarding_phase") or "shadow"
    except Exception as exc:
        logger.debug("effective_phase: could not fetch phase for %s/%s: %s", site_id, module_type, exc)
    return "shadow"


async def get_site_phase(site_id: str, module_type: str | None = None) -> str:
    """Fetch current onboarding phase for a site. Delegates to effective_phase().

    Args:
        site_id:     Site code (e.g. 'S001') or UUID.
        module_type: Optional module type — passed through to effective_phase() for
                     per-module override resolution.

    Returns:
        One of: 'shadow', 'advisory', 'supervised', 'auto'.
        Falls back to 'shadow' on any error or missing value.
    """
    return await effective_phase(site_id, module_type)

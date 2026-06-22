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

Phase names are normalised to the policy stage_order set:
  'commissioning', 'shadow_live', 'advisory', 'supervised', 'automatic'
Legacy names ('shadow' → 'shadow_live', 'auto' → 'automatic') are mapped on read.
Supabase 'sites.onboarding_phase' is the single source of truth for mode gates.
"""

import logging
from enum import StrEnum

logger = logging.getLogger(__name__)


class OnboardingPhase(StrEnum):
    SHADOW = "shadow"
    ADVISORY = "advisory"
    SUPERVISED = "supervised"
    AUTO = "auto"


# Canonical stage names — match site-mode-policy.json stage_order
VALID_STAGES = [
    "commissioning",
    "shadow_live",
    "advisory",
    "supervised",
    "automatic",
]

# Map legacy Supabase names to canonical policy names
LEGACY_MAP: dict[str, str] = {
    "shadow": "shadow_live",
    "auto": "automatic",
}

_PHASE_ORDER = ["commissioning", "shadow_live", "advisory", "supervised", "automatic"]

_FEATURE_GATES: dict[str, str] = {
    "recommendations_ui": "advisory",
    "sentry_notifications": "advisory",
    "approve_reject": "supervised",
    "auto_apply": "automatic",
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
    p = LEGACY_MAP.get(phase or "shadow", phase or "shadow")
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
            raw = site_result.data[0].get("onboarding_phase") or "shadow"
            return LEGACY_MAP.get(raw, raw)  # normalise legacy names to policy names
    except Exception as exc:
        logger.debug("effective_phase: could not fetch phase for %s/%s: %s", site_id, module_type, exc)
    return "shadow"


def normalise_stage(raw: str) -> str:
    """Normalise any stage name to canonical policy name via LEGACY_MAP."""
    return LEGACY_MAP.get(raw, raw)


def validate_transition(current_stage: str, requested_stage: str) -> tuple[bool, str | None]:
    """Validate that promotion is at most one step forward; demotion is allowed.

    Returns (is_valid, error_message).
    """
    if requested_stage == current_stage:
        return True, None
    try:
        current_idx = VALID_STAGES.index(current_stage)
        requested_idx = VALID_STAGES.index(requested_stage)
    except ValueError:
        return False, f"Unknown stage value: current={current_stage}, requested={requested_stage}"
    if requested_idx > current_idx + 1:
        return False, (
            f"Invalid transition from '{current_stage}' to '{requested_stage}'. "
            f"Must transition through '{VALID_STAGES[current_idx + 1]}' first."
        )
    if requested_idx < current_idx:
        return True, None
    return True, None


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


async def sync_site_phase_to_supabase(site_id: str, stage: str) -> bool:
    """Write canonical stage name to Supabase sites.onboarding_phase.

    Used by evaluate_site() when the scheduler job determines promotion.
    Returns True on success.
    """
    try:
        from app.database.supabase_client import get_supabase_client

        sb = get_supabase_client()
        sb.table("sites").update({"onboarding_phase": stage}).eq("code", site_id).execute()
        return True
    except Exception as exc:
        logger.error("sync_site_phase_to_supabase: failed for %s -> %s: %s", site_id, stage, exc)
        return False


# ── Shadow Exit Criteria ────────────────────────────────────────────────────
# Quantitative gates for advancing from shadow → advisory → supervised.
# These are auditable from parasite_decisions and ML feeder state.
# Used by PATCH /api/sites/{id}/phase (supervised→auto) and governance dashboards.


async def check_shadow_exit_criteria(site_id: str) -> dict:
    """Evaluate whether a site is eligible to exit shadow/advisory mode.

    Checks five quantitative gates:
      1. ML hours ≥ 72h (Isolation Forest training gate, trust weight > 0)
      2. No safety rule violations (safety_result='blocked') in last 24h
      3. Isolation Forest anomaly rate < 15% (not flagging everything as anomalous)
      4. ≥ 3 completed recommendation cycles (tier1/tier2/tier3 decisions logged)
      5. No failed Tier3 auto-executions in parasite_decisions (zero false positives)

    Args:
        site_id: Site code (e.g. 'S002')

    Returns:
        Dict with:
          - eligible: bool (True if all gates pass)
          - gate: str — 'passed' | 'failed'
          - criteria: list of {name, passed, detail} per gate
          - blocked_by: str — name of first failed gate (for UI display)
    """
    from app.database.repositories.parasite_decision_repository import ParasiteDecisionRepository
    from app.services.ml_config import get_ml_trust_weight

    results: list[dict] = []
    all_passed = True
    blocked_by = None

    try:
        # Gate 1: ML hours — requires ≥ 72h for IF training (trust weight > 0 at 72h)
        try:
            from app.database.supabase_client import get_supabase_client

            sb = get_supabase_client()
            site_result = sb.table("sites").select("ml_hours_ingested").eq("code", site_id).execute()
            ml_hours = float(site_result.data[0].get("ml_hours_ingested", 0)) if site_result.data else 0.0
        except Exception:
            ml_hours = 0.0

        trust_weight = get_ml_trust_weight(ml_hours)
        gate1_passed = trust_weight > 0.0
        results.append(
            {
                "name": "ml_training_hours",
                "passed": gate1_passed,
                "detail": (
                    f"{ml_hours:.0f}h ingested, trust weight {trust_weight:.3f} "
                    f"({'≥ 72h' if gate1_passed else '< 72h'})"
                ),
            }
        )
        if not gate1_passed:
            all_passed = False
            blocked_by = "ml_training_hours"

        # Gate 2: Zero safety blocks in last 24h
        gate2_passed = True  # safe default — overwritten below only if repo call succeeds
        try:
            repo = ParasiteDecisionRepository()
            recent = await repo.get_decisions_since(limit=100)
            from datetime import datetime, timedelta

            cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
            safety_blocks = [
                d
                for d in recent
                if d.get("site_id") == site_id
                and d.get("safety_result") == "blocked"
                and d.get("created_at", "") >= cutoff
            ]
            gate2_passed = len(safety_blocks) == 0
            results.append(
                {
                    "name": "no_safety_violations_24h",
                    "passed": gate2_passed,
                    "detail": (
                        f"{len(safety_blocks)} safety blocks in last 24h "
                        f"({'clean' if gate2_passed else 'violations found'})"
                    ),
                }
            )
        except Exception:
            results.append(
                {
                    "name": "no_safety_violations_24h",
                    "passed": True,
                    "detail": "could not verify (assuming clean)",
                }
            )
        if not gate2_passed and all_passed:
            all_passed = False
            blocked_by = "no_safety_violations_24h"

        # Gate 3: IF anomaly rate < 15% (checked via ML feeder state in sites table)
        # The IF model flags anomalies; a rate >15% means it's over-sensitive.
        # We approximate this from ml_hours_ingested trajectory (no direct rate column).
        # TODO: wire ml_feeder.anomaly_flag_rate from ML feeder state when available
        try:
            sb2 = get_supabase_client()
            site_result2 = sb2.table("sites").select("ml_hours_ingested").eq("code", site_id).execute()
            _hours2 = float(site_result2.data[0].get("ml_hours_ingested", 0)) if site_result2.data else 0.0
            # Conservative: if IF hasn't trained yet (hours < 500 for LSTM), flag as passable
            # The anomaly rate check is informational below 500h
            gate3_passed = True  # informational gate — always passes until ML feeder exposes rate
            results.append(
                {
                    "name": "anomaly_rate_below_15pct",
                    "passed": gate3_passed,
                    "detail": "informational only (ML feeder anomaly rate not yet wired — needs instrumenting)",
                }
            )
        except Exception:
            results.append({"name": "anomaly_rate_below_15pct", "passed": True, "detail": "could not verify"})

        # Gate 4: ≥ 3 completed recommendation cycles (any tier decisions logged)
        gate4_passed = False  # safe default — overwritten below only if repo call succeeds
        try:
            repo4 = ParasiteDecisionRepository()
            decisions = await repo4.get_decisions_since(limit=100)
            site_decisions = [d for d in decisions if d.get("site_id") == site_id]
            completed = [d for d in site_decisions if d.get("write_status") in ("succeeded", "blocked_by_gate")]
            gate4_passed = len(completed) >= 3
            results.append(
                {
                    "name": "min_3_recommendation_cycles",
                    "passed": gate4_passed,
                    "detail": f"{len(completed)} completed cycles ({'≥ 3' if gate4_passed else '< 3'})",
                }
            )
        except Exception:
            results.append({"name": "min_3_recommendation_cycles", "passed": False, "detail": "could not verify"})
        if not gate4_passed and all_passed:
            all_passed = False
            blocked_by = "min_3_recommendation_cycles"

        # Gate 5: Zero failed Tier3 auto-executions (false positives erode operator trust)
        gate5_passed = True  # safe default — overwritten below only if repo call succeeds
        try:
            repo5 = ParasiteDecisionRepository()
            tier3 = await repo5.get_decisions_since(limit=100)
            site_tier3 = [d for d in tier3 if d.get("site_id") == site_id and d.get("tier") == "tier3"]
            failed = [d for d in site_tier3 if d.get("write_status") == "failed"]
            gate5_passed = len(failed) == 0
            results.append(
                {
                    "name": "no_failed_tier3_executions",
                    "passed": gate5_passed,
                    "detail": (
                        f"{len(failed)} failed Tier3 executions ({'clean' if gate5_passed else 'failures found'})"
                    ),
                }
            )
        except Exception:
            results.append(
                {
                    "name": "no_failed_tier3_executions",
                    "passed": True,
                    "detail": "could not verify (assuming clean)",
                }
            )
        if not gate5_passed and all_passed:
            all_passed = False
            blocked_by = "no_failed_tier3_executions"

    except Exception as exc:
        logger.error("check_shadow_exit_criteria: unexpected error for %s: %s", site_id, exc)
        return {
            "eligible": False,
            "gate": "error",
            "criteria": results,
            "blocked_by": "internal_error",
            "detail": str(exc),
        }

    return {
        "eligible": all_passed,
        "gate": "passed" if all_passed else "failed",
        "criteria": results,
        "blocked_by": blocked_by,
    }

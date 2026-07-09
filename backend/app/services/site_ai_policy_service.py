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
    "ml_training_enabled": False,
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
            supabase.table("system_settings").insert(
                {
                    "key": "siteAiPolicies",
                    "value": policies,
                    "category": "siteAiPolicies",
                    "data_type": "object",
                }
            ).execute()
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
    if "ml_training_enabled" in candidate:
        normalized["ml_training_enabled"] = bool(candidate["ml_training_enabled"])
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


def is_site_ml_training_enabled(site_id: str | None) -> bool:
    """Return whether ML training is enabled for a site."""
    if not site_id:
        return False
    return bool(get_site_ai_policy(site_id).get("ml_training_enabled", False))


def set_site_ai_policy(site_id: str, policy: dict[str, Any]) -> dict[str, Any]:
    """Persist AI policy for a specific site and return stored value."""
    policies = _get_site_ai_policies()
    if not isinstance(policies, dict):
        policies = {}
    normalized = _normalize_policy(policy)
    policies[site_id] = normalized
    _save_site_ai_policies(policies)
    return normalized


# Telemetry metrics that gate ML training readiness.
# Feedback-loop metrics (truth_check, rollback_rate, label_lag) are
# intentionally excluded — they depend on ML training already running.
_ML_READINESS_METRICS: tuple[str, ...] = (
    "freshness_minutes",
    "ingest_error_rate_pct_1h",
    "match_coverage_pct",
    "manual_source_pct",
    "unmatched_points_pct",
    "commissioning_all_gates_passed",
    "consecutive_pass_days",
)


async def get_ml_training_readiness(site_id: str) -> dict[str, Any]:
    """Evaluate whether a site is ready to enable ML training.

    Checks telemetry health only.  Feedback-loop metrics are ignored
    because the feedback loop does not exist until ML training starts.
    """
    from app.config.settings import settings
    from app.services.commissioning_service import CommissioningService
    from app.services.quality_gate_evaluator import QualityGateEvaluator
    from app.services.quality_gate_policy import RuleState

    try:
        evaluator = QualityGateEvaluator()

        db_mode = CommissioningService()._get_site_phase(site_id)
        mode = db_mode if db_mode else settings.resolved_ingestion_mode.value

        metrics = await evaluator.collect_metrics(site_id)
        result = evaluator.evaluate(mode, metrics, site_id=site_id)

        # Filter to telemetry-only metrics.
        # Readiness is strict: all selected telemetry gates must pass before
        # the site ML toggle can be enabled.
        telemetry_results: list[dict[str, Any]] = []
        blocking: list[str] = []
        for rule in result.rule_results:
            if rule.metric not in _ML_READINESS_METRICS:
                continue
            telemetry_results.append(
                {
                    "metric": rule.metric,
                    "value": rule.value,
                    "state": rule.state.value,
                    "threshold": {
                        "pass_bound": rule.threshold.pass_bound,
                        "warn_bound": rule.threshold.warn_bound,
                        "direction": rule.threshold.direction,
                    },
                }
            )
            if rule.state not in (RuleState.PASS, RuleState.NA):
                blocking.append(rule.metric)

        # Compute overall from telemetry metrics only — the evaluator's
        # result.overall includes feedback-loop metrics which are irrelevant
        # for ML training readiness.
        telemetry_states = [r["state"] for r in telemetry_results]
        if any(s == "fail" for s in telemetry_states):
            overall = "fail"
        elif any(s == "warn" for s in telemetry_states):
            overall = "warn"
        else:
            overall = "pass"

        ready = len(blocking) == 0

        return {
            "ready": ready,
            "overall": overall,
            "blocking_metrics": blocking,
            "telemetry_results": telemetry_results,
            "evaluated_at": getattr(result, "evaluated_at", None),
        }
    except Exception as e:
        logger.warning("Failed to evaluate ML training readiness for %s: %s", site_id, e)
        return {
            "ready": False,
            "overall": "unknown",
            "blocking_metrics": [],
            "telemetry_results": [],
            "error": str(e),
        }

"""Operator-facing recommendation preflight evidence.

This service builds a compact, human-readable summary that can be shown before
an operator approves a supervised action.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from app.services.quality_gate_evaluator import CONFIDENCE_CAP, QualityGateEvaluator

logger = logging.getLogger(__name__)

_METRIC_LABELS = {
    "truth_check_pass_rate_pct": "Truth Check",
    "mv_accuracy_7d_pct": "M&V Accuracy",
    "rollback_rate_7d_pct": "Rollback Rate",
    "label_lag_p95_hours": "Label Lag",
    "comfort_violation_rate_7d_pct": "Comfort Violations",
    "freshness_minutes": "Freshness",
    "ingest_error_rate_pct_1h": "Error Rate",
    "match_coverage_pct": "Match Coverage",
    "manual_source_pct": "Manual Sources",
    "unmatched_points_pct": "Unmatched Points",
    "commissioning_all_gates_passed": "Commissioning Gates",
    "feedback_capture_rate_7d_pct": "Feedback Capture",
    "drift_critical_alerts_24h": "Drift Alerts",
}

_CONTROL_TIER_TO_GATE_MODE = {
    "monitor": "advisory",
    "supervised": "supervised",
    "auto_execute": "live_control",
}


def _to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_signed(value: float | None, unit: str) -> str:
    if value is None:
        return "--"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f} {unit}"


def _fmt_signed_zar(value: float | None) -> str:
    if value is None:
        return "--"
    sign = "+" if value > 0 else "-"
    return f"{sign}R{abs(value):.2f}"


def _quality_label(metric: str) -> str:
    return _METRIC_LABELS.get(metric, metric.replace("_", " ").replace(" pct", "").title())


def resolve_site_quality_gate_mode(site_id: str) -> tuple[str, dict[str, Any]]:
    """Resolve the quality-gate evaluation mode from the selected site profile."""
    from app.config.settings import settings
    from app.services.profile_service import get_profile_service
    from app.services.site_operating_mode_service import resolve_site_operating_mode

    profile_service = get_profile_service()
    config = profile_service.load_site_profile_config(site_id)
    if config:
        gate_mode = _CONTROL_TIER_TO_GATE_MODE.get(
            str(config.control_tier or "").strip().lower(),
            settings.resolved_ingestion_mode.value,
        )
        return gate_mode, {
            "active_profile": config.active_profile,
            "control_tier": config.control_tier,
            "operating_mode": resolve_site_operating_mode(site_id),
        }

    return settings.resolved_ingestion_mode.value, {
        "active_profile": None,
        "control_tier": None,
        "operating_mode": resolve_site_operating_mode(site_id),
    }


async def collect_quality_gate_preflight(site_id: str) -> dict[str, Any] | None:
    """Return current quality gate status in a compact dict."""
    if not site_id:
        return None
    try:
        evaluator = QualityGateEvaluator()
        mode, profile_context = resolve_site_quality_gate_mode(site_id)
        metrics = await evaluator.collect_metrics(site_id)
        result = evaluator.evaluate(mode, metrics, site_id=site_id)
        return {
            "overall": result.overall.value,
            "enforcement": result.enforcement.value,
            "failed_rules": list(result.failed_rules or []),
            "warn_rules": list(result.warn_rules or []),
            "profile_context": profile_context,
        }
    except Exception as exc:
        logger.warning("Could not collect recommendation preflight quality gate for %s: %s", site_id, exc)
        return None


def collect_equipment_outcome_history(
    *,
    site_id: str,
    equipment_id: str,
    lookback_days: int = 30,
    limit: int = 3,
) -> dict[str, Any]:
    """Return recent measured recommendation outcomes for the same equipment."""
    if not site_id or not equipment_id:
        return {"count": 0, "rows": [], "positive": 0, "negative": 0, "total_kwh": 0.0, "total_zar": 0.0}

    try:
        from app.database.supabase_client import get_supabase_client

        cutoff = (datetime.now(UTC) - timedelta(days=lookback_days)).isoformat()
        result = (
            get_supabase_client()
            .table("recommendations")
            .select(
                "id,timestamp,executed_at,status,outcome_validated,outcome_notes,"
                "actual_saving_kwh,actual_saving_zar,action"
            )
            .eq("site_id", site_id)
            .eq("target_equipment", equipment_id)
            .gte("timestamp", cutoff)
            .not_.is_("actual_saving_kwh", "null")
            .order("timestamp", desc=True)
            .limit(limit)
            .execute()
        )
        rows = result.data or []
    except Exception as exc:
        logger.warning("Could not collect recommendation outcome history for %s/%s: %s", site_id, equipment_id, exc)
        rows = []

    savings = [_to_float(row.get("actual_saving_kwh")) or 0.0 for row in rows]
    zar = [_to_float(row.get("actual_saving_zar")) or 0.0 for row in rows]
    return {
        "count": len(rows),
        "rows": rows,
        "positive": sum(1 for value in savings if value > 0),
        "negative": sum(1 for value in savings if value < 0),
        "total_kwh": sum(savings),
        "total_zar": sum(zar),
    }


async def build_recommendation_preflight_lines(
    recommendation: Any,
    *,
    quality_gate: dict[str, Any] | None = None,
) -> list[str]:
    """Build concise text lines for a supervised approval prompt."""
    site_id = str(getattr(recommendation, "site_id", "") or "")
    equipment_id = str(getattr(recommendation, "target_equipment", "") or "")
    if quality_gate is None:
        quality_gate = await collect_quality_gate_preflight(site_id)

    history = collect_equipment_outcome_history(site_id=site_id, equipment_id=equipment_id)
    count = int(history.get("count") or 0)
    positive = int(history.get("positive") or 0)
    negative = int(history.get("negative") or 0)
    total_kwh = _to_float(history.get("total_kwh")) or 0.0
    total_zar = _to_float(history.get("total_zar")) or 0.0

    failed_rules = list((quality_gate or {}).get("failed_rules") or [])
    quality_failed = str((quality_gate or {}).get("overall") or "").lower() == "fail"
    enforcement = str((quality_gate or {}).get("enforcement") or "")
    profile_context = (quality_gate or {}).get("profile_context") or {}
    active_profile = profile_context.get("active_profile")
    control_tier = profile_context.get("control_tier")
    operating_mode = profile_context.get("operating_mode")

    try:
        confidence = recommendation.get_numeric_confidence()
    except Exception:
        confidence = _to_float(getattr(recommendation, "confidence_score", None)) or 0.0

    risk_reasons: list[str] = []
    if quality_failed:
        risk_reasons.append("Quality Gate FAIL")
    if count == 0:
        risk_reasons.append("no measured history on this equipment")
    elif negative and not positive:
        risk_reasons.append("recent measured outcomes increased energy")
    elif negative:
        risk_reasons.append("mixed measured history")

    if quality_failed or negative:
        verdict = "CAUTION"
    elif count == 0:
        verdict = "CHECK"
    else:
        verdict = "SUPPORTED"

    lines = [f"Preflight: {verdict} - " + "; ".join(risk_reasons or ["recent evidence is positive"])]

    profile_bits = []
    if active_profile:
        profile_bits.append(str(active_profile).replace("_", " "))
    if control_tier:
        profile_bits.append(str(control_tier))
    if operating_mode:
        profile_bits.append(str(operating_mode))
    if profile_bits:
        lines.append(f"Site profile: {' / '.join(profile_bits)}.")

    if count:
        lines.append(
            "History: "
            f"{count} measured, {positive} positive, {negative} negative, "
            f"total {_fmt_signed(total_kwh, 'kWh')} / {_fmt_signed_zar(total_zar)}."
        )
    else:
        lines.append("History: no measured same-equipment outcomes in the last 30 days.")

    if failed_rules:
        blockers = ", ".join(_quality_label(rule) for rule in failed_rules[:4])
        extra = f" +{len(failed_rules) - 4} more" if len(failed_rules) > 4 else ""
        lines.append(f"Quality blockers: {blockers}{extra}.")

    if enforcement == "cap_confidence" and confidence:
        lines.append(f"Confidence: model {confidence * 100:.0f}%, effective cap {CONFIDENCE_CAP * 100:.0f}%.")

    return lines

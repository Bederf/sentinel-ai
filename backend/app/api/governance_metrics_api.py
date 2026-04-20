"""Governance metrics REST API.

Exposes 5 endpoints for programmatic access to governance metrics:
quality gate rules, model drift, approval latency, cost by route,
and POPIA evidence packs.
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.middleware.auth_middleware import require_auth
from app.models.auth import AuthContext, AuthLevel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/governance", tags=["governance"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_counter_samples(metric_name: str) -> list[dict[str, Any]]:
    """Read labelled counter values from the Prometheus REGISTRY."""
    from app.api.metrics import REGISTRY

    # prometheus_client strips _total from Counter.name but keeps it on samples
    base = metric_name.removesuffix("_total")
    samples: list[dict[str, Any]] = []
    for metric in REGISTRY.collect():
        if metric.name in (metric_name, base, f"{base}_total"):
            for sample in metric.samples:
                if sample.name.endswith("_created"):
                    continue
                samples.append({"labels": dict(sample.labels), "value": sample.value})
    return samples


def _read_histogram_samples(metric_name: str) -> dict[str, list[dict[str, Any]]]:
    """Read histogram bucket / sum / count samples from the Prometheus REGISTRY."""
    from app.api.metrics import REGISTRY

    result: dict[str, list[dict[str, Any]]] = {
        "buckets": [],
        "sum": [],
        "count": [],
    }
    for metric in REGISTRY.collect():
        if metric.name == metric_name:
            for sample in metric.samples:
                if sample.name.endswith("_bucket"):
                    result["buckets"].append({"labels": dict(sample.labels), "value": sample.value})
                elif sample.name.endswith("_sum"):
                    result["sum"].append({"labels": dict(sample.labels), "value": sample.value})
                elif sample.name.endswith("_count"):
                    result["count"].append({"labels": dict(sample.labels), "value": sample.value})
    return result


def _percentile_from_buckets(buckets: list[dict[str, Any]], target: float) -> float:
    """Approximate a percentile from histogram bucket data.

    *buckets* should be sorted by ``le`` ascending.  Uses linear
    interpolation between bucket boundaries.
    """
    if not buckets:
        return 0.0

    # Sort by le (upper bound)
    sorted_buckets = sorted(
        buckets,
        key=lambda b: float(b["labels"].get("le", "inf")) if b["labels"].get("le") != "+Inf" else float("inf"),
    )

    total = sorted_buckets[-1]["value"] if sorted_buckets else 0
    if total == 0:
        return 0.0

    threshold = target * total
    prev_bound = 0.0
    prev_count = 0.0

    for b in sorted_buckets:
        le_str = b["labels"].get("le", "+Inf")
        if le_str == "+Inf":
            upper = float("inf")
        else:
            upper = float(le_str)

        count = b["value"]
        if count >= threshold:
            if math.isinf(upper):
                return prev_bound
            # Linear interpolation
            if count == prev_count:
                return upper
            fraction = (threshold - prev_count) / (count - prev_count)
            return prev_bound + fraction * (upper - prev_bound)

        prev_bound = upper
        prev_count = count

    return prev_bound


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/quality-gate-rules")
async def get_quality_gate_rules(auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED))) -> dict[str, Any]:
    """Return per-rule pass/fail/warn counts from Prometheus registry."""
    samples = _read_counter_samples("sentinel_quality_gate_rule_evaluations_total")

    # Aggregate by rule_name and status
    rules_map: dict[str, dict[str, int]] = {}
    for s in samples:
        rule = s["labels"].get("rule_name", "unknown")
        status = s["labels"].get("status", "unknown")
        if rule not in rules_map:
            rules_map[rule] = {"pass": 0, "warn": 0, "fail": 0}
        if status in rules_map[rule]:
            rules_map[rule][status] += int(s["value"])

    rules = [{"rule_name": name, **counts} for name, counts in sorted(rules_map.items())]
    return {"rules": rules}


@router.get("/drift-scores")
async def get_drift_scores(auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED))) -> dict[str, Any]:
    """Return current drift scores for all active models."""
    from app.ml.models.model_drift_calculator import ModelDriftCalculator
    from app.services.governance_metrics_collector import governance_metrics

    calc = ModelDriftCalculator()
    scores = await calc.get_all_drift_scores()

    # Emit drift scores to Prometheus gauges so Grafana panels have data
    for s in scores:
        governance_metrics.record_drift_score(s["model_id"], s["model_type"], s["drift_score"])

    alerts = [s for s in scores if s.get("drift_score", 0) > 0.3]

    return {"models": scores, "alerts": alerts}


@router.get("/approval-latency")
async def get_approval_latency(auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED))) -> dict[str, Any]:
    """Return approval latency percentiles from histogram data."""
    hist = _read_histogram_samples("sentinel_approval_latency_seconds")

    # Aggregate all buckets (across label combinations)
    all_buckets: dict[str, float] = {}
    for b in hist["buckets"]:
        le = b["labels"].get("le", "+Inf")
        all_buckets[le] = all_buckets.get(le, 0) + b["value"]

    bucket_list = [{"labels": {"le": le}, "value": val} for le, val in all_buckets.items()]

    p50 = round(_percentile_from_buckets(bucket_list, 0.5), 3)
    p95 = round(_percentile_from_buckets(bucket_list, 0.95), 3)
    p99 = round(_percentile_from_buckets(bucket_list, 0.99), 3)

    total_approvals = int(sum(s["value"] for s in hist["count"]))

    # Rejection rate from approval decisions counter
    decision_samples = _read_counter_samples("sentinel_approval_decisions_total")
    total_decisions = 0
    total_rejections = 0
    for s in decision_samples:
        count = int(s["value"])
        total_decisions += count
        if s["labels"].get("decision") == "rejected":
            total_rejections += count

    rejection_rate = total_rejections / total_decisions if total_decisions > 0 else 0.0

    return {
        "percentiles": {"p50": p50, "p95": p95, "p99": p99},
        "total_approvals": total_approvals,
        "rejection_rate": round(rejection_rate, 4),
    }


@router.get("/cost-by-route")
async def get_cost_by_route(auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED))) -> dict[str, Any]:
    """Return token/cost breakdown by route.

    Costs in Prometheus are tracked in USD. This endpoint converts to ZAR
    using the ai_usage_tracker exchange rate for display consistency.
    """
    from app.services.ai_usage_tracker import AiUsageTracker

    token_samples = _read_counter_samples("sentinel_ai_tokens_by_route_total")
    cost_samples = _read_counter_samples("sentinel_ai_cost_by_route_total")

    # Get current USD→ZAR rate
    tracker = AiUsageTracker()
    usd_zar = getattr(tracker, "_usd_zar", 18.50)

    # Aggregate tokens by route
    tokens_map: dict[str, int] = {}
    for s in token_samples:
        route = s["labels"].get("route", "unknown")
        tokens_map[route] = tokens_map.get(route, 0) + int(s["value"])

    # Aggregate costs by route (USD in Prometheus, convert to ZAR)
    cost_map_usd: dict[str, float] = {}
    for s in cost_samples:
        route = s["labels"].get("route", "unknown")
        cost_map_usd[route] = cost_map_usd.get(route, 0) + s["value"]

    # Merge
    all_routes = sorted(set(tokens_map.keys()) | set(cost_map_usd.keys()))
    routes = [
        {
            "route": r,
            "tokens": tokens_map.get(r, 0),
            "cost_usd": round(cost_map_usd.get(r, 0.0), 4),
            "cost_zar": round(cost_map_usd.get(r, 0.0) * usd_zar, 2),
        }
        for r in all_routes
    ]

    total_usd = sum(r["cost_usd"] for r in routes)
    return {
        "routes": routes,
        "total_tokens": sum(r["tokens"] for r in routes),
        "total_cost_usd": round(total_usd, 4),
        "total_cost_zar": round(total_usd * usd_zar, 2),
        "usd_zar_rate": usd_zar,
    }


@router.get("/popia-evidence")
async def get_popia_evidence(
    year: int | None = Query(default=None, description="Year (default: current)"),
    month: int | None = Query(default=None, ge=1, le=12, description="Month 1-12 (default: current)"),
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
) -> dict[str, Any]:
    """Return monthly POPIA evidence pack."""
    from app.services.popia_evidence_pack_service import POPIAEvidencePackService

    svc = POPIAEvidencePackService()

    now = datetime.now(UTC)
    y = year or now.year
    m = month or now.month

    pack = await svc.generate_monthly_pack(y, m)
    return pack

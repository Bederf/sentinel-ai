"""Prometheus-format /metrics endpoint for AI governance observability.

Exposes SENTINEL AI control metrics in Prometheus text exposition format
for scraping by Prometheus/Victoria Metrics.

Phase 114-05: Creates the endpoint structure with static/demo values.
Real metric collection hooks into existing services will be wired in
Phase 2 (Control Implementation) per compliance.md roadmap.
"""

from __future__ import annotations

import ipaddress
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Dedicated registry (avoids polluting the default process-level registry
# which ships with python GC / platform metrics we don't want exposed).
# ---------------------------------------------------------------------------
REGISTRY = CollectorRegistry()

# ---------------------------------------------------------------------------
# Metric definitions — 8 AI governance metrics
# ---------------------------------------------------------------------------

# 1. Quality gate evaluations
sentinel_quality_gate_evaluations_total = Counter(
    "sentinel_quality_gate_evaluations_total",
    "Total quality-gate evaluations by site and outcome",
    labelnames=["site_id", "status"],
    registry=REGISTRY,
)

# 2. Quality gate enforcement level (current state gauge)
sentinel_quality_gate_enforcement = Gauge(
    "sentinel_quality_gate_enforcement",
    "Current enforcement level per site (1 = active for that enforcement level)",
    labelnames=["site_id", "enforcement"],
    registry=REGISTRY,
)

# 3. Recommendations generated
sentinel_recommendations_total = Counter(
    "sentinel_recommendations_total",
    "Total recommendations by site, tier, and action disposition",
    labelnames=["site_id", "tier", "action"],
    registry=REGISTRY,
)

# 4. Approval decisions
sentinel_approval_decisions_total = Counter(
    "sentinel_approval_decisions_total",
    "Total approval workflow decisions by site and outcome",
    labelnames=["site_id", "decision"],
    registry=REGISTRY,
)

# 5. Safety violations
sentinel_safety_violations_total = Counter(
    "sentinel_safety_violations_total",
    "Total safety boundary violations by site and severity",
    labelnames=["site_id", "severity"],
    registry=REGISTRY,
)

# 6. Model drift alerts (gauge — current active alert count)
sentinel_model_drift_alerts = Gauge(
    "sentinel_model_drift_alerts",
    "Active model drift alerts by site and model type",
    labelnames=["site_id", "model_type"],
    registry=REGISTRY,
)

# 7. Rollback events
sentinel_rollback_total = Counter(
    "sentinel_rollback_total",
    "Total automated rollback events by site and equipment type",
    labelnames=["site_id", "equipment_type"],
    registry=REGISTRY,
)

# 8. Build / version info
sentinel_info = Info(
    "sentinel",
    "SENTINEL build and configuration metadata",
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# HTTP request metrics (Phase 127 — RequestMetricsMiddleware)
# ---------------------------------------------------------------------------

# 9. HTTP request counter
sentinel_http_requests_total = Counter(
    "sentinel_http_requests_total",
    "Total HTTP requests by method, path pattern, and status code",
    labelnames=["method", "path", "status_code"],
    registry=REGISTRY,
)

# 10. HTTP request duration histogram
sentinel_http_request_duration_seconds = Histogram(
    "sentinel_http_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=["method", "path"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=REGISTRY,
)

# 11. HTTP requests in progress
sentinel_http_requests_in_progress = Gauge(
    "sentinel_http_requests_in_progress",
    "Number of HTTP requests currently being processed",
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Tool-call metrics (Phase 127 — chat pipeline instrumentation)
# ---------------------------------------------------------------------------

# 12. Tool call counter
sentinel_tool_calls_total = Counter(
    "sentinel_tool_calls_total",
    "Total tool calls by tool name and outcome",
    labelnames=["tool_name", "outcome"],
    registry=REGISTRY,
)

# 13. Tool call duration histogram
sentinel_tool_call_duration_seconds = Histogram(
    "sentinel_tool_call_duration_seconds",
    "Tool call execution duration in seconds",
    labelnames=["tool_name"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Database & cache metrics (Phase 125 — Supabase Performance Completion)
# ---------------------------------------------------------------------------

# 14. Supabase query duration
sentinel_db_query_duration_seconds = Histogram(
    "sentinel_db_query_duration_seconds",
    "Supabase PostgREST query duration in seconds",
    labelnames=["repository", "method"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
    registry=REGISTRY,
)

# 15. Cache operations counter
sentinel_cache_operations_total = Counter(
    "sentinel_cache_operations_total",
    "Cache operations by type (hit, miss, error)",
    labelnames=["operation"],
    registry=REGISTRY,
)

# 16. Cache hit rate gauge
sentinel_cache_hit_rate_percent = Gauge(
    "sentinel_cache_hit_rate_percent",
    "Current cache hit rate percentage",
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Static info set once at import time
# ---------------------------------------------------------------------------
_MODE = os.getenv("SENTINEL_MODE", "simulation")
_VERSION = os.getenv("APP_VERSION", "14.9")
_BUILD_DATE = os.getenv("BUILD_DATE", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
_DEMO_MODE = os.getenv("DEMO_MODE", "").lower() in ("true", "1", "yes")

sentinel_info.info(
    {
        "version": _VERSION,
        "mode": _MODE,
        "build_date": _BUILD_DATE,
    }
)

# ---------------------------------------------------------------------------
# Seed demo values (only when DEMO_MODE=true).
# In production, metrics start at 0 and increment from real service events.
# Phase 115-01: Real instrumentation wired into services.
# ---------------------------------------------------------------------------
_DEMO_SEEDED = False


def _seed_demo_values() -> None:
    """Populate counters with representative demo data (idempotent)."""
    global _DEMO_SEEDED
    if _DEMO_SEEDED:
        return
    _DEMO_SEEDED = True

    from app.core.site_resolver import get_primary_site

    _site = get_primary_site() or "unknown"

    # Quality gate evaluations
    sentinel_quality_gate_evaluations_total.labels(site_id=_site, status="pass").inc(142)
    sentinel_quality_gate_evaluations_total.labels(site_id=_site, status="warn").inc(18)
    sentinel_quality_gate_evaluations_total.labels(site_id=_site, status="fail").inc(3)

    # Enforcement gauge — normal is active
    sentinel_quality_gate_enforcement.labels(site_id=_site, enforcement="normal").set(1)
    sentinel_quality_gate_enforcement.labels(site_id=_site, enforcement="cap_confidence").set(0)
    sentinel_quality_gate_enforcement.labels(site_id=_site, enforcement="suppress_tier3").set(0)
    sentinel_quality_gate_enforcement.labels(site_id=_site, enforcement="block_writes").set(0)

    # Recommendations
    sentinel_recommendations_total.labels(site_id=_site, tier="tier1", action="auto_execute").inc(87)
    sentinel_recommendations_total.labels(site_id=_site, tier="tier2", action="pending_approval").inc(34)
    sentinel_recommendations_total.labels(site_id=_site, tier="tier3", action="advisory").inc(12)
    sentinel_recommendations_total.labels(site_id=_site, tier="tier3", action="blocked").inc(2)

    # Approvals
    sentinel_approval_decisions_total.labels(site_id=_site, decision="approved").inc(31)
    sentinel_approval_decisions_total.labels(site_id=_site, decision="rejected").inc(2)
    sentinel_approval_decisions_total.labels(site_id=_site, decision="expired").inc(1)

    # Safety — zero violations (healthy state)
    sentinel_safety_violations_total.labels(site_id=_site, severity="warning").inc(0)
    sentinel_safety_violations_total.labels(site_id=_site, severity="block").inc(0)
    sentinel_safety_violations_total.labels(site_id=_site, severity="alarm").inc(0)

    # Drift — no active alerts
    sentinel_model_drift_alerts.labels(site_id=_site, model_type="AHU").set(0)
    sentinel_model_drift_alerts.labels(site_id=_site, model_type="CHILLER").set(0)
    sentinel_model_drift_alerts.labels(site_id=_site, model_type="FCU").set(0)

    # Rollbacks — zero
    sentinel_rollback_total.labels(site_id=_site, equipment_type="CHILLER").inc(0)
    sentinel_rollback_total.labels(site_id=_site, equipment_type="AHU").inc(0)


# ---------------------------------------------------------------------------
# IP allowlist — restrict /metrics to local / Docker networks
# ---------------------------------------------------------------------------
_ALLOWED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),  # localhost
    ipaddress.ip_network("10.0.0.0/8"),  # Docker default bridge / overlay
    ipaddress.ip_network("172.16.0.0/12"),  # Docker bridge range
    ipaddress.ip_network("192.168.0.0/16"),  # Private LAN
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
]

# Allow override via env var (comma-separated CIDRs)
_EXTRA_CIDRS = os.getenv("METRICS_ALLOWED_CIDRS", "")
if _EXTRA_CIDRS:
    for cidr in _EXTRA_CIDRS.split(","):
        cidr = cidr.strip()
        if cidr:
            _ALLOWED_NETWORKS.append(ipaddress.ip_network(cidr, strict=False))


def _is_allowed(client_ip: str) -> bool:
    """Return True if client IP is in the allowlist."""
    try:
        addr = ipaddress.ip_address(client_ip)
        return any(addr in net for net in _ALLOWED_NETWORKS)
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
@router.get(
    "/metrics",
    response_class=PlainTextResponse,
    tags=["monitoring"],
    summary="Prometheus metrics endpoint",
    description="Returns AI governance metrics in Prometheus text exposition format.",
)
async def prometheus_metrics(request: Request) -> PlainTextResponse:
    """Serve Prometheus-format metrics.

    No authentication required (Prometheus scrape needs unauthenticated access).
    Access is restricted by IP allowlist (localhost, Docker networks, private LAN).
    """
    client_ip = request.client.host if request.client else "127.0.0.1"

    if not _is_allowed(client_ip):
        return PlainTextResponse(
            content="# Access denied: client IP not in allowlist\n",
            status_code=403,
            media_type="text/plain",
        )

    # Seed demo values on first request (only in DEMO_MODE)
    if _DEMO_MODE:
        _seed_demo_values()

    # Generate Prometheus text exposition
    output = generate_latest(REGISTRY)
    return PlainTextResponse(
        content=output.decode("utf-8"),
        status_code=200,
        media_type=CONTENT_TYPE_LATEST,
    )

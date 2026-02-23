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
# Static info set once at import time
# ---------------------------------------------------------------------------
_MODE = os.getenv("SENTINEL_MODE", "simulation")
_VERSION = os.getenv("APP_VERSION", "13.2")
_BUILD_DATE = os.getenv("BUILD_DATE", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

sentinel_info.info(
    {
        "version": _VERSION,
        "mode": _MODE,
        "build_date": _BUILD_DATE,
    }
)

# ---------------------------------------------------------------------------
# Seed demo values so the endpoint is non-empty before real hooks are wired.
# These will be superseded once service-level instrumentation lands (Phase 2).
# ---------------------------------------------------------------------------
_DEMO_SEEDED = False


def _seed_demo_values() -> None:
    """Populate counters with representative demo data (idempotent)."""
    global _DEMO_SEEDED
    if _DEMO_SEEDED:
        return
    _DEMO_SEEDED = True

    # Quality gate evaluations
    sentinel_quality_gate_evaluations_total.labels(site_id="site-002", status="pass").inc(142)
    sentinel_quality_gate_evaluations_total.labels(site_id="site-002", status="warn").inc(18)
    sentinel_quality_gate_evaluations_total.labels(site_id="site-002", status="fail").inc(3)

    # Enforcement gauge — normal is active
    sentinel_quality_gate_enforcement.labels(site_id="site-002", enforcement="normal").set(1)
    sentinel_quality_gate_enforcement.labels(site_id="site-002", enforcement="cap_confidence").set(0)
    sentinel_quality_gate_enforcement.labels(site_id="site-002", enforcement="suppress_tier3").set(0)
    sentinel_quality_gate_enforcement.labels(site_id="site-002", enforcement="block_writes").set(0)

    # Recommendations
    sentinel_recommendations_total.labels(site_id="site-002", tier="tier1", action="auto_execute").inc(87)
    sentinel_recommendations_total.labels(site_id="site-002", tier="tier2", action="pending_approval").inc(34)
    sentinel_recommendations_total.labels(site_id="site-002", tier="tier3", action="advisory").inc(12)
    sentinel_recommendations_total.labels(site_id="site-002", tier="tier3", action="blocked").inc(2)

    # Approvals
    sentinel_approval_decisions_total.labels(site_id="site-002", decision="approved").inc(31)
    sentinel_approval_decisions_total.labels(site_id="site-002", decision="rejected").inc(2)
    sentinel_approval_decisions_total.labels(site_id="site-002", decision="expired").inc(1)

    # Safety — zero violations (healthy state)
    sentinel_safety_violations_total.labels(site_id="site-002", severity="warning").inc(0)
    sentinel_safety_violations_total.labels(site_id="site-002", severity="block").inc(0)
    sentinel_safety_violations_total.labels(site_id="site-002", severity="alarm").inc(0)

    # Drift — no active alerts
    sentinel_model_drift_alerts.labels(site_id="site-002", model_type="AHU").set(0)
    sentinel_model_drift_alerts.labels(site_id="site-002", model_type="CHILLER").set(0)
    sentinel_model_drift_alerts.labels(site_id="site-002", model_type="FCU").set(0)

    # Rollbacks — zero
    sentinel_rollback_total.labels(site_id="site-002", equipment_type="CHILLER").inc(0)
    sentinel_rollback_total.labels(site_id="site-002", equipment_type="AHU").inc(0)


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

    # Seed demo values on first request
    _seed_demo_values()

    # Generate Prometheus text exposition
    output = generate_latest(REGISTRY)
    return PlainTextResponse(
        content=output.decode("utf-8"),
        status_code=200,
        media_type=CONTENT_TYPE_LATEST,
    )

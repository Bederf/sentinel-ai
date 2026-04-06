"""Prometheus-format /metrics endpoint for AI governance observability.

Exposes SENTINEL AI control metrics in Prometheus text exposition format
for scraping by Prometheus/Victoria Metrics.

Phase 114-05: Creates the endpoint structure with static baseline values.
Real metric collection hooks into existing services will be wired in
Phase 2 (Control Implementation) per compliance.md roadmap.
"""

from __future__ import annotations

import ipaddress
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
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

from app.config.settings import settings
from app.middleware.auth_middleware import require_auth
from app.models.auth import AuthContext, AuthLevel

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
# FM / Media Wall metrics (Phase 144 — Building Intelligence Dashboard)
# ---------------------------------------------------------------------------

# 17. Active alerts by severity and building
sentinel_alerts = Gauge(
    "sentinel_alerts",
    "Active alerts by severity and building",
    labelnames=["severity", "building", "status"],
    registry=REGISTRY,
)

# 18. Job cards by status and outcome
sentinel_job_cards = Gauge(
    "sentinel_job_cards",
    "Job card records by building, status, and outcome",
    labelnames=["building", "status", "outcome"],
    registry=REGISTRY,
)

# 19. Job cards created total (counter for rate calculations)
sentinel_job_cards_created_total = Counter(
    "sentinel_job_cards_created_total",
    "Total job cards created by building",
    labelnames=["building"],
    registry=REGISTRY,
)

# 20. SLA met count
sentinel_sla_met = Gauge(
    "sentinel_sla_met",
    "Count of SLA-compliant completed jobs by building",
    labelnames=["building"],
    registry=REGISTRY,
)

# 21. Critical response time
sentinel_critical_response_time_seconds = Gauge(
    "sentinel_critical_response_time_seconds",
    "Average response time for critical alerts in seconds",
    labelnames=["severity", "building"],
    registry=REGISTRY,
)

# 22. Equipment health status
sentinel_equipment_health = Gauge(
    "sentinel_equipment_health",
    "Equipment health status gauge (1 = in this state)",
    labelnames=["building", "equipment", "health"],
    registry=REGISTRY,
)

# 23. Equipment issues (for table panel)
sentinel_equipment_issues = Gauge(
    "sentinel_equipment_issues",
    "Active equipment issues with details",
    labelnames=["building", "equipment", "issue", "severity"],
    registry=REGISTRY,
)

# 24. Maintenance backlog in days
sentinel_maintenance_backlog_days = Gauge(
    "sentinel_maintenance_backlog_days",
    "Days of pending maintenance work per building",
    labelnames=["building"],
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Phase 160 — AI Governance Metrics (5 new families)
# ---------------------------------------------------------------------------

# 25. Quality gate pass/fail per rule (supplements #1 which tracks by site/status)
sentinel_quality_gate_rule_evaluations_total = Counter(
    "sentinel_quality_gate_rule_evaluations_total",
    "Quality gate evaluations by individual rule and outcome",
    labelnames=["rule_name", "status"],
    registry=REGISTRY,
)

# 26. Model drift score per model (supplements #6 which is alert count)
sentinel_model_drift_score = Gauge(
    "sentinel_model_drift_score",
    "Current drift score per model (0.0-1.0, higher = more drift)",
    labelnames=["model_id", "model_type"],
    registry=REGISTRY,
)

# 27. Tool-call errors by error type (supplements #12 which tracks by outcome)
sentinel_tool_call_errors_total = Counter(
    "sentinel_tool_call_errors_total",
    "Tool call errors by tool name and error classification",
    labelnames=["tool_name", "error_type"],
    registry=REGISTRY,
)

# 28. Approval latency histogram
sentinel_approval_latency_seconds = Histogram(
    "sentinel_approval_latency_seconds",
    "Time from approval request to decision in seconds",
    labelnames=["site_id", "tier"],
    buckets=[1, 5, 15, 30, 60, 120, 300, 600, 1800],
    registry=REGISTRY,
)

# 29. (Removed — rejection rate computed from sentinel_approval_decisions_total counter)

# 30. Token usage by route and site
sentinel_ai_tokens_by_route_total = Counter(
    "sentinel_ai_tokens_by_route_total",
    "AI tokens consumed by route, site, and provider",
    labelnames=["route", "site_id", "provider"],
    registry=REGISTRY,
)

# 31. Cost by route and site
sentinel_ai_cost_by_route_total = Counter(
    "sentinel_ai_cost_by_route_total",
    "AI cost in USD by route and site",
    labelnames=["route", "site_id"],
    registry=REGISTRY,
)

# 32. Retrieval latency histogram (canonical/hybrid retrieval paths)
sentinel_retrieval_latency_seconds = Histogram(
    "sentinel_retrieval_latency_seconds",
    "Retrieval query latency by retrieval path and fallback mode",
    labelnames=["retrieval_path", "fallback"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
    registry=REGISTRY,
)

# 33. Retrieval hit counter
sentinel_retrieval_hits_total = Counter(
    "sentinel_retrieval_hits_total",
    "Total retrieval hits returned by retrieval path and fallback mode",
    labelnames=["retrieval_path", "fallback"],
    registry=REGISTRY,
)

# 34. Retrieval fallback usage counter
sentinel_retrieval_fallbacks_total = Counter(
    "sentinel_retrieval_fallbacks_total",
    "Total retrieval fallback activations by fallback type",
    labelnames=["fallback"],
    registry=REGISTRY,
)


_site_name_cache: dict[str, str] = {}


def _resolve_site_name(client, site_id: str) -> str:
    """Resolve site UUID to readable name, with caching."""
    if not site_id or site_id == "None":
        return "unknown"
    if site_id in _site_name_cache:
        return _site_name_cache[site_id]
    try:
        resp = client.table("sites").select("name, code").eq("id", site_id).limit(1).execute()
        if resp.data:
            name = resp.data[0].get("code") or resp.data[0].get("name") or site_id
            _site_name_cache[site_id] = name
            return name
    except Exception:
        pass
    _site_name_cache[site_id] = site_id
    return site_id


def _collect_fm_metrics() -> None:
    """Collect FM metrics from Supabase for the media wall dashboard.

    Called on each /metrics scrape to provide fresh data.
    Gauges are reset and re-populated from live database queries.
    """
    import logging

    logger = logging.getLogger("sentinel.metrics")

    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        if not client:
            return
    except Exception:
        return

    # --- Alerts by severity and building ---
    try:
        alerts_resp = client.table("alerts").select("severity, site_id").eq("status", "active").execute()
        # Reset alert gauges
        sentinel_alerts._metrics.clear()

        if alerts_resp.data:
            # Count by severity and building
            alert_counts: dict[tuple[str, str], int] = {}
            for alert in alerts_resp.data:
                sev = alert.get("severity", "info")
                building = _resolve_site_name(client, alert.get("site_id", ""))
                key = (sev, building)
                alert_counts[key] = alert_counts.get(key, 0) + 1

            for (sev, building), count in alert_counts.items():
                sentinel_alerts.labels(severity=sev, building=building, status="active").set(count)
    except Exception as e:
        logger.debug(f"FM metrics: alerts query failed: {e}")

    # --- Equipment health ---
    try:
        equip_resp = client.table("equipment").select("code, name, health_score, site_id, status").execute()
        sentinel_equipment_health._metrics.clear()
        sentinel_equipment_issues._metrics.clear()

        if equip_resp.data:
            building_degrading: dict[str, int] = {}
            for eq in equip_resp.data:
                health = eq.get("health_score")
                if health is None:
                    continue
                site = _resolve_site_name(client, eq.get("site_id", ""))
                code = eq.get("code", "unknown")
                status = eq.get("status", "unknown")

                if health < 50:
                    state = "critical"
                elif health < 75:
                    state = "degrading"
                    building_degrading[site] = building_degrading.get(site, 0) + 1
                else:
                    state = "healthy"

                sentinel_equipment_health.labels(building=site, equipment=code, health=state).set(1)

                # Populate issues table for degrading/critical
                if state in ("critical", "degrading"):
                    issue_text = f"Health score {health}% — {status}"
                    sentinel_equipment_issues.labels(
                        building=site,
                        equipment=code,
                        issue=issue_text,
                        severity="critical" if state == "critical" else "warning",
                    ).set(1)
    except Exception as e:
        logger.debug(f"FM metrics: equipment query failed: {e}")

    # --- Work orders (job cards) ---
    try:
        wo_resp = client.table("work_orders").select("site_id, status, priority, created_at, completed_at").execute()
        sentinel_job_cards._metrics.clear()
        sentinel_sla_met._metrics.clear()
        sentinel_maintenance_backlog_days._metrics.clear()

        if wo_resp.data:
            # Count by building + status
            wo_counts: dict[tuple[str, str], int] = {}
            completed_by_building: dict[str, int] = {}
            sla_met_by_building: dict[str, int] = {}
            open_by_building: dict[str, int] = {}

            for wo in wo_resp.data:
                site = _resolve_site_name(client, wo.get("site_id", ""))
                status = wo.get("status", "open")
                wo_counts[(site, status)] = wo_counts.get((site, status), 0) + 1

                if status == "completed":
                    completed_by_building[site] = completed_by_building.get(site, 0) + 1
                    # SLA: completed within 48h = met
                    created = wo.get("created_at")
                    completed = wo.get("completed_at")
                    if created and completed:
                        try:
                            from datetime import datetime as dt

                            c = dt.fromisoformat(created.replace("Z", "+00:00"))
                            d = dt.fromisoformat(completed.replace("Z", "+00:00"))
                            if (d - c).total_seconds() < 172800:  # 48h
                                sla_met_by_building[site] = sla_met_by_building.get(site, 0) + 1
                        except Exception:
                            pass
                elif status in ("open", "in_progress", "assigned"):
                    open_by_building[site] = open_by_building.get(site, 0) + 1

            for (site, status), count in wo_counts.items():
                outcome = "first_fix" if status == "completed" else "pending"
                sentinel_job_cards.labels(building=site, status=status, outcome=outcome).set(count)

            for site, count in sla_met_by_building.items():
                sentinel_sla_met.labels(building=site).set(count)

            # Backlog = open work orders (rough proxy for days)
            for site, count in open_by_building.items():
                sentinel_maintenance_backlog_days.labels(building=site).set(count)
    except Exception as e:
        logger.debug(f"FM metrics: work orders query failed: {e}")


# ---------------------------------------------------------------------------
# Static info set once at import time
# ---------------------------------------------------------------------------
_MODE = os.getenv("SENTINEL_MODE", settings.resolved_ingestion_mode.value)
_VERSION = os.getenv("APP_VERSION", settings.app_version)
_BUILD_DATE = os.getenv("BUILD_DATE", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

sentinel_info.info(
    {
        "version": _VERSION,
        "mode": _MODE,
        "build_date": _BUILD_DATE,
        "config_checksum": settings.config_checksum,
    }
)

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
    dependencies=[Depends(require_auth(AuthLevel.AUTHENTICATED))],
)
async def prometheus_metrics(
    request: Request,
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
) -> PlainTextResponse:
    """Serve Prometheus-format metrics.

    Requires AUTHENTICATED level (AUDITOR role or higher) for access.
    Phase 168-01: Closed MONITORING-001 gap by adding authentication requirement.
    """
    # Authentication check is done via require_auth dependency above
    # client_ip check removed - role-based access now the primary control

    # Collect live FM metrics from Supabase (media wall dashboard)
    try:
        _collect_fm_metrics()
    except Exception:
        pass  # Never let metrics collection crash the endpoint

    # Generate Prometheus text exposition
    output = generate_latest(REGISTRY)
    return PlainTextResponse(
        content=output.decode("utf-8"),
        status_code=200,
        media_type=CONTENT_TYPE_LATEST,
    )

---
title: "AI Monitoring and Metrics Governance"
type: "guide"
status: "active"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
tags: ["ai-governance", "monitoring", "metrics", "prometheus", "alerts"]
domain: "compliance"
audience: "all"
complexity: "advanced"
estimated_read_time: 15
---

# AI Monitoring and Metrics Governance

## Current State (Updated 2026-02-26, Phases 127 + 125)

- AI health and drift are exposed via JSON APIs under `backend/app/api/mlops.py`.
- Audit/decision telemetry is strong in log-based observability (Loki/Promtail/Grafana).
- Prometheus runs from `/opt/aimthelaw` (`docker-compose.monitoring.yml`), scraping SENTINEL every 30s.
- **16 Prometheus metric families** at `/metrics` endpoint (`backend/app/api/metrics.py`): 8 AI governance + 3 HTTP request + 2 tool-call + 3 database/cache (Phase 125).
- **7 of 8 AI governance metrics wired to production code** (Phase 127). Only approval `expired` has no code path (no expiry mechanism exists).
- **RequestMetricsMiddleware** (`backend/app/middleware/request_metrics.py`) captures all HTTP routes.
- **Tool-call instrumentation** in `chat_tools.execute_tool()` tracks duration + success/fail per tool.
- **Database/cache instrumentation** (Phase 125): Supabase query duration histogram, cache hit/miss/error counter, cache hit rate gauge.
- Monitoring stack fully running: Prometheus, Grafana, Loki, Promtail, Node Exporter.

## Observability Gaps

| Gap | Current Evidence | Status |
|---|---|---|
| Prometheus backend scraping for AI controls is incomplete | `/opt/aimthelaw/config/prometheus.yml` now includes `sentinel-backend` scrape job | **RESOLVED** -- scrape target validated `UP` (`2026-02-23`) |
| No canonical Prometheus exposition for AI controls | `/api/mlops/metrics` returns JSON (not Prometheus text format) | **RESOLVED** -- `/metrics` endpoint ships Prometheus text format |
| Alerting focuses on log events | `/opt/aimthelaw/config/grafana/provisioning/alerting/sentinel-ai-governance-alert-rules.yml` | **RESOLVED** -- 4 AI governance alert rules provisioned (`2026-02-23`) |
| Cost/approval metrics are not standardized | Mixed APIs and logs | **RESOLVED** -- 16 stable metric families defined and wired (Phases 127 + 125) |
| Metrics defined but not wired to production code | 8 counters/gauges existed as dead code | **RESOLVED** -- 7 of 8 wired to services, 5 new metrics added (Phase 127) |

## Prometheus Metrics

The `/metrics` endpoint (`backend/app/api/metrics.py`) exposes the following AI governance metrics in Prometheus text exposition format.

### AI Governance Metrics (1-8)

| # | Metric Name | Type | Labels | Description | Wired |
|---|---|---|---|---|---|
| 1 | `sentinel_quality_gate_evaluations_total` | Counter | `site_id`, `status` (pass/warn/fail) | Total quality-gate evaluations by site and outcome | `quality_gate_evaluator.py` |
| 2 | `sentinel_quality_gate_enforcement` | Gauge | `site_id`, `enforcement` (normal/cap_confidence/suppress_tier3/block_writes) | Current enforcement level per site (1 = active) | `quality_gate_evaluator.py` |
| 3 | `sentinel_recommendations_total` | Counter | `site_id`, `tier` (tier1/tier2/tier3), `action` (advisory/pending_approval/auto_execute/blocked) | Total recommendations by site, tier, and action disposition | `tier_routing_engine.py` |
| 4 | `sentinel_approval_decisions_total` | Counter | `site_id`, `decision` (approved/rejected/expired) | Total approval workflow decisions by site and outcome | `approval_service.py` |
| 5 | `sentinel_safety_violations_total` | Counter | `site_id`, `severity` (warning/block/alarm) | Total safety boundary violations by site and severity | `safety_interlocks.py` |
| 6 | `sentinel_model_drift_alerts` | Gauge | `site_id`, `model_type` | Active model drift alerts by site and model type | `background_scheduler.py` |
| 7 | `sentinel_rollback_total` | Counter | `site_id`, `equipment_type` | Total automated rollback events by site and equipment type | `approval_service.py` |
| 8 | `sentinel_info` | Info | `version`, `mode`, `build_date` | SENTINEL build and configuration metadata | `metrics.py` (static) |

### HTTP Request Metrics (9-11, Phase 127)

| # | Metric Name | Type | Labels | Description | Wired |
|---|---|---|---|---|---|
| 9 | `sentinel_http_requests_total` | Counter | `method`, `path`, `status_code` | Total HTTP requests (path normalized) | `request_metrics.py` |
| 10 | `sentinel_http_request_duration_seconds` | Histogram | `method`, `path` | HTTP request duration (9 buckets: 10ms-10s) | `request_metrics.py` |
| 11 | `sentinel_http_requests_in_progress` | Gauge | — | Number of HTTP requests currently being processed | `request_metrics.py` |

### Tool-Call Metrics (12-13, Phase 127)

| # | Metric Name | Type | Labels | Description | Wired |
|---|---|---|---|---|---|
| 12 | `sentinel_tool_calls_total` | Counter | `tool_name`, `outcome` (success/error) | Total tool calls by tool name and outcome | `chat_tools.py` |
| 13 | `sentinel_tool_call_duration_seconds` | Histogram | `tool_name` | Tool call execution duration (9 buckets: 50ms-30s) | `chat_tools.py` |

### Database & Cache Metrics (14-16, Phase 125)

| # | Metric Name | Type | Labels | Description | Wired |
|---|---|---|---|---|---|
| 14 | `sentinel_db_query_duration_seconds` | Histogram | `repository`, `method` | Supabase PostgREST query duration (9 buckets: 5ms-2.5s) | `cache_service.py` via `track_query()` context manager |
| 15 | `sentinel_cache_operations_total` | Counter | `operation` (hit/miss/error) | Redis cache operations by outcome | `cache_service.py` |
| 16 | `sentinel_cache_hit_rate_percent` | Gauge | — | Current cache hit rate percentage | `cache_service.py` |

Repositories instrumented with `track_query()`: `equipment` (get_all, get_by_id), `building` (get_all, get_by_id), `alert` (get_active_by_building).

### Scrape Configuration

Add the following job to `/opt/aimthelaw/config/prometheus.yml`:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: "sentinel-backend"
    scrape_interval: 30s
    metrics_path: /metrics
    static_configs:
      - targets: ["bms-intelligence_backend:9095"]
        labels:
          instance: "sentinel"
          environment: "production"
```

### Access Control

The `/metrics` endpoint uses an IP allowlist (no authentication required for Prometheus scrape compatibility):

- `127.0.0.0/8` (localhost)
- `10.0.0.0/8` (Docker default bridge / overlay)
- `172.16.0.0/12` (Docker bridge range)
- `192.168.0.0/16` (private LAN)
- `::1/128` (IPv6 loopback)

Additional CIDRs can be added via the `METRICS_ALLOWED_CIDRS` environment variable (comma-separated).

## Grafana Dashboard

Recommended panels for the SENTINEL AI Governance dashboard:

### Quality Gate Pass Rate (Time Series)

- **Query:** `rate(sentinel_quality_gate_evaluations_total{status="pass"}[5m]) / rate(sentinel_quality_gate_evaluations_total[5m])`
- **Thresholds:** Green >= 0.95, Yellow >= 0.80, Red < 0.80
- **Description:** Percentage of quality gate evaluations passing over time. Drops below 95% indicate degrading control effectiveness.

### Recommendation Tier Distribution (Pie Chart)

- **Query:** `sum by (tier) (sentinel_recommendations_total)`
- **Description:** Distribution of recommendations across tiers. A healthy system should have tier1 > tier2 > tier3. High tier3 volume may indicate over-cautious gating.

### Safety Violation Count (Stat Panel)

- **Query:** `sum(sentinel_safety_violations_total)`
- **Target:** 0 (any non-zero value triggers investigation)
- **Thresholds:** Green = 0, Red > 0
- **Description:** Total safety boundary violations. This should always be zero in a healthy system.

### Model Drift Alerts (Time Series)

- **Query:** `sentinel_model_drift_alerts`
- **Threshold line:** 0 (any positive value = active drift)
- **Description:** Active model drift alerts by model type. Persistent drift (> 7 days) triggers retraining review.

### Approval Latency P95 (Gauge)

- **Query:** `histogram_quantile(0.95, rate(sentinel_approval_decisions_total[1h]))`
- **Thresholds:** Green < 4h, Yellow < 24h, Red >= 24h
- **Description:** 95th percentile time from recommendation to approval decision. Long latency indicates approval workflow bottlenecks.
- **Note:** Full latency histogram will be added in Phase 2 when real service hooks are wired.

## Alert Rules

Alert rules mapping metrics to runbooks for operational response:

### 1. Safety Violation Alert

```yaml
- alert: SentinelSafetyViolation
  expr: rate(sentinel_safety_violations_total[5m]) > 0
  for: 0m  # immediate
  labels:
    severity: critical
  annotations:
    summary: "Safety boundary violation detected at {{ $labels.site_id }}"
    runbook: "docs/06-safety-compliance/safety-interlocks-engine.md"
    action: "Page on-call engineer immediately. Check equipment logs and disable automatic control if needed."
```

### 2. Model Drift Persistent Alert

```yaml
- alert: SentinelModelDriftPersistent
  expr: sentinel_model_drift_alerts > 0
  for: 7d
  labels:
    severity: warning
  annotations:
    summary: "Model drift active for 7+ days: {{ $labels.model_type }} at {{ $labels.site_id }}"
    runbook: "docs/08-ai-ml/write-policy-and-rollout.md"
    action: "Notify ML lead. Review model performance and schedule retraining if accuracy below threshold."
```

### 3. Quality Gate Block Writes Alert

```yaml
- alert: SentinelQualityGateBlockWrites
  expr: sentinel_quality_gate_enforcement{enforcement="block_writes"} == 1
  for: 0m  # immediate
  labels:
    severity: critical
  annotations:
    summary: "Quality gate enforcing BLOCK_WRITES at {{ $labels.site_id }}"
    runbook: "docs/ai-governance/06-human-oversight-and-approval.md"
    action: "Page ops team. All AI writes are blocked. Investigate quality gate failure and activate kill switch if needed."
```

### 4. Rollback Rate Alert

```yaml
- alert: SentinelHighRollbackRate
  expr: rate(sentinel_rollback_total[1h]) > 2
  for: 15m
  labels:
    severity: warning
  annotations:
    summary: "High rollback rate (>2/hr) for {{ $labels.equipment_type }} at {{ $labels.site_id }}"
    runbook: "docs/ai-governance/07-incident-and-rollback.md"
    action: "Notify operations. Investigate equipment behavior and consider disabling automatic optimization."
```

### Alert Routing Summary

| Metric | Condition | Severity | Action | Runbook |
|---|---|---|---|---|
| `sentinel_safety_violations_total` | rate > 0 | Critical | Page on-call | `docs/06-safety-compliance/safety-interlocks-engine.md` |
| `sentinel_model_drift_alerts` | > 0 for 7d | Warning | Notify ML lead | `docs/08-ai-ml/write-policy-and-rollout.md` |
| `sentinel_quality_gate_enforcement{enforcement="block_writes"}` | == 1 | Critical | Page ops | Kill switch playbook |
| `sentinel_rollback_total` | rate > 2/hr | Warning | Notify ops | `docs/ai-governance/07-incident-and-rollback.md` |

## Evidence and Ownership

- **Metrics endpoint:** `backend/app/api/metrics.py`
- **Dashboards:** `/opt/aimthelaw/config/grafana/provisioning/dashboards/sentinel-ai-governance.json`
- **Alerting rules:** `/opt/aimthelaw/config/grafana/provisioning/alerting/sentinel-ai-governance-alert-rules.yml`
- **Evidence snapshots:** `docs/ai-governance/evidence/drift-reports/`
- **Validation evidence:** `docs/ai-governance/evidence/monitoring/2026-02-23-prometheus-grafana-validation.md`
- **Owner:** AI Engineering + Operations

## Cross-Repo Note

In `/opt/aimthelaw/config/prometheus.yml`, the `sentinel-backend` scrape job is enabled and validated. Treat this as shared platform work between `bms-intelligence` (metric exposition) and `aimthelaw` (scrape/alerts).

## Phase 2 Roadmap

**Completed (Phase 127, 2026-02-26):**

- ~~Wire real metric collection hooks into existing services~~ — 7 of 8 AI governance metrics wired, RequestMetricsMiddleware added, tool-call instrumentation added
- ~~Add histogram metrics for approval latency and recommendation processing time~~ — HTTP duration + tool-call duration histograms added

**Remaining (Control Implementation, 2026-04-01 to 2026-05-31):**

- Wire approval `expired` counter (requires building an expiry mechanism first)
- Gather 14 consecutive days of scrape stability evidence for gate closure
- Tune alert thresholds against production baseline
- Add dedicated approval latency histogram (current counter tracks decisions, not duration)

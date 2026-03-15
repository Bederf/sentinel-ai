---
title: AI Governance Metrics — Prometheus Instrumentation & POPIA Evidence
status: Active
version: 1.0
created: 2026-03-15
updated: 2026-03-15
phases: 160
tags: [governance, prometheus, popia, compliance, ml-drift, grafana]
domain: compliance
audience: operators
complexity: intermediate
estimated_read_time: 8
---

# AI Governance Metrics

## Overview

Phase 160 adds five Prometheus metric families that track AI governance health: quality gate pass/fail rates, model drift scores, tool-call error rates, approval latency, and AI token/cost breakdowns by route. A POPIA evidence pack generator produces monthly compliance snapshots, and six Grafana dashboard panels visualise the metrics in real time.

**42 tests** across three test files cover the collector, POPIA evidence pack, drift calculator, and REST API.

## Metric Families

| # | Metric | Type | Labels | Source |
|---|--------|------|--------|--------|
| 25 | `sentinel_quality_gate_rule_evaluations_total` | Counter | `rule_name`, `status` | `quality_gate_evaluator.py` |
| 26 | `sentinel_model_drift_score` | Gauge | `model_id`, `model_type` | `model_drift_calculator.py` |
| 27 | `sentinel_tool_call_errors_total` | Counter | `tool_name`, `error_type` | `chat_tools.py` |
| 28 | `sentinel_approval_latency_seconds` | Histogram | `site_id`, `tier` | `approval_service.py` |
| 29 | `sentinel_approval_rejection_rate` | Gauge | `site_id` | `approval_service.py` |
| 30 | `sentinel_ai_tokens_by_route_total` | Counter | `route`, `site_id`, `provider` | `ai_usage_tracker.py` |
| 31 | `sentinel_ai_cost_by_route_total` | Counter | `route`, `site_id` | `ai_usage_tracker.py` |

All metrics are emitted best-effort (try/except) via `GovernanceMetricsCollector` with lazy Prometheus imports, bounded label values, and input sanitisation.

## GovernanceMetricsCollector

**File:** `backend/app/services/governance_metrics_collector.py`

The collector is a thin wrapper with six recording methods. Each method validates inputs (clamps values, truncates label strings) and silently drops invalid emissions rather than raising.

Error classification in `chat_tools.py` maps exceptions to five error types: `param_validation`, `timeout`, `permission`, `module_inactive`, and `execution`.

## POPIA Evidence Pack

**File:** `backend/app/services/popia_evidence_pack_service.py`

Generates a monthly compliance evidence pack with four sections:

| Section | Content |
|---------|---------|
| **Consent** | Total consent records, granted/declined counts, grant rate |
| **Retention** | Retention run count, records purged/retained |
| **DSR** | Data subject request count, completion rate, average SLA days |
| **Access Control** | Audit event counts (placeholder — wired when audit events instrumented) |

Packs are stored FIFO-capped at 24 entries (two years of monthly snapshots). Data is aggregated from existing JSON data files (`consent_records.json`, `popia_retention_runs.json`, `privacy_requests.json`).

## Model Drift Calculator

**File:** `backend/app/ml/models/model_drift_calculator.py`

Computes per-model drift scores using:

```
drift = max(0, min(1, 1 - recent_r_squared / max(baseline_r_squared, 0.01)))
```

Alert thresholds:

| Level | Score Range |
|-------|------------|
| `ok` | 0.0 -- 0.3 |
| `warning` | 0.3 -- 0.6 |
| `critical` | 0.6 -- 1.0 |

Edge cases (baseline <= 0, negative r-squared, None model_id) all produce valid clamped scores.

## REST API Endpoints

All endpoints are under `/api/governance/` and registered in `backend/app/api/governance_metrics_api.py`.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/governance/quality-gate-rules` | GET | Per-rule pass/fail/warn counts from Prometheus registry |
| `/api/governance/drift-scores` | GET | Model drift scores with alert levels; filters models above threshold (default 0.3) |
| `/api/governance/approval-latency` | GET | p50/p95/p99 latency percentiles approximated from histogram buckets |
| `/api/governance/cost-by-route` | GET | Token and cost breakdown per API route from Prometheus counters |
| `/api/governance/popia-evidence` | GET | Monthly POPIA evidence pack; optional `year` and `month` query params (defaults to current month) |

## Grafana Dashboard

Six panels added to `infrastructure/grafana/provisioning/dashboards/sentinel-ai-governance.json` in a dedicated row titled **Phase 160 — AI Governance Metrics** (panel IDs 9--15).

| Panel | Visualisation | PromQL |
|-------|--------------|--------|
| Quality Gate Pass/Fail by Rule | Stacked timeseries | `sum by (rule_name, status) (rate(sentinel_quality_gate_rule_evaluations_total[5m]))` |
| Model Drift Score Trends | Timeseries | `sentinel_model_drift_score` |
| Tool Error Rate by Type | Bar chart | `sum by (error_type) (rate(sentinel_tool_call_errors_total[5m]))` |
| Approval Latency Distribution | Histogram | `sentinel_approval_latency_seconds_bucket` |
| AI Cost per Route | Bar chart | `sum by (route) (sentinel_ai_cost_by_route_total)` |
| POPIA Evidence Pack Status | Stat | `sentinel_popia_evidence_pack_generated_total` |

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/api/metrics.py` | Prometheus metric definitions (metrics 25--31) |
| `backend/app/services/governance_metrics_collector.py` | Best-effort metric emission |
| `backend/app/services/popia_evidence_pack_service.py` | Monthly POPIA evidence aggregator |
| `backend/app/ml/models/model_drift_calculator.py` | Per-model drift scoring |
| `backend/app/api/governance_metrics_api.py` | REST API router |
| `infrastructure/grafana/provisioning/dashboards/sentinel-ai-governance.json` | Grafana panels |
| `backend/tests/services/test_governance_metrics_collector.py` | 13 collector tests |
| `backend/tests/services/test_popia_evidence_pack.py` | 6 evidence pack tests |
| `backend/tests/ml/test_model_drift_calculator.py` | 12 drift calculator tests |
| `backend/tests/api/test_governance_metrics_api.py` | 11 API tests |

## Related Documentation

- [AI Cost Tracking](ai-cost-tracking.md) — per-provider cost tracking (v48.0)
- [Safety Interlocks Engine](../06-safety-compliance/safety-interlocks-engine.md) — safety violation metrics
- [Monitoring Stack](../10-operations/monitoring-stack.md) — Prometheus/Grafana deployment
- [POPIA Compliance Register](../compliance/popia-compliance-register.md) — POPIA controls and evidence

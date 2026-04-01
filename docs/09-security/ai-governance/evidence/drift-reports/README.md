# Drift Report Evidence

**Collection date:** 2026-02-23 (framework established)
**Collector:** SENTINEL Governance Team
**Review cycle:** Monthly (1st of month)

## Collection Status

Drift reports are collected monthly via automated Prometheus metric export and manual review.

**Current status:** Framework ready, first collection scheduled for 2026-03-01.

## Drift Monitoring Infrastructure

| Component | Location | Metrics |
|-----------|----------|---------|
| Quality Gate Evaluator | `backend/app/services/quality_gate_evaluator.py` | 14 metrics across 5 services |
| Quality Gate Policy | `backend/app/services/quality_gate_policy.py` | 42 threshold entries (14 metrics x 3 modes) |
| MLOps Health Endpoint | `GET /api/ml/health` | drift_critical_alerts_24h, feedback_capture_rate_7d_pct |
| Training Readiness | `GET /api/ml/training-readiness` | Mode-aware thresholds for retraining triggers |

## Expected Report Contents

Each monthly drift report will contain:

1. **Per-model drift metrics:** Feature distribution shifts, prediction confidence trends
2. **Quality gate pass rates:** 14-metric evaluation results aggregated over the month
3. **Threshold breaches:** Any metrics that crossed warning/critical thresholds
4. **Action log:** Drift-triggered retraining events or model version changes
5. **Comparison:** Month-over-month trend for key stability indicators

## Why No Reports Yet

SENTINEL is currently operating in `shadow_live` mode (Phase 116 compliance status). Monthly drift collection requires:
- Stable Prometheus scrape for at least 14 consecutive days (compliance.md Phase 2 gate item)
- First management review cycle to validate report format

Target: First drift report collection 2026-03-01.

## Compliance Mapping

| Framework | Control | Evidence |
|-----------|---------|----------|
| ISO 42001 | A.6.2.6 (Monitoring and measurement) | Drift detection metrics |
| NIST AI RMF | MS 2.6 (Residual risk) | Model stability tracking |
| NIST AI RMF | GV 6.1 (Metrics and monitoring) | Governance metrics dashboard |

# Quality Gate API Reference

**Base URL:** `http://localhost:9095/api`
**Authentication:** Bearer token (JWT)
**Source:** `backend/app/api/optimization_quality.py`

---

## Overview

The Quality Gate evaluates 14 metrics against mode-specific thresholds to determine whether the PARASITE recommendation pipeline may execute device writes. The gate is the single decision point for "writes allowed" in live_control.

See [Agent Contract Appendix](../08-ai-ml/agent-contract-appendix.md) for the full 42-entry threshold table and metric definitions.

---

## Endpoints

### GET /api/optimization/quality-gate/{site_id}

Evaluate all 14 quality metrics for a site against the threshold registry for the current ingestion mode.

**Parameters:**

| Name | In | Type | Required | Description |
|------|-----|------|----------|-------------|
| `site_id` | path | string | yes | Site identifier (e.g. `site-002`, `S002`) |

**Response (200 OK):**

```json
{
  "site_id": "site-002",
  "ingestion_mode": "simulation",
  "thresholds_used": "simulation",
  "metric_values": {
    "freshness_minutes": 5.2,
    "ingest_error_rate_pct_1h": 0.0,
    "match_coverage_pct": 92.0,
    "manual_source_pct": 0.0,
    "unmatched_points_pct": 8.0,
    "commissioning_all_gates_passed": 1.0,
    "truth_check_pass_rate_pct": 100.0,
    "consecutive_pass_days": 14.0,
    "mv_accuracy_7d_pct": 85.0,
    "comfort_violation_rate_7d_pct": 2.0,
    "rollback_rate_7d_pct": 0.0,
    "feedback_capture_rate_7d_pct": 95.0,
    "label_lag_p95_hours": 4.0,
    "drift_critical_alerts_24h": 0.0
  },
  "rule_results": [
    {
      "metric": "freshness_minutes",
      "value": 5.2,
      "state": "pass",
      "pass_bound": 1440.0,
      "warn_bound": 4320.0
    }
  ],
  "overall_status": "pass",
  "enforcement_action": "normal",
  "reason_codes": []
}
```

**Response fields:**

| Field | Type | Description |
|-------|------|-------------|
| `site_id` | string | Site evaluated |
| `ingestion_mode` | string | Current mode: `simulation`, `shadow_live`, `live_control` |
| `thresholds_used` | string | Which mode's thresholds were applied |
| `metric_values` | object | Raw values for all 14 metrics |
| `rule_results` | array | Per-metric evaluation with state and bounds |
| `overall_status` | string | `pass`, `warn`, or `fail` |
| `enforcement_action` | string | `normal`, `cap_confidence`, `suppress_tier3`, `block_writes` |
| `reason_codes` | array | Machine-readable codes for any failures |

**Error responses:**

| Status | Condition |
|--------|-----------|
| 404 | Empty or invalid site_id |
| 500 | Metric collection or evaluation failure |

---

## Enforcement actions

The enforcement action determines what the recommendation pipeline does:

| Mode | Gate Result | Enforcement | Effect |
|------|------------|-------------|--------|
| simulation | PASS/WARN | `normal` | Full pipeline runs (simulated writes) |
| simulation | FAIL | `cap_confidence` | Confidence capped at 0.59, forces Tier 1 advisory |
| shadow_live | PASS/WARN | `normal` | Full pipeline runs (no writes regardless) |
| shadow_live | FAIL | `suppress_tier3` | Tier 3 auto-execute disabled |
| live_control | PASS | `normal` | Full pipeline including real device writes |
| live_control | WARN | `suppress_tier3` | Tier 3 disabled, Tier 2 approval still works |
| live_control | FAIL | `block_writes` | All device writes blocked |

See [Write Policy & Rollout](../08-ai-ml/write-policy-and-rollout.md) for the complete mode-by-mode write policy.

---

## Reason codes

When the gate returns WARN or FAIL, reason codes indicate which metrics triggered:

| Code | Triggered by |
|------|-------------|
| `data_freshness_fail` | `freshness_minutes` |
| `ingest_error_rate_fail` | `ingest_error_rate_pct_1h` |
| `match_coverage_fail` | `match_coverage_pct` |
| `json_in_live_fail` | `manual_source_pct` |
| `commissioning_fail` | `commissioning_all_gates_passed` |
| `truth_check_fail` | `truth_check_pass_rate_pct` |
| `mv_accuracy_fail` | `mv_accuracy_7d_pct` |
| `feedback_coverage_fail` | `feedback_capture_rate_7d_pct` |
| `drift_critical_fail` | `drift_critical_alerts_24h` |
| `quality_gate_block` | `unmatched_points_pct`, `consecutive_pass_days`, `comfort_violation_rate_7d_pct`, `rollback_rate_7d_pct`, `label_lag_p95_hours` |

---

## Metric sources

| # | Metric | Source service |
|---|--------|---------------|
| 1 | `freshness_minutes` | MonitoringService |
| 2 | `ingest_error_rate_pct_1h` | MonitoringService |
| 3 | `match_coverage_pct` | MonitoringService |
| 4 | `manual_source_pct` | MonitoringService provenance |
| 5 | `unmatched_points_pct` | MonitoringService |
| 6 | `commissioning_all_gates_passed` | CommissioningService |
| 7 | `truth_check_pass_rate_pct` | CommissioningService |
| 8 | `consecutive_pass_days` | CommissioningService |
| 9 | `mv_accuracy_7d_pct` | MVVerificationService |
| 10 | `comfort_violation_rate_7d_pct` | MVVerificationService |
| 11 | `rollback_rate_7d_pct` | MVVerificationService |
| 12 | `feedback_capture_rate_7d_pct` | MLFeedbackService |
| 13 | `label_lag_p95_hours` | MLFeedbackService |
| 14 | `drift_critical_alerts_24h` | Audit log |

---

## Integration with approval pipeline

The quality gate is checked at two points:

1. **Tier routing** (in `tier_routing_engine.py`): Gate result determines whether Tier 3 is available
2. **Tier 3 execution** (in `approval_service.py`): Gate re-checked at execution time (defense-in-depth)

Both checks record the `gate_status`, `enforcement`, and `gate_snapshot_id` in the `parasite_decisions` audit record. See [Agent Contract Appendix Section D](../08-ai-ml/agent-contract-appendix.md#d-parasitedecision-audit-record-schema) for the full schema.

---

## Related documents

- [Agent Contract Appendix](../08-ai-ml/agent-contract-appendix.md) — 42-entry threshold table, 14 metric definitions
- [Write Policy & Rollout](../08-ai-ml/write-policy-and-rollout.md) — Mode-by-mode enforcement, rollout checklist
- [Agent Contract](../08-ai-ml/agent-contract.md) — Agent specs, workflow maps
- [Optimization API](optimization.md) — Tier routing, profile management
- [Recommendations API](recommendations-api.md) — Approval/rejection endpoints
- [MLOps API](mlops-api.md) — Training readiness, outcome recording

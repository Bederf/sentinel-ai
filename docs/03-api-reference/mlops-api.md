---
title: "MLOps Monitoring API Reference"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-02-06"
updated: "2026-02-06"
author: "Sentinel Development Team"
tags: ["api", "mlops", "drift-detection", "alerting", "metrics", "retraining"]
domain: "general"
audience: "developers"
complexity: "advanced"
estimated_read_time: 10
---

# MLOps Monitoring API Reference

Phase 45-03 MLOps Monitoring endpoints. Drift detection, ML alerting, automatic retraining triggers, and success metrics.

Base path: `/api/mlops`

## Drift Detection

### GET `/api/mlops/drift/feature/{equipment_type}`

Detect feature distribution drift for an equipment type using simplified KS-test.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| threshold | float | 0.1 | KS statistic threshold |

**Response:**
```json
{
  "equipment_type": "chiller",
  "features_checked": 8,
  "drifted_features": 2,
  "drift_detected": true,
  "details": [
    {"feature": "compressor_current", "ks_statistic": 0.15, "drifted": true},
    {"feature": "chw_supply_temp", "ks_statistic": 0.04, "drifted": false}
  ]
}
```

### GET `/api/mlops/drift/model/{model_type}`

Detect prediction accuracy drift for a model type (`lstm` | `autoencoder`).

**Phase 236-03 (measured drift):** this verdict is now derived ONLY from
measured rolling accuracy in `ml_model_accuracy`, written daily by the ML
accuracy job (`MLAccuracyService`), which joins logged predictions
(`ml_prediction_log`) to `telemetry_hourly` actuals. The prior hardcoded
baselines (0.89/0.85) and demo fallbacks were removed. When no measured
accuracy row exists for the model kind (cold start / not enough joined
samples), the endpoint fails closed:

```json
{
  "model_type": "lstm",
  "verdict": "insufficient_data",
  "drift_detected": false,
  "recent_accuracy": null,
  "historical_accuracy": null
}
```

When measured data exists, `recent_accuracy` is the rolling measured MAE (LSTM)
or median score (AE), `historical_accuracy` is the model's own registered
training-time reference, and `drift_detected` is true only when measured
performance degrades beyond the model's own baseline. This coarse per-kind
summary prefers a `drift_suspected` model within the latest run; the
authoritative per-model signal is the `ml_model_drift` advisory raised by the
accuracy job. Drift is report-only — it never triggers retrain or activation.

### GET `/api/mlops/drift/all`

Comprehensive drift detection across all equipment and model types.

### GET `/api/mlops/drift/history`

Drift detection history. Param: `limit` (default 20).

## Alerts

### GET `/api/mlops/alerts`

ML system alerts with filters.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| severity | string | null | Filter: info, warning, critical |
| alert_type | string | null | Filter: drift_detected, model_stale, etc. |
| acknowledged | bool | null | Filter by ack status |
| limit | int | 50 | Max results |

### POST `/api/mlops/alerts/check`

Run all alert checks and return new alerts.

**Response:**
```json
{
  "new_alerts": 2,
  "alerts": [
    {
      "alert_id": "ml_alert_001",
      "type": "drift_detected",
      "severity": "warning",
      "message": "Feature drift detected for chiller compressor_current",
      "created_at": "2026-02-06T10:00:00Z"
    }
  ]
}
```

### POST `/api/mlops/alerts/{alert_id}/acknowledge`

Acknowledge an alert.

### GET `/api/mlops/alerts/summary`

Alert counts by severity and type.

## Retraining Triggers

### POST `/api/mlops/triggers/evaluate`

Evaluate drift scores and trigger retraining if thresholds breached.

**Response:**
```json
{
  "evaluated": true,
  "triggers_fired": 1,
  "details": [
    {"model_type": "lstm", "equipment_type": "chiller", "triggered": true, "reason": "feature_drift"}
  ]
}
```

### GET `/api/mlops/triggers/history`

Retraining trigger history. Param: `limit` (default 20).

### GET `/api/mlops/triggers/config`

Current trigger configuration.

**Response:**
```json
{
  "auto_retrain_enabled": true,
  "feature_drift_threshold": 0.1,
  "cooldown_minutes": 60,
  "last_trigger": "2026-02-06T09:00:00Z"
}
```

### PUT `/api/mlops/triggers/config`

Update trigger configuration.

| Parameter | Type | Description |
|-----------|------|-------------|
| auto_retrain_enabled | bool | Enable/disable auto-retrain |
| feature_drift_threshold | float | KS threshold for drift |
| cooldown_minutes | int | Min time between retrains |

## Success Metrics

### GET `/api/mlops/metrics`

All success metrics with targets.

**Response:**
```json
{
  "overall_score": 81.8,
  "metrics": {
    "unplanned_failure_reduction": {"value": 45.2, "target": 40, "met": true},
    "maintenance_planning_accuracy": {"value": 82.5, "target": 80, "met": true},
    "false_positive_rate": {"value": 7.3, "target": 10, "met": true},
    "technician_adoption": {"value": 78.0, "target": 70, "met": true},
    "roi_percent": {"value": 340, "target": 300, "met": true}
  },
  "targets_met": 5,
  "targets_total": 5
}
```

### GET `/api/mlops/metrics/trend`

Historical metrics trend. Param: `limit` (default 30).

### POST `/api/mlops/metrics/outcome`

Record a prediction outcome for accuracy tracking.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| prediction_id | string | Yes | Prediction identifier |
| equipment_id | string | Yes | Equipment identifier |
| predicted_failure | bool | Yes | Was failure predicted? |
| actual_failure | bool | Yes | Did failure occur? |
| prediction_date | string | Yes | When predicted |
| outcome_date | string | Yes | When outcome observed |

## Reports

### GET `/api/mlops/reports/{period}`

Generate performance report.

| Parameter | Type | Values | Description |
|-----------|------|--------|-------------|
| period | path | weekly, monthly | Report period |
| report_date | string | null | Report date (default: now) |

## Health

### GET `/api/mlops/health`

Comprehensive MLOps health status.

**Response:**
```json
{
  "status": "healthy",
  "overall_score": 81.8,
  "targets_met": 5,
  "critical_alerts": 0,
  "drift_detected": false,
  "metrics_summary": {...},
  "alert_summary": {...}
}
```

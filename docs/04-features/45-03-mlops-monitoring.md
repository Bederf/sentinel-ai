---
title: "MLOps Monitoring & Success Metrics"
type: "spec"
status: "approved"
version: "1.0.0"
created: "2026-02-06"
updated: "2026-02-06"
author: "Sentinel Development Team"
tags: ["ml", "mlops", "drift-detection", "monitoring", "metrics", "alerting"]
domain: "general"
audience: "developers"
complexity: "advanced"
estimated_read_time: 10
---

# Phase 45-03: MLOps Monitoring & Success Metrics

Drift detection, ML alerting, automatic retraining triggers, and success metrics tracking for production ML models.

## Overview

Closes the ML lifecycle with production monitoring. Detects when models or features drift from training distributions, alerts operators, automatically triggers retraining when thresholds are breached, and tracks five key success metrics against defined targets.

## Architecture

```
+------------------+     +---------------------+     +-------------------+
| Live Predictions |---->| DriftDetector       |---->| MLAlertManager    |
| Feature Data     |     | (KS-test, accuracy) |     | (severity-based)  |
+------------------+     +---------------------+     +-------------------+
                                   |                         |
                                   v                         v
                          +--------------------+    +-------------------+
                          | RetrainingTrigger  |    | MLMetrics         |
                          | (auto w/ cooldown) |    | Dashboard         |
                          +--------------------+    +-------------------+
                                   |
                                   v
                          +--------------------+
                          | MetricsCalculator  |
                          | (5 success targets)|
                          +--------------------+
```

## Components

### DriftDetector

**File:** `backend/ml/monitoring/drift.py`

Feature and model drift detection:
- **Feature drift:** Simplified KS-test comparing current feature distributions to training baseline
- **Model drift:** Prediction accuracy degradation over time
- **Thresholds:** Configurable per metric (default KS statistic > 0.1)
- No scipy dependency — lightweight implementation

### MLAlertManager

**File:** `backend/ml/monitoring/alerts.py`

ML-specific alerting system:
- Alert types: drift_detected, model_stale, performance_degraded, retraining_failed
- Severity levels: info, warning, critical
- Acknowledgement workflow
- Alert summary and history

### RetrainingTrigger

**File:** `backend/ml/monitoring/triggers.py`

Automatic retraining based on drift signals:
- Evaluates drift scores against thresholds
- Cooldown period prevents retrain storms (configurable, default 60 min)
- Auto-retrain toggle (can be disabled for manual-only)
- Trigger history tracking

### MetricsCalculator

**File:** `backend/ml/metrics/calculator.py`

Five success metrics with targets:

| Metric | Target | Demo Result |
|--------|--------|-------------|
| Unplanned failure reduction | 40% | 45.2% |
| Maintenance planning accuracy | 80% | 82.5% |
| False positive rate | <10% | 7.3% |
| Technician adoption rate | 70% | 78.0% |
| ROI | 300% | 340% |

- Weekly and monthly report generation
- Trend tracking over time
- Prediction outcome recording for accuracy measurement

## API Endpoints

All endpoints under `/api/mlops/`:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/drift/feature/{equipment_type}` | Feature drift detection |
| GET | `/drift/model/{model_type}` | Model accuracy drift |
| GET | `/drift/all` | Comprehensive drift scan |
| GET | `/drift/history` | Drift detection history |
| GET | `/alerts` | ML alerts with filters |
| POST | `/alerts/check` | Run alert checks |
| POST | `/alerts/{alert_id}/acknowledge` | Acknowledge alert |
| GET | `/alerts/summary` | Alert summary |
| POST | `/triggers/evaluate` | Evaluate retraining triggers |
| GET | `/triggers/history` | Trigger history |
| GET | `/triggers/config` | Current trigger config |
| PUT | `/triggers/config` | Update trigger config |
| GET | `/metrics` | All success metrics |
| GET | `/metrics/trend` | Metrics trend history |
| POST | `/metrics/outcome` | Record prediction outcome |
| GET | `/reports/{period}` | Weekly/monthly report |
| GET | `/health` | MLOps health status |

See [MLOps API Reference](../03-api-reference/mlops-api.md) for full details.

## Frontend

**File:** `frontend/src/components/MLMetrics.tsx`

Dashboard showing:
- Overall ML score ring (0-100)
- Five success metric cards with target comparison
- Drift status indicators
- Alert feed with acknowledge controls
- Metrics trend charts

## Testing

MLOps components are tested through the comprehensive ML test suite and integration tests.

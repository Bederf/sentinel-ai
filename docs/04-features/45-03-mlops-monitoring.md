---
title: "MLOps Monitoring & Success Metrics"
type: "spec"
status: "approved"
version: "1.1.0"
created: "2026-02-06"
updated: "2026-02-11"
author: "Sentinel Development Team"
tags: ["ml", "mlops", "drift-detection", "monitoring", "metrics", "alerting", "dashboard"]
domain: "general"
audience: "developers"
complexity: "advanced"
estimated_read_time: 15
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

## Frontend Dashboard

**File:** `frontend/src/components/MLMetrics.tsx` (878 lines)

Complete MLOps dashboard component displaying:

### Dashboard Sections

1. **Overall Health Badge**
   - ML system health status (healthy/warning/critical)
   - Color-coded indicator

2. **Score Ring**
   - Circular progress indicator showing overall ML score (0-100)
   - Demo value: 82/100

3. **Summary Cards**
   - **Targets Met:** Progress badge (e.g., 5/5 targets met)
   - **Critical Alerts:** Alert count with severity badge
   - **Drift Detected:** Status indicator (detected/not detected)

4. **Success Metrics** (5 metric cards with progress bars)
   - **Unplanned Failure Reduction:** Current 45.2% vs Target 40% ✅
   - **Maintenance Planning Accuracy:** Current 82.5% vs Target 80% ✅
   - **False Positive Rate:** Current 7.3% vs Target <10% ✅
   - **Mean Time to Detect:** Current 18.5h vs Target <24h ✅
   - **Prediction Lead Time:** Current 8.2 days vs Target 7 days ✅

5. **Drift Detection Panel**
   - Equipment type drift status table
   - Model type drift status table
   - Feature drift scores per equipment

6. **ML Alerts Panel**
   - Alert feed with severity badges
   - Acknowledge controls
   - Real-time alert updates

7. **Performance Reports Section**
   - Weekly report button
   - Monthly report button
   - Report generation and download

### Features

- Building selector for scoped dashboards
- Auto-refresh every 60 seconds
- Loading skeletons for smooth UX
- Error boundaries with fallback messages
- Responsive design (desktop/tablet/mobile)

**API Client:** `frontend/src/lib/mlopsApi.ts` (189 lines)
- Complete TypeScript types for all responses
- Methods: getHealth, getMetrics, getAllDrift, getAlerts, generateReport
- Proper authentication headers and error handling

### Navigation Integration

Accessible via:
- Route: `/metrics/ml`
- Menu: Metrics → ML Monitoring

## Implementation Status

**✅ COMPLETE (1 Bug Fix Applied 2026-02-11)**

### Infrastructure Inventory

| Component | File | Status | Lines |
|-----------|------|--------|-------|
| API Routes | `backend/app/api/mlops.py` | ✅ Complete | 265 |
| Drift Detection | `backend/ml/monitoring/drift.py` | ✅ Complete | 312 |
| Alert Manager | `backend/ml/monitoring/alerts.py` | ✅ Complete | 315 |
| Metrics Calculator | `backend/ml/metrics/calculator.py` | ✅ Complete | 454 |
| Performance Monitor | `backend/app/ml/monitoring/performance_monitor.py` | ✅ Complete + Fix | 330 |
| Retraining Trigger | `backend/ml/monitoring/triggers.py` | ✅ Complete | 245 |
| Dashboard Component | `frontend/src/components/MLMetrics.tsx` | ✅ Complete | 878 |
| API Client | `frontend/src/lib/mlopsApi.ts` | ✅ Complete | 189 |
| Router Registration | `backend/app/api/registrars/analytics.py` | ✅ Registered | Line 57 |

### Bug Fixes Applied

**Issue Found (2026-02-11):** `MetricsCalculator._get_model_health()` called `PerformanceMonitor.get_model_health_summary()` which didn't exist, causing 500 errors on health and report endpoints.

**Fix Applied:** Added missing method to PerformanceMonitor class that:
- Evaluates recent model performance over past 7 days
- Calculates health status based on accuracy and precision thresholds
- Returns model count and health breakdown (healthy/warning/critical)
- Includes recent accuracy metrics for reporting
- Has graceful error handling with fallback response

**Impact:** Resolves AttributeError that would crash health and report endpoints

## Testing

### Test Script

**File:** `backend/scripts/test_mlops_dashboard.py` (270+ lines)

Comprehensive testing script covering:
- Module import verification (DriftDetector, MLAlertManager, MetricsCalculator, PerformanceMonitor)
- All 12 API endpoints with expected field validation
- Response status code checking
- JSON response parsing validation
- Color-coded output (pass/fail/error)
- Connection error handling

**Run tests:**
```bash
cd backend
source venv/bin/activate
python scripts/test_mlops_dashboard.py
```

**Expected output:**
- Green checkmarks for passing tests
- Red X marks for failures
- Clear error messages if endpoints return errors
- Summary table showing pass/fail counts

### Manual Verification Checklist

#### Backend Startup
- [ ] Start backend: `./start-backend.sh`
- [ ] No import errors in startup logs
- [ ] API available at http://localhost:9095
- [ ] No module import errors for ML services

#### API Endpoints (via curl or browser)
```bash
# Health endpoint
curl http://localhost:9095/api/mlops/health

# Metrics
curl http://localhost:9095/api/mlops/metrics

# Drift detection
curl http://localhost:9095/api/mlops/drift/all

# Alerts
curl http://localhost:9095/api/mlops/alerts

# Weekly report
curl http://localhost:9095/api/mlops/reports/weekly
```

#### Frontend Dashboard
- [ ] Start frontend: `./start-frontend.sh`
- [ ] Navigate to: http://localhost:9096/metrics/ml
- [ ] Score ring displays 82/100
- [ ] All 5 metric cards visible with progress bars
- [ ] Summary cards show targets, alerts, drift status
- [ ] Drift panel shows equipment types and models
- [ ] Alerts panel loads without errors
- [ ] Report buttons are functional
- [ ] Auto-refresh working (check Network tab every 60s)
- [ ] No TypeScript errors in console
- [ ] No 404 errors for API calls
- [ ] Loading states appear smoothly

### Demo Data Values

All endpoints return realistic seeded values when no simulation logs exist:

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Failure Reduction | 45.2% | 40% | ✅ Met |
| Planning Accuracy | 82.5% | 80% | ✅ Met |
| False Positive Rate | 7.3% | <10% | ✅ Met |
| Time to Detect | 18.5h | <24h | ✅ Met |
| Prediction Lead Time | 8.2 days | 7 days | ✅ Met |
| **Overall Score** | **82/100** | — | ✅ Healthy |

### Integration with Simulation

To use real metrics data instead of demo values:

1. Run 24-hour lifecycle simulation:
   ```bash
   curl -X POST http://localhost:9095/api/lifecycle/demo/normal-day
   ```

2. This generates JSONL event logs in:
   ```
   backend/app/data/simulation_logs/
   ```

3. PerformanceMonitor reads these logs and calculates real metrics:
   - Confusion matrix from fault + repair events
   - Accuracy, precision, recall, F1 score
   - Equipment-specific performance

4. Dashboard displays actual system performance data

## Known Limitations (Demo Mode)

1. **No persistence** - Metrics reset on backend restart
2. **Demo data only** - Uses seeded values unless simulation logs generated
3. **No real models** - Mock accuracy/drift calculations based on seeded baselines
4. **No email reports** - Reports generated on-demand only
5. **In-memory alerts** - Max 500 alerts stored (oldest pruned first)
6. **No Supabase storage** - All data ephemeral

## Production Deployment Notes

To move from demo to production:

1. **Replace demo data generation:**
   - Point DriftDetector to real feature distributions from model training
   - Use actual prediction accuracy metrics from live models
   - Read real equipment fault events from work order system

2. **Add persistence:**
   - Store alerts to Supabase `ml_alerts` table
   - Persist metrics history to `ml_metrics` table
   - Archive reports to `ml_reports` table

3. **Add real-time updates:**
   - Connect dashboard to WebSocket for live alert streaming
   - Auto-refresh metrics every 30 seconds instead of 60
   - Trigger alerts immediately on drift detection

4. **Add automation:**
   - Schedule background retraining trigger checks
   - Email reports weekly to stakeholders
   - Create Slack notifications for critical alerts

See [MLOps API Reference](../03-api-reference/mlops-api.md) for complete endpoint documentation.

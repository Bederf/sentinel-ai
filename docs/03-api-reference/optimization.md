---
title: "Optimization API"
type: "reference"
status: "draft"
version: "1.1.0"
created: "2026-03-31"
updated: "2026-05-17"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 12
---

# Optimization API

## Overview

Optimization API endpoints for HVAC load shedding, AI optimization, profile management, and M&V verification.

## Endpoints

### Core Optimization
- POST /optimization/analyze — Analyze building and generate recommendations
- POST /optimization/approve — Apply approved recommendations
- GET /optimization/status/{site_id} — Get optimization status + monthly savings
- POST /optimization/toggle/{site_id} — Enable/disable optimization

### Load Shedding
- GET /optimization/scenarios
- GET /optimization/eskom-status
- GET /optimization/eskom-status/{site_id}
- GET /optimization/eskomsepush/areas
- GET /optimization/eskomsepush/allowance
- GET /optimization/thermal-runway
- POST /optimization/analyze-load-shedding

### Profile Management
- GET /optimization/profiles — List available profiles
- GET /optimization/settings/{site_id} — Get site profile config
- PUT /optimization/settings/{site_id} — Update profile + control tier
- POST /optimization/settings/{site_id}/zone-override — Add zone override
- DELETE /optimization/settings/{site_id}/zone-override/{zone_id} — Remove zone override

### Measurement & Verification (M&V)
- GET /optimization/mv/summary/{site_id} — Get M&V verification stats (accuracy, outcomes, rollbacks)
- POST /optimization/mv/verify — Trigger pending verifications (call periodically)

## Optimization Status Values

The `GET /optimization/status/{site_id}` endpoint returns an `optimization_status` field with the following values:

| Status | Description | Frontend Label | Color |
|--------|-------------|----------------|-------|
| `optimized` | Successfully applied optimization | "Optimised" | Green |
| `optimizing` | Optimization in progress | "Optimising..." | Amber |
| `recommendation_pending` | Pending recommendations awaiting approval | "Action required" | Amber |
| `learning` | Site in onboarding phase, building baseline models | "Learning" | Blue |
| `disabled` | Optimization deliberately disabled | "Paused" | Gray |
| `error` | Error state (connection, Modbus, etc.) | "Attention needed" | Red |
| `active` | Optimization enabled, operational, waiting for patterns | "Monitoring" | Green |
| `unknown` | Status cannot be determined | "Pending" | Gray |

**Status Derivation Logic:**
```python
if not optimization_enabled:
    status = "disabled"
elif last_recommendation and last_recommendation.status == "pending":
    status = "recommendation_pending"
elif last_optimization:
    status = "optimized"
elif error_message:
    status = "error"
elif onboarding_phase in ("commissioning", "shadow_live"):
    status = "learning"
else:
    status = "active"
```

## Tier Routing (Phase 82)

Recommendations are routed through a confidence-based tier system that determines
what action is taken for each recommendation.

### Routing Tiers

| Tier | Confidence | Behavior |
|------|-----------|----------|
| **Blocked** | < 0.30 | Rejected entirely. Cannot be approved. |
| **Tier 1 (Advisory)** | 0.30 - 0.60 | Display only. Cannot be approved in enforce mode. |
| **Tier 2 (Approval)** | 0.60 - 0.85 | Requires human approval before execution. |
| **Tier 3 (Auto-Execute)** | >= 0.85 | Auto-applied in auto_execute mode (safety permitting). |

FCU systems have a confidence cap of 0.45, forcing them to advisory-only routing.

### Control Tier Execution Matrix

| Routing Tier | monitor | human_in_loop | auto_execute |
|---|---|---|---|
| Blocked | blocked | blocked | blocked |
| Tier 1 | log_only | advisory | advisory |
| Tier 2 | log_only | pending_approval | pending_approval |
| Tier 3 | log_only | pending_approval | auto_execute |

### New Response Fields

The following fields are added to `/optimization/analyze` and `/optimization/status/{site_id}` responses:

| Field | Type | Description |
|-------|------|-------------|
| `control_tier` | string | Active control tier: monitor, human_in_loop, auto_execute |
| `routing_summary` | object | Counts of blocked, advisory, pending_approval, auto_executed |
| `routing_details` | array | Per-recommendation tier, action, effective_confidence |
| `execution_summary` | object | attempted/succeeded/failed counts for auto-applied items |

### Approval Hardening

When `optimization_routing_enforced=True`:
- **Blocked** recommendations cannot be approved (rejected with reason)
- **Advisory** recommendations cannot be approved (rejected with reason)
- **Already auto-executed** items return idempotent success
- Only **tier2_approval** and **tier3 pending_approval** items can be approved

### Shadow Mode vs Enforce Mode

- **Shadow mode** (default, `optimization_routing_enforced=False`): Routing decisions are computed and logged but do not change existing behavior. Auto-apply uses legacy `site_mode` logic.
- **Enforce mode** (`optimization_routing_enforced=True`): Routing decisions control auto-apply and approval paths. Only tier3+safety-passed items are auto-applied.

## ML Context Injection (Phase 132)

When `POST /optimization/analyze` is called, the AI Optimizer now gathers ML model outputs before building Claude's prompt. This bridges trained ML models (20 active) with Claude's recommendation engine.

### ML Context Sources

| Source | Service | Data Injected |
|--------|---------|---------------|
| LSTM Forecasting | `ml_inference.LSTMInferenceService` | 24/48/72h temperature/load forecasts per equipment |
| Anomaly Detection | `ml_inference.AnomalyDetectionService` | Equipment with anomaly score > 0.5 |
| Fault Classification | `classification_service.FailureClassificationService` | Fault type probabilities > 0.4 confidence |
| Health Trends | `health_feature_provider.HealthFeatureProvider` | Equipment with degrading health (7d slope < -0.5) |
| Building Features | `feature_engineering_service.FeatureEngineeringService` | EUI, Base Load Index, CDD, Efficiency Score |

### How It Works

```
analyze_building()
    ├── _gather_current_conditions()     # Current state
    ├── _gather_ml_context()             # ML predictions ← NEW
    │   ├── LSTM forecasts (capped at 10)
    │   ├── Anomaly alerts (score > 0.5)
    │   ├── Fault classifications (confidence > 0.4)
    │   ├── Health trends (degrading only)
    │   └── Building features (EUI, BLI, CDD)
    ├── _build_optimization_prompt()     # Includes ML section
    └── _analyze_with_claude()           # Claude uses ML data
```

### Claude Prompt Enhancement

The ML context is inserted as a dedicated section between "Current Conditions" and "Weather Forecast" in Claude's prompt. Claude is instructed to:

1. Use LSTM forecasts for pre-cooling/pre-heating decisions
2. Flag equipment with elevated anomaly scores for inspection
3. Factor fault classification probabilities into maintenance recommendations
4. Consider health degradation trends when loading equipment
5. Reference building efficiency metrics (EUI, base load index) for energy recommendations

### Building-Level Features

| Feature | Formula | Benchmark |
|---------|---------|-----------|
| **EUI** | `daily_kWh / building_m²` | < 0.15 excellent, > 0.50 poor |
| **Base Load Index** | `off_hours_kWh / total_daily_kWh` | < 0.15 excellent, > 0.40 poor |
| **CDD** | `Σ max(0, T_hour - 18°C) / 24` | SA base temp 18°C |
| **Efficiency Score** | Weighted composite (0-100) | EUI 35%, BLI 25%, setpoint 25%, CDD 15% |

## Dashboard KPI: Potential Savings

The "Potential Savings" KPI displayed on the dashboard is calculated from ML failure predictions:

### Formula

```
Potential Savings = Σ(prediction.financial_impact.potential_loss_zar)
WHERE prediction.severity IN ('critical', 'warning')
```

### Methodology

1. **ML Failure Predictions:** LSTM forecasting + autoencoder anomaly detection identify at-risk equipment
2. **Financial Impact Calculation:** Each prediction includes `potential_loss_zar` comprising:
   - Equipment replacement cost (if failure occurs)
   - Downtime cost (business interruption)
   - Energy penalty (inefficient operation until failure)
3. **Aggregation:** Sum across all critical/warning severity predictions
4. **Currency:** ZAR (South African Rand)

### Example

If 3 predictions exist:
- Chiller bearing failure: R1,200,000 potential loss
- AHU belt degradation: R450,000 potential loss  
- Pump cavitation: R1,016,000 potential loss

**Total Potential Savings: R2,666,000**

### Client Conversation

**Peter Marshall asks:** "How did you arrive at R2.6M?"

**Response:** "That's the sum of potential losses from 3 ML-flagged equipment risks. It includes replacement costs, downtime estimates, and energy penalties. If SENTINEL's preventive recommendations are actioned — scheduling the chiller bearing inspection, replacing the AHU belt, clearing the pump intake — those losses are avoided. The number updates daily as new predictions arrive and existing ones are resolved."

### Response Changes

Recommendations generated after ML context injection include richer reasoning that references predicted future state:

- "LSTM forecasts predict 3°C temperature rise in 24h — pre-cool now"
- "Anomaly score 0.82 on AHU-L2-001 — schedule inspection"
- "Bearing wear probability 65% — reduce loading on chiller"

## Implementation

- Core optimization: `backend/app/api/ai_recommendations.py`
- Load shedding: `backend/app/api/optimization.py`
- Tier router: `backend/app/services/optimization_tier_router.py`
- M&V service: `backend/app/services/mv_verification_service.py`
- AI optimizer: `backend/app/services/ai_optimizer.py`
- ML context bridge: `backend/app/services/ai_optimizer.py` (`_gather_ml_context`, `_format_ml_context_section`)
- Feature engineering: `backend/app/services/feature_engineering_service.py`
- ML inference: `backend/app/services/ml_inference.py`
- Fault classification: `backend/app/services/classification_service.py`
- Health features: `backend/app/services/health_feature_provider.py`

## Key Changes

**2026-02-27 (Phase 132)**
- ML Context Injection: LSTM forecasts, anomaly scores, fault classifications, health trends, and building-level features injected into Claude's optimization prompt
- Building-level feature engineering: EUI, Base Load Index, CDD, Building Efficiency Score
- Claude task instructions updated to use ML predictions for proactive recommendations

**2026-02-19**
- Monthly savings now use schedule-aware projection (actual weekdays + TOU-weighted rates)
- Recommendations include `data_quality` field showing live vs defaulted sensor data
- M&V endpoints added for post-action verification of predicted vs actual savings
- Tier routing added: confidence-based routing with shadow/enforce modes (Phase 82)
- Status endpoint includes `routing_summary` and `control_tier` from last recommendation
- Approval path hardened to reject blocked/advisory in enforce mode

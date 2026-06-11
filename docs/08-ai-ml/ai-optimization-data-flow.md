---
title: "AI Optimization Data Flow — Complete Data Source Inventory"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-06-11"
updated: "2026-06-11"
author: "Sentinel Development Team"
tags: ["ai", "optimization", "data-flow", "recommendations", "reference"]
related: ["./ai-recommendation-system.md", "../02-architecture/ML-DATA-ARCHITECTURE.md", "../04-features/ai-optimization-pipeline.md"]
domain: "bms"
audience: "developers|operators"
complexity: "advanced"
estimated_read_time: 15
---

# AI Optimization Data Flow — Complete Data Source Inventory

Every AI-OPT recommendation is built from ~40 data sources across 5 layers. This document inventories every source — table, API, live sensor read, ML model, and derived service — that feeds into a single recommendation.

## Overview

The AI optimizer (`app/services/ai_optimizer.py`) runs every 30 minutes via APScheduler (`background_scheduler.py:381`). For each registered site, it:

1. Checks pre-gates (onboarding phase, optimization toggle, condition change)
2. Gathers current conditions from 30+ sources
3. Submits everything to Claude (LLM path) or a rule engine (fallback path)
4. Safety-validates each recommendation
5. Deduplicates against existing PENDING recs (48h window)
6. Persists to `recommendations` table
7. Sends advisory to FM Telegram (if sendable)

## Layer 1 — Supabase Tables (12)

| # | Table | Columns Read | Purpose |
|---|-------|-------------|---------|
| 1 | `sites` | `onboarding_phase`, `optimization_enabled`, `nmd_limit_kva`, `demand_charge_per_kva`, `optimization_status`, `id` | Phase gate, feature toggle, tariff config |
| 2 | `equipment` | `code`, `type`, `health_score`, `status`, `operating_data` (setpoints, anomaly scores, lstm_anomaly scores) | Equipment inventory, health context, live operating points |
| 3 | `site_modules` | `module_type`, `status` | Active module inventory |
| 4 | `work_orders` | `equipment_code`, `title`, `priority`, `status` | Active urgent/critical WOs (filtered) |
| 5 | `ipmvp_energy` | `import_kwh` (last 100 rows) | IPMVP baseline comparison (96-row sum = ~24h) |
| 6 | `ipmvp_tariff` | `tariff_data` JSON (peak hours, rates per band) | Energy cost calculation |
| 7 | `equipment_sensor_readings` | `point_name`, `value`, `recorded_at` (last 200) | Recent sensor trend context |
| 8 | `health_snapshots` | `health_score`, `health_status`, `components` | Equipment health trends |
| 9 | `audit_logs` | `event_type` (drift critical alerts, 24h) | Quality gate drift metric |
| 10 | `devices` | device definitions, points, types | Device inventory (via device_manager) |
| 11 | `recommendations` | existing PENDING recs (48h, limit 500) | Dedup: `(target_equipment, point, value)` |
| 12 | `site_thresholds` | health/critical/warning boundaries | Threshold configuration |

**Fallback:** `data/sites.json` and `data/optimization_profiles.json` when Supabase is unreachable.

## Layer 2 — External APIs (3)

| # | API | Endpoint | Data Read |
|---|-----|----------|-----------|
| 13 | **OpenWeatherMap** | `/data/2.5/weather` | Current outdoor temp, humidity, pressure, wind |
| 14 | **OpenWeatherMap** | `/data/2.5/forecast` | 3h interval: temp, humidity, cloud cover → solar load |
| 15 | **Bridge API** | `http://10.99.0.1:8080/api/sites/{site_id}/telemetry` | Electrical aggregate: `total_kw`, `hvac_kw`, `lighting_kw`, `solar_kw` + condition-change detection |

## Layer 3 — Live Real-Time Sensor Reads (6 categories via Bridge/BACnet/DALI)

| # | Source | Points Read |
|---|--------|-------------|
| 16 | **HVAC device points** (via `device_manager.read_device_value()`) | Indoor temp, outdoor temp, humidity, setpoints, cooling/heating signals, supply temp, flow, speed |
| 17 | **SOLAR device points** | `ac_power`, `efficiency`, `performance_ratio` |
| 18 | **BESS device points** | `soc`, `power`, `mode`, `temperature` |
| 19 | **METER device points** | `active_power` (solar-specific meters) |
| 20 | **DALI Lighting Service** | Per zone: `occupancy_percent`, `avg_lux`, `zone_name`, `active_scene`, dim levels |
| 21 | **IAQ Service** (DALI bridge) | Per zone: CO2, humidity, IAQ score, status (only if non-temp sensors live) |

Operating data has a 2-hour staleness TTL — readings older than 2h are excluded.

## Layer 4 — ML Model Inference (3 local models)

| # | Model | Method | Outputs |
|---|-------|--------|---------|
| 22 | **LSTM Forecast Service** | `predict(equipment_id, type)` | 24h/48h/72h forecasts per equipment |
| 23 | **Anomaly Detection Service** | `check_all_equipment()` | `anomaly_score`, `severity`, `is_anomaly` (threshold: >0.5) |
| 24 | **Classification Service** | `get_fleet_failure_risks()` | `predicted_fault_type`, `confidence`, `equipment_type` (min confidence: 0.4) |

## Layer 5 — Derived / Computed Services (11)

| # | Service | Input | Output |
|---|---------|-------|--------|
| 25 | **Health Feature Provider** | `health_snapshots` + daily rollups | `health_score_current`, trend slopes (7d/30d), volatility (30d), confidence, baseline deviation |
| 26 | **Feature Engineering Service** | `compute_site_features(site_id)` | Derived building-level aggregate metrics |
| 27 | **FCU State Tracker** | Zone occupancy transitions (in-memory) | Inferred FCU running state, post-occupancy waste detection |
| 28 | **Decision Memory Service** | Past decision outcomes (in-memory) | Learned patterns + resolved outcomes (last 10) |
| 29 | **ML Feedback Service** | `get_scoring_inputs()`, `get_feedback_summary()` | Per-module success rates, scoring multipliers, feedback capture rate |
| 30 | **Profile Service** | Supabase profiles / `optimization_profiles.json` | Active profile name, weights, targets, thresholds |
| 31 | **Monitoring Service** | `get_snapshot()` | `freshness_minutes`, `ingest_error_rate`, `match_coverage`, `unmatched_points`, `manual_source_pct`, commissioning gate status |
| 32 | **Commissioning Service** | `_truth_checks` | `truth_check_pass_rate_pct` (agreement %) |
| 33 | **MV Verification Service** | Supabase `verification_results` | `mv_accuracy_7d_pct`, `rollback_rate_7d_pct` |
| 34 | **Audit Logger** | Supabase `audit_logs` | `drift_critical_alerts_24h` |
| 35 | **ContextPreComputeService** | All above | Pre-computed context rules: FCU waste, AHU overcapacity, free cooling, BESS idle during peak |

## Trigger Conditions

The optimizer evaluates current conditions against these triggers. A recommendation is only generated when one or more conditions are met:

| Condition | Threshold | Data Sources Used |
|-----------|-----------|-------------------|
| Free cooling opportunity | Outdoor temp within 5°C of indoor avg | OpenWeatherMap + HVAC live reads |
| High humidity | Indoor humidity > 62% (occupied hours) | HVAC live reads / IAQ |
| HVAC overload | HVAC load > 75% of total site load | Bridge telemetry |
| AHU overcapacity | AHU speed > 85% with outdoor < 18°C | HVAC live reads + OpenWeatherMap |
| Pre-peak window | Current time within 60 min of peak tariff | Tariff config + clock |
| BESS discharge opportunity | SOC > 80% during off-peak | BESS live reads + tariff |
| Zone temp deviation | Deviation > 1.5°C from setpoint for > 20 min | HVAC live reads |

## Recommendation Object

```python
Recommendation(
    site_id=str,                # From site loop iteration
    timestamp=datetime,         # utcnow()
    action_type="ai_optimization",
    risk_level=ActionRiskLevel.LOW,  # MEDIUM for holistic
    target_equipment=str,            # From optimizer output
    action={"point": str, "value": float},  # Specific adjustment
    reason=str,                  # LLM-generated or rule-based rationale
    expected_impact={
        "current_value": float,
        "recommended_value": float,
        "unit": str,
        "energy_savings_percent": float,
        "cost_zar": float,
    },
    confidence=str,              # "0.75"
    confidence_score=float,      # 0.0-1.0
    profile=str,                 # Site optimization profile
    source="ai_optimizer",
    source_type="ml_model",      # or "rule_based"
    status=RecommendationStatus.PENDING,
    requires_approval=True,
    shadow_mode=bool,
)
```

## Recommendation Flow (Simplified)

```
APScheduler (30min)
  → _run_optimization_analysis_gated()
    → _run_optimization_analysis()
      → Pre-gates (phase, toggle, condition change)
      → For each site:
        → analyze_building(site_id)
          → _gather_current_conditions()       # 21 sources
          → Weather forecast                    # 2 sources
          → _get_energy_prices()                # 2 sources
          → _categorize_equipment()             # 1 source
          → _gather_lighting_zone_data()        # 1 source
          → _gather_ml_context()                # 6 sources
          → _gather_decision_memory()
          → _gather_feedback_success_rates()
          → Site profile                        # 1 source
          → ContextPreComputeService            # 4 rules
          → QualityGateEvaluator                # 7 metrics
          → HealthFeatureEnrichment             # 1 source
          → Claude (LLM) or rule engine (fallback)
        → Safety validation
        → Dedup check
        → Persist to DB
        → SSE event (Cockpit UI)
        → Telegram notification (FM advisory)

## Outcome Verification & Learning Loop

When the FM taps the "Create WO" button, the work order is created and the recommendation is marked `APPROVED`. The technician is notified, does the work, and taps "✅ Done" to close the WO.

### Closeout → Verification

On WO closeout (`chat_tools.py:4253`):

1. Recommendation promoted to `EXECUTED`, stamped with `executed_at`
2. One-shot APScheduler job scheduled for **+30 minutes** (`run_date=utcnow+30min`)

At +30 minutes, `validate_outcome()` (`recommendation_outcome_service.py:26`) runs:

| Step | What It Does |
|------|-------------|
| **Read telemetry** | Queries device manager (in-memory) → Supabase telemetry fallback for current value of the adjusted point (e.g., current `speed_percent` on that AHU) |
| **Evaluate** | Compares actual vs recommended value with type-specific tolerance: setpoints ±1.5, lighting ±15%, generic ±10% |
| **Store** | Writes `outcome_validated`, `outcome_notes`, `outcome_validated_at` to the recommendation in Supabase |
| **Learn** | Feeds outcome into both learning paths below |

### Path 1 — Decision Memory (pattern-based, into Claude prompt)

`_record_to_decision_memory()` → `DecisionMemoryService`:

- Stores `DecisionRecord` with: equipment_type, diagnosis, action_type, outcome
- When ≥3 records exist for the same `(event_type, equipment_type)` with ≥50% success, extracts a `DecisionPattern`

**Consumed on next AI-OPT cycle** via `_gather_decision_memory()` → injected into Claude prompt as:

> *"HISTORICAL PATTERN MEMORY: If a pattern shows a previous action failed, do not repeat it without a specific reason to believe conditions have changed."*

### Path 2 — ML Feedback (score multipliers, programmatic)

`_record_to_ml_feedback()` → `MLFeedbackService`:

- Tracks success rates per module type (hvac, lighting, solar, bess, generator)

**Consumed two ways:**

| Consumption | Mechanism | Impact |
|------------|-----------|--------|
| **Prompt injection** | `_gather_feedback_success_rates()` → *"RECOMMENDATION SUCCESS RATES: For <60% success, only recommend when clearly anomalous"* | Soft — Claude may override |
| **Score multiplier** | `_success_rate_to_multiplier()`: ≥90%→1.1x, ≥80%→1.05x, 65-80%→1.0x, 50-65%→0.9x, <50%→0.8x. Applied in `RecommendationScorer.score_recommendation()` | Hard — affects ranking |

### Learning Flow Diagram

```
WO Close (✅ Done)
  → +30min → validate_outcome()
               ├──► DecisionMemoryService
               │      └── pattern extraction (≥3 records, ≥50% success)
               │      └── injected into Claude prompt on next cycle
               │
               └──► MLFeedbackService
                      └── module-level success rates
                      ├── prompt injection (advisory)
                      └── score multiplier 0.8-1.1x (programmatic)
```

**Result:** Every WO closeout makes the next cycle slightly smarter. Successful outcomes boost confidence in similar recs; failed ones suppress them. No manual intervention needed.
```

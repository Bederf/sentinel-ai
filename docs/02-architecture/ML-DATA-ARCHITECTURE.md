---
title: "SENTINEL — ML Data Architecture & AI Recommendation Engine"
type: "architecture"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# SENTINEL — ML Data Architecture & AI Recommendation Engine

## Technical Reference Document

**Version:** 1.0 | **Date:** 2026-02-27 | **Status:** Reference — guides implementation priorities

---

## 1. Overview

SENTINEL's intelligence layer operates across two distinct but interconnected ML domains:

1. **Building Operations ML** — system-wide patterns, energy, occupancy, environmental conditions
2. **Equipment Condition ML** — individual asset health, fault detection, remaining useful life

Both feed into a unified **AI Recommendation Engine** that generates prioritised, actionable outputs for the SENTINEL dashboard, chat interface, and notification channels (WhatsApp/Telegram via Sentry).

---

## 2. Building Operations ML

### 2.1 Data Sources & Ingestion

| Source | Data Type | Frequency |
|---|---|---|
| eiEnterprise | Energy consumption per zone/floor | 15-min intervals |
| Kamstrup smart meters | Water consumption, flow rates | 15-min intervals |
| BMS (Siemens Desigo, etc.) | HVAC setpoints, damper positions, AHU states | Real-time / 1-min |
| Occupancy sensors | Zone presence, headcount estimates | Real-time |
| Weather API | Ambient temp, humidity, solar irradiance | Hourly |
| Calendar/booking systems | Scheduled occupancy, events | Daily sync |
| Solar/BESS systems | Generation, battery state, grid import/export | 5-min intervals |

### 2.2 Feature Engineering

**Temporal Features**
- Hour of day, day of week, month, public holiday flag (South African calendar)
- Rolling averages: 1hr, 24hr, 7-day windows
- Lag features: t-1, t-4, t-96 (previous 15-min, 1hr, 24hr)

**Derived Operational Features**
- Energy Use Intensity (EUI): `kWh / m²`
- Cooling load ratio: `actual consumption / theoretical baseline`
- Occupancy efficiency: `energy consumed / occupied hours`
- Setpoint deviation score: `|actual temp - setpoint| averaged across zones`
- Pre-cooling effectiveness: `temp delta achieved vs energy spent before peak hours`
- Base load index: `off-hours consumption / total daily consumption`

**Environmental Features**
- Cooling Degree Days (CDD) — critical for SA climate normalisation
- Internal vs external temperature differential
- Relative humidity impact score

### 2.3 ML Models — Building Operations

**Model 1: Energy Anomaly Detection**
- Type: Isolation Forest / Autoencoder
- Input: EUI, weather-normalised consumption, time features
- Output: Anomaly score (0–1), flagged intervals
- Trigger: Score > 0.75 generates recommendation

**Model 2: Occupancy Prediction**
- Type: Gradient Boosted Trees (XGBoost/LightGBM)
- Input: Historical occupancy, calendar, time features, access control data
- Output: Predicted occupancy per zone per 15-min interval
- Used by: HVAC pre-conditioning rules, lighting automation

**Model 3: Thermal Load Forecasting**
- Type: LSTM or Prophet (depending on data availability)
- Input: Weather forecast, predicted occupancy, historical load
- Output: Predicted cooling load for next 24hrs
- Used by: Chiller staging optimisation, peak shaving rules

**Model 4: Operational Efficiency Scoring**
- Type: Regression / Scoring model
- Input: All operational features
- Output: Building efficiency score (0–100) per day
- Used by: Sustainability reporting, portfolio benchmarking

### 2.4 Building Operations — Recommendation Triggers

```
IF energy_anomaly_score > 0.75 AND occupancy < 0.3
  → RECOMMEND: "Zone X consuming above baseline with low occupancy — check AHU schedule"

IF predicted_load[peak_hours] > threshold AND battery_soc > 60%
  → RECOMMEND: "Pre-cool recommended 07:00–08:30 to reduce peak demand charge"

IF base_load_index > 0.35
  → RECOMMEND: "High off-hours consumption detected — audit after-hours HVAC and lighting"

IF cooling_load_ratio > 1.2 AND CDD < historical_average
  → RECOMMEND: "Overcooling detected relative to weather conditions — review setpoints"
```

---

## 3. Equipment Condition Assessment ML

### 3.1 Data Sources

| Source | Equipment | Data Points |
|---|---|---|
| BMS points | Chillers, AHUs, FCUs | Runtime hours, start/stop cycles, temperatures, pressures, current draw |
| Vibration sensors (where fitted) | Pumps, fans, compressors | Frequency spectrum, amplitude |
| Smart meters | All electrical equipment | kWh, kW demand, power factor |
| Inspection records | All equipment | Condition scores, observations, photos |
| Work order history | All equipment | Fault type, resolution time, repeat faults |
| Maintenance schedules | All equipment | Last service date, next due, service type |

### 3.2 Equipment Feature Engineering

**Health Indicators**
- Runtime hours since last service
- Start/stop cycle count (compressors are sensitive to this)
- Operating efficiency ratio: `current performance / nameplate performance`
- Fault frequency: faults per 30-day rolling window
- Mean Time Between Failures (MTBF) trend
- Energy consumption vs. load ratio drift

**Condition Assessment Inputs (from inspections)**
- Visual condition score (1–5 scale per component)
- Refrigerant pressure readings
- Filter condition index
- Belt/drive condition
- Electrical insulation resistance readings
- Vibration baseline deviation %

### 3.3 ML Models — Equipment Condition

**Model 1: Fault Classification** ✅ IMPLEMENTED
- Type: Multi-class classifier (Random Forest / XGBoost)
- Input: BMS operational data, recent fault history, equipment age
- Output: Fault type probability distribution
- Classes: Refrigerant leak, bearing wear, filter blockage, electrical fault, controls fault, no fault
- Used by: Work order auto-generation with fault type pre-filled

**Model 2: Remaining Useful Life (RUL) Prediction** ⚠️ STUB
- Type: Survival analysis or LSTM regression
- Input: Runtime hours, cycle counts, efficiency drift, maintenance history
- Output: Estimated remaining life in days/hours, confidence interval
- Used by: Planned maintenance scheduling, capital replacement planning

**Model 3: Anomaly Detection per Asset** ✅ IMPLEMENTED
- Type: Autoencoder per equipment class (7 models active)
- Input: Operational telemetry (last 30 days rolling)
- Output: Anomaly flag + anomaly score + severity classification
- Used by: Real-time alerts, inspection prioritisation

**Model 4: Inspection Priority Scoring** 🆕 RULE-BASED
- Type: Weighted scoring model
- Input: Days since last inspection, anomaly score, fault history, RUL estimate, asset criticality
- Output: Priority score (0–100) per asset
- Used by: Maintenance scheduling module, helpdesk queue

### 3.4 Equipment Condition — Recommendation Triggers

```
IF fault_classification['bearing_wear'] > 0.65
  → RECOMMEND: "Bearing wear probability 65%+ on [Asset X] — schedule inspection within 7 days"

IF rul_estimate < 30 AND asset_criticality == 'high'
  → RECOMMEND: "Critical asset [X] estimated < 30 days remaining — initiate replacement planning"

IF anomaly_score > 0.8 AND last_service > 90_days
  → RECOMMEND: "Overdue service + anomaly detected on [Asset X] — elevate work order priority"

IF repeat_fault_count > 2 AND fault_type == same
  → RECOMMEND: "Recurring fault pattern on [Asset X] — root cause investigation required"
```

---

## 4. Unified AI Recommendation Engine

### 4.1 Recommendation Object Schema

```json
{
  "recommendation_id": "uuid",
  "timestamp": "ISO8601",
  "building_id": "string",
  "asset_id": "string | null",
  "category": "energy | hvac | equipment | water | compliance",
  "severity": "info | warning | critical",
  "trigger_model": "string",
  "trigger_score": 0.0,
  "title": "string",
  "description": "string",
  "estimated_saving": {
    "value": 0.0,
    "unit": "ZAR | kWh | kL",
    "period": "daily | monthly | annual"
  },
  "action_required": "string",
  "work_order_auto_create": true,
  "assigned_to": "internal | contractor | none",
  "status": "open | acknowledged | in_progress | resolved",
  "module_required": "string | null"
}
```

### 4.2 Recommendation Priority Logic

```
Priority Score = (severity_weight × 0.4) + (saving_weight × 0.3) + (confidence × 0.2) + (asset_criticality × 0.1)

severity_weight:   critical=1.0, warning=0.6, info=0.2
saving_weight:     normalised ZAR value against portfolio average
confidence:        model output probability / anomaly score
asset_criticality: defined per asset in asset registry
```

### 4.3 Feedback Loop — Model Retraining

- When a work order is **resolved**, the resolution data (fault confirmed Y/N, actual fault type, time to resolve) feeds back into training data
- When a recommendation is **dismissed**, the reason is logged and used to adjust threshold calibration
- Inspection results feed back into equipment condition models quarterly
- Energy baseline models retrain monthly with updated consumption data
- Occupancy models retrain weekly as patterns shift seasonally

### 4.4 Data Pipeline Architecture

```
[BMS / Meters / Sensors]
        ↓
[Data Ingestion Layer — READy Manager / Direct API]
        ↓
[Feature Engineering Service]
        ↓
[Model Inference Service]  ←——  [Trained Model Registry]
        ↓
[Recommendation Engine]
        ↓
[API Endpoints] → [Dashboard] → [Chat Interface] → [Sentry Notifications]
        ↓
[Work Order Auto-Creation] → [MRI Evolution / ServiceNow]
        ↓
[Feedback Capture] → [Model Retraining Pipeline]
```

---

## 5. Implementation Status

### Current State (v32.0)

| Component | Status | Notes |
|-----------|--------|-------|
| LSTM Forecasting (7 types) | ✅ Active | 24/48/72h predictions per equipment |
| Autoencoder Anomaly (7 types) | ✅ Active | Per-asset anomaly scores + severity |
| Fault Classification (5 RF) | ✅ Active | Chiller, AHU, Gen, FCU, UPS |
| Health Rating (5-component) | ✅ Active | Weighted formula with trend momentum |
| ML Feeder (SENTINEL→ML) | ✅ Active | Accumulates data, trains at 500h |
| ML→Claude Context Injection | ✅ Active | Forecasts + anomalies in Claude prompt |
| Feature Engineering (derived) | ✅ Active | EUI, Base Load Index, CDD |
| Building Efficiency Score | ✅ Active | Rule-based 0-100 daily score |
| Inspection Priority Scoring | ✅ Active | Weighted scoring model |
| RUL Prediction | ⚠️ Stub | Survival model registered, unused |
| Occupancy Prediction | ❌ Not started | Phase 130-02d future work |
| Building-wide EUI Anomaly | ❌ Not started | Need building-level model |

### Critical Gap Closed

**ML→Claude Context Injection**: The `_gather_ml_context()` method in `ai_optimizer.py` now injects LSTM forecasts, anomaly scores, fault classifications, and health trend slopes into Claude's optimisation prompt. This enables recommendations based on **predicted future state**, not just current conditions.

---

## 6. Implementation Notes

**Model Storage**: Each model is versioned and stored with metadata (training date, dataset size, performance metrics, feature list) in the model registry (`ml/models/registry.json`).

**Inference**: Models are served as lightweight service singletons. Building operations models run on schedule (every 15 mins). Equipment models run on new data arrival or on-demand during inspections.

**Cold Start**: For buildings with limited historical data, use portfolio-level models as a starting point, then fine-tune per building as data accumulates.

**Module Gating**: Advanced ML features (RUL prediction, fault classification) are gated behind relevant paid modules. Base anomaly detection and efficiency scoring are available in the base package.

**South African Context**: All energy baselines account for Eskom load-shedding stages — consumption during load-shedding should be excluded from baseline calculations or flagged separately to avoid skewing models.

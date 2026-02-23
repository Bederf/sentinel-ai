---
title: "Model Card: Chiller Failure Prediction"
type: "model-card"
status: "active"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
model_id: "lstm-chiller-v2.1"
equipment_type: "CHILLER"
r_squared: 0.6065
tier2_threshold: 0.70
tier3_threshold: 0.85
tags: ["ai-governance", "model-card", "chiller", "hvac", "lstm", "autoencoder"]
domain: "compliance"
audience: ["developers", "data-scientists", "auditors"]
complexity: "intermediate"
---

# Model Card: Chiller Failure Prediction

## 1. Model Information

| Field | Value |
|-------|-------|
| **Model Name** | Chiller Failure Prediction |
| **Model ID** | `lstm-chiller-v2.1` (LSTM), `ae-chiller-v1.3` (Autoencoder) |
| **Model Type** | Dual: Bidirectional LSTM + Symmetric Autoencoder |
| **Equipment Type** | CHILLER |
| **Version** | 2.1 (LSTM), 1.3 (Autoencoder) |
| **Owner** | SENTINEL Development Team |
| **Status** | Active |
| **R-squared (avg)** | 0.6065 (highest accuracy among active models) |
| **Last Retrained** | Monthly (automatic via MLOps pipeline) |

## 2. Intended Use

**Primary use case:** Predict remaining useful life (RUL) of centrifugal and scroll chillers and detect anomalous operating patterns before failure occurs.

**In-scope:**
- Siemens Desigo centrifugal chillers
- CAREL refrigeration controllers
- Carrier AquaEdge units
- Daikin magnetic bearing chillers
- Site 002, Site 005, Site 012 installations (4 instances total)

**Out-of-scope (do NOT use for):**
- Absorption chillers (different thermodynamic cycle)
- Residential/domestic refrigeration
- Chillers with fewer than 30 days of telemetry history
- Direct actuator positioning (SENTINEL sends setpoints; local Desigo control loop manages actuators)

## 3. Training Data

| Field | Value |
|-------|-------|
| **Source** | Site 002 chiller telemetry via BACnet/device abstraction layer |
| **Collection Period** | 365 days (simulation-generated with JHB climate model) |
| **Volume** | 1,095 days equivalent (3-year training target), 35,040 samples at 15-min intervals per year |
| **Features** | 10 input KPIs (see below) |
| **Refresh Cadence** | LSTM monthly, Autoencoder weekly |
| **Preprocessing** | Min-max normalization (0-1), 15-minute interval resampling, gap filling via linear interpolation |

**Input features:**
1. `chw_supply_temp` (chilled water supply temperature, degrees C)
2. `chw_return_temp` (chilled water return temperature, degrees C)
3. `compressor_outlet_pressure` (kPa)
4. `compressor_power_draw` (kW)
5. `cooling_load_percent` (estimated via delta-T)
6. `condenser_fan_speed` (percent)
7. `superheat_actual` (K, refrigerant efficiency)
8. `condenser_pressure` (kPa, fouling indicator)
9. `motor_vibration` (mm/s, bearing condition)
10. `oil_return_temp` (degrees C, lubrication condition)

**Data sheet reference:** `docs/ai-governance/data-sheets/EQUIPMENT-TELEMETRY.md`

## 4. Evaluation Metrics

| Metric | Value |
|--------|-------|
| **R-squared** | 0.6065 |
| **LSTM MAE** | 8.3 days |
| **LSTM RMSE** | 12.1 days |
| **AE Sensitivity** | 89% (true positive rate) |
| **AE Specificity** | 92% (true negative rate) |

**LSTM architecture:**
- Bidirectional LSTM, 128 units per layer, 2 layers
- Input window: 30 days at 15-minute intervals
- Output horizon: 60-90 days
- Batch size: 32, Learning rate: 0.001 (Adam), Early stopping patience: 5 epochs

**Autoencoder architecture:**
- Encoder: 64 -> 32 -> 16, Decoder: 16 -> 32 -> 64
- Activation: ReLU (hidden), Linear (output)
- Anomaly threshold: reconstruction error > 0.3
- Trained on 2 years of normal operation data

**Confidence thresholds:**

| Tier | Threshold | Action |
|------|-----------|--------|
| Tier 2 (Advisory) | 0.70 | Recommend to operator for review |
| Tier 3 (Auto-execute) | 0.85 | Execute setpoint change within safety bounds |

## 5. Known Limitations

- **Cold weather degradation:** Accuracy degrades below 5 degrees C outdoor temperature (uncommon in Johannesburg but relevant for high-altitude winter nights)
- **Equipment type scope:** Limited to scroll and centrifugal compressor types; absorption chillers have fundamentally different failure modes
- **Simulation training bias:** Training data from 365-day simulation may not fully capture real-world sensor noise, drift, and calibration issues
- **Seasonal variation:** JHB climate model assumes southern hemisphere patterns (sun in north sky, Oct-Mar wet season); models may underperform if deployed in northern hemisphere without retraining
- **Part-load accuracy:** Prediction accuracy lower during extended part-load operation (below 30% cooling load)

**Failure modes:**
- False positive: Predicts failure that does not occur (unnecessary maintenance scheduled) -- estimated 8% rate
- False negative: Misses impending failure (critical if chiller serves data center) -- estimated 11% rate
- Anomaly false alarm: Autoencoder triggers on unusual but safe operating conditions (hot day, high load)

**Environmental sensitivity:**
- Carbon intensity: SA grid = 0.35 kg CO2/kWh (used in energy impact calculations)
- Cost rate: R5/kWh commercial (used in savings estimates)
- JHB altitude (~1,750m) affects condenser performance assumptions

## 6. Safety and Compliance

**Safety controls:**
- **CHW supply temperature bounded 5-12 degrees C** (SafetyEngine enforced) -- prevents freeze risk and insufficient cooling
- **Zone temperature bounded 16-28 degrees C** -- occupant comfort maintained regardless of optimization
- All setpoint commands validated through SafetyEngine before execution
- Chiller staging rules enforce minimum run time and anti-short-cycle protection

**SENTINEL mode discipline:**
- Simulation/Shadow: Recommends + logs only (no writes to equipment)
- Supervised: Requires operator approval before setpoint change
- Automatic: Executes within quality gates (QualityGateEvaluator enforces)

**Regulatory alignment:**
- NIST AI RMF: MS 2.5 (model documentation), MS 2.9 (model card)
- ISO 42001: A.6.2.6 (AI system documentation)
- POPIA: No PII in training data (equipment telemetry only)

## 7. Deployment History

| Date | Event | Notes |
|------|-------|-------|
| 2026-02-06 | Initial deployment | v9.0 ML Predictive Maintenance milestone |
| 2026-02-10 | Registry migration | Phase 68-03: moved to database-driven registry |
| 2026-02-19 | Quality gate integration | v14.0: confidence-based tier routing active |
| 2026-02-20 | Health assessment timeline | v16.1: 5-component weighted health formula |

**Rollback triggers:**
- R-squared drops below 0.45 (sustained over 7 days)
- False positive rate exceeds 20%
- Safety boundary violation detected (any single occurrence triggers immediate review)
- Anomaly detector sensitivity drops below 75%

## 8. Ethical Considerations

- No personal data used in training or inference
- Model cannot discriminate against individuals
- Outputs affect equipment operations, not people directly
- Building occupant comfort maintained via safety bounds (16-28 degrees C zone temp)
- Energy savings recommendations consider environmental impact (0.35 kg CO2/kWh grid factor)

---

*This model card follows the SENTINEL AI Governance Framework. For updates, contact the SENTINEL Development Team.*

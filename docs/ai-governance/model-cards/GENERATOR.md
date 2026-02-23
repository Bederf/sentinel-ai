---
title: "Model Card: Generator Failure Prediction"
type: "model-card"
status: "active"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
model_id: "lstm-gen-v1.6"
equipment_type: "GENERATOR"
r_squared: 0.3710
tier2_threshold: 0.85
tier3_threshold: 0.95
tags: ["ai-governance", "model-card", "generator", "electrical", "cox-ph"]
domain: "compliance"
audience: ["developers", "data-scientists", "auditors"]
complexity: "intermediate"
---

# Model Card: Generator Failure Prediction

## 1. Model Information

| Field | Value |
|-------|-------|
| **Model Name** | Generator Failure Prediction |
| **Model ID** | `lstm-gen-v1.6` (LSTM), `ae-gen-v1.1` (Autoencoder) |
| **Model Type** | Dual: LSTM + Autoencoder (Cox Proportional Hazards for survival analysis) |
| **Equipment Type** | GENERATOR |
| **Version** | 1.6 (LSTM), 1.1 (Autoencoder) |
| **Owner** | SENTINEL Development Team |
| **Status** | Active (elevated thresholds -- lowest R-squared, active improvement) |
| **R-squared (avg)** | 0.3710 (lowest among active models) |
| **Last Retrained** | Monthly (automatic via MLOps pipeline) |

## 2. Intended Use

**Primary use case:** Predict diesel generator failure modes (fuel system degradation, valve carbon buildup, bearing wear) and schedule preventive maintenance based on runtime hours and operating trends.

**In-scope:**
- Diesel backup generators
- Generator automatic transfer switches (mechanical wear tracking)
- 14 instances across active sites (largest fleet among active model types)
- Monitoring and alerting only (no direct control)

**Out-of-scope (do NOT use for):**
- Gas turbine generators (different thermodynamic cycle)
- Solar/wind generators (renewable, no fuel system)
- Real-time load transfer decisions during power events
- Generators with fewer than 60 days of telemetry history

## 3. Training Data

| Field | Value |
|-------|-------|
| **Source** | Site 002, Site 005, Site 012 generator telemetry via BACnet/Modbus |
| **Collection Period** | 365 days simulation + historical maintenance records |
| **Volume** | 3+ years equivalent (daily intervals -- low-frequency equipment) |
| **Features** | 7 input KPIs (see below) |
| **Refresh Cadence** | LSTM monthly |
| **Preprocessing** | Daily aggregation (generators operate infrequently), runtime-weighted normalization |

**Input features:**
1. `runtime_total_hours` (cumulative, maintenance schedule driver)
2. `load_profile` (percent utilization during operation)
3. `fuel_consumption_rate` (liters/hour, engine efficiency)
4. `coolant_temperature` (degrees C, engine stress)
5. `exhaust_temperature` (degrees C, combustion quality)
6. `oil_pressure` (bar, lubrication health)
7. `transfer_switch_operations` (count, mechanical wear)

**Data sheet reference:** `docs/ai-governance/data-sheets/EQUIPMENT-TELEMETRY.md`

## 4. Evaluation Metrics

| Metric | Value |
|--------|-------|
| **R-squared** | 0.3710 |
| **LSTM MAE** | 12.3 days |
| **LSTM RMSE** | 18.7 days |
| **AE Sensitivity** | 82% |
| **AE Specificity** | 87% |

**LSTM architecture:**
- Input window: 60 days at daily intervals (low-frequency equipment)
- Output horizon: 60-180 days (generators have long degradation curves)
- Primary failure modes: Fuel system degradation, valve carbon buildup

**Autoencoder architecture:**
- Bottleneck: 10 units
- Anomaly threshold: reconstruction error > 0.38
- Trained on both steady-state and transient operational data

**Confidence thresholds (ELEVATED due to low R-squared):**

| Tier | Threshold | Action |
|------|-----------|--------|
| Tier 2 (Advisory) | 0.85 (elevated from standard 0.70) | Recommend to operator for review |
| Tier 3 (Auto-execute) | 0.95 (elevated from standard 0.85) | N/A -- monitoring only |

**Elevated threshold rationale:** With R-squared at 0.3710, the model explains only 37% of variance. Elevated thresholds (0.85/0.95) ensure only high-confidence predictions generate recommendations, reducing false alarm fatigue for maintenance teams.

## 5. Known Limitations

- **Sparse start-attempt data:** Generators operate infrequently (monthly tests, rare outages), providing limited failure event data for training
- **Fuel quality variance:** Diesel fuel quality varies by supplier and storage age; fuel degradation (gumming) is a key failure mode but difficult to sense remotely
- **Lowest R-squared (0.37):** Model is under active improvement; explains only 37% of variance
- **Long prediction horizon uncertainty:** 60-180 day prediction window introduces significant cumulative error (RMSE = 18.7 days)
- **Transfer switch mechanical wear:** Limited telemetry on transfer switch internals; operation count is a coarse proxy for actual contact wear

**Failure modes:**
- False positive: Predicts fuel system issue that is actually seasonal temperature effect on fuel viscosity
- False negative: Misses bearing wear because oil pressure sensor has insufficient resolution
- Start failure prediction gap: Model cannot reliably predict start failures (too few events in training data)

**Environmental sensitivity:**
- Ambient temperature affects fuel viscosity and starting reliability
- SA load-shedding frequency affects generator utilization rate (more frequent = faster wear)
- Fuel storage conditions (heat, moisture) affect fuel quality degradation

## 6. Safety and Compliance

**Safety controls:**
- **No direct control** -- generator model is monitoring and alerting only
- Alerts trigger maintenance work orders (WO-SIM auto-created when health < 50%)
- Critical alerts escalate to facility manager for emergency readiness assessment
- Transfer switch alerts include expected switchover time impact

**SENTINEL mode discipline:**
- All modes: Monitoring and alerting only (no control actions)
- Work order generation: automated when health < 50% (PostgreSQL trigger)
- Technician assigned by equipment type -> specialty mapping

**Regulatory alignment:**
- NIST AI RMF: MS 2.5 (model documentation), MS 2.9 (model card)
- ISO 42001: A.6.2.6 (AI system documentation)
- POPIA: No PII in training data (equipment telemetry only)
- SANS 10142: Electrical safety compliance maintained
- Generator readiness: Model supports (does not replace) mandatory weekly test schedule

## 7. Deployment History

| Date | Event | Notes |
|------|-------|-------|
| 2026-02-06 | Initial deployment | v9.0 ML Predictive Maintenance milestone |
| 2026-02-10 | Registry migration | Phase 68-03: database-driven registry |
| 2026-02-19 | Elevated thresholds applied | v14.0: 0.85/0.95 due to low R-squared |

**Rollback triggers:**
- R-squared drops below 0.25 (sustained over 14 days)
- Missed critical failure (any single occurrence triggers immediate review)
- False positive rate exceeds 30% (higher tolerance due to elevated thresholds)
- Start failure not predicted within 30-day window

**Active improvement plan:**
- Collecting more start-attempt event data across sites
- Investigating fuel quality proxy sensors (fuel turbidity, water content)
- Cox Proportional Hazards survival analysis for time-to-failure modeling

## 8. Ethical Considerations

- No personal data used in training or inference
- Model cannot discriminate against individuals
- Generator readiness has safety implications: backup power for hospitals (Site 005), data centers
- Model errs on side of caution: early maintenance recommendation preferred over missed failure
- Environmental: fuel consumption optimization reduces diesel emissions

---

*This model card follows the SENTINEL AI Governance Framework. For updates, contact the SENTINEL Development Team.*

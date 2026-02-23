---
title: "Model Card: AHU Degradation Prediction"
type: "model-card"
status: "active"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
model_id: "lstm-ahu-v2.0"
equipment_type: "AHU"
r_squared: 0.4915
tier2_threshold: 0.70
tier3_threshold: 0.85
tags: ["ai-governance", "model-card", "ahu", "hvac", "random-forest"]
domain: "compliance"
audience: ["developers", "data-scientists", "auditors"]
complexity: "intermediate"
---

# Model Card: AHU Degradation Prediction

## 1. Model Information

| Field | Value |
|-------|-------|
| **Model Name** | AHU Degradation Prediction |
| **Model ID** | `lstm-ahu-v2.0` (LSTM), `ae-ahu-v1.2` (Autoencoder) |
| **Model Type** | Dual: Bidirectional LSTM + Autoencoder |
| **Equipment Type** | AHU |
| **Version** | 2.0 (LSTM), 1.2 (Autoencoder) |
| **Owner** | SENTINEL Development Team |
| **Status** | Active |
| **R-squared (avg)** | 0.4915 |
| **Last Retrained** | Monthly (LSTM), Weekly (Autoencoder) |

## 2. Intended Use

**Primary use case:** Predict filter clogging timelines, motor bearing degradation, and anomalous operating patterns in air handling units.

**In-scope:**
- Supply air handling units (50-200 kW capacity)
- Return air processing units
- Mixed air control AHUs
- 30 instances across Site 002, Site 005, Site 012

**Out-of-scope (do NOT use for):**
- Residential HVAC split systems
- AHUs with fewer than 14 days of telemetry history
- Units without filter differential pressure sensors (filter replacement prediction unavailable)
- Direct fan speed or damper positioning (SENTINEL sends setpoints; local BMS control loop manages actuators)

## 3. Training Data

| Field | Value |
|-------|-------|
| **Source** | Site 002 AHU sensor data via BACnet/device abstraction layer |
| **Collection Period** | 365 days (simulation-generated with JHB climate model) |
| **Volume** | 730 days equivalent (2-year training target), 35,040 samples at 15-min intervals per year |
| **Features** | 10 input KPIs (see below) |
| **Refresh Cadence** | LSTM monthly, Autoencoder weekly |
| **Preprocessing** | Min-max normalization, 15-minute interval resampling, gap filling via forward-fill then linear interpolation |

**Input features:**
1. `supply_air_temperature` (degrees C, control accuracy)
2. `return_air_temperature` (degrees C, building ambient)
3. `mixed_air_temperature` (degrees C, damper control)
4. `supply_fan_speed_percent` (percent, energy consumption)
5. `supply_fan_pressure_delta` (Pa, filter fouling indicator)
6. `outdoor_air_percent` (percent, economizer position)
7. `supply_humidity` (percent, dehumidification)
8. `motor_current` (Amps, bearing friction)
9. `filter_pressure_drop` (Pa, replacement countdown)
10. `belt_tension` (N, wear indicator -- optional sensor)

**Data sheet reference:** `docs/ai-governance/data-sheets/EQUIPMENT-TELEMETRY.md`

## 4. Evaluation Metrics

| Metric | Value |
|--------|-------|
| **R-squared** | 0.4915 |
| **LSTM MAE** | 2.4 days |
| **LSTM RMSE** | 4.1 days |
| **AE Sensitivity** | 91% |
| **AE Specificity** | 94% |

**LSTM architecture:**
- Bidirectional LSTM, 128 units per layer, 2 layers
- Input window: 14 days at 15-minute intervals
- Output horizon: 14-30 days (faster failure modes than chiller)
- Primary failure mode: Filter clogging, motor bearing degradation

**Autoencoder architecture:**
- Bottleneck: 8 units (smaller than chiller due to simpler patterns)
- Anomaly threshold: reconstruction error > 0.4
- False positive rate: 5-8% (higher sensitivity tuning)
- Trained on 18 months of normal operation data

**Confidence thresholds:**

| Tier | Threshold | Action |
|------|-----------|--------|
| Tier 2 (Advisory) | 0.70 | Recommend to operator for review |
| Tier 3 (Auto-execute) | 0.85 | Execute within safety bounds |

## 5. Known Limitations

- **Filter differential pressure calibration drift:** Pressure sensors require annual calibration; uncalibrated sensors cause inaccurate filter life predictions
- **Seasonal HVAC load variation:** Summer cooling loads in JHB differ significantly from winter heating loads; model accuracy varies 10-15% between seasons
- **Economizer mode transitions:** Accuracy drops during free-cooling transitions when outdoor air damper position changes rapidly
- **Belt-driven vs direct-drive:** Model trained primarily on belt-driven fans; direct-drive units may show different degradation patterns for motor bearings

**Failure modes:**
- False positive on filter replacement: Humidity spike misinterpreted as pressure drop increase
- Missed motor bearing degradation: Gradual current increase masked by load changes
- Seasonal false alarms: Summer high-load operation misclassified as degradation

**Environmental sensitivity:**
- JHB wet season (Oct-Mar): Higher humidity increases filter loading rate
- Southern hemisphere: North-facing AHU intakes receive more solar heating
- Altitude (1,750m): Lower air density affects fan performance curves

## 6. Safety and Compliance

**Safety controls:**
- **Supply air temperature bounded 12-35 degrees C** -- prevents freeze risk and overheating
- **Minimum outdoor airflow maintained** -- ASHRAE 62.1 ventilation compliance
- Filter replacement alerts at 60 Pa (medium) and 80 Pa (urgent) pressure drop
- Fan motor overload protection via current monitoring

**SENTINEL mode discipline:**
- Simulation/Shadow: Recommends + logs only (no writes to equipment)
- Supervised: Requires operator approval before setpoint change
- Automatic: Executes within quality gates

**Regulatory alignment:**
- NIST AI RMF: MS 2.5 (model documentation), MS 2.9 (model card)
- ISO 42001: A.6.2.6 (AI system documentation)
- POPIA: No PII in training data (equipment telemetry only)

## 7. Deployment History

| Date | Event | Notes |
|------|-------|-------|
| 2026-02-06 | Initial deployment | v9.0 ML Predictive Maintenance milestone |
| 2026-02-10 | Registry migration | Phase 68-03: database-driven registry |
| 2026-02-19 | Quality gate integration | v14.0: confidence-based tier routing |
| 2026-02-20 | Health assessment timeline | v16.1: per-equipment health history |

**Rollback triggers:**
- R-squared drops below 0.35 (sustained over 7 days)
- False positive rate exceeds 20%
- Safety boundary violation detected
- Filter replacement prediction error exceeds 7 days consistently

## 8. Fairness & Bias

**Bias risk: MEDIUM** (see full assessment: [`fairness-bias-baseline.md`](../fairness-bias-baseline.md))

**Identified biases:**
- **Seasonal/climate bias:** JHB wet season (Oct-Mar) and dry season create distinct loading patterns. Northern hemisphere or coastal deployments would experience different humidity profiles. 10-15% accuracy variation between seasons is documented.
- **Equipment subtype bias:** Trained primarily on belt-driven fans. Direct-drive units may show different motor bearing degradation patterns.
- **Economizer mode bias:** Accuracy drops during free-cooling transitions when outdoor air damper position changes rapidly.
- **Altitude bias:** JHB altitude (1,750m) affects fan performance curves. Lower-altitude deployments may need recalibration.

**Mitigations:**
- Climate-aware feature engineering accounts for seasonal variation
- Humidity guard rule adjusts thresholds for wet season (Oct-Mar: lower to 40%, cap at 55%)
- Filter replacement alerts use differential pressure (physics-based, not model-dependent)
- Safety bounds (supply air 12-35 degrees C, minimum outdoor airflow per ASHRAE 62.1)
- Quality gate WARN enforcement in shadow mode addresses seasonal false alarm risk

**Fairness assessment:** AHU recommendations apply the same safety bounds and confidence thresholds regardless of unit location or zone served. Ventilation rates are maintained per ASHRAE 62.1, ensuring indoor air quality is not compromised by optimization for any zone.

**Review cadence:** Quarterly fairness metrics review per NIST AI RMF MS 2.7.

## 9. Ethical Considerations

- No personal data used in training or inference
- Model cannot discriminate against individuals
- Indoor air quality recommendations prioritize occupant health (ventilation rates maintained)
- Energy savings balanced against comfort and air quality requirements

---

*This model card follows the SENTINEL AI Governance Framework. For updates, contact the SENTINEL Development Team.*

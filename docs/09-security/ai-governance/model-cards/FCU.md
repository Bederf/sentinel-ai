---
title: "Model Card: FCU Health Assessment"
type: "model-card"
status: "active"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
model_id: "lstm-fcu-v1.9"
equipment_type: "FCU"
r_squared: 0.4236
tier2_threshold: 0.70
tier3_threshold: 0.85
tags: ["ai-governance", "model-card", "fcu", "vav", "hvac", "zone-control"]
domain: "compliance"
audience: ["developers", "data-scientists", "auditors"]
complexity: "intermediate"
---

# Model Card: FCU Health Assessment

## 1. Model Information

| Field | Value |
|-------|-------|
| **Model Name** | FCU Health Assessment |
| **Model ID** | `lstm-fcu-v1.9` (LSTM), `ae-fcu-v1.1` (Autoencoder) |
| **Model Type** | Dual: Bidirectional LSTM + Autoencoder |
| **Equipment Type** | FCU (also serves VAV with same model) |
| **Version** | 1.9 (LSTM), 1.1 (Autoencoder) |
| **Owner** | SENTINEL Development Team |
| **Status** | Active |
| **R-squared (avg)** | 0.4236 |
| **Last Retrained** | Monthly (LSTM), Weekly (Autoencoder) |

**IMPORTANT: Confidence capped at 0.45 -- advisory-only model. Recommendations from this model are NEVER auto-executed regardless of tier thresholds.**

## 2. Intended Use

**Primary use case:** Assess health of fan coil units and VAV boxes by detecting actuator stiction, damper mechanism degradation, and zone control quality issues.

**In-scope:**
- VAV boxes (perimeter and core zones)
- FCU units (4-pipe fan coil)
- Hydronic zone controllers
- 8 FCU + 3 VAV instances across active sites

**Out-of-scope (do NOT use for):**
- Split system air conditioners (different control architecture)
- FCUs without damper position feedback sensors
- Zone control decisions in occupied spaces without operator review (advisory-only)
- Direct actuator positioning (local BMS control loop manages actuators)

## 3. Training Data

| Field | Value |
|-------|-------|
| **Source** | Site 002 FCU/VAV sensor data, aggregated across 100+ zones |
| **Collection Period** | 365 days (simulation-generated with JHB climate model) |
| **Volume** | 1.5 years equivalent training data, aggregated across all zone equipment |
| **Features** | 7 input KPIs (see below) |
| **Refresh Cadence** | LSTM monthly, Autoencoder weekly |
| **Preprocessing** | Min-max normalization, 15-minute intervals, gap fill with zone-average imputation |

**Input features:**
1. `zone_temp_setpoint` (degrees C, comfort target)
2. `zone_temp_actual` (degrees C, measured)
3. `damper_position_feedback` (percent, actuator health)
4. `airflow_measured` (CFM, or inferred from damper position)
5. `reheat_valve_position` (percent, heating mode)
6. `zone_occupancy` (binary, load indicator)
7. `actuator_response_time` (seconds, mechanical wear)

**Data sheet reference:** `docs/ai-governance/data-sheets/EQUIPMENT-TELEMETRY.md`

## 4. Evaluation Metrics

| Metric | Value |
|--------|-------|
| **R-squared** | 0.4236 |
| **LSTM MAE** | 1.2 days |
| **LSTM RMSE** | 2.3 days |
| **AE Sensitivity** | 87% |
| **AE Specificity** | 89% |

**LSTM architecture:**
- Bidirectional LSTM, 128 units per layer, 2 layers
- Input window: 7 days at 15-minute intervals
- Output horizon: 7-14 days (zone equipment fails quickly)
- Primary failure modes: Actuator stiffness, damper mechanism jam

**Autoencoder architecture:**
- Bottleneck: 6 units (smallest among active models -- simple equipment)
- Anomaly threshold: reconstruction error > 0.35
- Trained on 1 year of zone data across all buildings

**Confidence thresholds:**

| Tier | Threshold | Action |
|------|-----------|--------|
| Tier 2 (Advisory) | 0.70 | Recommend to operator for review |
| Tier 3 (Auto-execute) | 0.85 | **BLOCKED: confidence capped at 0.45** |

**Confidence cap rationale:** FCU/VAV models have R-squared of 0.4236 and high variability due to occupancy patterns. The 0.45 confidence cap ensures all recommendations require human review, preventing unintended zone control changes that could affect occupant comfort.

## 5. Known Limitations

- **Highly variable occupancy patterns:** Zone usage is unpredictable (meetings, events, WFH days), causing significant noise in baseline establishment
- **Valve position sensor noise:** Analog valve position feedback is noisy (2-5% jitter), making stiction detection imprecise
- **Short failure horizon:** 7-14 day prediction window provides limited advance warning for maintenance scheduling
- **Cross-zone interference:** Adjacent zone HVAC interactions (open doors, shared plenum) affect individual zone predictions
- **Low R-squared:** 0.4236 indicates the model explains only 42% of variance -- significant room for improvement

**Failure modes:**
- False stiction alert: Sensor noise misinterpreted as actuator stiction (most common false positive)
- Missed damper jam: Gradual stiction increase within noise band goes undetected
- Occupancy-driven false alarm: Unusual occupancy pattern (late meeting) triggers anomaly detection

**Environmental sensitivity:**
- Zone numbering encodes floor: 001-099 = L0, 100-199 = L1, 200-299 = L2
- Top floors have more heat gain: model allows 1.2x more aggressive setpoint increase for top-floor zones
- Southern hemisphere: North-facing perimeter zones receive most solar gain

## 6. Safety and Compliance

**Safety controls:**
- **Zone temperature bounded 16-28 degrees C** (SafetyEngine enforced) -- occupant comfort maintained
- **Confidence capped at 0.45** -- all FCU recommendations are advisory-only
- **Never auto-execute:** Regardless of tier thresholds, FCU model output always requires human approval
- Minimum airflow maintained per zone for ventilation compliance

**SENTINEL mode discipline:**
- Simulation/Shadow: Recommends + logs only
- Supervised: Requires operator approval (ALWAYS for FCU due to confidence cap)
- Automatic: FCU recommendations are excluded from automatic execution

**Regulatory alignment:**
- NIST AI RMF: MS 2.5 (model documentation), MS 2.9 (model card)
- ISO 42001: A.6.2.6 (AI system documentation)
- POPIA: No PII in training data (zone telemetry only; occupancy is binary, not identity-linked)

## 7. Deployment History

| Date | Event | Notes |
|------|-------|-------|
| 2026-02-06 | Initial deployment | v9.0 ML Predictive Maintenance milestone |
| 2026-02-10 | Registry migration | Phase 68-03: database-driven registry |
| 2026-02-19 | Confidence cap applied | v14.0: capped at 0.45 after QA review |
| 2026-02-20 | Health assessment timeline | v16.1: per-equipment health history |

**Rollback triggers:**
- R-squared drops below 0.30 (sustained over 7 days)
- False positive rate exceeds 25% (higher tolerance due to advisory-only role)
- Safety boundary violation detected
- Consistent misclassification of healthy actuators as degraded

## 8. Fairness & Bias

**Bias risk: MEDIUM** (see full assessment: [`fairness-bias-baseline.md`](../fairness-bias-baseline.md))

**Identified biases:**
- **Occupancy pattern bias:** Training data reflects a specific building schedule. Buildings with different usage patterns (hospitals, retail, co-working) will have different zone dynamics, reducing model accuracy.
- **Zone location bias:** Perimeter zones (solar gain) behave differently from core zones (internal loads). Model treats both equally, which may create accuracy disparity across zone types.
- **Sensor noise bias:** Valve position feedback jitter (2-5%) varies by manufacturer, potentially biasing stiction detection toward noisier sensors.
- **Cross-zone interference:** Adjacent zone interactions through shared plenums are not fully modeled.

**Mitigations:**
- **Confidence capped at 0.45** -- all FCU recommendations are advisory-only, requiring human review. This is the primary mitigation against bias impact.
- Mode discipline: FCU recommendations are excluded from automatic execution in all modes
- Zone-average imputation for missing data reduces individual sensor bias
- Safety bounds (zone 16-28 degrees C) maintained regardless of model output

**Fairness assessment:** The advisory-only status of the FCU model means that even if occupancy pattern bias causes inaccurate zone-level predictions, no automated action is taken. Human operators validate all FCU recommendations before implementation, providing a human-in-the-loop check against biased outputs.

**Review cadence:** Quarterly fairness metrics review per NIST AI RMF MS 2.7.

## 9. Ethical Considerations

- No personal data used in training or inference
- Occupancy data is binary (occupied/unoccupied), not identity-linked
- Zone comfort is prioritized: model recommendations never compromise occupant comfort
- Advisory-only status ensures human judgment governs all zone control changes

---

*This model card follows the SENTINEL AI Governance Framework. For updates, contact the SENTINEL Development Team.*

---
title: "Fairness and Bias Baseline Analysis"
type: "assessment"
status: "active"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
domain: "compliance"
tags: ["ai-governance", "fairness", "bias", "nist-ai-rmf", "ms-2.7"]
audience: ["auditors", "management", "data-scientists"]
complexity: "intermediate"
nist_control: "MS 2.7"
iso_42001_clause: "A.6.2.6"
closes_nc: "NC-002"
---

# Fairness and Bias Baseline Analysis

## 1. Scope

This assessment covers all AI systems operating within the SENTINEL Building Management System (BMS) Intelligence platform. SENTINEL manages commercial building equipment -- chillers, air handling units, fan coil units, UPS systems, generators, and DALI lighting -- across multiple sites in South Africa.

**Key distinction:** SENTINEL manages equipment, not people. Fairness in this context refers to algorithmic and operational fairness -- ensuring that optimization recommendations, maintenance predictions, and energy management do not systematically disadvantage certain building zones, equipment types, or operating conditions. Demographic fairness (age, gender, race, disability) is not applicable because SENTINEL does not process personal data or make decisions about individuals.

**AI systems in scope:**

| Model | Equipment Type | R-squared | Status | Control Authority |
|-------|---------------|-----------|--------|-------------------|
| `lstm-chiller-v2.1` | CHILLER | 0.6065 | Active | Setpoint recommendations |
| `lstm-ahu-v2.0` | AHU | 0.4915 | Active | Setpoint recommendations |
| `lstm-fcu-v1.9` | FCU | 0.4236 | Active (advisory-only, confidence capped at 0.45) | Advisory only |
| `lstm-ups-v1.0` | UPS | 0.4144 | Active | Monitoring only |
| `lstm-gen-v1.6` | GENERATOR | 0.3710 | Active (elevated thresholds 0.85/0.95) | Monitoring only |
| `dali-placeholder-v0.1` | DALI | N/A | Placeholder (no trained model) | N/A |

**Regulatory driver:** This assessment satisfies NIST AI RMF measure MS 2.7 (bias assessment) and closes nonconformity NC-002 in the CAPA register.

## 2. Fairness Framework

Traditional AI fairness frameworks focus on demographic equity (ensuring AI does not discriminate against protected groups). SENTINEL operates in the building management domain where the "subjects" are equipment and building zones, not people. We therefore define fairness along four operational equity dimensions relevant to BMS AI:

### 2.1 Zone Equity

**Definition:** Optimization recommendations should not systematically favor certain building zones over others.

**Concern:** Executive floors or high-visibility zones could receive preferential comfort optimization while general office zones, server rooms, or storage areas receive less attention from predictive maintenance.

**Assessment criteria:**
- Recommendation frequency should be proportional to equipment density per zone
- Setpoint optimization should target the same comfort band (16-28 degrees C) regardless of zone function
- Maintenance prediction alerts should not cluster in specific zones unless driven by actual equipment condition

**Current state:** SENTINEL applies identical safety bounds (16-28 degrees C zone temperature) and identical confidence thresholds across all zones. Zone numbering encodes floor level (001-099 = L0, 100-199 = L1, 200-299 = L2) but does not encode zone priority or importance. The top-floor heat gain adjustment (1.2x more aggressive setpoint increase) is physics-based, not preference-based.

### 2.2 Equipment Equity

**Definition:** Maintenance predictions and health assessments should not deprioritize certain equipment types based on model accuracy rather than actual risk.

**Concern:** Models with higher R-squared (Chiller at 0.6065) could generate more actionable recommendations than lower-accuracy models (Generator at 0.3710), creating a coverage gap where less-modeled equipment receives less predictive attention.

**Assessment criteria:**
- All active equipment types should have trained models or be on a documented training roadmap
- Lower-accuracy models should have compensating controls (elevated thresholds, advisory-only mode)
- Equipment health scoring should use the same 5-component weighted formula regardless of type

**Current state:** All 6 equipment types are registered in the ML model registry. Lower-accuracy models have compensating controls:
- FCU (R-squared 0.4236): Confidence capped at 0.45, advisory-only
- Generator (R-squared 0.3710): Elevated thresholds (0.85/0.95), monitoring-only
- DALI: Placeholder with Tridonic-first principle (native controller handles core functions)

The 5-component health rating formula (baseline 35%, service 20%, runtime 20%, fault 15%, trend 10%) is applied uniformly across all equipment types.

### 2.3 Temporal Equity

**Definition:** Recommendations should account for all operating periods, not just peak hours or business hours.

**Concern:** Models trained primarily on business-hour data could perform poorly during off-hours, weekends, or holidays -- periods when equipment still operates and failures can occur undetected.

**Assessment criteria:**
- Training data should cover full 24-hour cycles, 7 days per week
- Model accuracy should be evaluated separately for peak, off-peak, and weekend periods
- After-hours alerts should receive the same escalation treatment as business-hour alerts

**Current state:** Training data is generated from 365-day simulation covering all hours. The building schedule model defines 9 daily states (early morning warmup, morning ramp, peak occupancy, lunch transition, afternoon, evening ramp-down, after-hours, deep night, weekend/holiday) ensuring temporal coverage. However, simulation data may not accurately represent real after-hours operating patterns where human operators are absent and equipment behaves differently.

### 2.4 Economic Equity

**Definition:** Energy optimization savings should be distributed across zones and systems, not concentrated in a single area while other areas bear the cost.

**Concern:** Aggressive energy optimization in one zone (e.g., reducing cooling) could shift thermal load to adjacent zones, improving one zone's energy metrics at the expense of another.

**Assessment criteria:**
- Energy savings calculations should account for cross-zone thermal transfer
- No single zone should bear a disproportionate share of comfort trade-offs for building-wide savings
- Carbon intensity calculations (0.35 kg CO2/kWh) should be applied consistently

**Current state:** The lifecycle orchestrator processes all zones together (not independently), and the building physics model accounts for inter-zone heat transfer. Safety bounds (16-28 degrees C) prevent any zone from being "sacrificed" for building-wide optimization. Energy cost calculations use a consistent rate (R5/kWh commercial) across all zones.

## 3. Bias Assessment by Model

### 3.1 Chiller Failure Prediction (R-squared = 0.6065)

**Bias risk: LOW-MEDIUM**

| Bias Dimension | Risk | Description |
|----------------|------|-------------|
| Geographic/site bias | Medium | Training data from Site 002 only. Chiller types, sizes, and loading patterns at other sites may differ. |
| Seasonal bias | Low | JHB climate model covers full year with southern hemisphere patterns. |
| Equipment subtype bias | Medium | Trained on scroll and centrifugal compressors. Absorption chillers excluded (different thermodynamic cycle). |
| Simulation bias | Low-Medium | 365-day simulation may not capture real-world sensor drift, noise, and calibration issues. |

**Mitigations in place:**
- Confidence scoring penalizes out-of-distribution inputs (OOD detection)
- Quality gates (QualityGateEvaluator) enforce mode discipline
- Safety bounds (CHW supply 5-12 degrees C, zone 16-28 degrees C) prevent harmful outcomes regardless of model bias
- Tier 3 auto-execute requires 0.85 confidence threshold

**Residual risk:** Model may underperform on chiller types not represented in Site 002 training data. This is acceptable because new sites enter simulation mode first, allowing performance validation before live control.

### 3.2 AHU Degradation Prediction (R-squared = 0.4915)

**Bias risk: MEDIUM**

| Bias Dimension | Risk | Description |
|----------------|------|-------------|
| Seasonal/climate bias | Medium-High | JHB wet season (Oct-Mar) and dry season create distinct loading patterns. Northern hemisphere or coastal deployments would experience different humidity profiles. |
| Equipment subtype bias | Medium | Trained on belt-driven fans. Direct-drive units may show different motor bearing degradation patterns. |
| Economizer mode bias | Medium | Accuracy drops during free-cooling transitions. Sites with frequent economizer mode changes may see more false alarms. |
| Altitude bias | Low | JHB altitude (1,750m) affects fan performance curves. Lower-altitude deployments may need recalibration. |

**Mitigations in place:**
- Climate-aware feature engineering accounts for seasonal variation
- Humidity guard rule adjusts thresholds for wet season (Oct-Mar: lower to 40%, cap at 55%)
- Filter replacement alerts use differential pressure (physics-based, not model-dependent)
- Safety bounds (supply air 12-35 degrees C, minimum outdoor airflow per ASHRAE 62.1)

**Residual risk:** 10-15% accuracy variation between seasons is documented. Model may generate seasonal false alarms that could desensitize operators. Mitigation: quality gate WARN enforcement in shadow mode.

### 3.3 FCU Health Assessment (R-squared = 0.4236)

**Bias risk: MEDIUM**

| Bias Dimension | Risk | Description |
|----------------|------|-------------|
| Occupancy pattern bias | High | Training data reflects specific building schedule. Buildings with different usage patterns (hospitals, retail, co-working) will have different zone dynamics. |
| Zone location bias | Medium | Perimeter zones (solar gain) behave differently from core zones (internal loads). Model treats both equally, which may create accuracy disparity. |
| Sensor noise bias | Medium | Valve position feedback jitter (2-5%) creates noise that varies by manufacturer, potentially biasing stiction detection toward noisier sensors. |
| Cross-zone interference | Low-Medium | Adjacent zone interactions through shared plenums not fully modeled. |

**Mitigations in place:**
- **Confidence capped at 0.45** -- all FCU recommendations are advisory-only, requiring human review
- Mode discipline: FCU recommendations excluded from automatic execution in all modes
- Zone-average imputation for missing data reduces individual sensor bias
- Safety bounds (zone 16-28 degrees C) maintained regardless of model output

**Residual risk:** Advisory-only status is the primary mitigation. Even if model bias causes inaccurate zone-level predictions, no automated action is taken. Human operators validate all FCU recommendations before implementation.

### 3.4 UPS Battery Degradation (R-squared = 0.4144)

**Bias risk: LOW**

| Bias Dimension | Risk | Description |
|----------------|------|-------------|
| Battery chemistry bias | Low-Medium | VRLA lead-acid and lithium-ion have different degradation curves. Model may be more accurate for one chemistry. |
| Environmental bias | Low | UPS rooms are typically climate-controlled, reducing ambient temperature variance. |
| Utilization pattern bias | Low | Battery charge/discharge cycles are physics-driven, with minimal occupancy or zone dependency. |

**Mitigations in place:**
- Monitoring and alerting only -- no direct control actions
- Battery degradation is primarily physics-based (Arrhenius relationship), reducing susceptibility to operational bias
- Work order generation requires operator confirmation

**Residual risk:** Minimal. UPS monitoring is inherently low-bias because battery degradation follows well-understood electrochemical processes.

### 3.5 Generator Failure Prediction (R-squared = 0.3710)

**Bias risk: LOW-MEDIUM**

| Bias Dimension | Risk | Description |
|----------------|------|-------------|
| Data sparsity bias | High | Generators operate infrequently (monthly tests, rare outages). Sparse start-attempt data creates significant class imbalance in training. |
| Fuel quality bias | Medium | Diesel fuel quality varies by supplier and storage conditions. Model cannot sense fuel quality directly. |
| Utilization pattern bias | Medium | SA load-shedding frequency affects generator utilization rate. Sites with different grid reliability will have different usage profiles. |

**Mitigations in place:**
- **Elevated thresholds (0.85/0.95)** compensate for low R-squared
- Monitoring and alerting only -- no direct control
- Cox Proportional Hazards survival analysis provides secondary validation
- Mandatory weekly test schedule maintained independently of model predictions

**Residual risk:** Start failure prediction remains unreliable due to insufficient event data. This is documented as a known limitation. Active improvement plan includes collecting more start-attempt data across sites.

### 3.6 DALI Lighting Optimization (No trained model)

**Bias risk: NOT APPLICABLE**

No trained model exists. DALI intelligence is provided by Tridonic-native DALI-2 capabilities (daylight harvesting, occupancy dimming, scene management). AI value-add is planned for cross-system coordination, predictive maintenance (lumDATA Part 251/253), and tariff-aware scheduling only.

**When model is trained:** Bias assessment will be performed as part of the model activation governance review. Training data must include at least 180 days of lumDATA telemetry from 2 or more sites.

## 4. Data Bias Assessment

### 4.1 Training Data Limitations

| Bias Source | Description | Severity | Mitigation |
|-------------|-------------|----------|------------|
| **Single-site training** | All models trained primarily on Site 002 data. Geographic, building-type, and operational biases from this single site propagate to all predictions. | High | New sites enter simulation mode first. Model performance validated before live control. Confidence scoring penalizes OOD inputs. |
| **Simulation vs. real-world** | 365-day simulation data lacks real-world sensor noise, drift, calibration issues, and unexpected operating conditions. | Medium | Quality gates (QualityGateEvaluator) detect when model operates outside training distribution. Mode discipline restricts execution authority. |
| **JHB climate model** | Southern hemisphere, high-altitude (1,750m), specific wet/dry seasons. Models may not transfer to other climates without retraining. | Medium | Climate-aware feature engineering. Documented in model cards as known limitation. |
| **Technician feedback subjectivity** | Work order outcomes influenced by technician experience level. More experienced technicians may provide different assessments than less experienced ones. | Low-Medium | MLOps feedback loop includes label lag tracking (p95 hours). Training readiness thresholds require minimum feedback volume. |
| **Equipment fleet composition** | Training fleet may not represent all manufacturers, models, and vintages. Equipment from different manufacturers may have different failure signatures. | Medium | Point-driven optimization (key off available control points, not equipment type strings). Equipment type is a hint, not a gate. |

### 4.2 Label Bias

Training labels (health scores, failure events, degradation state) are derived from:
1. **Simulation engine** -- deterministic, reproducible, but potentially oversimplified
2. **Sensor telemetry** -- subject to drift, noise, and calibration errors
3. **Technician assessments** -- subjective, influenced by experience level
4. **Work order outcomes** -- binary (resolved/unresolved), losing nuance

**Mitigation:** The quality gate framework tracks feedback_capture_rate_7d_pct, label_lag_p95_hours, and drift_critical_alerts_24h to detect label quality degradation. Training readiness thresholds are mode-aware: live mode requires 0.85 capture rate with 180 minimum samples; shadow mode requires 0.75/120; simulation requires 0.50/30.

### 4.3 Representation Analysis

| Population | Represented in Training | Gap | Impact |
|------------|------------------------|-----|--------|
| HVAC equipment (CHILLER, AHU, FCU) | Well represented (100+ instances) | Manufacturer diversity limited | May underperform on non-Siemens equipment |
| Electrical equipment (UPS, GEN) | Moderately represented (18 instances) | Sparse failure events for generators | Low prediction confidence for rare failures |
| Lighting (DALI) | Not represented (placeholder) | No training data | No AI predictions generated |
| Night/weekend operation | Represented in simulation | Real-world after-hours patterns unknown | Potential accuracy gap outside business hours |
| Extreme weather events | Partially represented | Simulation may not capture extremes | Heat waves, cold snaps may cause OOD behavior |

## 5. Baseline Metrics

The following metrics establish the fairness baseline for SENTINEL's AI systems. Initial target values are defined below. Actual baseline values will be populated from the first quarterly review using production data.

### 5.1 Zone Equity Metrics

| Metric | Target | Measurement Method | Frequency |
|--------|--------|-------------------|-----------|
| Prediction accuracy variance by zone | Less than 10% R-squared variance across zones within same model | Compare per-zone R-squared for FCU/VAV models | Quarterly |
| Recommendation distribution by zone | Proportional to equipment count per zone (within 15% tolerance) | Count recommendations per zone / equipment count per zone | Quarterly |
| Comfort deviation by zone | Less than 0.5 degrees C mean deviation from setpoint across zones | Compare actual vs setpoint temperature by zone | Monthly |

### 5.2 Equipment Equity Metrics

| Metric | Target | Measurement Method | Frequency |
|--------|--------|-------------------|-----------|
| Recommendation rate by equipment type | Proportional to equipment count (within 20% tolerance) | Count recommendations per type / equipment count per type | Quarterly |
| False positive rate variance by type | Less than 15% FP rate variance across equipment types | Compare FP rates from work order feedback | Quarterly |
| Health score distribution by type | No equipment type has median health below 40% unless driven by actual condition | Compare median health scores across types | Monthly |

### 5.3 Temporal Equity Metrics

| Metric | Target | Measurement Method | Frequency |
|--------|--------|-------------------|-----------|
| Prediction accuracy: peak vs. off-peak | Less than 15% R-squared variance between peak and off-peak hours | Split evaluation dataset by time period | Quarterly |
| Alert response time: business vs. after-hours | Less than 30 minutes additional response lag for after-hours alerts | Compare alert-to-acknowledgment times | Monthly |
| Coverage gap: weekend/holiday | No model should have more than 20% accuracy degradation on weekends | Split evaluation by day type | Quarterly |

### 5.4 Economic Equity Metrics

| Metric | Target | Measurement Method | Frequency |
|--------|--------|-------------------|-----------|
| Energy savings distribution by zone | No zone bears more than 25% of building-wide comfort trade-off | Compare setpoint deviations by zone during optimization | Quarterly |
| Cost savings attribution | Savings attributed proportionally to zone equipment, not concentrated | Compare R/kWh savings by zone | Quarterly |

**NOTE:** These are target metrics. Initial baseline values will be populated from the first quarterly review scheduled for Q2 2026. Until production data is available, simulation-derived metrics from the lifecycle orchestrator serve as provisional baselines.

## 6. Assessment Conclusion

### 6.1 Overall Fairness Risk: LOW

SENTINEL poses LOW fairness risk for the following structural reasons:

1. **Equipment, not people:** SENTINEL manages building equipment, not individuals. There is no demographic impact, no personally identifiable information in training data, and no decisions that affect individuals differently based on protected characteristics.

2. **Safety interlocks prevent harmful outcomes:** Regardless of model bias, SafetyEngine enforces hard bounds:
   - Zone temperature: 16-28 degrees C
   - Chilled water supply: 5-12 degrees C
   - Supply air temperature: 12-35 degrees C
   - Minimum ventilation rates per ASHRAE 62.1
   These bounds cannot be overridden by AI recommendations.

3. **Quality gates cap confidence on low-accuracy models:**
   - FCU: Confidence capped at 0.45, advisory-only
   - Generator: Elevated thresholds (0.85/0.95), monitoring-only
   - QualityGateEvaluator enforces CAP_CONFIDENCE, SUPPRESS_TIER3, and BLOCK_WRITES actions

4. **Mode discipline restricts execution authority:**
   - Simulation/Shadow: Recommends and logs only (no writes to equipment)
   - Supervised: Requires operator approval
   - Automatic: Executes only within quality gates, with fail-closed behavior in live_control mode

5. **Single-site bias is structurally mitigated:** New sites enter simulation mode first, allowing model performance validation before any live control. This prevents untested bias from propagating to new environments.

### 6.2 Residual Risks

| Risk | Severity | Mitigation | Monitoring |
|------|----------|------------|------------|
| Single-site training bias | Medium | OOD confidence penalization, simulation-first onboarding | Quarterly R-squared comparison across sites |
| Seasonal accuracy variation | Low-Medium | Climate-aware features, humidity guards | Monthly accuracy by season |
| Technician feedback subjectivity | Low | Label quality tracking, minimum sample thresholds | MLOps feedback_capture_rate |
| Equipment subtype coverage gaps | Medium | Point-driven optimization, equipment-agnostic design | Model card known limitations |

### 6.3 Recommendations

1. **Populate baseline metrics** from first quarterly review (Q2 2026)
2. **Expand training data** to include Sites 005 and 012 when sufficient telemetry is available
3. **Monitor zone equity** in FCU/VAV models as occupancy patterns become established
4. **Review generator model** when additional start-attempt events are collected
5. **Perform full bias assessment** for DALI model when training begins

## 7. Review Cadence

| Activity | Frequency | Responsible |
|----------|-----------|-------------|
| Fairness metrics review | Quarterly | ML Lead |
| Bias assessment update | Annually (or on model retrain) | Compliance Lead |
| Zone equity audit | Quarterly | Operations Lead |
| Model card fairness sections | Updated with each model version | AI Engineering Lead |
| Management review input | Semi-annually | AIMS Management |

## 8. Document History

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 1.0.0 | 2026-02-23 | SENTINEL Governance Team | Initial fairness/bias baseline analysis. Closes NC-002. |

## 9. Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| ML Lead | ___________________ | ________ | ________ |
| Compliance Lead | ___________________ | ________ | ________ |
| Operations Lead | ___________________ | ________ | ________ |

---

*This assessment follows the SENTINEL AI Governance Framework and satisfies NIST AI RMF measure MS 2.7 (bias assessment). For updates, contact the SENTINEL Governance Team.*

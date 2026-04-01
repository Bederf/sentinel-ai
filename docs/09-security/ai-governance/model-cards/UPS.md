---
title: "Model Card: UPS Battery Degradation"
type: "model-card"
status: "active"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
model_id: "lstm-ups-v1.0"
equipment_type: "UPS"
r_squared: 0.4144
tier2_threshold: 0.70
tier3_threshold: 0.85
tags: ["ai-governance", "model-card", "ups", "electrical", "battery"]
domain: "compliance"
audience: ["developers", "data-scientists", "auditors"]
complexity: "intermediate"
---

# Model Card: UPS Battery Degradation

## 1. Model Information

| Field | Value |
|-------|-------|
| **Model Name** | UPS Battery Degradation Prediction |
| **Model ID** | `lstm-ups-v1.0` |
| **Model Type** | LSTM-based time series prediction |
| **Equipment Type** | UPS |
| **Version** | 1.0 |
| **Owner** | SENTINEL Development Team |
| **Status** | Active |
| **R-squared (avg)** | 0.4144 |
| **Last Retrained** | Monthly (automatic via MLOps pipeline) |

## 2. Intended Use

**Primary use case:** Predict battery degradation in uninterruptible power supply systems and detect anomalous discharge/charge patterns that indicate impending battery failure.

**In-scope:**
- UPS battery systems (VRLA lead-acid and lithium-ion)
- Battery string monitoring and health trending
- 4 instances across active sites
- Monitoring and alerting only (no direct control)

**Out-of-scope (do NOT use for):**
- Battery Energy Storage Systems (BESS) -- different use profile and chemistry
- UPS bypass or transfer switch control decisions
- Real-time load shedding decisions during power events
- UPS units without battery voltage and current telemetry

## 3. Training Data

| Field | Value |
|-------|-------|
| **Source** | Site 002 UPS telemetry via BACnet/Modbus device abstraction layer |
| **Collection Period** | 365 days (simulation-generated) |
| **Volume** | Training equivalent covers battery charge/discharge cycles over simulated lifetime |
| **Features** | Battery voltage, current, temperature, runtime remaining, charge cycles |
| **Refresh Cadence** | LSTM monthly |
| **Preprocessing** | Min-max normalization, hourly resampling (UPS data changes slowly), outlier removal for power event spikes |

**Data sheet reference:** `docs/ai-governance/data-sheets/EQUIPMENT-TELEMETRY.md`

## 4. Evaluation Metrics

| Metric | Value |
|--------|-------|
| **R-squared** | 0.4144 |
| **Prediction accuracy** | Moderate -- battery degradation is inherently nonlinear |

**Confidence thresholds:**

| Tier | Threshold | Action |
|------|-----------|--------|
| Tier 2 (Advisory) | 0.70 | Recommend battery inspection/replacement to operator |
| Tier 3 (Auto-execute) | 0.85 | N/A -- monitoring only, no direct control actions |

## 5. Known Limitations

- **Battery chemistry sensitivity:** VRLA lead-acid and lithium-ion have fundamentally different degradation curves; model accuracy varies by chemistry type
- **Ambient temperature sensitivity:** Battery life is highly temperature-dependent (Arrhenius relationship); accuracy degrades in uncontrolled environments
- **Infrequent discharge events:** Most UPS batteries rarely discharge fully, creating sparse failure data for training
- **String imbalance detection:** Individual cell monitoring not available on all UPS models; string-level voltage may mask weak cells
- **Nonlinear degradation:** Battery end-of-life degradation accelerates suddenly ("knee" in capacity curve), making long-horizon prediction inherently difficult

**Failure modes:**
- False optimism: Predicts battery health is good when individual cells are failing (masked by string average)
- Late warning: Sudden capacity drop in final 10% of battery life not predicted early enough
- Temperature correlation: Seasonal temperature changes misinterpreted as degradation trend

**Environmental sensitivity:**
- UPS room temperature directly affects battery life prediction accuracy
- Power quality (frequency of micro-outages) affects charge cycle count

## 6. Safety and Compliance

**Safety controls:**
- **No direct control** -- UPS model is monitoring and alerting only
- Alerts trigger maintenance work orders for battery inspection
- Critical alerts escalate to facility manager immediately
- Battery replacement recommendations include lead time for procurement

**SENTINEL mode discipline:**
- All modes: Monitoring and alerting only (no control actions)
- Work order generation requires operator confirmation
- Critical battery alerts bypass normal approval workflow for notification (not control)

**Regulatory alignment:**
- NIST AI RMF: MS 2.5 (model documentation), MS 2.9 (model card)
- ISO 42001: A.6.2.6 (AI system documentation)
- POPIA: No PII in training data (equipment telemetry only)
- Electrical safety: SANS 10142 compliance maintained (model does not affect electrical safety systems)

## 7. Deployment History

| Date | Event | Notes |
|------|-------|-------|
| 2026-02-06 | Initial deployment | v9.0 ML Predictive Maintenance milestone |
| 2026-02-10 | Registry migration | Phase 68-03: database-driven registry |
| 2026-02-19 | Quality gate integration | v14.0: confidence-based tier routing |

**Rollback triggers:**
- R-squared drops below 0.30 (sustained over 7 days)
- Missed critical battery failure (any single occurrence triggers review)
- Consistent false alarms (>3 per month per UPS unit)

## 8. Ethical Considerations

- No personal data used in training or inference
- Model cannot discriminate against individuals
- Power continuity has safety implications: model errs on side of caution (early warning preferred over missed failure)
- Battery disposal recommendations follow environmental regulations

---

*This model card follows the SENTINEL AI Governance Framework. For updates, contact the SENTINEL Development Team.*

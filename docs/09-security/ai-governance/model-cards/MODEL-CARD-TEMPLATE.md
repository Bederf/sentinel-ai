---
title: "Model Card: {MODEL_NAME}"
type: "model-card"
status: "draft"
version: "0.1.0"
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
author: "SENTINEL Governance Team"
model_id: "{model-id}"
equipment_type: "{equipment_type}"
r_squared: null
tier2_threshold: null
tier3_threshold: null
tags: ["ai-governance", "model-card"]
domain: "compliance"
audience: ["developers", "data-scientists", "auditors"]
complexity: "intermediate"
---

# Model Card: {MODEL_NAME}

> Template version 1.0 | Based on [Mitchell et al. 2019](https://arxiv.org/abs/1810.03993) adapted for SENTINEL BMS context.
> See `docs/ai-governance/05-model-and-data-governance.md` for minimum required fields.

## 1. Model Information

| Field | Value |
|-------|-------|
| **Model Name** | {Full descriptive name} |
| **Model ID** | {model-id from ml_models table} |
| **Model Type** | {LSTM, Autoencoder, Random Forest, Cox PH, etc.} |
| **Equipment Type** | {CHILLER, AHU, FCU, UPS, GENERATOR, DALI} |
| **Version** | {semantic version} |
| **Owner** | SENTINEL Development Team |
| **Status** | {active / placeholder / degraded / disabled} |
| **R-squared (avg)** | {0.00 - 1.00 or N/A} |
| **Last Retrained** | {date or N/A} |

## 2. Intended Use

**Primary use case:** {What the model predicts/detects}

**In-scope:**
- {Bullet list of supported scenarios}

**Out-of-scope (do NOT use for):**
- {Bullet list of unsupported scenarios}

## 3. Training Data

| Field | Value |
|-------|-------|
| **Source** | {Data origin} |
| **Collection Period** | {Date range} |
| **Volume** | {Number of samples/days} |
| **Features** | {Number of input features} |
| **Refresh Cadence** | {How often retrained} |
| **Preprocessing** | {Normalization, gap filling, etc.} |

**Data sheet reference:** `docs/ai-governance/data-sheets/EQUIPMENT-TELEMETRY.md`

## 4. Evaluation Metrics

| Metric | Value |
|--------|-------|
| **R-squared** | {value} |
| **LSTM MAE** | {days} |
| **LSTM RMSE** | {days} |
| **AE Sensitivity** | {%} |
| **AE Specificity** | {%} |

**Confidence thresholds:**

| Tier | Threshold | Action |
|------|-----------|--------|
| Tier 2 (Advisory) | {value} | Recommend to operator |
| Tier 3 (Auto-execute) | {value} | Execute within safety bounds |

## 5. Known Limitations

- {Limitation 1}
- {Limitation 2}
- {Limitation 3}

**Failure modes:**
- {What happens when the model is wrong}

**Environmental sensitivity:**
- {Climate, seasonal, or operational conditions that affect accuracy}

## 6. Safety and Compliance

**Safety controls:**
- {Safety boundary 1}
- {Safety boundary 2}

**SENTINEL mode discipline:**
- Simulation/Shadow: Recommends + logs only (no writes)
- Supervised: Requires operator approval
- Automatic: Executes within quality gates

**Regulatory alignment:**
- NIST AI RMF: MS 2.5 (model documentation), MS 2.9 (model card)
- ISO 42001: A.6.2.6 (AI system documentation)
- POPIA: No PII in training data (equipment telemetry only)

## 7. Deployment History

| Date | Event | Notes |
|------|-------|-------|
| {date} | {Initial deployment / retrain / rollback} | {details} |

**Rollback triggers:**
- R-squared drops below {threshold}
- False positive rate exceeds {threshold}
- Safety boundary violation detected

## 8. Ethical Considerations

- No personal data used in training or inference
- Model cannot discriminate against individuals
- Outputs affect equipment operations, not people directly
- Building occupant comfort maintained via safety bounds

---

*This model card follows the SENTINEL AI Governance Framework. For updates, contact the SENTINEL Development Team.*

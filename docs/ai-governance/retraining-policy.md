---
title: "ML Model Retraining Policy"
type: "policy"
status: "active"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
tags: ["ai-governance", "retraining", "ml-models", "nist-ai-rmf", "mlops"]
domain: "compliance"
audience: "all"
complexity: "intermediate"
estimated_read_time: 12
nist_reference: "MG 2.4"
---

# ML Model Retraining Policy

## 1. Scope

This policy governs the retraining of all active ML models in the SENTINEL model registry. It defines when models are retrained, how retraining is validated, and what evidence is produced for audit purposes.

### 1.1 Models in Scope

SENTINEL maintains **6 active equipment-type model families**, each with two model architectures (LSTM for remaining useful life prediction and Autoencoder for anomaly detection), for a total of **14 active model instances** (some equipment types share architectures):

| Model Family | Model ID (LSTM) | Model ID (AE) | Equipment Types | Status |
|--------------|-----------------|---------------|-----------------|--------|
| AHU | `lstm-ahu-v2.1` | `ae-ahu-v1.3` | AHU | Active |
| CHILLER | `lstm-chiller-v2.1` | `ae-chiller-v1.3` | CHILLER | Active |
| FCU | `lstm-fcu-v2.1` | `ae-fcu-v1.3` | FCU | Active |
| UPS | `lstm-ups-v2.1` | `ae-ups-v1.3` | UPS | Active |
| GENERATOR | `lstm-generator-v2.1` | `ae-generator-v1.3` | GENERATOR | Active |
| DALI | `lstm-dali-v2.1` | `ae-dali-v1.3` | DALI | Active |

**Model cards** for each family are maintained in `docs/ai-governance/model-cards/`.

### 1.2 Out of Scope

- Third-party LLM models (Anthropic Claude, Ollama) -- governed by [Third-Party AI Risk Register](third-party-ai-risk-register.md)
- Rule-based systems (safety interlocks, threshold alerts) -- no ML component
- Feature engineering pipelines -- these are updated as part of model retraining

---

## 2. Retraining Cadence

### 2.1 Scheduled Retraining

The background retraining scheduler (`backend/ml/training/retraining_scheduler.py`) runs a daily staleness check:

| Parameter | Value |
|-----------|-------|
| **Check frequency** | Every 24 hours |
| **Staleness threshold** | Model age > 30 days |
| **Performance threshold** | R-squared < 0.65 |
| **Models per cycle** | 1 (to prevent resource contention) |
| **Full fleet refresh** | All 14 models within 2 weeks |
| **Scheduling service** | APScheduler via `BackgroundSchedulerService` |

**Priority order for scheduled retraining:**
1. Missing models (no active model exists)
2. Oldest models (highest age first)
3. Worst performers (lowest R-squared first)

### 2.2 Triggered Retraining

In addition to scheduled retraining, models are retrained on demand when:

| Trigger | Detection Method | Response Time |
|---------|-----------------|---------------|
| **Drift alert** | Model drift monitoring detects distribution shift exceeding threshold | Next retraining cycle (within 24h) |
| **Significant data change** | New equipment type onboarded, major sensor reconfiguration | Manual trigger by AI Engineering Lead |
| **Operator request** | Operator reports degraded prediction quality | Manual trigger via `/api/ml-retraining/trigger` |
| **Quality gate failure** | Quality gate evaluator reports persistent metric failures | Escalated to AI Engineering Lead for assessment |
| **Safety incident** | Any safety boundary violation linked to model output | Immediate review; retraining if model is root cause |

### 2.3 Cooldown Rules

To prevent excessive retraining that could destabilise model performance:

| Rule | Threshold |
|------|-----------|
| Minimum interval between retraining attempts for the **same model** | 4 hours |
| Maximum retraining attempts per model per day | 3 |
| Maximum concurrent retraining jobs | 1 |

---

## 3. Retraining Process

### 3.1 Step 1: Training-Readiness Gate Check

Before retraining begins, the system verifies that sufficient data and feedback exist for a meaningful training run. The thresholds vary by SENTINEL operational mode:

| Metric | Live Mode | Shadow Mode | Simulation Mode |
|--------|-----------|-------------|-----------------|
| Feedback capture rate (7-day) | >= 85% | >= 75% | >= 50% |
| Minimum labelled samples | 180 | 120 | 30 |
| Label lag P95 (hours) | <= 5 | <= 3 | <= 1 |

If the training-readiness gate fails, retraining is deferred to the next cycle and the failure is logged.

### 3.2 Step 2: Model Training

Training is executed using the fleet fine-tuning architecture (`backend/ml/training/fine_tuning.py`):

1. Training data is loaded from the most recent telemetry (site-specific)
2. Data is preprocessed: min-max normalisation, 15-minute interval resampling, gap filling via linear interpolation
3. Model is trained with configured hyperparameters (epochs, batch size, learning rate)
4. Training runs in a **background thread** -- API requests continue uninterrupted
5. Old model remains active during training (zero-downtime guarantee)

### 3.3 Step 3: Validation Checklist

Every retrained model must pass the following validation before it can replace the current active model:

| Check | Criteria | Failure Action |
|-------|----------|----------------|
| R-squared maintained or improved | New R-squared >= (previous R-squared - 0.05) | Reject new model; retain previous version |
| No safety regression | New model does not produce outputs outside safety boundaries on validation set | Reject new model; flag for investigation |
| Quality gate pass | New model passes quality gate evaluation in current operational mode | Reject new model; retain previous version |
| Anomaly detector sensitivity | Autoencoder sensitivity >= 75% (true positive rate) | Reject new model; retain previous version |
| No false-positive spike | False positive rate <= 20% on validation set | Reject new model; retain previous version |

### 3.4 Step 4: Promotion

Validated models follow the SENTINEL mode discipline for promotion:

| Stage | Description | Duration |
|-------|-------------|----------|
| **Shadow evaluation** | New model runs in parallel with current model; outputs compared but not acted upon | 24--48 hours (automatic) |
| **Supervised** | New model generates live recommendations requiring operator approval | 7 days for first deployment; 24 hours for routine retraining |
| **Automatic** | New model executes within quality gates without operator approval | Ongoing until next retraining |

For routine retraining (scheduled staleness), shadow evaluation is automatic and promotion to supervised/automatic follows the site's current operational mode.

---

## 4. Run Log Template

Every retraining event must produce a run log entry. These entries form the auditable record of model lifecycle changes.

### 4.1 Run Log Format

| Run ID | Date | Model | Trigger | R-squared Before | R-squared After | Validated By | Promoted | Notes |
|--------|------|-------|---------|-----------------|----------------|-------------|----------|-------|
| `RUN-2026-0223-001` | 2026-02-23 | lstm-chiller-v2.1 | scheduled/staleness | 0.5850 | 0.6065 | Automated validation | Yes | Routine retraining; R-squared improved |
| `RUN-2026-0222-001` | 2026-02-22 | ae-ahu-v1.3 | drift/distribution_shift | 0.6800 | 0.7120 | AI Engineering Lead | Yes | Drift alert triggered by occupancy pattern change |
| `RUN-2026-0221-001` | 2026-02-21 | lstm-fcu-v2.1 | operator_request | 0.7200 | 0.6900 | Automated validation | No | R-squared regression > 0.05; previous model retained |

### 4.2 Run Log Fields

| Field | Description | Required |
|-------|-------------|----------|
| **Run ID** | Unique identifier: `RUN-{YYYY}-{MMDD}-{SEQ}` | Yes |
| **Date** | ISO 8601 date of retraining | Yes |
| **Model** | Model ID from registry (e.g., `lstm-chiller-v2.1`) | Yes |
| **Trigger** | What initiated retraining: `scheduled/staleness`, `drift/{type}`, `operator_request`, `safety_incident`, `manual` | Yes |
| **R-squared Before** | R-squared score of the current active model | Yes |
| **R-squared After** | R-squared score of the newly trained model | Yes |
| **Validated By** | `Automated validation` or name of reviewer who approved | Yes |
| **Promoted** | `Yes` or `No` -- whether the new model replaced the active model | Yes |
| **Notes** | Free-text explanation of outcome, issues, or observations | Optional |

### 4.3 Run Log Storage

- **Primary:** `evidence/retraining-run-logs/` directory, one file per quarter (e.g., `2026-Q1.md`)
- **API access:** `GET /api/ml-retraining/history` returns the last 50 run log entries
- **Retention:** Run logs retained for 3 years (audit requirement)

---

## 5. Rollback Procedure

If a retrained model demonstrates degraded performance after promotion:

| Step | Action | Timeline |
|------|--------|----------|
| 1 | Detect degradation via quality gate, drift monitoring, or operator report | Ongoing monitoring |
| 2 | AI Engineering Lead reviews run log and validation results | Within 1 hour of detection |
| 3 | Revert to previous model version | Within 5 minutes of decision |
| 4 | Log rollback in run log with `Promoted: No (rolled back)` and reason | Immediately after rollback |
| 5 | Investigate root cause (data quality, training bug, distribution shift) | Within 24 hours |
| 6 | Schedule corrective retraining with fix applied | Next available cycle |

**Rollback triggers:**
- R-squared drops below 0.45 sustained over 7 days
- False positive rate exceeds 20%
- Any safety boundary violation linked to model output
- Anomaly detector sensitivity drops below 75%

---

## 6. Roles and Responsibilities

| Role | Responsibility |
|------|---------------|
| **AI Engineering Lead** | Owns this policy; approves triggered retraining; reviews rollbacks; signs off on model promotions for first deployments |
| **MLOps Owner** | Monitors retraining scheduler health; maintains training infrastructure; responds to training failures |
| **Operations Lead** | Reports prediction quality issues; approves model deployment to supervised/automatic mode |
| **Compliance Lead** | Reviews run logs quarterly; verifies audit trail completeness; confirms NIST MG 2.4 compliance |

---

## 7. Cross-References

| Document | Relevance |
|----------|-----------|
| [Background ML Retraining Architecture](../02-architecture/background-ml-retraining.md) | Technical implementation of retraining scheduler and worker |
| [Model Cards](model-cards/) | Per-model documentation including training data, metrics, and limitations |
| [Quality Gate Policy](../../backend/app/services/quality_gate_policy.py) | 14-metric quality gate with mode-specific thresholds |
| [Residual Risk Disclosure](residual-risk-disclosure.md) | Operator-facing risk communication (R-001 model accuracy degradation) |
| [Control Applicability Matrix](control-applicability-matrix.md) | Maps this policy to NIST MG 2.4 and ISO 42001 A.6.1 |
| [Third-Party AI Risk Register](third-party-ai-risk-register.md) | Vendor model change governance (separate from internal retraining) |
| [Monitoring and Metrics](08-monitoring-and-metrics.md) | MLOps health metrics including drift detection |

---

## 8. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2026-02-23 | SENTINEL Governance Team | Initial retraining policy with cadence, process, validation, run log template, and rollback procedure |

---

*This policy satisfies NIST AI RMF MG 2.4 (AI system deactivation and retraining governance). It is reviewed semi-annually or when significant changes are made to the ML model registry or training infrastructure.*

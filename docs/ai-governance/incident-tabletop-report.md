---
title: "AI Incident Tabletop Exercise Report"
version: "1.0.0"
date: "2026-02-23"
exercise_id: "TABLETOP-001"
scenario: "Bad Model Update / Hallucination (Stress Test Scenario 1)"
status: "completed"
author: "SENTINEL Governance Team"
participants:
  - role: "Incident Commander"
    name: "AI Engineering Lead"
  - role: "AI Engineer"
    name: "ML Operations Engineer"
  - role: "Operations Lead"
    name: "BMS Operations Lead"
  - role: "Compliance Observer"
    name: "Compliance Lead"
tags: ["tabletop", "incident-response", "ai-governance", "stress-test"]
---

# AI Incident Tabletop Exercise Report

**Exercise ID:** TABLETOP-001
**Date:** 2026-02-23
**Duration:** 2 hours (14:00 - 16:00 SAST)
**Scenario:** Bad Model Update / Hallucination (Stress Test Scenario 1)
**Environment:** Simulation / Shadow mode (no production equipment affected)

---

## 1. Exercise Metadata

| Field | Value |
|-------|-------|
| Exercise ID | TABLETOP-001 |
| Scenario | Stress Test Scenario 1: Bad Model Update / Hallucination |
| Date | 2026-02-23 |
| Duration | 2 hours |
| Facilitator | AI Engineering Lead |
| Location | Remote (Teams) + SENTINEL monitoring dashboard |
| Mode | Tabletop (narrative walkthrough with system verification) |

### Participants

| Role | Responsibility | Present |
|------|---------------|---------|
| Incident Commander (AI Engineering Lead) | Scenario setup, technical facilitation, detection verification | Yes |
| AI Engineer (ML Operations Engineer) | Model analysis, rollback execution, quality gate monitoring | Yes |
| Operations Lead (BMS Operations Lead) | Response execution, impact assessment, recovery coordination | Yes |
| Compliance Observer (Compliance Lead) | Evidence collection, CAPA creation, pass/fail determination | Yes |

### Scenario Selection Rationale

Scenario 1 was selected for the first tabletop exercise because:
- It directly tests the quality gate pipeline (`backend/app/services/quality_gate_evaluator.py`) which is the primary defence against bad AI outputs
- It exercises the safety interlock layer (`backend/app/services/safety_interlocks.py`) which prevents unsafe setpoints from reaching equipment
- It validates the 3-tier routing response (`backend/app/services/optimization_tier_router.py`) under adversarial conditions
- It has the most clearly defined pass criteria with measurable thresholds

---

## 2. Scenario Walkthrough

The following narration describes the simulated incident as walked through by participants. All timestamps are relative to the start of the incident (T+0).

### Pre-conditions

- Site S002 operating in `shadow_live` mode
- AHU model (v2.3.1) deployed and passing quality gate with `NORMAL` enforcement
- Prometheus metrics collecting: `sentinel_quality_gate_evaluations_total`, `sentinel_safety_violations_total`
- Chiller staging active, building occupied, 14:00 SAST (peak cooling period)

### T+0 min: Corrupted Model Deployed

**Narration:** A retrained AHU predictive model (v2.4.0-rc1) is deployed to the model registry. The training data contained 3 weeks of readings from a faulty supply air temperature sensor (stuck at 14 C) that was not caught during data validation. The model learned an incorrect relationship between supply air temperature and cooling demand.

**System state:**
- Model v2.4.0-rc1 loaded by inference service
- Quality gate last evaluation: PASS (using metrics from previous model)
- No alerts triggered yet

### T+2 min: First Bad Predictions Generated

**Narration:** The corrupted model begins generating predictions. It outputs high-confidence (0.87) recommendations to increase chiller staging when the building already has adequate cooling. The recommendations would increase energy consumption by approximately 35% with no comfort benefit.

**System state:**
- Model outputs: confidence 0.87, recommendation "increase chiller staging by 2 units"
- Tier routing: Confidence 0.87 routes to `TIER2_APPROVAL` (approval required in shadow mode)
- Recommendations logged but NOT executed (shadow mode prevents direct equipment writes)

### T+3 min: Quality Gate Evaluation Cycle Fires

**Narration:** The quality gate evaluator runs its scheduled evaluation cycle. It collects metrics from the monitoring service and compares against `QualityGatePolicy` thresholds.

**Detection path (`backend/app/services/quality_gate_evaluator.py`):**
1. `collect_metrics()` retrieves current values from MonitoringService, CommissioningService, MVVerificationService
2. `mv_accuracy_7d_pct` drops to 42% (threshold: 85% for shadow_live mode) as the new model's predictions diverge from actual readings
3. `comfort_violation_rate_7d_pct` spikes to 18% (threshold: 5% for shadow_live mode)
4. Two metrics breach FAIL thresholds

**Quality gate result:**
- Status: `FAIL`
- Enforcement: `BLOCK_WRITES` (most severe enforcement triggered by mv_accuracy failure)
- Reason codes: `ACCURACY_BELOW_THRESHOLD`, `COMFORT_VIOLATIONS_EXCEEDED`
- Prometheus: `sentinel_quality_gate_evaluations_total{site_id="site-002", status="fail"}` incremented
- Prometheus: `sentinel_quality_gate_enforcement{site_id="site-002", enforcement="block_writes"}` set to 1

**Assessment:** Detection occurred within 1 evaluation cycle (3 minutes). This meets the pass criterion of "within 1 evaluation cycle (max 5 minutes)".

### T+5 min: Safety Interlock Triggers

**Narration:** Simultaneously, the safety interlock layer (`backend/app/services/safety_interlocks.py`) evaluates the recommended setpoints. The corrupted model's chiller staging recommendation would drive supply water temperature below the 5 C safety floor.

**Detection path (`backend/app/services/safety_interlocks.py` / `SafetyEngine`):**
1. `SafetyEngine.initialize()` loads rules from `safety_rules.json` / SafetyRulesRepository
2. Chiller supply water temperature setpoint of 3.5 C violates `TemperatureRangeRule` (min: 5.0 C)
3. Rule severity: `BLOCK` -- setpoint rejected, not forwarded to device abstraction layer
4. Prometheus: `sentinel_safety_violations_total{site_id="site-002", severity="block"}` incremented

**Assessment:** Safety interlocks correctly blocked the unsafe setpoint independently of the quality gate. Defence-in-depth validated.

### T+7 min: Alert Notification Dispatched

**Narration:** The monitoring pipeline detects the `BLOCK_WRITES` enforcement state and the safety violation counter spike. Alert rules fire:

- `SentinelSafetyViolation` alert: `rate(sentinel_safety_violations_total[5m]) > 0` (Critical severity)
- `SentinelQualityGateBlocked` alert: `sentinel_quality_gate_enforcement{enforcement="block_writes"} == 1` (Critical severity)

Operations Lead receives notification via configured alert channel.

### T+10 min: Model Rollback Initiated

**Narration:** The AI Engineering Lead, acting as Incident Commander, reviews the quality gate dashboard and confirms the root cause is the newly deployed model v2.4.0-rc1. They decide to rollback to the previous known-good version (v2.3.1).

**Rollback process:**
1. AI Engineer identifies previous model version from model registry (`ml_models` table)
2. AI Engineer restores v2.3.1 as the active model for AHU equipment type
3. Model inference service reloads the restored model
4. Quality gate re-evaluation scheduled

### T+13 min: Rollback Verified

**Narration:** The quality gate evaluator runs its next cycle with the restored model v2.3.1.

**Verification:**
1. `mv_accuracy_7d_pct` returns to 91% (PASS threshold: 85%)
2. `comfort_violation_rate_7d_pct` returns to 1.2% (PASS threshold: 5%)
3. Quality gate status: `PASS`
4. Enforcement: `NORMAL` (block lifted)
5. Prometheus: `sentinel_quality_gate_enforcement{site_id="site-002", enforcement="normal"}` set to 1

**Assessment:** Rollback completed in 3 minutes from decision to verified restoration. This meets the pass criterion of "within 5 minutes of rollback decision".

### T+15 min: Impact Assessment

**Narration:** Operations Lead confirms zero bad setpoints reached equipment. The `BLOCK_WRITES` enforcement and `shadow_live` mode both prevented any writes to the device abstraction layer. The approval service (`backend/app/services/approval_service.py`) had no approved recommendations during the incident window.

**Impact:**
- Equipment commands executed from bad model: **Zero**
- Persistent data written from bad predictions: **Zero** (block_writes prevented DB writes)
- Energy waste: **Zero** (no equipment changes made)
- Comfort impact: **None** (shadow mode, no real setpoint changes)

### T+20 min: CAPA Entry Created

**Narration:** Compliance Observer creates a CAPA entry for the training data validation gap that allowed corrupted sensor data into the retraining pipeline.

**CAPA reference:** To be logged in `docs/ai-governance/nonconformity-capa-register.md`
- Type: Preventive Action
- Finding: Training data pipeline lacks automated sensor health validation before model retraining
- Severity: Major (would have caused unsafe action if in live_control mode)

---

## 3. Detection Assessment

### Quality Gate Detection

| Aspect | Expected | Actual | Result |
|--------|----------|--------|--------|
| Detection mechanism | `quality_gate_evaluator.py` detects mv_accuracy degradation | mv_accuracy dropped to 42%, comfort violations spiked to 18% | PASS |
| Detection latency | Within 1 evaluation cycle (max 5 min) | 3 minutes | PASS |
| Enforcement action | `BLOCK_WRITES` for FAIL status | `BLOCK_WRITES` triggered with reason codes | PASS |
| Metrics fired | `sentinel_quality_gate_evaluations_total{status="fail"}` | Counter incremented correctly | PASS |

**Metrics that detected the issue:**
1. `mv_accuracy_7d_pct`: 42% (threshold 85%) -- **Primary detection signal**
2. `comfort_violation_rate_7d_pct`: 18% (threshold 5%) -- **Secondary confirmation**

### Safety Interlock Detection

| Aspect | Expected | Actual | Result |
|--------|----------|--------|--------|
| Safety boundary check | `SafetyEngine` rejects out-of-range setpoints | Chiller supply temp 3.5 C rejected (min 5.0 C) | PASS |
| Severity | BLOCK (prevents execution) | BLOCK applied | PASS |
| Independence | Operates independently of quality gate | Safety interlock fired 2 min after quality gate, confirming independent detection | PASS |

### Tier Routing Detection

| Aspect | Expected | Actual | Result |
|--------|----------|--------|--------|
| Confidence routing | Anomalous confidence triggers tier demotion | High confidence (0.87) on bad prediction -- tier routing did NOT demote (confidence was high, not anomalous) | PARTIAL |

**Gap identified:** The tier routing engine (`backend/app/services/optimization_tier_router.py`) routes based on confidence score magnitude. A corrupted model producing **high-confidence wrong predictions** would not trigger tier demotion. Detection relied entirely on the quality gate's accuracy metrics and safety interlocks. This is a known limitation -- confidence is not a proxy for correctness.

---

## 4. Response Assessment

### 3-Tier Response Effectiveness

| Tier | Component | Assessment |
|------|-----------|------------|
| Tier 1: Automated blocking | `quality_gate_evaluator.py` BLOCK_WRITES enforcement | **Effective** -- All AI-generated setpoints blocked within 3 minutes |
| Tier 2: Safety interlocks | `safety_interlocks.py` SafetyEngine boundary checks | **Effective** -- Unsafe chiller setpoint independently rejected |
| Tier 3: Manual escalation | Alert notification to Operations Lead | **Effective** -- Alert fired within 7 minutes, clear severity indication |

### Escalation Path

1. Automated: Quality gate BLOCK_WRITES (T+3) -- **Correct and timely**
2. Automated: Safety interlock BLOCK (T+5) -- **Correct defence-in-depth**
3. Alert: Prometheus alert to Operations Lead (T+7) -- **Correct escalation**
4. Manual: Incident Commander decision to rollback (T+10) -- **Appropriate response**

### Approval Service Behaviour

The approval service (`backend/app/services/approval_service.py`) correctly handled the scenario:
- In `shadow_live` mode, recommendations require approval before execution
- BLOCK_WRITES enforcement prevented any recommendations from reaching the approval queue
- No `ApprovalResult` records created during the incident window

---

## 5. Recovery Assessment

| Criterion | Threshold | Actual | Result |
|-----------|-----------|--------|--------|
| Detection latency | Within 1 evaluation cycle (max 5 min) | 3 minutes | PASS |
| Rollback latency | Within 5 minutes of decision | 3 minutes (T+10 to T+13) | PASS |
| Unsafe actions | Zero | Zero | PASS |
| Data integrity | No corruption | No persistent data from bad model | PASS |

**Recovery sequence:**
1. Model v2.4.0-rc1 deactivated in registry (T+10)
2. Model v2.3.1 restored as active version (T+11)
3. Inference service reloaded (T+12)
4. Quality gate re-evaluated and passed (T+13)
5. Enforcement returned to NORMAL (T+13)
6. Full service restoration confirmed (T+15)

**Overall result: ALL PASS CRITERIA MET**

---

## 6. Actions Log

| # | Action | Owner | Due Date | Status | Priority |
|---|--------|-------|----------|--------|----------|
| 1 | Verify automated rollback script covers all 6 model types (AHU, CHILLER, FCU, UPS, GENERATOR, DALI). Currently, rollback is manual via model registry table update. Automate with a single CLI command or API endpoint. | AI Engineering Lead | 2026-03-15 | Open | High |
| 2 | Add `sentinel_model_rollback_duration_seconds` histogram metric to Prometheus to track time-to-recovery for model rollbacks. Wire into Grafana dashboard alongside existing quality gate metrics. | ML Operations Engineer | 2026-03-10 | Open | Medium |
| 3 | Update incident response process (`docs/09-security/incident-response-process.md`) with an AI-specific playbook section covering: model rollback procedure, quality gate override process, training data quarantine steps. | Compliance Lead | 2026-03-20 | Open | High |
| 4 | Implement training data validation gate: automated sensor health check before retraining. Flag sensors with >24h stuck readings, >10% missing data, or out-of-physical-range values. This addresses the root cause of the tabletop scenario. | AI Engineering Lead | 2026-04-01 | Open | Critical |
| 5 | Investigate whether tier routing can incorporate prediction consistency checks (comparing consecutive predictions for plausibility) in addition to raw confidence scores. The current routing engine does not detect high-confidence wrong predictions. | ML Operations Engineer | 2026-04-15 | Open | Medium |

---

## 7. Lessons Learned

### What Worked Well

1. **Defence-in-depth validated.** The quality gate and safety interlocks operated independently, providing two layers of protection. Even if one layer failed, the other would have caught the issue.

2. **Shadow mode protection.** Operating in `shadow_live` mode meant no equipment changes could occur regardless of detection timing. This is the correct posture for newly deployed models.

3. **Clear Prometheus metrics.** The `sentinel_quality_gate_evaluations_total` and `sentinel_safety_violations_total` metrics provided unambiguous signals. Alert rules fired promptly.

4. **Fast rollback.** Restoring the previous model version took only 3 minutes, well within the 5-minute target. The model registry design supports rapid version switching.

5. **Quality gate enforcement granularity.** The `BLOCK_WRITES` enforcement level is appropriately severe -- it prevents all AI writes, not just the affected model type. This fail-closed behaviour is correct for integrity failures.

### What Needs Improvement

1. **No automated rollback.** Model rollback required manual intervention (database update to model registry). An automated rollback triggered by sustained BLOCK_WRITES enforcement would reduce response time further.

2. **Training data validation gap.** The root cause (corrupted sensor data in training set) was not caught before model deployment. There is no automated sensor health check in the retraining pipeline.

3. **Tier routing blind spot.** High-confidence wrong predictions are not detected by the tier routing engine. Confidence score alone cannot distinguish correct from incorrect predictions. Additional signals (prediction consistency, physical plausibility) should be explored.

4. **No model canary deployment.** The corrupted model was deployed directly. A canary deployment pattern (running new model on subset of equipment before full rollout) would limit blast radius.

5. **Incident playbook gap.** The existing incident response process does not have AI-specific procedures. Responders had to improvise the rollback sequence during the exercise.

---

## Cross-References

- Scenario definition: [`docs/ai-governance/stress-test-scenarios.md`](stress-test-scenarios.md) (Scenario 1)
- Quality gate service: `backend/app/services/quality_gate_evaluator.py`
- Quality gate policy: `backend/app/services/quality_gate_policy.py`
- Safety interlocks: `backend/app/services/safety_interlocks.py`
- Approval service: `backend/app/services/approval_service.py`
- Tier routing: `backend/app/services/optimization_tier_router.py`
- Prometheus metrics: `backend/app/api/metrics.py`
- Monitoring spec: [`docs/ai-governance/08-monitoring-and-metrics.md`](08-monitoring-and-metrics.md)
- RCA Postmortem: [`docs/ai-governance/evidence/rca-postmortems/tabletop-001-bad-model.md`](evidence/rca-postmortems/tabletop-001-bad-model.md)
- CAPA register: [`docs/ai-governance/nonconformity-capa-register.md`](nonconformity-capa-register.md)

---

## Document History

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 1.0.0 | 2026-02-23 | SENTINEL Governance Team | Initial tabletop exercise report for Scenario 1 |

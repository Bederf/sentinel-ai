---
title: "RCA Postmortem: Bad Model Update / Hallucination (Tabletop)"
version: "1.0.0"
date: "2026-02-23"
exercise_id: "TABLETOP-001"
scenario: "Stress Test Scenario 1"
severity: "Major"
status: "closed"
rca_type: "tabletop-exercise"
author: "SENTINEL Governance Team"
tags: ["rca", "postmortem", "tabletop", "model-quality", "quality-gate"]
---

# RCA Postmortem: Bad Model Update / Hallucination

**Exercise:** TABLETOP-001
**Date:** 2026-02-23
**Type:** Tabletop exercise (simulated incident, not production)
**Severity:** Major

---

## Summary

During tabletop exercise TABLETOP-001, participants simulated a scenario where a retrained AHU predictive model (v2.4.0-rc1) was deployed with training data corrupted by a faulty supply air temperature sensor (stuck at 14 C for 3 weeks). The corrupted model produced high-confidence (0.87) incorrect recommendations that would have increased chiller staging unnecessarily, wasting approximately 35% additional energy and driving chiller supply water temperature below the 5 C safety floor.

The quality gate evaluator and safety interlocks both detected and blocked the bad predictions. No unsafe actions reached equipment. All pass criteria were met.

---

## Timeline

| Time | Event | Actor |
|------|-------|-------|
| T+0 min | Corrupted model v2.4.0-rc1 deployed to model registry | Automated (deployment pipeline) |
| T+2 min | First bad predictions generated (confidence 0.87, chiller staging increase) | Model inference service |
| T+3 min | Quality gate evaluation: `mv_accuracy_7d_pct` = 42% (threshold 85%), enforcement escalated to `BLOCK_WRITES` | `quality_gate_evaluator.py` |
| T+5 min | Safety interlock: chiller supply temp setpoint 3.5 C rejected (min 5.0 C), severity BLOCK | `safety_interlocks.py` / `SafetyEngine` |
| T+7 min | Prometheus alerts fired: `SentinelSafetyViolation` (Critical), `SentinelQualityGateBlocked` (Critical) | Monitoring pipeline |
| T+7 min | Operations Lead notified via alert channel | Alert routing |
| T+10 min | Incident Commander decides to rollback to model v2.3.1 | AI Engineering Lead |
| T+11 min | Model v2.3.1 restored as active version in registry | AI Engineer |
| T+12 min | Inference service reloaded with restored model | AI Engineer |
| T+13 min | Quality gate re-evaluation: PASS, enforcement returned to NORMAL | `quality_gate_evaluator.py` |
| T+15 min | Impact assessment complete: zero bad setpoints reached equipment | Operations Lead |
| T+20 min | CAPA entry created for training data validation gap | Compliance Lead |

---

## Root Cause

**Primary root cause:** Absence of automated sensor health validation in the model retraining pipeline.

A faulty supply air temperature sensor at Site S002 produced stuck readings (constant 14 C) for 3 weeks. These readings were ingested into the training dataset without validation. The model learned an incorrect relationship between supply air temperature and cooling demand, causing it to consistently recommend increased chiller staging regardless of actual conditions.

**Root cause category:** Process gap (data validation)

---

## Contributing Factors

| Factor | Description | Mitigation |
|--------|-------------|------------|
| No sensor health gate | Retraining pipeline does not check sensor data quality before training | Implement pre-training sensor health validation |
| No canary deployment | New model deployed to all AHU equipment simultaneously | Implement canary pattern (subset first) |
| Manual rollback | Rollback requires manual model registry update | Automate rollback triggered by sustained BLOCK_WRITES |
| High-confidence blind spot | Tier routing does not detect high-confidence wrong predictions | Investigate prediction consistency checks |

---

## Impact

### Actual Impact (Tabletop)

| Category | Impact |
|----------|--------|
| Equipment commands from bad model | **Zero** (BLOCK_WRITES enforcement + shadow mode) |
| Persistent data from bad predictions | **Zero** (writes blocked) |
| Energy waste | **Zero** (no equipment changes) |
| Comfort impact | **None** (shadow mode) |
| Duration of exposure | **3 minutes** (T+0 to T+3 detection) |

### Potential Impact (If Controls Had Failed)

| Category | Estimated Impact |
|----------|-----------------|
| Energy waste | ~35% increase in chiller energy during affected hours |
| Equipment risk | Chiller supply water below 5 C safety limit (potential freeze damage) |
| Comfort | Overcooling in occupied zones |
| Financial | Estimated R2,500/day in excess energy costs at Site S002 |

---

## Corrective Actions

| # | Action | Owner | Due Date | Status | CAPA Ref |
|---|--------|-------|----------|--------|----------|
| CA-1 | Implement automated sensor health validation gate in retraining pipeline: reject training data from sensors with >24h stuck readings, >10% missing data, or out-of-physical-range values | AI Engineering Lead | 2026-04-01 | Open | CAPA-004 (pending) |
| CA-2 | Automate model rollback: CLI command or API endpoint to restore previous model version for any equipment type, triggered by sustained BLOCK_WRITES (>2 consecutive evaluation cycles) | AI Engineering Lead | 2026-03-15 | Open | -- |
| CA-3 | Add `sentinel_model_rollback_duration_seconds` Prometheus histogram for rollback time-to-recovery tracking | ML Operations Engineer | 2026-03-10 | Open | -- |

---

## Preventive Actions

| # | Action | Owner | Due Date | Status |
|---|--------|-------|----------|--------|
| PA-1 | Implement canary model deployment: new models deployed to 1 equipment instance for 24h before full rollout | AI Engineering Lead | 2026-04-15 | Open |
| PA-2 | Add prediction plausibility checks to tier routing engine: compare consecutive predictions for physical consistency (e.g., recommendation should not contradict current sensor readings by >2 standard deviations) | ML Operations Engineer | 2026-04-15 | Open |
| PA-3 | Create AI-specific incident response playbook section in `docs/09-security/incident-response-process.md` covering: model rollback, quality gate override, training data quarantine | Compliance Lead | 2026-03-20 | Open |
| PA-4 | Schedule quarterly tabletop exercises for remaining scenarios (Scenario 2: Compliance Breach, Scenario 3: Multi-System Failure) | Compliance Lead | 2026-05-15 | Open |

---

## Verification of Controls

The following controls were validated during the exercise:

| Control | Service | Verified |
|---------|---------|----------|
| Quality gate BLOCK_WRITES enforcement | `backend/app/services/quality_gate_evaluator.py` | Yes -- triggered on mv_accuracy degradation |
| Safety interlock boundary check | `backend/app/services/safety_interlocks.py` | Yes -- rejected out-of-range chiller setpoint |
| Tier routing confidence check | `backend/app/services/optimization_tier_router.py` | Partial -- does not detect high-confidence wrong predictions |
| Prometheus alert rules | `backend/app/api/metrics.py` + alert config | Yes -- both safety and quality gate alerts fired |
| Shadow mode write prevention | Mode enforcement in approval pipeline | Yes -- no writes permitted in shadow_live mode |
| Approval service blocking | `backend/app/services/approval_service.py` | Yes -- no recommendations reached approval queue |

---

## Pass Criteria Results

| Criterion | Threshold | Actual | Result |
|-----------|-----------|--------|--------|
| Detection latency | Within 1 evaluation cycle (max 5 min) | 3 minutes | **PASS** |
| Rollback latency | Within 5 minutes of rollback decision | 3 minutes | **PASS** |
| Unsafe actions | Zero | Zero | **PASS** |
| Data integrity | No corruption | No persistent data written | **PASS** |

**Overall: ALL PASS CRITERIA MET**

---

## Cross-References

- Tabletop report: [`docs/ai-governance/incident-tabletop-report.md`](../../incident-tabletop-report.md)
- Scenario definition: [`docs/ai-governance/stress-test-scenarios.md`](../../stress-test-scenarios.md)
- CAPA register: [`docs/ai-governance/nonconformity-capa-register.md`](../../nonconformity-capa-register.md)
- Quality gate evaluator: `backend/app/services/quality_gate_evaluator.py`
- Safety interlocks: `backend/app/services/safety_interlocks.py`
- Approval service: `backend/app/services/approval_service.py`
- Prometheus metrics: `backend/app/api/metrics.py`

---

## Document History

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 1.0.0 | 2026-02-23 | SENTINEL Governance Team | Initial RCA postmortem from tabletop exercise TABLETOP-001 |

---
title: "AI Stress Test Scenarios"
type: "template"
status: "active"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
tags: ["ai-governance", "stress-test", "resilience", "compliance"]
domain: "compliance"
audience: "engineering-and-operations"
complexity: "intermediate"
estimated_read_time: 12
---

# AI Stress Test Scenarios

## Purpose

This document defines structured stress test scenarios to validate SENTINEL's resilience under adverse conditions. These are tabletop exercises with documented expected behavior, designed to be executed quarterly by the governance team.

Each scenario specifies:

- **Trigger**: The adverse condition being simulated
- **Expected Detection**: How SENTINEL should detect the problem
- **Expected Response**: Automatic and manual responses expected
- **Evidence to Capture**: What artifacts to collect during the exercise
- **Pass Criteria**: Measurable thresholds that define success or failure

Scenarios that fail their pass criteria generate a nonconformity entry in the [CAPA register](nonconformity-capa-register.md).

## Scenario 1: Bad Model Update / Hallucination

### Overview

An ML model is retrained with corrupted or unrepresentative data, producing high-confidence wrong predictions that could lead to unsafe or wasteful equipment control decisions.

### Trigger

- ML model retrained with corrupted training data (e.g., sensor data from a faulty meter ingested without validation)
- Model produces high-confidence predictions that are objectively wrong (e.g., recommends cooling when heating is needed)
- Predictions pass basic schema validation but contain semantically incorrect recommendations

### Expected Detection

| Detection Layer | Mechanism | Reference |
|----------------|-----------|-----------|
| Quality Gate | R-squared degradation below mode-specific threshold triggers `BLOCK_WRITES` enforcement | `backend/app/services/quality_gate_evaluator.py` |
| Drift Monitoring | Feature distribution shift flagged by drift detection service | `docs/ai-governance/08-monitoring-and-metrics.md` |
| Safety Interlocks | Out-of-range setpoint values blocked by safety boundary checks | `backend/app/services/safety_engine.py` |
| Tier Routing | Anomalous confidence scores cause tier demotion (Tier 3 to Tier 1) | `backend/app/services/optimization_tier_router.py` |

### Expected Response

**Automatic:**

1. Quality gate enforcement escalates to `BLOCK_WRITES` -- no AI-generated setpoints reach equipment
2. Safety interlocks reject any setpoint outside physical safety limits
3. Alert generated via monitoring pipeline (Prometheus metric spike)

**Manual:**

1. Operations Lead receives quality gate alert notification
2. Operations Lead investigates model performance dashboard
3. ML Lead performs root cause analysis on training data
4. ML Lead triggers model rollback to previous known-good version

**Rollback:**

1. Previous model version restored from model registry within 5 minutes
2. Quality gate re-evaluated against restored model
3. Service returns to normal operation once quality gate passes

### Evidence to Capture

- [ ] Timeline of events from model deployment to detection
- [ ] Detection latency (time from bad prediction to quality gate block)
- [ ] Rollback latency (time from rollback decision to restored service)
- [ ] Number of bad predictions that reached any downstream system
- [ ] CAPA entry if pass criteria not met
- [ ] Screenshots/logs of quality gate enforcement in action

### Pass Criteria

| Criterion | Threshold | Measurement |
|-----------|-----------|-------------|
| Detection latency | Within 1 evaluation cycle (max 5 minutes) | Time from first bad prediction to quality gate block |
| Rollback latency | Within 5 minutes of rollback decision | Time from decision to restored previous model |
| Unsafe actions | Zero | Count of bad setpoints that reached equipment |
| Data integrity | No corruption | Verify no persistent data written from bad predictions |

---

## Scenario 2: Compliance Breach / Cost Runaway

### Overview

A third-party AI API (Claude/Anthropic) begins generating recommendations that bypass quality gate logic, or a prompt injection / model behavior change causes uncontrolled spending and potentially inappropriate outputs.

### Trigger

- Third-party API (Claude) begins generating recommendations that bypass quality gate logic
- Possible causes: prompt injection via user input, upstream model behavior change, API credential compromise
- Spending spikes beyond normal operational budget
- AI outputs deviate from expected format or safety constraints

### Expected Detection

| Detection Layer | Mechanism | Reference |
|----------------|-----------|-----------|
| Tier Routing | Anomalous confidence scores detected in recommendation pipeline | `backend/app/services/optimization_tier_router.py` |
| Cost Monitoring | Token/cost tracking flags spending spike above daily budget threshold | `docs/ai-governance/08-monitoring-and-metrics.md` |
| Audit Trail | All AI outputs captured with provenance metadata for forensic review | `backend/app/utils/ai_provenance.py` |
| Rate Limiting | Request rate exceeds configured limits per route/tenant | `backend/app/middleware/` |

### Expected Response

**Automatic:**

1. Rate limiting activates to throttle excessive API calls
2. Cost cap triggers API suspension when daily budget exceeded (2x threshold)
3. Quality gate blocks recommendations with anomalous confidence patterns
4. All outputs continue to be logged with full provenance metadata

**Manual:**

1. Security Lead receives cost/rate alert notification
2. Security Lead activates incident response process per `docs/09-security/incident-response-process.md`
3. Security Lead revokes or rotates Claude API credentials
4. Operations Lead switches critical operations to Ollama local LLM fallback
5. Compliance Lead initiates forensic review of captured audit trail

**Fallback:**

1. Ollama local LLM activated for critical operations (Tier 1 recommendations only)
2. Tier 2 and Tier 3 recommendations suspended until API integrity confirmed
3. Service restored once new credentials issued and root cause identified

### Evidence to Capture

- [ ] Cost timeline showing spend rate before, during, and after incident
- [ ] Detection trigger that first identified the anomaly
- [ ] Containment actions taken with timestamps
- [ ] Forensic review of AI outputs during the incident window
- [ ] Incident report per `docs/09-security/incident-response-process.md`
- [ ] CAPA entry if pass criteria not met

### Pass Criteria

| Criterion | Threshold | Measurement |
|-----------|-----------|-------------|
| Cost containment | Within 2x daily budget | Total spend during incident vs. daily budget |
| Data exfiltration | Zero | Confirm no sensitive data sent to unauthorized endpoints |
| Service restoration | Within 30 minutes | Time from incident declaration to restored service |
| Audit completeness | 100% | All AI outputs during window have provenance records |

---

## Scenario 3: Multi-System Failure

### Overview

Multiple critical infrastructure components fail simultaneously: monitoring (Prometheus) goes down, model inference times out, and the primary database (Supabase) connection is lost. This tests SENTINEL's graceful degradation and recovery capabilities.

### Trigger

- Prometheus monitoring service becomes unavailable (no metrics collection or alerting)
- ML model inference requests timeout consistently (model service unresponsive)
- Supabase database connection lost (no reads or writes to primary datastore)
- Alerting capability is impaired because monitoring is down

### Expected Detection

| Detection Layer | Mechanism | Reference |
|----------------|-----------|-----------|
| Health Checks | Application-level health check failures cascade | `backend/app/api/health.py` |
| Fallback Activation | Repository layer detects Supabase failure, activates JSON fallback | 3-tier fallback pattern (Supabase -> Redis -> JSON) |
| External Monitoring | External uptime monitor (not dependent on SENTINEL) detects service degradation | Infrastructure monitoring |
| Timeout Detection | Model inference timeout triggers circuit breaker | `backend/app/services/` |

### Expected Response

**Automatic:**

1. `DEMO_MODE` fallback activates -- JSON data files serve read requests
2. Redis cache serves recently-cached data where available
3. Model inference circuit breaker opens -- recommendations paused gracefully
4. Application continues serving basic monitoring and status endpoints
5. Write operations queued or rejected with clear error messages

**Manual:**

1. On-call engineer notified via external channel (SMS/phone -- not dependent on SENTINEL)
2. On-call engineer triages: restore monitoring first (Prometheus)
3. Once monitoring restored, diagnose database and model service failures
4. Database recovery: verify data integrity, restore connection
5. Model service recovery: restart inference service, verify predictions

**Recovery:**

1. Services restart with exponential backoff
2. Monitoring (Prometheus) restored first to enable visibility
3. Database connection re-established and data integrity verified
4. Model inference service restarted and quality gate validated
5. Queued write operations replayed if applicable

### Evidence to Capture

- [ ] Failure timeline showing sequence and correlation of failures
- [ ] Recovery sequence with timestamps for each component
- [ ] Data integrity check results (no data loss or corruption)
- [ ] User impact assessment (requests served via fallback vs. failed)
- [ ] Gaps in monitoring coverage during the outage window
- [ ] CAPA entry if pass criteria not met

### Pass Criteria

| Criterion | Threshold | Measurement |
|-----------|-----------|-------------|
| Data loss | Zero | Post-recovery data integrity audit |
| Graceful degradation | Service available in read-only/fallback mode | User-facing endpoints respond (even if degraded) |
| Recovery time | Within 1 hour | Time from first failure to full service restoration |
| Monitoring gap | Documented | All gaps in alerting coverage identified and logged |

---

## Execution Protocol

### Schedule

- **Frequency**: Quarterly (Q2, Q3, Q4 2026; then ongoing)
- **First execution**: Phase 2 Week 7-8 (2026-05-13 to 2026-05-26)
- **Duration**: 2 hours per scenario (6 hours total per quarterly cycle)

### Participants

| Role | Responsibility |
|------|---------------|
| AI Engineering Lead | Scenario setup, technical facilitation, detection verification |
| Operations Lead | Response execution, recovery coordination, impact assessment |
| Security Lead | Incident response activation, forensic review, compliance verification |
| Compliance Lead | Evidence collection, CAPA creation, management review reporting |

### Execution Steps

1. **Preparation** (30 minutes before)
   - Review scenario trigger and expected behavior
   - Confirm all participants are available
   - Prepare evidence collection templates
   - Verify test environment isolation (never run on production equipment)

2. **Scenario Execution** (90 minutes)
   - Facilitator describes trigger condition
   - Participants walk through detection and response steps
   - Record actual vs. expected behavior at each stage
   - Time all response actions against pass criteria thresholds

3. **Debrief** (30 minutes)
   - Compare actual outcomes to pass criteria
   - Identify gaps and improvement opportunities
   - Create CAPA entries for any failed pass criteria
   - Document lessons learned

### Documentation

- File scenario results in `docs/ai-governance/evidence/rca-postmortems/`
- Naming convention: `stress-test-{scenario-number}-{date}.md`
- Example: `stress-test-01-2026-05-13.md`

### CAPA Integration

- Any scenario where pass criteria are not met generates a nonconformity in the [CAPA register](nonconformity-capa-register.md)
- Severity determined by nature of failure:
  - **Critical**: Unsafe action executed or data loss occurred
  - **Major**: Detection or response exceeded time thresholds
  - **Minor**: Documentation or process gaps identified

## Cross-References

- Quality Gate: `backend/app/services/quality_gate_evaluator.py`
- Safety Engine: `backend/app/services/safety_engine.py`
- Incident Response: `docs/09-security/incident-response-process.md`
- CAPA Register: `docs/ai-governance/nonconformity-capa-register.md`
- Monitoring: `docs/ai-governance/08-monitoring-and-metrics.md`
- AI Provenance: `backend/app/utils/ai_provenance.py`
- Data Privacy: `docs/ai-governance/data-privacy-policy.md`

## Document History

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 1.0.0 | 2026-02-23 | SENTINEL Governance Team | Initial creation with 3 stress test scenarios and execution protocol |

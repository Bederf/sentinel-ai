---
title: "NIST AI RMF Control-Effectiveness Review"
version: "1.0.0"
date: "2026-02-23"
framework: "NIST AI Risk Management Framework (AI RMF 1.0)"
status: "completed"
review_period: "2026-01 to 2026-02"
author: "SENTINEL Governance Team"
tags: ["ai-governance", "nist-ai-rmf", "control-effectiveness", "assurance-review"]
---

# NIST AI RMF Control-Effectiveness Review

**Review Period:** January -- February 2026
**Reviewer:** SENTINEL Governance Team
**Framework:** NIST AI Risk Management Framework (AI RMF 1.0)
**Scope:** All AI/ML capabilities deployed in SENTINEL BMS Intelligence platform

---

## Executive Summary

This review assesses the effectiveness of controls implemented in SENTINEL against the NIST AI Risk Management Framework across all four core functions: GOVERN, MAP, MEASURE, and MANAGE. Each control is evaluated with an effectiveness rating, evidence artifacts, identified gaps, and recommended actions.

### Summary Table

| Function | Controls Reviewed | Effective | Partially Effective | Ineffective | Effectiveness Rate |
|----------|------------------|-----------|--------------------|--------------|--------------------|
| GOVERN (GV) | 3 | 2 | 1 | 0 | 83% |
| MAP (MP) | 2 | 2 | 0 | 0 | 100% |
| MEASURE (MS) | 3 | 2 | 1 | 0 | 83% |
| MANAGE (MG) | 3 | 2 | 1 | 0 | 83% |
| **Total** | **11** | **8** | **3** | **0** | **87%** |

**Overall NIST AI RMF Compliance: 87% (8 of 11 controls Effective, 3 Partially Effective, 0 Ineffective)**

---

## 1. GOVERN (GV) -- Governance Structure Effectiveness

The GOVERN function establishes the organisational structures, policies, and accountability mechanisms for AI risk management.

### GV 1.1: AI Management Policy

| Field | Detail |
|-------|--------|
| **Control Ref** | GV 1.1 |
| **Requirement** | Organisation has an AI management policy that defines roles, responsibilities, acceptable use, and risk appetite for AI systems |
| **Evidence Artifact(s)** | `docs/ai-governance/ai-management-policy.md` (v1.0.0, approved 2026-02-23) |
| **Effectiveness Rating** | **Effective** |
| **Assessment** | Policy exists with clear scope (Section 2), roles and responsibilities (Section 3), risk appetite statement, acceptable use boundaries, and review schedule. Covers all 6 ML model types deployed in SENTINEL. Approved and versioned. |
| **Residual Gaps** | Policy has not yet undergone its first annual review cycle (created 2026-02-23, review due 2027-02). No evidence of policy acknowledgement by all personnel. |
| **Recommended Actions** | 1. Collect signed policy acknowledgements from all SENTINEL operators. 2. Schedule first annual review for Q1 2027. |

### GV 4.2: Third-Party AI Risk Management

| Field | Detail |
|-------|--------|
| **Control Ref** | GV 4.2 |
| **Requirement** | Risks from third-party AI components are identified, assessed, and managed with documented controls |
| **Evidence Artifact(s)** | `docs/ai-governance/third-party-ai-risk-register.md` (v1.0.0, active) |
| **Effectiveness Rating** | **Effective** |
| **Assessment** | Register documents 2 third-party AI providers (Anthropic Claude, Ollama local). Risk assessments include data flow analysis, contractual controls, fallback mechanisms, and residual risk ratings. The Ollama local fallback provides continuity if the primary Claude API is unavailable. |
| **Residual Gaps** | Register does not yet include sub-processors of third parties (e.g., Anthropic's cloud infrastructure providers). Contractual AI-specific clauses (data retention, model versioning) are identified as needed but not yet negotiated. |
| **Recommended Actions** | 1. Request sub-processor list from Anthropic. 2. Draft AI-specific contractual addendum for third-party agreements. |

### GV 6.1: Metrics and Monitoring

| Field | Detail |
|-------|--------|
| **Control Ref** | GV 6.1 |
| **Requirement** | Measurable metrics are defined and monitored to assess AI system performance, safety, and compliance |
| **Evidence Artifact(s)** | `backend/app/api/metrics.py` (Prometheus instrumentation), `docs/ai-governance/08-monitoring-and-metrics.md` (governance specification) |
| **Effectiveness Rating** | **Partially Effective** |
| **Assessment** | 14 Prometheus metrics defined and instrumented in `metrics.py`, covering quality gate evaluations, safety violations, model inference latency, tier routing decisions, and drift detection. Alert rules defined in monitoring spec with severity levels and escalation paths. Metrics are collected and exposed. |
| **Residual Gaps** | Prometheus is deployed but Grafana dashboards are not yet configured for governance-specific views. Alert routing to on-call personnel is defined in documentation but not yet wired to a live notification channel. Historical metric retention policy not defined. |
| **Recommended Actions** | 1. Create Grafana dashboard for AI governance metrics (quality gate pass rate, safety violations trend, model drift). 2. Wire alert routing to operational notification channel (Telegram/email). 3. Define metric retention policy (minimum 12 months for audit evidence). |

---

## 2. MAP (MP) -- Risk Identification

The MAP function identifies and documents AI-specific risks, including model-level risk classification and documentation.

### MP 2.3: Model Risk Classification

| Field | Detail |
|-------|--------|
| **Control Ref** | MP 2.3 |
| **Requirement** | AI systems are classified by risk level using a documented methodology aligned with regulatory frameworks |
| **Evidence Artifact(s)** | `docs/ai-governance/01-risk-classification.md` (v1.0.0, approved) |
| **Effectiveness Rating** | **Effective** |
| **Assessment** | Risk classification register covers all 6 ML model types (AHU, CHILLER, FCU, UPS, GENERATOR, DALI) plus 2 third-party AI integrations (Claude, Ollama). Classification methodology maps to both EU AI Act risk tiers (Unacceptable/High/Limited/Minimal) and NIST impact levels. SENTINEL classified as "Limited Risk" under EU AI Act and "Medium Impact" under NIST, with clear justification. |
| **Residual Gaps** | None significant. Classification should be re-evaluated if SENTINEL expands to life-safety critical applications (e.g., fire suppression control). |
| **Recommended Actions** | 1. Re-evaluate classification if scope expands to safety-critical building systems. |

### MP 4.1: Model Documentation

| Field | Detail |
|-------|--------|
| **Control Ref** | MP 4.1 |
| **Requirement** | Each AI model has standardised documentation covering purpose, training data, performance metrics, limitations, and intended use |
| **Evidence Artifact(s)** | `docs/ai-governance/model-cards/` (6 model cards: AHU.md, CHILLER.md, FCU.md, UPS.md, GENERATOR.md, DALI.md), `docs/ai-governance/model-cards/MODEL-CARD-TEMPLATE.md` |
| **Effectiveness Rating** | **Effective** |
| **Assessment** | All 6 deployed ML models have model cards following a standardised template. Cards document: model type, training data source, feature set, performance metrics (R-squared, MAE), limitations, intended use, and responsible party. Template ensures consistency across future models. Data sheets exist in `docs/ai-governance/data-sheets/` for training data provenance. |
| **Residual Gaps** | Model cards do not yet include field-validated performance metrics (only simulation/shadow metrics available). Version history within model cards is minimal. |
| **Recommended Actions** | 1. Update model cards with field-validated metrics once live_control deployment occurs. 2. Add version changelog to each model card. |

---

## 3. MEASURE (MS) -- Risk Measurement

The MEASURE function quantifies risks through assessment, testing, and ongoing measurement.

### MS 2.6: Residual Risk Disclosure

| Field | Detail |
|-------|--------|
| **Control Ref** | MS 2.6 |
| **Requirement** | Residual risks that cannot be fully mitigated are documented and disclosed to operators and affected parties |
| **Evidence Artifact(s)** | `docs/ai-governance/residual-risk-disclosure.md` (v1.0.0, active) |
| **Effectiveness Rating** | **Effective** |
| **Assessment** | Disclosure document identifies 5 residual risks with severity, likelihood, existing mitigations, and acceptance rationale. Risks include: sensor dependency, model drift between retraining cycles, third-party API availability, simulation-to-live gap, and operator override risk. Each risk has a named owner and review date. Written in operator-accessible language. |
| **Residual Gaps** | Disclosure has not yet been formally acknowledged by site operators. No mechanism to track operator awareness. |
| **Recommended Actions** | 1. Distribute disclosure to Site S002 operations team and collect acknowledgement. 2. Include residual risk review in quarterly management review agenda. |

### MS 2.7: Fairness and Bias Assessment

| Field | Detail |
|-------|--------|
| **Control Ref** | MS 2.7 |
| **Requirement** | AI systems are assessed for fairness and bias, with documented methodology and results |
| **Evidence Artifact(s)** | `docs/ai-governance/fairness-bias-baseline.md` (v1.0.0, active, closes NC-002) |
| **Effectiveness Rating** | **Effective** |
| **Assessment** | Baseline analysis completed covering all 6 model types. Assessment methodology documented (statistical parity, equal opportunity, calibration across zones). BMS-specific bias dimensions identified (zone location, floor level, equipment age, occupancy pattern). Baseline metrics recorded. The analysis correctly identifies that BMS AI bias risk is lower than human-facing AI but still relevant for equitable service delivery across building zones. Closes nonconformity NC-002 from CAPA register. |
| **Residual Gaps** | Baseline is theoretical/simulation-based. No production fairness metrics collected yet. Ongoing monitoring for bias drift not yet automated. |
| **Recommended Actions** | 1. Implement automated fairness metric collection once live_control is active. 2. Add zone-level equity metric to Prometheus dashboard. |

### MS 2.11: Stress Testing

| Field | Detail |
|-------|--------|
| **Control Ref** | MS 2.11 |
| **Requirement** | AI systems are tested under adverse conditions to validate resilience and safety |
| **Evidence Artifact(s)** | `docs/ai-governance/stress-test-scenarios.md` (v1.0.0, active, 3 scenarios), `docs/ai-governance/incident-tabletop-report.md` (TABLETOP-001 executed), `docs/ai-governance/evidence/rca-postmortems/tabletop-001-bad-model.md` |
| **Effectiveness Rating** | **Partially Effective** |
| **Assessment** | Three stress test scenarios documented with clear triggers, expected detection, expected response, evidence requirements, and measurable pass criteria. Scenario 1 (Bad Model Update) has been executed as a tabletop exercise (TABLETOP-001) with all pass criteria met. Execution protocol defines quarterly schedule, participant roles, and CAPA integration. |
| **Residual Gaps** | Only 1 of 3 scenarios executed so far. Scenarios 2 (Compliance Breach) and 3 (Multi-System Failure) have not yet been exercised. No automated stress test harness -- exercises are manual tabletop only. |
| **Recommended Actions** | 1. Execute Scenario 2 and 3 tabletop exercises by Q2 2026. 2. Investigate automated stress test capability for regression testing of safety interlocks. |

---

## 4. MANAGE (MG) -- Risk Management

The MANAGE function implements ongoing risk treatment, including model lifecycle management, incident response, and corrective actions.

### MG 2.4: Retraining Governance

| Field | Detail |
|-------|--------|
| **Control Ref** | MG 2.4 |
| **Requirement** | Model retraining is governed by documented policy including triggers, approval, validation, and rollback procedures |
| **Evidence Artifact(s)** | `docs/ai-governance/retraining-policy.md` (v1.0.0, active) |
| **Effectiveness Rating** | **Effective** |
| **Assessment** | Retraining policy defines: trigger conditions (scheduled quarterly, drift-triggered, incident-triggered), data requirements, validation gates, approval workflow, rollback procedure, and documentation requirements. Policy references quality gate evaluator for post-retraining validation. Rollback procedure is documented. |
| **Residual Gaps** | Retraining has not yet been executed in production (platform in simulation/shadow mode). No training data validation gate exists to prevent corrupted data from entering the pipeline (identified in TABLETOP-001 exercise). |
| **Recommended Actions** | 1. Implement automated training data validation gate per TABLETOP-001 Action 4. 2. Execute first governed retraining cycle and document evidence. |

### MG 3.1: CAPA Process

| Field | Detail |
|-------|--------|
| **Control Ref** | MG 3.1 |
| **Requirement** | A corrective and preventive action (CAPA) process exists to address nonconformities, with tracking, closure, and effectiveness verification |
| **Evidence Artifact(s)** | `docs/ai-governance/nonconformity-capa-register.md` (v1.2.0, active) |
| **Effectiveness Rating** | **Partially Effective** |
| **Assessment** | CAPA register exists with structured format: ID, severity, finding, root cause, corrective action, owner, due date, status, evidence. Register contains active entries including NC-002 (fairness baseline, closed with `fairness-bias-baseline.md` as evidence). Process integrates with management review and stress test outcomes. Severity-based SLAs defined (critical 30d, major 60d, minor 90d). |
| **Residual Gaps** | Effectiveness verification step is defined in process but has not been exercised for any closed CAPA (no management review cycle completed yet). No automated CAPA aging alerts. Some CAPAs lack root cause analysis depth (single-sentence descriptions). |
| **Recommended Actions** | 1. Conduct first management review including CAPA effectiveness verification. 2. Implement CAPA aging alerts (notify owner at 75% of due date). 3. Require structured root cause analysis (5 Whys or fishbone) for Major/Critical CAPAs. |

### MG 4.1: Model Lifecycle Management

| Field | Detail |
|-------|--------|
| **Control Ref** | MG 4.1 |
| **Requirement** | AI models are managed through a defined lifecycle including deployment, monitoring, evaluation, retirement, with automated quality gates |
| **Evidence Artifact(s)** | `backend/app/services/quality_gate_evaluator.py` (14 metrics, 3 modes), `backend/app/services/quality_gate_policy.py` (42 threshold entries), `backend/app/services/tier_routing_engine.py` (confidence-based routing), `backend/app/services/optimization_tier_router.py` (3-tier routing) |
| **Effectiveness Rating** | **Effective** |
| **Assessment** | Comprehensive model lifecycle controls implemented in code. Quality gate evaluator assesses 14 metrics across 3 operational modes (simulation, shadow_live, live_control) with mode-specific thresholds. Enforcement escalation: NORMAL -> CAP_CONFIDENCE(0.59) -> SUPPRESS_TIER3 -> BLOCK_WRITES. Tier routing engine routes recommendations based on confidence, with demotion for anomalous scores. Safety interlocks provide independent physical boundary checks. Fail-closed design in live_control mode. Validated in TABLETOP-001 exercise. |
| **Residual Gaps** | Model retirement process is defined in policy but not yet implemented as an automated workflow. No canary deployment pattern for new model versions. Model registry is database-only with no GitOps integration. |
| **Recommended Actions** | 1. Implement automated model retirement workflow (archive model, remove from inference, document reason). 2. Implement canary deployment pattern per TABLETOP-001 recommendation. |

---

## Findings Summary

### Strengths

1. **Comprehensive policy framework.** All core governance documents exist, are versioned, and follow a consistent structure.
2. **Defence-in-depth controls.** Quality gate, safety interlocks, and tier routing provide three independent layers of protection, validated by tabletop exercise.
3. **Mode-aware design.** Controls adapt to operational mode (simulation/shadow/live), with fail-closed behaviour in live_control mode. This is architecturally sound.
4. **Complete model documentation.** All 6 deployed models have model cards with standardised format.
5. **Risk classification completed.** EU AI Act and NIST risk levels documented with clear justification.

### Areas for Improvement

1. **Operational evidence gap.** Many controls are documented and implemented in code but have not yet been exercised in production. The platform operates in simulation/shadow mode.
2. **Monitoring pipeline incomplete.** Prometheus metrics are instrumented but Grafana dashboards and alert routing are not fully wired.
3. **First management review pending.** CAPA effectiveness verification and policy review cycles have not yet completed their first iteration.
4. **Training data validation gap.** Identified in TABLETOP-001 -- retraining pipeline lacks automated sensor health validation.

### Risk Trending

| Risk Area | Trend | Justification |
|-----------|-------|---------------|
| Model quality | Stable | Quality gate provides automated checks; no production deployment yet |
| Safety | Improving | Safety interlocks validated in tabletop; actions logged for improvement |
| Governance | Improving | Policy framework complete; operational evidence building |
| Third-party | Stable | Risk register active; contractual controls pending |

---

## Next Review

- **Scheduled:** Q2 2026 (after first management review cycle)
- **Focus areas:** Operational evidence from shadow/live deployments, CAPA effectiveness verification, Scenarios 2 and 3 tabletop completion, Grafana dashboard deployment

---

## Cross-References

- AI Management Policy: `docs/ai-governance/ai-management-policy.md`
- Third-Party Risk Register: `docs/ai-governance/third-party-ai-risk-register.md`
- Monitoring and Metrics: `docs/ai-governance/08-monitoring-and-metrics.md`
- Risk Classification: `docs/ai-governance/01-risk-classification.md`
- Model Cards: `docs/ai-governance/model-cards/` (6 models)
- Residual Risk Disclosure: `docs/ai-governance/residual-risk-disclosure.md`
- Fairness and Bias Baseline: `docs/ai-governance/fairness-bias-baseline.md`
- Stress Test Scenarios: `docs/ai-governance/stress-test-scenarios.md`
- Tabletop Report: `docs/ai-governance/incident-tabletop-report.md`
- Retraining Policy: `docs/ai-governance/retraining-policy.md`
- CAPA Register: `docs/ai-governance/nonconformity-capa-register.md`
- Quality Gate Evaluator: `backend/app/services/quality_gate_evaluator.py`
- Quality Gate Policy: `backend/app/services/quality_gate_policy.py`
- Tier Routing Engine: `backend/app/services/tier_routing_engine.py`
- Optimization Tier Router: `backend/app/services/optimization_tier_router.py`
- Prometheus Metrics: `backend/app/api/metrics.py`

---

## Document History

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 1.0.0 | 2026-02-23 | SENTINEL Governance Team | Initial NIST AI RMF control-effectiveness review covering 11 controls across 4 functions |

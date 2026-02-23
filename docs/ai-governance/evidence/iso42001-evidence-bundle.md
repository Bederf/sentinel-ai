---
title: "ISO/IEC 42001 Evidence Bundle"
type: "evidence"
status: "Draft"
version: "1.0.0"
date: "2026-02-23"
owner: "Compliance Lead"
author: "SENTINEL Governance Team"
tags: ["iso-42001", "evidence", "compliance", "audit", "phase-3"]
domain: "compliance"
audience: "all"
complexity: "advanced"
estimated_read_time: 20
---

# ISO/IEC 42001 Evidence Bundle

## Coverage Summary

| Metric | Value |
|--------|-------|
| **Total Applicable Controls** | 13 |
| **Controls with Evidence** | 13 |
| **Implemented** | 10 (77%) |
| **Partial** | 3 (23%) |
| **Planned** | 0 (0%) |
| **Evidence Coverage** | 100% (all controls have at least one evidence path) |

## Control Evidence Matrix

### ISO-A.2.2 -- AI Policy and Objectives

| Field | Detail |
|-------|--------|
| **Control Description** | The organization shall establish an AI policy and define measurable objectives aligned with the AIMS scope |
| **Implementation Status** | Implemented |
| **Evidence Paths** | |

| # | Evidence Artifact | Path | Exists |
|---|------------------|------|--------|
| 1 | AI Management Policy | `docs/ai-governance/ai-management-policy.md` | Yes |
| 2 | Write Policy and Rollout (mode discipline) | `docs/08-ai-ml/write-policy-and-rollout.md` | Yes |
| 3 | AIMS Scope Statement | `docs/ai-governance/00-scope-and-system-boundaries.md` | Yes |

**Verification Method:** File review -- confirm policy contains measurable KPIs, mode discipline objectives, and references the AIMS scope.

**Gap Notes:** None. Policy is complete with 4 measurable objectives and annual review cycle.

---

### ISO-A.2.3 -- Roles, Responsibilities, and Authorities

| Field | Detail |
|-------|--------|
| **Control Description** | The organization shall define and communicate AI-related roles, responsibilities, and authorities |
| **Implementation Status** | Implemented |
| **Evidence Paths** | |

| # | Evidence Artifact | Path | Exists |
|---|------------------|------|--------|
| 1 | Architecture Capability Model | `docs/architecture-repository/governance/architecture-capability.md` | Yes |
| 2 | Architecture Board Charter | `docs/architecture-repository/governance/architecture-board-charter.md` | Yes |
| 3 | Competence Training Register | `docs/ai-governance/competence-training-register.md` | Yes |
| 4 | Control Applicability Matrix (Owner column) | `docs/ai-governance/control-applicability-matrix.md` | Yes |

**Verification Method:** Review capability model for role definitions; verify charter assigns decision authority; confirm competence register maps roles to required competencies; check matrix has owner for each control.

**Gap Notes:** None. Roles are defined across Architecture Lead, AI Engineering Lead, Security/Compliance Lead, and Operations Lead.

---

### ISO-A.4.1 -- AI Risk Assessment

| Field | Detail |
|-------|--------|
| **Control Description** | The organization shall perform AI risk assessments to identify and evaluate risks specific to AI systems |
| **Implementation Status** | Implemented |
| **Evidence Paths** | |

| # | Evidence Artifact | Path | Exists |
|---|------------------|------|--------|
| 1 | Risk Classification Framework | `docs/ai-governance/01-risk-classification.md` | Yes |
| 2 | Residual Risk Disclosure | `docs/ai-governance/residual-risk-disclosure.md` | Yes |
| 3 | Fairness/Bias Baseline | `docs/ai-governance/fairness-bias-baseline.md` | Yes |
| 4 | Stress Test Scenarios | `docs/ai-governance/stress-test-scenarios.md` | Yes |

**Verification Method:** Confirm risk classification covers all 6 active ML models; verify per-use-case risk tiers (limited/high) are assigned; check residual risk disclosure includes operator-facing summaries.

**Gap Notes:** None. Risk tiers assigned per AI feature with EU AI Act alignment.

---

### ISO-A.4.2 -- AI Risk Treatment

| Field | Detail |
|-------|--------|
| **Control Description** | The organization shall define and implement risk treatment measures for identified AI risks |
| **Implementation Status** | Implemented |
| **Evidence Paths** | |

| # | Evidence Artifact | Path | Exists |
|---|------------------|------|--------|
| 1 | Quality Gate Policy (42 threshold entries) | `backend/app/services/quality_gate_policy.py` | Yes |
| 2 | Quality Gate Evaluator | `backend/app/services/quality_gate_evaluator.py` | Yes |
| 3 | Live-Control Entry Criteria | `docs/ai-governance/live-control-entry-criteria.md` | Yes |

**Verification Method:** Inspect quality_gate_policy.py for 14 metrics x 3 modes = 42 threshold entries; verify enforcement actions (CAP_CONFIDENCE, SUPPRESS_TIER3, BLOCK_WRITES, NORMAL); confirm live-control entry criteria document exists with checklist.

**Gap Notes:** None. Risk treatment is enforced programmatically via quality gates with mode-specific thresholds.

---

### ISO-A.5.1 -- Data Governance for AI

| Field | Detail |
|-------|--------|
| **Control Description** | The organization shall establish data governance practices appropriate for AI systems |
| **Implementation Status** | Implemented |
| **Evidence Paths** | |

| # | Evidence Artifact | Path | Exists |
|---|------------------|------|--------|
| 1 | Data Privacy Policy (POPIA) | `docs/09-security/data-privacy-policy.md` | Yes |
| 2 | Model and Data Governance Framework | `docs/ai-governance/05-model-and-data-governance.md` | Yes |
| 3 | Data Sheets (3 governed datasets) | `docs/ai-governance/data-sheets/EQUIPMENT-TELEMETRY.md`, `docs/ai-governance/data-sheets/RAG-KNOWLEDGE-BASE.md`, `docs/ai-governance/data-sheets/WORK-ORDER-OUTCOMES.md` | Yes |
| 4 | Consent Service | `backend/app/services/consent_service.py` | Yes |

**Verification Method:** Verify data privacy policy covers 7 PI categories with retention schedules; confirm data sheets exist for each governed dataset; check consent service implementation.

**Gap Notes:** None. POPIA-compliant data governance with 9 retention categories, consent management, and PIA process.

---

### ISO-A.5.2 -- Data Quality Management

| Field | Detail |
|-------|--------|
| **Control Description** | The organization shall ensure data used in AI systems is of appropriate quality |
| **Implementation Status** | Implemented |
| **Evidence Paths** | |

| # | Evidence Artifact | Path | Exists |
|---|------------------|------|--------|
| 1 | Health Data Quality Gate | `backend/app/services/health_data_quality_gate.py` | Yes |
| 2 | Quality Gate Evaluator (data metrics) | `backend/app/services/quality_gate_evaluator.py` | Yes |

**Verification Method:** Inspect health_data_quality_gate.py for mode-specific confidence scoring (sim/shadow/live); verify freshness, match coverage, and truth-check metrics.

**Gap Notes:** None. Data quality is enforced through the health data quality gate with mode-specific confidence thresholds.

---

### ISO-A.6.1 -- AI System Lifecycle Management

| Field | Detail |
|-------|--------|
| **Control Description** | The organization shall manage the AI system throughout its lifecycle |
| **Implementation Status** | Implemented |
| **Evidence Paths** | |

| # | Evidence Artifact | Path | Exists |
|---|------------------|------|--------|
| 1 | Write Policy and Rollout | `docs/08-ai-ml/write-policy-and-rollout.md` | Yes |
| 2 | Retraining Policy | `docs/ai-governance/retraining-policy.md` | Yes |
| 3 | Model Cards (6 models) | `docs/ai-governance/model-cards/AHU.md`, `docs/ai-governance/model-cards/CHILLER.md`, `docs/ai-governance/model-cards/FCU.md`, `docs/ai-governance/model-cards/UPS.md`, `docs/ai-governance/model-cards/GENERATOR.md`, `docs/ai-governance/model-cards/DALI.md` | Yes |

**Verification Method:** Confirm 4-mode lifecycle (simulation, shadow_live, live_control, automatic) is documented with phased rollout checklist; verify retraining policy defines cadence and triggers; check all 6 model cards exist.

**Gap Notes:** None. Full lifecycle from simulation through automatic mode with retraining triggers and model cards.

---

### ISO-A.6.2 -- Safety Validation in AI Systems

| Field | Detail |
|-------|--------|
| **Control Description** | The organization shall validate AI systems for safety prior to deployment |
| **Implementation Status** | Implemented |
| **Evidence Paths** | |

| # | Evidence Artifact | Path | Exists |
|---|------------------|------|--------|
| 1 | Safety Interlocks Engine Documentation | `docs/06-safety-compliance/safety-interlocks-engine.md` | Yes |
| 2 | Safety Interlocks Service | `backend/app/services/safety_interlocks.py` | Yes |
| 3 | Safety Rules Configuration | `backend/app/data/safety_rules.json` | Yes |

**Verification Method:** Verify safety interlocks documentation covers 6 rule types and 3 severity levels; inspect safety_interlocks.py for defense-in-depth rule matching; confirm safety_rules.json contains 8+ rules covering temperature, pressure, interlocks, and runtime.

**Gap Notes:** None. Safety validation is enforced programmatically with a defense-in-depth approach.

---

### ISO-A.7.1 -- Third-Party AI Risk Management

| Field | Detail |
|-------|--------|
| **Control Description** | The organization shall manage risks from third-party AI components |
| **Implementation Status** | Partial |
| **Evidence Paths** | |

| # | Evidence Artifact | Path | Exists |
|---|------------------|------|--------|
| 1 | Third-Party AI Risk Register | `docs/ai-governance/third-party-ai-risk-register.md` | Yes |
| 2 | Third-Party Security Register | `docs/09-security/third-party-security-register.md` | Yes |

**Verification Method:** Verify third-party AI risk register covers Anthropic Claude API, WhatsApp, Telegram, and sub-processors; check for AI-specific risk assessments beyond security focus.

**Gap Notes:** Third-party register needs AI-specific expansion beyond security focus. Current register covers security risks but does not fully address AI-specific risks such as model bias propagation, output quality degradation, and vendor lock-in for AI capabilities. Target completion: 2026-04-15.

---

### ISO-A.8.1 -- Monitoring and Measurement of AI

| Field | Detail |
|-------|--------|
| **Control Description** | The organization shall monitor and measure AI system performance and control effectiveness |
| **Implementation Status** | Partial |
| **Evidence Paths** | |

| # | Evidence Artifact | Path | Exists |
|---|------------------|------|--------|
| 1 | Monitoring and Metrics Guide | `docs/ai-governance/08-monitoring-and-metrics.md` | Yes |
| 2 | Prometheus Metrics Endpoint | `backend/app/api/metrics.py` | Yes |
| 3 | MLOps Health API | `backend/app/api/mlops.py` | Yes |
| 4 | Evidence: Drift Reports Directory | `docs/ai-governance/evidence/drift-reports/` | Yes (empty) |

**Verification Method:** Verify monitoring guide defines metric types and alert thresholds; call `/metrics` endpoint to confirm Prometheus-format output; inspect mlops.py for drift detection endpoints.

**Gap Notes:** Prometheus-grade control effectiveness metrics not fully wired; monitoring evidence is split across systems. Drift reports directory exists but contains no evidence snapshots yet. Grafana dashboards referenced but not configured in SENTINEL scope. Target completion: 2026-04-15.

---

### ISO-A.8.2 -- Audit Trail and Traceability

| Field | Detail |
|-------|--------|
| **Control Description** | The organization shall maintain audit trails for AI system decisions |
| **Implementation Status** | Implemented |
| **Evidence Paths** | |

| # | Evidence Artifact | Path | Exists |
|---|------------------|------|--------|
| 1 | Audit Logging Documentation | `docs/06-safety-compliance/audit-logging.md` | Yes |
| 2 | Audit Logger Service | `backend/app/services/audit_logger.py` | Yes |
| 3 | Decision Event Logger | `backend/app/services/decision_event_logger.py` | Yes |
| 4 | Encryption Service (at-rest) | `backend/app/services/encryption_service.py` | Yes |
| 5 | Evidence: Audit Log Samples | `docs/ai-governance/evidence/audit-logs-samples/` | Yes (empty) |

**Verification Method:** Verify audit logging docs describe correlation ID scheme and 7-stage decision pipeline; inspect audit_logger.py and decision_event_logger.py for implementation; confirm encryption_service.py provides Fernet encryption at rest.

**Gap Notes:** Audit log samples directory exists but contains no representative samples yet. Samples should be collected during the next live operation cycle.

---

### ISO-A.10.1 -- Human Oversight of AI Decisions

| Field | Detail |
|-------|--------|
| **Control Description** | The organization shall ensure appropriate human oversight of AI-assisted decisions |
| **Implementation Status** | Implemented |
| **Evidence Paths** | |

| # | Evidence Artifact | Path | Exists |
|---|------------------|------|--------|
| 1 | Human Oversight and Approval Documentation | `docs/ai-governance/06-human-oversight-and-approval.md` | Yes |
| 2 | Approval Service | `backend/app/services/approval_service.py` | Yes |
| 3 | Optimization Tier Router | `backend/app/services/optimization_tier_router.py` | Yes |

**Verification Method:** Verify tier-based approval workflow: Tier 1 advisory, Tier 2 human approval, Tier 3 auto-execute with quality gates; confirm HIGH/CRITICAL risk is permanently locked to Tier 2 human approval; inspect approval_service.py for implementation.

**Gap Notes:** None. Three-tier human oversight model with risk-based escalation enforced programmatically.

---

### ISO-A.10.2 -- AI System Transparency

| Field | Detail |
|-------|--------|
| **Control Description** | The organization shall ensure AI system outputs are transparent and explainable |
| **Implementation Status** | Partial |
| **Evidence Paths** | |

| # | Evidence Artifact | Path | Exists |
|---|------------------|------|--------|
| 1 | Optimization Tier Router (confidence + reasoning) | `backend/app/services/optimization_tier_router.py` | Yes |
| 2 | AI Disclosure Badge | `frontend/src/components/AIDisclosureBadge.tsx` | Yes |
| 3 | AI Provenance Utility | `backend/app/utils/ai_provenance.py` | Yes |

**Verification Method:** Verify recommendations include confidence scores, reasoning chains, and evidence references; confirm AI disclosure badge renders in UI; check provenance utility for content tagging.

**Gap Notes:** Recommendation transparency needs standardized explanation templates across all AI output surfaces. Current implementation provides confidence scores and tier classification but does not have a uniform explanation format. Target completion: 2026-04-30.

---

## Cross-Reference: Controls Satisfying Multiple Frameworks

The following SENTINEL components provide evidence for ISO 42001 controls AND controls from other frameworks:

| SENTINEL Component | ISO 42001 Control | Also Satisfies |
|--------------------|-------------------|---------------|
| `quality_gate_policy.py` / `quality_gate_evaluator.py` | A.4.2, A.8.1 | NIST MS-1.1, NIST GV-1.5, EU Art.9, EU Art.15 |
| `approval_service.py` | A.10.1 | NIST MP-3.5, EU Art.14 |
| `safety_interlocks.py` | A.6.2 | NIST MS-2.6, EU Art.15 |
| `audit_logger.py` / `decision_event_logger.py` | A.8.2 | NIST MS-2.8, EU Art.12 |
| `write-policy-and-rollout.md` | A.2.2, A.6.1 | NIST GV-1.2 |
| `data-privacy-policy.md` / `consent_service.py` | A.5.1 | EU Art.10 |
| `optimization_tier_router.py` | A.10.2 | NIST MP-3.5, EU Art.50 |

## Evidence Collection Status

| Evidence Category | Directory | Files Present | Status |
|------------------|-----------|---------------|--------|
| Model Cards | `docs/ai-governance/model-cards/` | 6 (AHU, CHILLER, FCU, UPS, GENERATOR, DALI) | Complete |
| Data Sheets | `docs/ai-governance/data-sheets/` | 3 (EQUIPMENT-TELEMETRY, RAG-KNOWLEDGE-BASE, WORK-ORDER-OUTCOMES) | Complete |
| Drift Reports | `docs/ai-governance/evidence/drift-reports/` | 0 | Awaiting first drift snapshot |
| Audit Log Samples | `docs/ai-governance/evidence/audit-logs-samples/` | 0 | Awaiting live operation cycle |
| RCA/Postmortems | `docs/ai-governance/evidence/rca-postmortems/` | 0 | Awaiting first stress test execution |
| Training Records | `docs/ai-governance/evidence/training/` | 1 (README.md) | Framework ready; records pending training delivery |
| Model Card Snapshots | `docs/ai-governance/evidence/model-cards/` | 0 | Awaiting first model version promotion |

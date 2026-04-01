---
title: "SENTINEL Internal Audit Plan - Phase 3 Compliance Cycle"
type: "plan"
status: "Draft"
version: "1.0.0"
date: "2026-02-23"
owner: "Compliance Lead"
author: "SENTINEL Governance Team"
tags: ["audit", "iso-42001", "nist-ai-rmf", "eu-ai-act", "compliance", "phase-3"]
domain: "compliance"
audience: "all"
complexity: "advanced"
estimated_read_time: 25
---

# SENTINEL Internal Audit Plan - Phase 3 Compliance Cycle

## 1. Audit Scope Statement

### 1.1 In Scope

The following are within the scope of this internal audit:

| Area | Description | Boundary |
|------|-------------|----------|
| **SENTINEL AI Features** | All AI/ML features deployed in the SENTINEL BMS Intelligence Platform including predictive maintenance, optimization tier routing, health assessment, and recommendation generation | All 6 active ML models (AHU, CHILLER, FCU, UPS, GENERATOR, DALI) |
| **Data Pipeline** | Ingestion, processing, storage, and retention of equipment telemetry, work order outcomes, and RAG knowledge base data | Supabase database, Redis cache, JSON fallback stores |
| **AI Governance Framework** | Policies, procedures, registers, and controls documented under `docs/ai-governance/` | ISO 42001, NIST AI RMF 1.0, EU AI Act mapping |
| **Safety Controls** | Safety interlocks engine, quality gate enforcement, approval workflow, and kill switches | All tier-based decision controls |
| **Human Oversight** | Approval service, tier routing, operator disclosure, and AI literacy training programme | Tier 1-3 decision pipeline |
| **Monitoring and Metrics** | MLOps health monitoring, drift detection, Prometheus metrics endpoint, and audit logging | Backend monitoring services |
| **Architecture Governance** | TOGAF-aligned architecture repository, Architecture Board charter, ADM phase mapping | `docs/architecture-repository/` |

### 1.2 Excluded

| Exclusion | Rationale |
|-----------|-----------|
| Supabase platform infrastructure controls | Managed platform; covered by Supabase's own SOC 2 compliance |
| Network and host-level security | Covered by VPS provider infrastructure controls |
| Third-party API internals (Anthropic Claude, Meta WhatsApp) | Covered by vendor security assessments in `docs/ai-governance/third-party-ai-risk-register.md` |
| TOGAF 10 exam preparation | Personal certification, not a system control |
| Prometheus/Grafana/Loki infrastructure | Observability platform controls; only SENTINEL's emitted metrics are in scope |

### 1.3 Audit Objectives

1. Verify that AI governance controls are implemented as documented in the control applicability matrix
2. Assess the operating effectiveness of safety interlocks, quality gates, and approval workflows
3. Confirm that evidence artifacts exist and are maintained for each mapped control
4. Identify gaps between documented controls and actual implementation
5. Verify AI literacy training programme compliance with EU AI Act Article 4

---

## 2. Sampling Methodology

### 2.1 ISO/IEC 42001 Controls

**Population:** 13 applicable controls from `docs/ai-governance/control-applicability-matrix.md`
**Sample size:** 10 controls (77% coverage -- exceeds 60% minimum)

| # | Control ID | Control Description | Status | Sampling Rationale |
|---|-----------|---------------------|--------|-------------------|
| 1 | ISO-A.2.2 | AI policy and objectives | Implemented | Core governance foundation |
| 2 | ISO-A.2.3 | Roles, responsibilities, and authorities | Implemented | Accountability structure |
| 3 | ISO-A.4.1 | AI risk assessment | Implemented | Risk-based approach underpins all controls |
| 4 | ISO-A.4.2 | AI risk treatment | Implemented | Enforcement mechanism |
| 5 | ISO-A.5.1 | Data governance for AI | Implemented | POPIA and data quality critical |
| 6 | ISO-A.6.1 | AI system lifecycle management | Implemented | Mode discipline is core differentiator |
| 7 | ISO-A.6.2 | Safety validation in AI systems | Implemented | Safety-critical control |
| 8 | ISO-A.8.1 | Monitoring and measurement of AI | Partial | Gap verification required |
| 9 | ISO-A.8.2 | Audit trail and traceability | Implemented | Evidence integrity |
| 10 | ISO-A.10.1 | Human oversight of AI decisions | Implemented | Regulatory requirement |

**Excluded from sample:** ISO-A.5.2 (covered indirectly via A.5.1 and A.4.2), ISO-A.7.1 (third-party -- partial, lower priority), ISO-A.10.2 (transparency -- partial, covered via EU Art.50 sample).

### 2.2 NIST AI RMF Controls

**Population:** 9 applicable controls from control applicability matrix
**Sample size:** 7 controls (78% coverage)

| # | Control ID | Control Description | Status | Sampling Rationale |
|---|-----------|---------------------|--------|-------------------|
| 1 | NIST-GV-1.2 | AI governance and mode discipline | Implemented | Core operational control |
| 2 | NIST-GV-1.5 | Organizational AI risk tolerance | Implemented | Threshold enforcement |
| 3 | NIST-MP-3.5 | Human-AI decision allocation | Implemented | Safety-critical |
| 4 | NIST-MS-1.1 | Quality gates for AI decisions | Implemented | Central enforcement mechanism |
| 5 | NIST-MS-2.6 | Safety and security of AI systems | Implemented | Safety-critical |
| 6 | NIST-MS-2.8 | AI system logging and auditability | Implemented | Traceability |
| 7 | NIST-MG-2.4 | AI system deactivation (kill switch) | Implemented | Safety-critical failsafe |

**Excluded from sample:** NIST-GV-3.1 (Planned -- noted as gap), NIST-MG-4.3 (incident response -- sampled via EU Art.62).

### 2.3 EU AI Act Controls

**Population:** 10 applicable controls from control applicability matrix
**Sample size:** 7 controls (70% coverage)

| # | Control ID | Control Description | Status | Sampling Rationale |
|---|-----------|---------------------|--------|-------------------|
| 1 | EU-Art.4 | AI literacy obligation | Planned | Gap verification priority |
| 2 | EU-Art.5 | Prohibited AI practices | Implemented | Fundamental compliance |
| 3 | EU-Art.9 | Risk management system for high-risk AI | Implemented | Core control |
| 4 | EU-Art.12 | Record-keeping and traceability | Implemented | Evidence integrity |
| 5 | EU-Art.14 | Human oversight measures | Implemented | Safety-critical |
| 6 | EU-Art.50 | Transparency obligations | Partial | Gap verification |
| 7 | EU-Art.62 | Reporting of serious incidents | Implemented | Safety/regulatory |

**Excluded from sample:** EU-Art.10 (data governance -- covered via ISO-A.5.1), EU-Art.15 (accuracy/robustness -- covered via ISO-A.4.2 and ISO-A.6.2), EU-Art.13 (model cards -- Planned, deferred).

---

## 3. Audit Schedule

### 3.1 Three-Day Audit Plan

#### Day 1: Document Review (Policies, Procedures, Registers)

| Time | Activity | Controls Covered | Evidence to Examine | Auditor |
|------|----------|-----------------|--------------------|---------|
| 09:00-10:00 | Opening meeting and audit plan briefing | -- | This audit plan document | Lead Auditor |
| 10:00-11:30 | AI Management Policy and scope review | ISO-A.2.2, ISO-A.2.3 | `docs/ai-governance/ai-management-policy.md`, `docs/ai-governance/00-scope-and-system-boundaries.md`, `docs/architecture-repository/governance/architecture-capability.md` | Lead Auditor |
| 11:30-13:00 | Risk classification and treatment review | ISO-A.4.1, ISO-A.4.2, EU-Art.9 | `docs/ai-governance/01-risk-classification.md`, `backend/app/services/quality_gate_policy.py`, `docs/ai-governance/control-applicability-matrix.md` | Lead Auditor |
| 14:00-15:00 | Data governance and privacy review | ISO-A.5.1, EU-Art.5 | `docs/09-security/data-privacy-policy.md`, `docs/compliance/eu-ai-act-prohibited-practices-checklist.md` | Technical Auditor |
| 15:00-16:00 | Lifecycle and safety documentation review | ISO-A.6.1, ISO-A.6.2, NIST-GV-1.2 | `docs/08-ai-ml/write-policy-and-rollout.md`, `docs/06-safety-compliance/safety-interlocks-engine.md` | Technical Auditor |
| 16:00-17:00 | Monitoring, audit trail, and incident response review | ISO-A.8.1, ISO-A.8.2, EU-Art.62 | `docs/ai-governance/08-monitoring-and-metrics.md`, `docs/06-safety-compliance/audit-logging.md`, `docs/09-security/incident-response-process.md` | Lead Auditor |

#### Day 2: Technical Verification (Endpoints, Services, Implementation)

| Time | Activity | Controls Covered | Verification Method | Auditor |
|------|----------|-----------------|--------------------|---------|
| 09:00-10:30 | Quality gate enforcement verification | NIST-MS-1.1, NIST-GV-1.5, ISO-A.4.2 | Inspect `backend/app/services/quality_gate_evaluator.py` source; call `GET /api/optimization/quality-gate/{site_id}` endpoint; verify 14 metrics returned with enforcement actions | Technical Auditor |
| 10:30-12:00 | Safety interlocks and kill switch verification | NIST-MS-2.6, NIST-MG-2.4, ISO-A.6.2 | Inspect `backend/app/services/safety_interlocks.py` source; verify `backend/app/data/safety_rules.json` contains 8+ rules; confirm kill switch endpoints in write policy Section D | Technical Auditor |
| 13:00-14:00 | Approval service and tier routing verification | NIST-MP-3.5, ISO-A.10.1, EU-Art.14 | Inspect `backend/app/services/approval_service.py` and `backend/app/services/optimization_tier_router.py`; verify HIGH/CRITICAL risk locks to Tier 2 maximum | Technical Auditor |
| 14:00-15:00 | Audit trail and decision logging verification | NIST-MS-2.8, ISO-A.8.2, EU-Art.12 | Inspect `backend/app/services/audit_logger.py` and `backend/app/services/decision_event_logger.py`; verify correlation ID propagation; check `backend/app/services/encryption_service.py` for at-rest encryption | Technical Auditor |
| 15:00-16:00 | Prometheus metrics and monitoring verification | ISO-A.8.1 | Call `GET /metrics` endpoint on `backend/app/api/metrics.py`; verify Prometheus-format output; check `backend/app/api/mlops.py` for drift detection endpoints | Technical Auditor |
| 16:00-17:00 | Transparency and disclosure verification | EU-Art.50, EU-Art.4 | Inspect `frontend/src/components/AIDisclosureBadge.tsx` for AI disclosure; verify `backend/app/utils/ai_provenance.py` for provenance headers; check `docs/ai-governance/ai-literacy-training-package.md` curriculum | Lead Auditor |

#### Day 3: Interview Simulations and Closing

| Time | Activity | Controls Covered | Method | Auditor |
|------|----------|-----------------|--------|---------|
| 09:00-10:00 | Architecture Lead interview | ISO-A.2.2, ISO-A.2.3, NIST-GV-1.2 | Role-based knowledge check: AI management policy objectives, governance structure, mode discipline, Architecture Board charter responsibilities | Lead Auditor |
| 10:00-11:00 | AI Engineering Lead interview | ISO-A.4.1, ISO-A.6.1, NIST-MS-1.1 | Role-based knowledge check: risk classification process, lifecycle modes, quality gate thresholds, model retraining triggers | Lead Auditor |
| 11:00-12:00 | Operations Lead interview | ISO-A.10.1, NIST-MP-3.5, EU-Art.14 | Role-based knowledge check: Tier 2 approval process, escalation procedures, kill switch activation, safety interlock overrides | Lead Auditor |
| 13:00-14:00 | Security/Compliance Lead interview | ISO-A.5.1, ISO-A.8.2, EU-Art.62 | Role-based knowledge check: data privacy policy, audit trail integrity, incident response process, POPIA Section 22 notification | Lead Auditor |
| 14:00-15:00 | Technician interview (sample) | EU-Art.4 | AI literacy assessment: Module 1 and Module 2 questions from `docs/ai-governance/ai-literacy-training-package.md`; verify Basic (3/5) threshold per `docs/ai-governance/competence-training-register.md` | Lead Auditor |
| 15:00-16:00 | Findings consolidation and classification | -- | Auditors consolidate all findings, classify per Section 6, and draft corrective actions | Both Auditors |
| 16:00-17:00 | Closing meeting and preliminary findings presentation | -- | Present summary of findings, agree on corrective action owners and due dates, schedule follow-up | Both Auditors |

---

## 4. Owner Assignments

Each audit area is mapped to an accountable owner from the roles defined in `docs/ai-governance/competence-training-register.md`.

| Audit Area | Primary Owner | Backup / Consulted | Controls Covered |
|-----------|---------------|-------------------|-----------------|
| AI Management Policy and Scope | Architecture Lead | Compliance Lead | ISO-A.2.2, ISO-A.2.3 |
| Risk Classification and Treatment | AI Engineering Lead | Compliance Lead | ISO-A.4.1, ISO-A.4.2, EU-Art.9 |
| Data Governance and Privacy | Security Lead | AI Engineering Lead | ISO-A.5.1, EU-Art.5 |
| AI System Lifecycle | AI Engineering Lead | Operations Lead | ISO-A.6.1, NIST-GV-1.2 |
| Safety Validation | AI Engineering Lead | Operations Lead | ISO-A.6.2, NIST-MS-2.6, NIST-MG-2.4 |
| Monitoring and Measurement | AI Engineering Lead | Security Lead | ISO-A.8.1, NIST-MS-1.1, NIST-GV-1.5 |
| Audit Trail and Traceability | Security Lead | AI Engineering Lead | ISO-A.8.2, NIST-MS-2.8, EU-Art.12 |
| Human Oversight | Operations Lead | AI Engineering Lead | ISO-A.10.1, NIST-MP-3.5, EU-Art.14 |
| Transparency and Disclosure | AI Engineering Lead | Compliance Lead | EU-Art.50, EU-Art.4 |
| Incident Response | Security Lead | Operations Lead | EU-Art.62, NIST-MG-4.3 |

---

## 5. Evidence Requirements per Control

For each sampled control, the following specifies the required evidence and verification method.

### 5.1 ISO/IEC 42001 Sampled Controls

| Control ID | Control Title | Evidence Artifact | Verification Method |
|-----------|--------------|------------------|-------------------|
| ISO-A.2.2 | AI policy and objectives | `docs/ai-governance/ai-management-policy.md` | File exists; contains measurable KPIs; references mode discipline and write policy |
| ISO-A.2.3 | Roles, responsibilities, and authorities | `docs/architecture-repository/governance/architecture-capability.md`, `docs/ai-governance/competence-training-register.md` | File exists; roles defined with decision scope; competence matrix populated |
| ISO-A.4.1 | AI risk assessment | `docs/ai-governance/01-risk-classification.md` | File exists; per-feature risk classification with EU AI Act alignment; risk tiers assigned |
| ISO-A.4.2 | AI risk treatment | `backend/app/services/quality_gate_policy.py` | File exists; 42 threshold entries (14 metrics x 3 modes); enforcement actions defined |
| ISO-A.5.1 | Data governance for AI | `docs/09-security/data-privacy-policy.md` | File exists; 7 PI categories documented; retention schedules defined; POPIA cross-border rules |
| ISO-A.6.1 | AI system lifecycle management | `docs/08-ai-ml/write-policy-and-rollout.md` | File exists; 4-mode lifecycle documented; phased rollout checklist present |
| ISO-A.6.2 | Safety validation in AI systems | `docs/06-safety-compliance/safety-interlocks-engine.md`, `backend/app/services/safety_interlocks.py` | Documentation and code exist; 6 rule types and 3 severity levels documented; safety rules JSON populated |
| ISO-A.8.1 | Monitoring and measurement of AI | `docs/ai-governance/08-monitoring-and-metrics.md`, `backend/app/api/metrics.py` | Documentation exists; `/metrics` endpoint returns Prometheus-format data; drift detection documented |
| ISO-A.8.2 | Audit trail and traceability | `docs/06-safety-compliance/audit-logging.md`, `backend/app/services/audit_logger.py` | Documentation and code exist; correlation ID scheme documented; encryption at rest via `backend/app/services/encryption_service.py` |
| ISO-A.10.1 | Human oversight of AI decisions | `backend/app/services/approval_service.py`, `docs/ai-governance/06-human-oversight-and-approval.md` | Code and documentation exist; Tier 2 human approval enforced for HIGH/CRITICAL risk |

### 5.2 NIST AI RMF Sampled Controls

| Control ID | Control Title | Evidence Artifact | Verification Method |
|-----------|--------------|------------------|-------------------|
| NIST-GV-1.2 | AI governance and mode discipline | `docs/08-ai-ml/write-policy-and-rollout.md` | 4-mode write policy with escalating permissions documented; fail-closed behaviour specified |
| NIST-GV-1.5 | Organizational AI risk tolerance | `backend/app/services/quality_gate_policy.py` | Mode-specific thresholds define risk tolerance; live_control treats NA as FAIL |
| NIST-MP-3.5 | Human-AI decision allocation | `backend/app/services/optimization_tier_router.py`, `backend/app/services/approval_service.py` | Tier routing allocates by confidence and risk level; HIGH/CRITICAL locked to Tier 2 |
| NIST-MS-1.1 | Quality gates for AI decisions | `backend/app/services/quality_gate_evaluator.py` | 14-metric evaluator with CAP_CONFIDENCE, SUPPRESS_TIER3, BLOCK_WRITES, NORMAL actions |
| NIST-MS-2.6 | Safety and security of AI systems | `backend/app/services/safety_interlocks.py`, `backend/app/data/safety_rules.json` | Safety engine validates all device control operations; 8+ rules for temperature, pressure, interlocks, runtime |
| NIST-MS-2.8 | AI system logging and auditability | `backend/app/services/decision_event_logger.py`, `docs/06-safety-compliance/audit-logging.md` | Decision pipeline with 7 stages; correlation IDs; PARASITE decision audit trail |
| NIST-MG-2.4 | AI system deactivation (kill switch) | `docs/08-ai-ml/write-policy-and-rollout.md` (Section D) | Global, per-site, per-equipment, and auto-downgrade kill switches documented |

### 5.3 EU AI Act Sampled Controls

| Control ID | Control Title | Evidence Artifact | Verification Method |
|-----------|--------------|------------------|-------------------|
| EU-Art.4 | AI literacy obligation | `docs/ai-governance/ai-literacy-training-package.md`, `docs/ai-governance/competence-training-register.md` | Training curriculum with 4 modules exists; role-competence matrix populated; assessment thresholds defined |
| EU-Art.5 | Prohibited AI practices | `docs/compliance/eu-ai-act-prohibited-practices-checklist.md`, `docs/ai-governance/01-risk-classification.md` | Checklist confirms no prohibited practices; risk classification excludes social scoring, biometrics, emotion recognition |
| EU-Art.9 | Risk management system | `docs/ai-governance/01-risk-classification.md`, `backend/app/services/quality_gate_evaluator.py` | Risk classification per AI use case; quality gate enforcement prevents high-risk actions without controls |
| EU-Art.12 | Record-keeping and traceability | `docs/06-safety-compliance/audit-logging.md`, `backend/app/services/audit_logger.py` | Immutable audit trail with correlation IDs linking full decision pipeline |
| EU-Art.14 | Human oversight measures | `backend/app/services/approval_service.py` | Tier 2 human-in-the-loop enforced; HIGH/CRITICAL risk permanently locked to human approval |
| EU-Art.50 | Transparency obligations | `frontend/src/components/AIDisclosureBadge.tsx`, `backend/app/utils/ai_provenance.py` | AI disclosure badge rendered in UI; provenance utility tags AI-generated content |
| EU-Art.62 | Reporting of serious incidents | `docs/09-security/incident-response-process.md` | P1-P4 severity classification; POPIA Section 22 breach notification; FSR escalation templates |

---

## 6. Finding Classification

All audit findings are classified according to the following scheme:

| Classification | Code | Definition | Response Requirement |
|---------------|------|-----------|---------------------|
| **Major Nonconformity** | NC-MAJ | Absence or total breakdown of a required control; systemic failure to meet a framework requirement; a control that is documented but entirely non-functional | Corrective action plan within 5 business days; root cause analysis required; re-audit within 30 days |
| **Minor Nonconformity** | NC-MIN | Partial implementation of a required control; isolated instance of non-compliance; evidence exists but is incomplete or outdated | Corrective action plan within 10 business days; preventive action recommended; verified at next scheduled audit |
| **Observation** | OBS | Area where a control is implemented but could be strengthened; no framework requirement is violated but risk exposure could be reduced | Owner acknowledges and records in CAPA register within 15 business days; optional corrective action |
| **Opportunity for Improvement** | OFI | Best practice suggestion that goes beyond the minimum framework requirement; enhancement that would improve audit efficiency or control effectiveness | Logged for consideration at next management review; no mandatory corrective action |

### 6.1 Classification Criteria

Findings are classified based on the following decision tree:

1. **Does the control exist?** No = NC-MAJ
2. **Is the control operating as documented?** No = NC-MAJ (if systemic) or NC-MIN (if isolated)
3. **Is evidence complete and current?** No = NC-MIN
4. **Could the control be strengthened?** Yes = OBS
5. **Is there a best-practice enhancement available?** Yes = OFI

### 6.2 Escalation Rules

- Any NC-MAJ finding on a safety-critical control (ISO-A.6.2, NIST-MS-2.6, NIST-MG-2.4) triggers immediate escalation to the Architecture Board
- Two or more NC-MAJ findings in the same audit area trigger a management review agenda item
- All NC-MAJ findings must be recorded in `docs/ai-governance/nonconformity-capa-register.md`

---

## 7. Reporting Template

All findings are reported using the following standardized format. Each finding is recorded as a separate entry.

### 7.1 Individual Finding Template

```
---
Finding ID: [AUDIT-YYYY-NNN]
Date: [YYYY-MM-DD]
Auditor: [Name]
---

Control Reference: [e.g., ISO-A.4.2]
Framework: [ISO 42001 / NIST AI RMF / EU AI Act]
Control Title: [e.g., AI risk treatment]

Finding Description:
[Clear, factual description of what was found. Reference specific evidence examined.]

Evidence Examined:
- [File path or endpoint tested]
- [Observation or test result]

Classification: [NC-MAJ / NC-MIN / OBS / OFI]

Root Cause (for nonconformities):
[Analysis of why the gap exists]

Corrective Action Required:
[Specific, measurable action to address the finding]

Owner: [Role responsible for corrective action]
Due Date: [YYYY-MM-DD]
Verification Method: [How the corrective action will be confirmed]
```

### 7.2 Audit Summary Report Template

```
---
title: "SENTINEL Internal Audit Summary Report"
audit_cycle: "Phase 3 - [YYYY-Q#]"
audit_dates: "[Day 1 date] to [Day 3 date]"
lead_auditor: "[Name]"
technical_auditor: "[Name]"
---

## Executive Summary
[1-2 paragraph overview of audit scope, key findings, and overall compliance posture]

## Audit Scope
[Reference to this audit plan document]

## Findings Summary

| Classification | Count | Controls Affected |
|---------------|-------|------------------|
| Major Nonconformity | [N] | [List] |
| Minor Nonconformity | [N] | [List] |
| Observation | [N] | [List] |
| Opportunity for Improvement | [N] | [List] |

## Framework Coverage

| Framework | Controls Sampled | Controls Passed | Coverage % |
|-----------|-----------------|----------------|-----------|
| ISO/IEC 42001 | 10 | [N] | [%] |
| NIST AI RMF | 7 | [N] | [%] |
| EU AI Act | 7 | [N] | [%] |

## Detailed Findings
[Individual finding entries per Section 7.1 template]

## Corrective Action Tracker

| Finding ID | Classification | Owner | Due Date | Status |
|-----------|---------------|-------|----------|--------|
| [ID] | [Code] | [Owner] | [Date] | Open / In Progress / Closed |

## Auditor Sign-Off

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Lead Auditor | | | |
| Technical Auditor | | | |

## Distribution
- Architecture Board
- Compliance Lead
- AI Engineering Lead
- Operations Lead
- Security Lead
```

### 7.3 Integration with Existing Registers

- All nonconformity findings (NC-MAJ and NC-MIN) are entered into `docs/ai-governance/nonconformity-capa-register.md` with a cross-reference to the finding ID
- Finding owners are assigned based on the owner mapping in Section 4 of this audit plan
- Corrective action due dates follow the response timelines defined in Section 6
- Status updates are tracked at the monthly Architecture Board operational review per `docs/architecture-repository/governance/architecture-board-charter.md`

---

## Appendix A: Audit Team Requirements

| Role | Qualification | Independence Requirement |
|------|-------------|------------------------|
| Lead Auditor | Familiarity with ISO 42001, NIST AI RMF, and EU AI Act; experience in AI system governance auditing | Must not be the primary developer of the controls being audited |
| Technical Auditor | Proficiency in Python, FastAPI, and frontend frameworks; ability to read source code and verify endpoint behaviour | Must not have authored the specific services under review in the past 6 months |

## Appendix B: Reference Documents

| Document | Path | Purpose |
|----------|------|---------|
| Control Applicability Matrix | `docs/ai-governance/control-applicability-matrix.md` | Source of control population and sampling frame |
| AI Management Policy | `docs/ai-governance/ai-management-policy.md` | Top-level AI governance policy |
| AIMS Scope Statement | `docs/ai-governance/00-scope-and-system-boundaries.md` | System boundary definition |
| Competence Training Register | `docs/ai-governance/competence-training-register.md` | Role-competence matrix and training records |
| AI Literacy Training Package | `docs/ai-governance/ai-literacy-training-package.md` | Training curriculum and assessment questions |
| Nonconformity CAPA Register | `docs/ai-governance/nonconformity-capa-register.md` | Corrective action tracking |
| Management Review Template | `docs/ai-governance/management-review-template.md` | Review cadence and decision log |
| Architecture Board Charter | `docs/architecture-repository/governance/architecture-board-charter.md` | Board governance and escalation |
| Write Policy and Rollout | `docs/08-ai-ml/write-policy-and-rollout.md` | Mode discipline and lifecycle |
| Safety Interlocks Engine | `docs/06-safety-compliance/safety-interlocks-engine.md` | Safety rule framework |
| Incident Response Process | `docs/09-security/incident-response-process.md` | Incident handling procedures |
| Data Privacy Policy | `docs/09-security/data-privacy-policy.md` | POPIA and data governance |

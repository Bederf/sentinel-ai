---
title: "Independent Audit Readiness Pack"
version: "1.1.0"
date: "2026-02-23"
status: "Draft"
owner: "Compliance Lead"
author: "SENTINEL Governance Team"
tags: ["ai-governance", "audit", "external-audit", "readiness", "iso-42001", "nist-ai-rmf", "eu-ai-act"]
domain: "compliance"
audience: "external-auditor"
complexity: "intermediate"
estimated_read_time: 20
---

# Independent Audit Readiness Pack

## Purpose

This document provides an external audit firm with the information needed to scope, plan, and execute an independent assessment of the SENTINEL AI Management System (AIMS). It consolidates the organisation overview, audit scope, evidence inventory, gap status, logistics, budget guidance, and auditor selection criteria into a single engagement-ready package.

**Intended audience:** External audit partner, engagement manager, lead auditor.

---

## 1. Organisation Overview

### 1.1 Platform Description

**SENTINEL BMS Intelligence** is an AI-powered Building Management System (BMS) intelligence layer that provides predictive maintenance, energy optimisation, and automated operational recommendations for commercial buildings. The platform integrates with host BMS controllers (e.g., Siemens Desigo CC) and augments them with machine learning capabilities.

| Attribute | Detail |
|-----------|--------|
| Platform name | SENTINEL BMS Intelligence |
| Domain | Commercial building management |
| Primary function | AI-driven equipment health prediction, energy optimisation, automated work order generation |
| Deployment model | On-premises server with cloud-hosted Supabase database |
| Production sites | 1 active site (Site S002 -- Johannesburg commercial building) |
| Programming languages | Python 3.11 (backend), TypeScript/React (frontend) |
| ML models | 6 deployed models (AHU, CHILLER, FCU, UPS, GENERATOR, DALI) |
| Third-party AI | Anthropic Claude (primary LLM), Ollama (local fallback) |
| Data processed | BMS telemetry (temperature, humidity, power, airflow), equipment status, work order history |
| Personal data | None -- all data is equipment/building-level; no biometric, employee, or tenant PII processed |

### 1.2 AI Features in Scope

The following AI/ML capabilities are subject to audit:

| # | Feature | Risk Level | Mode |
|---|---------|-----------|------|
| 1 | Equipment health prediction (6 model types) | Medium | Shadow |
| 2 | Energy consumption optimisation | Medium | Shadow |
| 3 | Automated work order generation | Low | Simulation |
| 4 | AI-powered diagnostics chat (Claude/Ollama) | Low | Active |
| 5 | Predictive maintenance scheduling | Medium | Shadow |
| 6 | Chiller staging optimisation | Medium | Shadow |
| 7 | 3-tier optimisation routing (confidence-based) | Medium | Shadow |
| 8 | Quality gate enforcement (14 metrics, 3 modes) | Medium | Active |
| 9 | Safety interlocks (physical boundary protection) | High | Active |
| 10 | Fairness/bias monitoring (zone equity) | Low | Simulation |

### 1.3 Deployment Context -- Operational Modes

SENTINEL operates in a progressive deployment model. The auditor should understand these modes as they affect which controls are exercised vs. documented-only:

| Mode | Description | Controls Exercised |
|------|-------------|-------------------|
| **Simulation** | All AI runs against simulated data. No connection to live equipment. | Quality gate logic, safety interlock rules, tier routing algorithms |
| **Shadow (shadow_live)** | AI processes live BMS data and generates recommendations, but recommendations are NOT executed on equipment. Logged for comparison only. | Quality gate evaluation with live data, safety boundary checks, Prometheus metrics collection |
| **Supervised (live_supervised)** | AI recommendations require explicit operator approval before execution. | Approval service, operator training verification, live-control entry criteria |
| **Automatic (live_control)** | AI recommendations auto-execute within quality gate and safety interlock boundaries. | Full control chain: quality gate -> safety interlocks -> tier routing -> device abstraction layer |

**Current state:** The platform is predominantly in **Shadow** mode. No features are in live_control. This means many controls are implemented in code and validated via tabletop exercises but have limited production operational evidence.

### 1.4 Team Structure

| Role | Responsibility | Audit Contact |
|------|---------------|--------------|
| AI Engineering Lead | Model development, quality gates, safety interlocks | Primary technical contact |
| ML Operations Engineer | Model deployment, monitoring, drift detection | Metrics and model lifecycle |
| Compliance Lead | Governance framework, CAPA management, audit coordination | Primary audit liaison |
| Operations Lead | Site operations, work order execution, operator training | Operational evidence |
| Architecture Lead | TOGAF governance, architecture decisions, board coordination | Architecture governance |
| Security Lead | Incident response, access control, encryption | Security controls |
| Frontend Lead | UI transparency, AI disclosure badges | User-facing controls |

---

## 2. Audit Scope Proposal

### 2.1 Scope Statement

The independent audit should assess whether SENTINEL has established, implemented, and is maintaining an AI Management System that conforms to the requirements of the applicable frameworks. The assessment should cover the governance structure, control design, control operating effectiveness (where operational evidence exists), and gap management.

### 2.2 Framework Coverage

#### 2.2.1 ISO/IEC 42001: AI Management System

**Scope:** Full AIMS conformity assessment covering:

- **Clauses 4-10** (Context, Leadership, Planning, Support, Operation, Performance, Improvement)
- **Annex A controls** (13 applicable controls as documented in `docs/ai-governance/control-applicability-matrix.md`)
- **Key focus areas:**
  - A.2.2 AI Impact Assessment (risk classification methodology)
  - A.4.4 AI System Lifecycle Process (quality gate, tier routing, model lifecycle)
  - A.6.2 Data Quality (data sheets, training data governance)
  - A.7.1 Monitoring Performance (Prometheus metrics, drift detection)
  - A.8.1 AI Transparency (provenance, disclosure badges)
  - A.10.2 Management Review (cadence, template, CAPA integration)

**Evidence bundle:** `docs/ai-governance/evidence/iso42001-evidence-bundle.md` (100% control coverage, 77% implemented, 23% partial)

#### 2.2.2 NIST AI Risk Management Framework (AI RMF 1.0)

**Scope:** Control-effectiveness review across all four core functions:

- **GOVERN** -- Policy framework, third-party risk, metrics/monitoring
- **MAP** -- Risk classification, model documentation
- **MEASURE** -- Residual risk disclosure, fairness assessment, stress testing
- **MANAGE** -- Retraining governance, CAPA process, model lifecycle management

**Key focus areas:**
  - GV 6.1 Metrics and Monitoring (Prometheus instrumentation vs. operational alerting gap)
  - MS 2.11 Stress Testing (1 of 3 scenarios executed; remaining 2 pending)
  - MG 3.1 CAPA Process (effectiveness verification pending first management review cycle)

**Review report:** `docs/ai-governance/nist-control-effectiveness-review.md` (87% effective: 8 Effective, 3 Partially Effective, 0 Ineffective)

#### 2.2.3 EU AI Act (Regulation (EU) 2024/1689)

**Scope:** Compliance assessment for Limited Risk classification:

- **Article 4** (AI Literacy) -- Training materials, competence register, delivery evidence
- **Article 5** (Prohibited Practices) -- Non-applicability confirmation
- **Article 50** (Transparency) -- Backend provenance, frontend badges, HTTP headers, and body-level provenance for non-streaming AI/recommendation APIs
- **Articles 52/53** (Registration) -- Internal register, classification rationale

**Key focus areas:**
  - Article 4 training delivery records (materials exist, completion records not yet collected)
  - Article 50 exported report watermarking and final transparency inventory
  - Compliance register maturity (currently v0.2.0, target v1.0.0)

**Review report:** `docs/ai-governance/eu-ai-act-assurance-review.md` (75% compliant: 1 Compliant, 3 Partially Compliant)

#### 2.2.4 Cross-Framework Evidence

A key design principle of the SENTINEL governance programme is that one control set satisfies multiple frameworks. The auditor should verify cross-framework mappings:

| Control Area | ISO 42001 | NIST AI RMF | EU AI Act |
|-------------|-----------|-------------|-----------|
| Risk classification | A.2.2 | MP 2.3 | Art. 6 (Annex III) |
| Model documentation | A.6.2, A.8.1 | MP 4.1 | Art. 11 (high-risk) |
| Quality gate | A.4.4, A.7.1 | GV 6.1, MG 4.1 | Art. 9 (high-risk) |
| Safety interlocks | A.4.4 | MG 4.1 | Art. 14 (human oversight) |
| Transparency | A.8.1 | MS 2.6 | Art. 50 |
| Training | A.10.2 | GV 1.1 | Art. 4 |
| CAPA process | Clause 10.1 | MG 3.1 | -- |
| Incident response | A.7.1 | MG 2.4 | Art. 62 (reporting) |
| Fairness/bias | A.6.2 | MS 2.7 | Art. 10 (data governance) |
| Third-party risk | A.4.4 | GV 4.2 | Art. 25 (importer obligations) |

**Evidence:** `docs/ai-governance/control-applicability-matrix.md` (unified control matrix with cross-references)

---

## 3. Evidence Inventory

All governance artifacts are stored in the SENTINEL repository under `docs/ai-governance/`, `docs/compliance/`, and `docs/architecture-repository/`. The following table provides a complete inventory organized by phase and framework relevance.

### 3.1 Phase 1 Artifacts (Foundations -- Phase 114)

| # | Artifact | Path | Created | Owner | Framework(s) |
|---|----------|------|---------|-------|-------------|
| 1 | AIMS Scope and System Boundaries | `docs/ai-governance/00-scope-and-system-boundaries.md` | 2026-02-23 | Compliance Lead | ISO 42001 Clause 4 |
| 2 | Risk Classification Register | `docs/ai-governance/01-risk-classification.md` | 2026-02-23 | Compliance Lead | ISO A.2.2, NIST MP 2.3, EU Art. 6 |
| 3 | ISO 42001 Control Mapping | `docs/ai-governance/02-control-mapping-iso42001.md` | 2026-02-23 | Compliance Lead | ISO 42001 Annex A |
| 4 | NIST AI RMF Control Mapping | `docs/ai-governance/03-control-mapping-nist-airmf.md` | 2026-02-23 | Compliance Lead | NIST AI RMF |
| 5 | EU AI Act Readiness Assessment | `docs/ai-governance/04-eu-ai-act-readiness.md` | 2026-02-23 | Compliance Lead | EU AI Act |
| 6 | Model and Data Governance | `docs/ai-governance/05-model-and-data-governance.md` | 2026-02-23 | AI Engineering Lead | ISO A.6.2, NIST MP 4.1 |
| 7 | Human Oversight and Approval | `docs/ai-governance/06-human-oversight-and-approval.md` | 2026-02-23 | Operations Lead | ISO A.4.4, EU Art. 14 |
| 8 | Incident and Rollback Procedures | `docs/ai-governance/07-incident-and-rollback.md` | 2026-02-23 | Security Lead | NIST MG 2.4 |
| 9 | Monitoring and Metrics Specification | `docs/ai-governance/08-monitoring-and-metrics.md` | 2026-02-23 | MLOps Lead | ISO A.7.1, NIST GV 6.1 |
| 10 | AI Management Policy | `docs/ai-governance/ai-management-policy.md` | 2026-02-23 | Compliance Lead | ISO 42001 Clause 5 |
| 11 | Control Applicability Matrix | `docs/ai-governance/control-applicability-matrix.md` | 2026-02-23 | Compliance Lead | Cross-framework |
| 12 | Management Review Template | `docs/ai-governance/management-review-template.md` | 2026-02-23 | Architecture Lead | ISO A.10.2 |
| 13 | CAPA Register | `docs/ai-governance/nonconformity-capa-register.md` | 2026-02-23 | Compliance Lead | ISO Clause 10.1, NIST MG 3.1 |

### 3.2 Phase 2 Artifacts (Control Implementation -- Phase 115)

| # | Artifact | Path | Created | Owner | Framework(s) |
|---|----------|------|---------|-------|-------------|
| 14 | AI Literacy Training Package | `docs/ai-governance/ai-literacy-training-package.md` | 2026-02-23 | HR Lead | EU Art. 4, ISO A.10.2 |
| 15 | Competence Training Register | `docs/ai-governance/competence-training-register.md` | 2026-02-23 | HR Lead | EU Art. 4 |
| 16 | Live-Control Entry Criteria | `docs/ai-governance/live-control-entry-criteria.md` | 2026-02-23 | AI Engineering Lead | ISO A.4.4 |
| 17 | Residual Risk Disclosure | `docs/ai-governance/residual-risk-disclosure.md` | 2026-02-23 | Operations Lead | NIST MS 2.6, ISO A.8.1 |
| 18 | Retraining Policy | `docs/ai-governance/retraining-policy.md` | 2026-02-23 | MLOps Lead | NIST MG 2.4 |
| 19 | Third-Party AI Risk Register | `docs/ai-governance/third-party-ai-risk-register.md` | 2026-02-23 | Security Lead | NIST GV 4.2 |
| 20 | Fairness/Bias Baseline Assessment | `docs/ai-governance/fairness-bias-baseline.md` | 2026-02-23 | ML Lead | NIST MS 2.7, EU Art. 10 |
| 21 | Stress Test Scenarios (3 scenarios) | `docs/ai-governance/stress-test-scenarios.md` | 2026-02-23 | Security Lead | NIST MS 2.11 |
| 22 | Model Cards (6 models) | `docs/ai-governance/model-cards/` | 2026-02-23 | AI Engineering Lead | NIST MP 4.1 |
| 23 | Data Sheets (3 datasets) | `docs/ai-governance/data-sheets/` | 2026-02-23 | Data Governance Lead | NIST MP 4.1, ISO A.6.2 |
| 24 | AI Provenance Utility | `backend/app/utils/ai_provenance.py` | 2026-02-23 | Backend Lead | EU Art. 50 |
| 25 | AI Disclosure Badge (UI component) | `frontend/src/components/AIDisclosureBadge.tsx` | 2026-02-23 | Frontend Lead | EU Art. 50 |
| 26 | Prometheus Metrics Endpoint | `backend/app/api/metrics.py` | 2026-02-23 | Backend Lead | NIST GV 6.1, ISO A.7.1 |
| 27 | Evidence Collection Index | `docs/ai-governance/evidence/README.md` | 2026-02-23 | Compliance Lead | Cross-framework |

### 3.3 Phase 3 Artifacts (Assurance -- Phase 116)

| # | Artifact | Path | Created | Owner | Framework(s) |
|---|----------|------|---------|-------|-------------|
| 28 | Internal Audit Plan | `docs/ai-governance/internal-audit-plan.md` | 2026-02-23 | Compliance Lead | ISO 42001 Clause 9.2 |
| 29 | ISO 42001 Evidence Bundle | `docs/ai-governance/evidence/iso42001-evidence-bundle.md` | 2026-02-23 | Compliance Lead | ISO 42001 |
| 30 | TOGAF Governance Evidence Bundle | `docs/ai-governance/evidence/togaf-governance-evidence.md` | 2026-02-23 | Architecture Lead | TOGAF 10 |
| 31 | Incident Tabletop Exercise Report | `docs/ai-governance/incident-tabletop-report.md` | 2026-02-23 | Security Lead | NIST MS 2.11, ISO A.7.1 |
| 32 | RCA Postmortem (Tabletop-001) | `docs/ai-governance/evidence/rca-postmortems/tabletop-001-bad-model.md` | 2026-02-23 | Security Lead | NIST MG 3.1 |
| 33 | NIST Control-Effectiveness Review | `docs/ai-governance/nist-control-effectiveness-review.md` | 2026-02-23 | ML Lead | NIST AI RMF |
| 34 | EU AI Act Assurance Review | `docs/ai-governance/eu-ai-act-assurance-review.md` | 2026-02-23 | Compliance Lead | EU AI Act |
| 35 | Independent Audit Readiness Pack | `docs/ai-governance/independent-audit-readiness-pack.md` | 2026-02-23 | Compliance Lead | Cross-framework |

### 3.4 Compliance and Architecture Governance Artifacts

| # | Artifact | Path | Created | Owner | Framework(s) |
|---|----------|------|---------|-------|-------------|
| 36 | EU AI Act Compliance Register | `docs/compliance/eu-ai-act-compliance-register.md` | 2026-02-23 | Compliance Lead | EU AI Act |
| 37 | EU AI Act Policy | `docs/compliance/eu-ai-act-policy.md` | 2026-02-23 | Compliance Lead | EU AI Act |
| 38 | EU AI Act Prohibited Practices Checklist | `docs/compliance/eu-ai-act-prohibited-practices-checklist.md` | 2026-02-23 | Product Lead | EU Art. 5 |
| 39 | Architecture Board Charter | `docs/architecture-repository/governance/architecture-board-charter.md` | 2026-02-23 | Architecture Lead | TOGAF 10 |
| 40 | ADM Mapping (SENTINEL) | `docs/architecture-repository/governance/adm-mapping-sentinel.md` | 2026-02-23 | Architecture Lead | TOGAF 10 |
| 41 | Architecture Capability Model | `docs/architecture-repository/governance/architecture-capability.md` | 2026-02-23 | Architecture Lead | TOGAF 10 |

### 3.5 Code-Level Evidence (Verifiable in Repository)

| # | Evidence | Path | Verification Method |
|---|----------|------|-------------------|
| 42 | Quality Gate Evaluator (14 metrics, 3 modes) | `backend/app/services/quality_gate_evaluator.py` | Code review, unit tests |
| 43 | Quality Gate Policy (42 threshold entries) | `backend/app/services/quality_gate_policy.py` | Code review |
| 44 | Safety Interlocks | `backend/app/services/safety_interlocks.py` | Code review, unit tests |
| 45 | Optimisation Tier Router | `backend/app/services/optimization_tier_router.py` | Code review, unit tests |
| 46 | Approval Service | `backend/app/services/approval_service.py` | Code review |
| 47 | AI Provenance Utility | `backend/app/utils/ai_provenance.py` | Code review |
| 48 | Prometheus Metrics Instrumentation | `backend/app/api/metrics.py` | Code review, endpoint verification |

**Total artifacts: 48** (35 governance documents, 6 model cards, 3 data sheets, 1 UI component, 3 code-level controls)

Supporting security evidence outside the AI governance count includes `docs/09-security/threat-model-summary.md`, which now provides the one-page threat model summary referenced by the infrastructure audit backlog.

---

## 4. Gap Status Summary

### 4.1 Phase 2 Gate Items -- Outstanding

The following Phase 2 gate items remain open. They are process-dependent or require production time and cannot be resolved through documentation alone:

| Gate Item | Status | Blocker | Estimated Resolution |
|-----------|--------|---------|---------------------|
| Prometheus scrape stable for 14 consecutive days | OPEN | Requires Grafana deployment and 14 days of stable scrape data | Q2 2026 (after Grafana deployment) |
| AI governance metrics published and alerting active | OPEN | Depends on Prometheus scrape stability + Grafana dashboard creation | Q2 2026 |
| Live AI risk register reviewed monthly with incident/CAPA links | OPEN | Requires first monthly review cycle to complete | Q2 2026 (first review scheduled) |

### 4.2 Phase 3 Gate Items -- Status After 116-01 and 116-02

| Gate Item | Status | Evidence |
|-----------|--------|----------|
| Internal audit completed across ISO/NIST/EU control mappings | COMPLETE | `docs/ai-governance/internal-audit-plan.md`, `docs/ai-governance/evidence/iso42001-evidence-bundle.md`, `docs/ai-governance/nist-control-effectiveness-review.md`, `docs/ai-governance/eu-ai-act-assurance-review.md` |
| Incident tabletop actions closed or accepted with owner/date | IN PROGRESS | `docs/ai-governance/incident-tabletop-report.md` -- 5 actions logged with owners and due dates. Actions tracked in CAPA register (NC-004). |
| Independent audit scope, budget, and timeline approved | IN PROGRESS | This document (audit readiness pack) provides the scope. Budget and timeline require executive approval. |
| All high/critical CAPA actions closed | IN PROGRESS | NC-001 through NC-003 CLOSED (Phase 1). NC-004 through NC-006 raised from Phase 3 findings -- see CAPA register. |
| Final compliance closure report approved by Architecture Board | NOT STARTED | Depends on CAPA closure and executive review |

### 4.3 NIST AI RMF Gaps (from Control-Effectiveness Review)

| Control | Rating | Gap | Severity |
|---------|--------|-----|----------|
| GV 6.1 Metrics and Monitoring | Partially Effective | Grafana dashboards not configured; alert routing not wired to live notification channel | Major |
| MS 2.11 Stress Testing | Partially Effective | Only 1 of 3 scenarios executed (Scenarios 2 and 3 pending) | Minor |
| MG 3.1 CAPA Process | Partially Effective | Effectiveness verification not yet exercised (no management review cycle completed) | Minor |

### 4.4 EU AI Act Gaps (from Assurance Review)

| Article | Status | Gap | Severity |
|---------|--------|-----|----------|
| Article 4 (AI Literacy) | Partially Compliant | Training delivery records not collected; no competence assessments on file | Major |
| Article 50 (Transparency) | Partially Compliant | Non-streaming AI/recommendation APIs now stamp body-level provenance; streaming chat remains header-based by design; exported reports still lack AI watermark | Minor |
| Articles 52/53 (Registration) | Partially Compliant | Compliance register at v0.2.0; EU database registration not evaluated | Minor |

### 4.5 Residual Risks Acknowledged

The following residual risks are formally disclosed in `docs/ai-governance/residual-risk-disclosure.md`:

1. **Sensor dependency** -- AI predictions depend on BMS sensor accuracy; sensor faults propagate to model outputs
2. **Model drift between retraining cycles** -- Performance may degrade between quarterly retraining
3. **Third-party API availability** -- Claude API outage falls back to local Ollama (reduced capability)
4. **Simulation-to-live gap** -- Controls validated in simulation/shadow may behave differently in live_control
5. **Operator override risk** -- Operators can override AI recommendations; overrides are logged but not prevented

---

## 5. Audit Logistics

### 5.1 Suggested Timeline

A 5 business day engagement is recommended for the initial independent assessment:

| Day | Focus | Activities |
|-----|-------|-----------|
| **Day 1** | Document review | Review governance pack (`docs/ai-governance/`), compliance register, control applicability matrix, CAPA register. Identify sampling plan. |
| **Day 2** | Technical verification | Repository access walkthrough, code review of quality gate evaluator, safety interlocks, tier router, Prometheus metrics endpoint. Demo environment demonstration. |
| **Day 3** | Evidence testing | Verify evidence paths exist and content matches claims. Test cross-framework mappings. Review model cards against model registry data. |
| **Day 4** | Interviews | AI Engineering Lead (model lifecycle, quality gates), Operations Lead (operational procedures, training), Compliance Lead (CAPA process, governance cadence), Architecture Lead (TOGAF governance, board charter) |
| **Day 5** | Findings and report | Consolidate findings, draft report, exit meeting with management team |

### 5.2 Access Requirements

| Resource | Access Method | Contact |
|----------|-------------|---------|
| Source code repository | Git clone / GitHub access (read-only) | AI Engineering Lead |
| Demo environment | Browser access to `http://localhost:3000` (frontend) and `http://localhost:9095/docs` (API docs) | AI Engineering Lead |
| Supabase database (read-only) | Direct query via Supabase Studio on `http://localhost:54323` | AI Engineering Lead |
| Prometheus metrics | Browser access to `http://localhost:9095/metrics` | Backend Lead |
| Documentation | Repository `docs/` directory | Compliance Lead |

**Note:** The demo environment (`DEMO_MODE=true`) provides full system functionality with simulated data. No production building data is exposed during the audit.

### 5.3 Contact Matrix

| Role | Audit Function | Availability |
|------|---------------|-------------|
| Compliance Lead | Primary audit liaison, scheduling, document requests | Full-time during audit week |
| AI Engineering Lead | Technical deep-dives, code walkthroughs, demo environment | On-call Days 2-3, interview Day 4 |
| Operations Lead | Operational procedures, training evidence, work order processes | Interview Day 4 |
| Architecture Lead | TOGAF governance, architecture decisions, board charter | Interview Day 4 |
| Security Lead | Incident response, access controls, stress test evidence | On-call Days 2-3 |

### 5.4 Document Request List

The auditor should request the following before the engagement begins:

| # | Document | Format | Pre-engagement Delivery |
|---|----------|--------|------------------------|
| 1 | This audit readiness pack | Markdown / PDF | Yes (this document) |
| 2 | Control applicability matrix | Markdown | Yes |
| 3 | CAPA register (current snapshot) | Markdown | Yes |
| 4 | Internal audit plan | Markdown | Yes |
| 5 | ISO 42001 evidence bundle | Markdown | Yes |
| 6 | NIST effectiveness review | Markdown | Yes |
| 7 | EU AI Act assurance review | Markdown | Yes |
| 8 | Repository access credentials | Secure transfer | Day 1 |
| 9 | Demo environment setup instructions | Markdown | Day 1 |

---

## 6. Budget Note Template

### 6.1 Engagement Scope Summary

| Parameter | Value |
|-----------|-------|
| Audit type | Independent AI governance assessment |
| Frameworks | ISO/IEC 42001, NIST AI RMF 1.0, EU AI Act |
| Duration | 5 business days (on-site or remote) |
| Team size | 1 lead auditor + 1 technical auditor (AI/ML specialist) |
| Deliverables | Findings report, gap assessment, recommendations, executive summary |

### 6.2 Typical Cost Ranges

The following ranges are indicative for AI governance audits in the South African market (2026 rates):

| Component | Estimated Range (ZAR) | Notes |
|-----------|----------------------|-------|
| Lead auditor (5 days) | R80,000 -- R120,000 | ISO Lead Auditor certified |
| Technical auditor (5 days) | R60,000 -- R100,000 | AI/ML domain specialist |
| Report preparation | R20,000 -- R40,000 | Findings consolidation and recommendations |
| Travel and expenses | R10,000 -- R30,000 | If on-site engagement (Johannesburg) |
| **Total estimated range** | **R170,000 -- R290,000** | Excluding VAT |

**International firms:** For auditors from international firms with ISO 42001 accreditation, expect the upper range or above. Remote-first engagements can reduce travel costs.

### 6.3 Budget Approval Requirements

- [ ] Executive sponsor approval (CFO or equivalent)
- [ ] Procurement process followed (3 quotes recommended)
- [ ] Engagement letter signed with scope, deliverables, and timeline
- [ ] NDA executed before repository access granted
- [ ] Insurance certificate verified (professional indemnity)

---

## 7. Candidate Shortlist Criteria

### 7.1 Mandatory Requirements

| # | Criterion | Verification Method |
|---|-----------|-------------------|
| 1 | **ISO 42001 accreditation** -- Firm must be accredited to perform ISO/IEC 42001 audits by a recognized accreditation body (e.g., SANAS in South Africa, UKAS in UK, JAS-ANZ in Australia/NZ) | Request accreditation certificate and scope |
| 2 | **AI/ML governance experience** -- At least one team member must have demonstrable experience auditing AI/ML systems, including model lifecycle management, algorithmic risk assessment, and data governance | Review CVs and engagement references |
| 3 | **South African regulatory context** -- Familiarity with POPIA (Protection of Personal Information Act), FSR (Financial Sector Regulation Act), and South African building regulations | Request previous SA engagement references |
| 4 | **Professional indemnity insurance** -- Minimum R10 million PI cover | Request certificate of insurance |
| 5 | **Independence** -- No consulting or implementation work performed for SENTINEL in the past 2 years | Independence declaration |

### 7.2 Desirable Criteria

| # | Criterion | Weight |
|---|-----------|--------|
| 1 | Experience with BMS/building technology sector | High |
| 2 | NIST AI RMF assessment experience | Medium |
| 3 | EU AI Act readiness assessment experience | Medium |
| 4 | TOGAF governance assessment capability | Low |
| 5 | References from similar-sized organisations (SME, 1-5 AI models) | High |
| 6 | Ability to conduct remote-first engagement | Medium |
| 7 | Previous ISO 27001/27701 audit experience (complementary frameworks) | Low |

### 7.3 Evaluation Scoring

| Criterion | Max Score |
|-----------|-----------|
| ISO 42001 accreditation | 25 |
| AI/ML governance experience | 25 |
| SA regulatory familiarity | 15 |
| Sector experience (BMS/building tech) | 15 |
| References | 10 |
| Cost competitiveness | 10 |
| **Total** | **100** |

**Minimum qualifying score:** 60/100 (must score maximum on mandatory criteria)

### 7.4 Engagement Process

1. **RFP distribution** -- Send this audit readiness pack with scope proposal to shortlisted firms
2. **Proposal receipt** -- 2-week response window
3. **Evaluation** -- Score proposals using criteria above
4. **Selection** -- Present top 2 candidates to executive sponsor for final decision
5. **Engagement** -- Execute NDA, engagement letter, and schedule audit week
6. **Audit execution** -- 5 business days per timeline above
7. **Report delivery** -- 2 weeks after audit completion
8. **Management response** -- 2 weeks after report delivery (CAPA entries for findings)

---

## 8. Submission-Ready Evidence Manifest

The validated evidence manifest is finalized and ready for submission to external auditors. The manifest includes 54 evidence artifacts across governance documents, model cards, data sheets, code-level controls, and evidence directories.

**Primary reference:** [`docs/ai-governance/evidence/README.md`](evidence/README.md) -- Validated Evidence Manifest section.

**Status:** Submission-ready pending external audit report. All artifacts are present and validated against independent audit readiness pack v1.0.0.

**Key artifact categories:**
- **Governance documents:** 35 artifacts (AIMS scope, risk registers, control mappings, policies, templates)
- **Model documentation:** 6 model cards, 3 data sheets
- **Code-level controls:** 7 critical AI safety and governance components
- **Evidence directories:** 6 structured directories for ongoing evidence collection

**Auditor note:** The evidence manifest is maintained in the repository and will be provided as part of the audit engagement package. The manifest is version-controlled and updated quarterly.

---

## Cross-References

- Unified Compliance Programme: [`/opt/bms-intelligence/compliance.md`](/opt/bms-intelligence/compliance.md)
- Internal Audit Plan: [`docs/ai-governance/internal-audit-plan.md`](internal-audit-plan.md)
- ISO 42001 Evidence Bundle: [`docs/ai-governance/evidence/iso42001-evidence-bundle.md`](evidence/iso42001-evidence-bundle.md)
- TOGAF Governance Evidence: [`docs/ai-governance/evidence/togaf-governance-evidence.md`](evidence/togaf-governance-evidence.md)
- NIST Effectiveness Review: [`docs/ai-governance/nist-control-effectiveness-review.md`](nist-control-effectiveness-review.md)
- EU AI Act Assurance Review: [`docs/ai-governance/eu-ai-act-assurance-review.md`](eu-ai-act-assurance-review.md)
- CAPA Register: [`docs/ai-governance/nonconformity-capa-register.md`](nonconformity-capa-register.md)
- Control Applicability Matrix: [`docs/ai-governance/control-applicability-matrix.md`](control-applicability-matrix.md)
- Residual Risk Disclosure: [`docs/ai-governance/residual-risk-disclosure.md`](residual-risk-disclosure.md)
- Evidence Collection Index: [`docs/ai-governance/evidence/README.md`](evidence/README.md)

---

## Document History

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 1.0.0 | 2026-02-23 | SENTINEL Governance Team | Initial audit readiness pack with 7 sections, 48 evidence artifacts inventoried |
| 1.1.0 | 2026-03-20 | SENTINEL Governance Team | Added Section 8: Submission-Ready Evidence Manifest; updated version |

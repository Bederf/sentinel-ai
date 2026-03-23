---
title: "AI Governance Evidence Index"
type: "reference"
status: "active"
version: "1.1.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
tags: ["ai-governance", "evidence", "audit"]
domain: "compliance"
audience: "all"
complexity: "beginner"
estimated_read_time: 6
---

# AI Governance Evidence Index

This directory stores audit-ready artifacts for the SENTINEL AI Management System (AIMS). Evidence is organized by category, collected on a defined schedule, and retained per the data privacy policy.

## Evidence Directories

### `training/`

**Purpose**: Store sign-off records, assessment results, and training completion logs for AI literacy (EU AI Act Article 4) and role-specific competence training.

**Contents**:
- Training completion certificates and sign-off records
- Assessment/quiz results per role
- Annual refresh evidence and re-certification logs
- Training package version history

**Collection trigger**: On completion of training event
**Owner**: HR Lead

### `drift-reports/`

**Purpose**: Monthly drift metric exports and drift action logs. Captures feature distribution shifts, model performance degradation, and corrective actions taken.

**Contents**:
- Monthly drift metric snapshots (per model)
- Feature distribution shift analyses
- Drift action logs (threshold breach, investigation, resolution)
- Trend reports for quarterly management review

**Collection trigger**: Monthly (automated export + manual review)
**Owner**: MLOps Lead

### `audit-logs-samples/`

**Purpose**: Quarterly representative audit trail samples demonstrating traceability of AI decisions from input through recommendation to outcome.

**Contents**:
- Representative API request/response traces
- Quality gate evaluation logs
- Tier routing decision samples
- Provenance metadata samples from `ai_provenance.py`

**Collection trigger**: Quarterly (sampled during management review prep)
**Owner**: Compliance Lead

### `rca-postmortems/`

**Purpose**: Stress test results, incident root cause analysis (RCA) reports, and corrective action records.

**Contents**:
- Stress test scenario execution reports (naming: `stress-test-{N}-{date}.md`)
- Incident RCA reports with timeline and root cause analysis
- CAPA closure evidence linked from nonconformity register
- Lessons learned summaries

**Collection trigger**: On event (stress test execution or incident occurrence)
**Owner**: Security Lead

### `model-cards/`

**Purpose**: Versioned model card snapshots used in management reviews. Point-in-time records of model documentation as reviewed and approved.

**Contents**:
- Model card snapshots (versioned copies at review date)
- Review sign-off records
- Model performance summary at time of review

**Collection trigger**: On model version change or quarterly review
**Owner**: AI Engineering Lead

### `data-sheets/`

**Purpose**: Dataset and corpus governance records documenting data provenance, quality, and usage rights.

**Contents**:
- Data sheet documents per governed dataset
- Data quality assessment records
- Data provenance and lineage documentation

**Collection trigger**: On dataset creation or major update
**Owner**: Data Governance Lead

## Phase 3 Assurance Artifacts (Phase 116)

The following artifacts were created during the Phase 3 assurance cycle and form the evidence base for independent audit readiness:

| # | Artifact | Path | Created | Owner |
|---|----------|------|---------|-------|
| 1 | Internal Audit Plan | `docs/ai-governance/internal-audit-plan.md` | 2026-02-23 | Compliance Lead |
| 2 | ISO 42001 Evidence Bundle | `docs/ai-governance/evidence/iso42001-evidence-bundle.md` | 2026-02-23 | Compliance Lead |
| 3 | TOGAF Governance Evidence Bundle | `docs/ai-governance/evidence/togaf-governance-evidence.md` | 2026-02-23 | Architecture Lead |
| 4 | Incident Tabletop Exercise Report | `docs/ai-governance/incident-tabletop-report.md` | 2026-02-23 | Security Lead |
| 5 | RCA Postmortem (Tabletop-001) | `docs/ai-governance/evidence/rca-postmortems/tabletop-001-bad-model.md` | 2026-02-23 | Security Lead |
| 6 | NIST Control-Effectiveness Review | `docs/ai-governance/nist-control-effectiveness-review.md` | 2026-02-23 | ML Lead |
| 7 | EU AI Act Assurance Review | `docs/ai-governance/eu-ai-act-assurance-review.md` | 2026-02-23 | Compliance Lead |
| 8 | Independent Audit Readiness Pack | `docs/ai-governance/independent-audit-readiness-pack.md` | 2026-02-23 | Compliance Lead |

## Validated Evidence Manifest

This section provides a normalized inventory of all evidence artifacts, validated against the independent audit readiness pack (v1.0.0) and FSR gap analysis (v3.1). Each entry includes concrete file path, owner role, validation note, and current status.

### Present

The following evidence artifacts are present and referenced in governance documentation:

| # | Artifact | Path | Owner | Validation Note | Status |
|---|----------|------|-------|----------------|--------|
| 1 | AIMS Scope and System Boundaries | `docs/ai-governance/00-scope-and-system-boundaries.md` | Compliance Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 2 | Risk Classification Register | `docs/ai-governance/01-risk-classification.md` | Compliance Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 3 | ISO 42001 Control Mapping | `docs/ai-governance/02-control-mapping-iso42001.md` | Compliance Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 4 | NIST AI RMF Control Mapping | `docs/ai-governance/03-control-mapping-nist-airmf.md` | Compliance Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 5 | EU AI Act Readiness Assessment | `docs/ai-governance/04-eu-ai-act-readiness.md` | Compliance Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 6 | Model and Data Governance | `docs/ai-governance/05-model-and-data-governance.md` | AI Engineering Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 7 | Human Oversight and Approval | `docs/ai-governance/06-human-oversight-and-approval.md` | Operations Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 8 | Incident and Rollback Procedures | `docs/ai-governance/07-incident-and-rollback.md` | Security Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 9 | Monitoring and Metrics Specification | `docs/ai-governance/08-monitoring-and-metrics.md` | MLOps Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 10 | AI Management Policy | `docs/ai-governance/ai-management-policy.md` | Compliance Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 11 | Control Applicability Matrix | `docs/ai-governance/control-applicability-matrix.md` | Compliance Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 12 | Management Review Template | `docs/ai-governance/management-review-template.md` | Architecture Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 13 | CAPA Register | `docs/ai-governance/nonconformity-capa-register.md` | Compliance Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 14 | AI Literacy Training Package | `docs/ai-governance/ai-literacy-training-package.md` | HR Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 15 | Competence Training Register | `docs/ai-governance/competence-training-register.md` | HR Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 16 | Live-Control Entry Criteria | `docs/ai-governance/live-control-entry-criteria.md` | AI Engineering Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 17 | Residual Risk Disclosure | `docs/ai-governance/residual-risk-disclosure.md` | Operations Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 18 | Retraining Policy | `docs/ai-governance/retraining-policy.md` | MLOps Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 19 | Third-Party AI Risk Register | `docs/ai-governance/third-party-ai-risk-register.md` | Security Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 20 | Fairness/Bias Baseline Assessment | `docs/ai-governance/fairness-bias-baseline.md` | ML Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 21 | Stress Test Scenarios (3 scenarios) | `docs/ai-governance/stress-test-scenarios.md` | Security Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 22 | Model Cards (6 models) | `docs/ai-governance/model-cards/` | AI Engineering Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 23 | Data Sheets (3 datasets) | `docs/ai-governance/data-sheets/` | Data Governance Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 24 | AI Provenance Utility | `backend/app/utils/ai_provenance.py` | Backend Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 25 | AI Disclosure Badge (UI component) | `frontend/src/components/AIDisclosureBadge.tsx` | Frontend Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 26 | Prometheus Metrics Endpoint | `backend/app/api/metrics.py` | Backend Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 27 | Evidence Collection Index | `docs/ai-governance/evidence/README.md` | Compliance Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 28 | Internal Audit Plan | `docs/ai-governance/internal-audit-plan.md` | Compliance Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 29 | ISO 42001 Evidence Bundle | `docs/ai-governance/evidence/iso42001-evidence-bundle.md` | Compliance Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 30 | TOGAF Governance Evidence Bundle | `docs/ai-governance/evidence/togaf-governance-evidence.md` | Architecture Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 31 | Incident Tabletop Exercise Report | `docs/ai-governance/incident-tabletop-report.md` | Security Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 32 | RCA Postmortem (Tabletop-001) | `docs/ai-governance/evidence/rca-postmortems/tabletop-001-bad-model.md` | Security Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 33 | NIST Control-Effectiveness Review | `docs/ai-governance/nist-control-effectiveness-review.md` | ML Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 34 | EU AI Act Assurance Review | `docs/ai-governance/eu-ai-act-assurance-review.md` | Compliance Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 35 | Independent Audit Readiness Pack | `docs/ai-governance/independent-audit-readiness-pack.md` | Compliance Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 36 | EU AI Act Compliance Register | `docs/compliance/eu-ai-act-compliance-register.md` | Compliance Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 37 | EU AI Act Policy | `docs/compliance/eu-ai-act-policy.md` | Compliance Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 38 | EU AI Act Prohibited Practices Checklist | `docs/compliance/eu-ai-act-prohibited-practices-checklist.md` | Product Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 39 | Architecture Board Charter | `docs/architecture-repository/governance/architecture-board-charter.md` | Architecture Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 40 | ADM Mapping (SENTINEL) | `docs/architecture-repository/governance/adm-mapping-sentinel.md` | Architecture Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 41 | Architecture Capability Model | `docs/architecture-repository/governance/architecture-capability.md` | Architecture Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 42 | Quality Gate Evaluator (14 metrics, 3 modes) | `backend/app/services/quality_gate_evaluator.py` | AI Engineering Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 43 | Quality Gate Policy (42 threshold entries) | `backend/app/services/quality_gate_policy.py` | AI Engineering Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 44 | Safety Interlocks | `backend/app/services/safety_interlocks.py` | AI Engineering Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 45 | Optimisation Tier Router | `backend/app/services/optimization_tier_router.py` | AI Engineering Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 46 | Approval Service | `backend/app/services/approval_service.py` | AI Engineering Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 47 | AI Provenance Utility | `backend/app/utils/ai_provenance.py` | Backend Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 48 | Prometheus Metrics Instrumentation | `backend/app/api/metrics.py` | Backend Lead | Referenced in independent audit readiness pack v1.0.0 | present |
| 49 | Training evidence directory | `docs/ai-governance/evidence/training/` | HR Lead | Evidence directory defined in README | present |
| 50 | Drift reports directory | `docs/ai-governance/evidence/drift-reports/` | MLOps Lead | Evidence directory defined in README | present |
| 51 | Audit log samples directory | `docs/ai-governance/evidence/audit-logs-samples/` | Compliance Lead | Evidence directory defined in README | present |
| 52 | RCA postmortems directory | `docs/ai-governance/evidence/rca-postmortems/` | Security Lead | Evidence directory defined in README | present |
| 53 | Model cards directory | `docs/ai-governance/evidence/model-cards/` | AI Engineering Lead | Evidence directory defined in README | present |
| 54 | Data sheets directory | `docs/ai-governance/evidence/data-sheets/` | Data Governance Lead | Evidence directory defined in README | present |

### Stale

No stale evidence identified as of 2026-03-20.

### Missing

No missing evidence identified as of 2026-03-20.

## Collection Schedule

| Category | Frequency | Trigger | Owner | Review Forum |
|----------|-----------|---------|-------|-------------|
| Training | On completion | Training event ends | HR Lead | Quarterly management review |
| Drift Reports | Monthly | Calendar (1st of month) | MLOps Lead | Monthly compliance review |
| Audit Log Samples | Quarterly | Management review prep | Compliance Lead | Quarterly management review |
| RCA/Postmortems | On event | Stress test or incident | Security Lead | Next management review |
| Model Cards | On change / quarterly | Model update or review | AI Engineering Lead | Quarterly management review |
| Data Sheets | On change | Dataset update | Data Governance Lead | Annual review |
| Assurance Reviews | Quarterly | Phase 3+ review cycle | Compliance Lead | Quarterly management review |
| Tabletop Exercises | Quarterly | Stress test schedule | Security Lead | Quarterly management review |
| CAPA Register Snapshot | Quarterly | Management review prep | Compliance Lead | Quarterly management review |

## Retention Policy

Evidence is retained per the data privacy policy (`docs/09-security/data-privacy-policy.md`):

- **Minimum retention**: 3 years for all compliance evidence
- **Regulatory evidence**: Retained for the duration required by applicable regulation (EU AI Act: 10 years for high-risk system documentation)
- **Deletion**: Only after retention period expires and with Compliance Lead approval

## Cross-References

- Stress test scenarios: [`stress-test-scenarios.md`](../stress-test-scenarios.md)
- CAPA register: [`nonconformity-capa-register.md`](../nonconformity-capa-register.md)
- Data privacy policy: [`data-privacy-policy.md`](../data-privacy-policy.md)
- Compliance programme: [`/opt/bms-intelligence/compliance.md`](/opt/bms-intelligence/compliance.md)

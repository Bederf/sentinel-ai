---
title: "AI Governance Pack"
type: "reference"
status: "active"
version: "1.1.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
tags: ["ai-governance", "index", "iso-42001", "nist-ai-rmf", "eu-ai-act"]
domain: "compliance"
audience: "all"
complexity: "beginner"
estimated_read_time: 5
---

# AI Governance Pack

**Compliance Programme Status:** Phase 3 Complete -- Pending Board Approval

Operational governance pack for:

- ISO/IEC 42001 alignment
- NIST AI RMF 1.0 mapping
- EU AI Act readiness

## Contents

### Core Governance Documents

- `00-scope-and-system-boundaries.md` -- AIMS scope statement, exclusions, and boundaries
- `01-risk-classification.md` -- Per-feature risk classification (EU AI Act aligned)
- `02-control-mapping-iso42001.md` -- ISO/IEC 42001 control mapping
- `03-control-mapping-nist-airmf.md` -- NIST AI RMF 1.0 control mapping
- `04-eu-ai-act-readiness.md` -- EU AI Act readiness assessment
- `05-model-and-data-governance.md` -- Model and data governance framework
- `06-human-oversight-and-approval.md` -- Human oversight and approval workflow
- `07-incident-and-rollback.md` -- Incident response and rollback procedures
- `08-monitoring-and-metrics.md` -- Prometheus metrics, dashboards, and alert rules

### Policy and Management

- `ai-management-policy.md` -- AI Management Policy with measurable objectives/KPIs
- `management-review-template.md` -- Management review cadence and decision log template
- `nonconformity-capa-register.md` -- AI nonconformity and CAPA workflow register
- `control-applicability-matrix.md` -- Control applicability matrix with owners/evidence links

### Phase 2: Training, Risk & Compliance

- `ai-literacy-training-package.md` -- AI literacy training curriculum (EU AI Act Article 4)
- `competence-training-register.md` -- Role-based competence register with annual refresh tracking
- `live-control-entry-criteria.md` -- Entry criteria evidence pack for live control mode
- `residual-risk-disclosure.md` -- Operator-facing residual risk disclosure per AI use case
- `retraining-policy.md` -- Model retraining cadence, trigger policy, and run log requirements
- `third-party-ai-risk-register.md` -- Third-party AI vendor risk register
- `fairness-bias-baseline.md` -- Fairness/bias baseline analysis across 6 models and 4 equity dimensions
- `stress-test-scenarios.md` -- 3 quarterly stress test scenario templates with pass criteria

### Model and Data Governance

- `model-cards/` -- Model cards for 6 active ML models (AHU, CHILLER, FCU, UPS, GENERATOR, DALI)
- `evidence/data-sheets/` -- Data sheets for governed datasets and corpora

### Phase 3: Assurance and Closure

- `internal-audit-plan.md` -- Internal audit plan (ISO/NIST/EU scope, sampling methodology, audit schedule)
- `incident-tabletop-report.md` -- Incident tabletop exercise report (Scenario 1: Bad Model Update)
- `nist-control-effectiveness-review.md` -- NIST AI RMF control-effectiveness review (11 controls, 87% effective)
- `eu-ai-act-assurance-review.md` -- EU AI Act assurance review (Articles 4/5/50/52-53, 75% compliant)
- `independent-audit-readiness-pack.md` -- Independent audit readiness pack (48 artifacts, 7 sections)
- `compliance-closure-report.md` -- Unified compliance closure report (Phases 1-3, executive summary, recommendations)
- `phase3-board-review-memo.md` -- Architecture Board review memo (4 decision items, resolution template)
- `evidence/iso42001-evidence-bundle.md` -- ISO 42001 evidence bundle (13 controls mapped with evidence paths)
- `evidence/togaf-governance-evidence.md` -- TOGAF governance evidence bundle
- `evidence/rca-postmortems/tabletop-001-bad-model.md` -- RCA postmortem for TABLETOP-001 scenario

### Evidence

- `evidence/README.md` -- Evidence collection index and process documentation (v1.1.0, quarterly cadence)
- `evidence/drift-reports/` -- Model drift evidence snapshots
- `evidence/audit-logs-samples/` -- Representative traceability samples
- `evidence/rca-postmortems/` -- Stress test results and incident RCA reports
- `evidence/training/` -- AI literacy and competence training records
- `evidence/model-cards/` -- Versioned model card snapshots for reviews
- `evidence/data-sheets/` -- Training data provenance sheets

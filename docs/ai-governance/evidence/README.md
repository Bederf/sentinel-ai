---
title: "AI Governance Evidence Index"
type: "reference"
status: "active"
version: "1.0.0"
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

## Collection Schedule

| Category | Frequency | Trigger | Owner | Review Forum |
|----------|-----------|---------|-------|-------------|
| Training | On completion | Training event ends | HR Lead | Quarterly management review |
| Drift Reports | Monthly | Calendar (1st of month) | MLOps Lead | Monthly compliance review |
| Audit Log Samples | Quarterly | Management review prep | Compliance Lead | Quarterly management review |
| RCA/Postmortems | On event | Stress test or incident | Security Lead | Next management review |
| Model Cards | On change / quarterly | Model update or review | AI Engineering Lead | Quarterly management review |
| Data Sheets | On change | Dataset update | Data Governance Lead | Annual review |

## Retention Policy

Evidence is retained per the data privacy policy (`docs/ai-governance/data-privacy-policy.md`):

- **Minimum retention**: 3 years for all compliance evidence
- **Regulatory evidence**: Retained for the duration required by applicable regulation (EU AI Act: 10 years for high-risk system documentation)
- **Deletion**: Only after retention period expires and with Compliance Lead approval

## Cross-References

- Stress test scenarios: [`stress-test-scenarios.md`](../stress-test-scenarios.md)
- CAPA register: [`nonconformity-capa-register.md`](../nonconformity-capa-register.md)
- Data privacy policy: [`data-privacy-policy.md`](../data-privacy-policy.md)
- Compliance programme: [`/opt/bms-intelligence/compliance.md`](/opt/bms-intelligence/compliance.md)

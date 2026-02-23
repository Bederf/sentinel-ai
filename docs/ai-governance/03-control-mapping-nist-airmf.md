---
title: "NIST AI RMF 1.0 Control Mapping"
type: "audit"
status: "draft"
version: "0.1.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
tags: ["ai-governance", "nist-ai-rmf", "control-mapping", "risk-management"]
domain: "compliance"
audience: "all"
complexity: "advanced"
estimated_read_time: 14
---

# NIST AI RMF 1.0 Control Mapping

## Current Posture

Current desk-based alignment estimate: **~71% strong alignment**.  
Main gaps are governance artifacts and monitoring evidence consistency.

## Function-Level Mapping

| NIST Function | Current Strengths | Evidence Paths | Main Gaps |
|---|---|---|---|
| GOVERN | Security governance baseline, role segregation, policy suite | `docs/09-security/`, `docs/compliance/` | AI-specific management review and competence register |
| MAP | AI use-case identification and risk context emerging | `docs/ai-governance/00-scope-and-system-boundaries.md`, `docs/ai-governance/01-risk-classification.md` | Formal impact/fairness and residual-risk artifacts |
| MEASURE | Drift, alerting, metrics endpoints in place | `backend/app/api/mlops.py`, `docs/04-features/45-03-mlops-monitoring.md` | Prometheus-style control effectiveness metrics not fully wired |
| MANAGE | Approval gating, rollback discipline, incident docs | `backend/app/services/approval_service.py`, `docs/09-security/incident-response-policy.md` | AI nonconformity/CAPA workflow and independent audit evidence |

## Top Gap Register

| Gap ID | Gap | NIST Area | Action | Target Date |
|---|---|---|---|---|
| NIST-G1 | Model cards incomplete | MEASURE | Create model cards for all active models | 2026-03-31 |
| NIST-G2 | Fairness and impact analysis absent | MAP/MEASURE | Baseline zone/tenant equity analysis | 2026-04-15 |
| NIST-G3 | Independent AI audit not scheduled | GOVERN | Define scope and schedule external review | 2026-04-30 |
| NIST-G4 | Residual risk disclosure absent | MAP/MANAGE | Publish operator-facing residual risk disclosures | 2026-03-31 |
| NIST-G5 | Retraining cadence not policy-bound | MANAGE | Publish retraining policy and trigger thresholds | 2026-04-15 |
| NIST-G6 | Third-party AI risk register not AI-specific | GOVERN | Expand third-party risk register for AI dependencies | 2026-04-15 |
| NIST-G7 | Monitoring evidence not audit-ready | MEASURE | Wire metrics + alerts + evidence retention | 2026-04-15 |

## Operating KPI Targets

- AI governance action closure rate: `>= 90%` per quarter
- Drift critical alert response: `< 4h` median
- Approval-gate failure triage: `< 2h` median
- Evidence completeness per mapped control: `>= 95%`

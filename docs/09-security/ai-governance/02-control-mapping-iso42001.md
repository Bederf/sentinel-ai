---
title: "ISO/IEC 42001 Control Mapping"
type: "audit"
status: "draft"
version: "0.1.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
tags: ["ai-governance", "iso-42001", "control-mapping", "aims"]
domain: "compliance"
audience: "all"
complexity: "advanced"
estimated_read_time: 15
---

# ISO/IEC 42001 Control Mapping

## Objective

Map AI management system controls to technical implementation and evidence so audit readiness is measurable.

## Control Mapping Table

| Control Area | Where Implemented | Metric Proving It Runs | Evidence Location | Owner | Review Frequency | Status |
|---|---|---|---|---|---|---|
| AIMS scope and context | `docs/ai-governance/00-scope-and-system-boundaries.md` | Scope review completion % | `docs/ai-governance/00-scope-and-system-boundaries.md` | Compliance Lead | Quarterly | In progress |
| AI policy and objectives | `docs/compliance/eu-ai-act-policy.md` + governance docs | Policy acknowledgment rate | `docs/compliance/` | Security Officer | Quarterly | In progress |
| Risk assessment process | `docs/ai-governance/01-risk-classification.md` | % use cases classified | `docs/ai-governance/01-risk-classification.md` | AI Engineering Lead | Monthly | In progress |
| Control applicability matrix | This document | % controls with owner/evidence | `docs/ai-governance/02-control-mapping-iso42001.md` | Compliance Lead | Monthly | In progress |
| Human oversight | `backend/app/services/approval_service.py` | Approval latency, approval failure rate | `docs/ai-governance/06-human-oversight-and-approval.md` | Ops Lead | Weekly | Partial |
| Safety validation | `backend/app/services/approval_service.py` | Safety validation pass/fail rate | Approval logs + runbooks | AI Engineering Lead | Weekly | Gap |
| Operational monitoring | `backend/app/api/mlops.py` | Drift alerts, health score trend | `docs/ai-governance/08-monitoring-and-metrics.md` | MLOps Owner | Daily | Partial |
| Incident response and corrective actions | `docs/09-security/incident-response-policy.md` | MTTR, corrective action closure % | `docs/ai-governance/07-incident-and-rollback.md` | Security Officer | Monthly | Partial |
| Audit trail and traceability | `backend/app/middleware/audit_middleware.py` | Audit event completeness | `docs/ai-governance/evidence/audit-logs-samples/` | Security Engineering | Monthly | Partial |
| Competence and awareness | HR/security training artefacts | AI training completion % | `docs/ai-governance/evidence/training/` | HR + Compliance | Quarterly | Gap |
| Supplier and third-party AI risk | `docs/09-security/third-party-security-register.md` | Supplier risk review completion % | Third-party register | Security Officer | Quarterly | Partial |
| Continual improvement | TODO + governance reviews | % overdue AI governance actions | `TODO.md` + review logs | Governance Board | Monthly | In progress |

## Priority Gaps

- No finalized AI competence/training register with role-based evidence.
- No closed nonconformity/CAPA workflow specific to AI incidents.
- Safety validation placeholder path in approval flow still requires full enforcement.
- Monitoring evidence is split across logs and JSON APIs without Prometheus-grade control effectiveness metrics.

## Next Actions (90 Days)

- Create AIMS management review template and meeting cadence record.
- Create AI nonconformity and corrective action workflow with RCA template.
- Complete safety validation hardening in approval pipeline.
- Implement metrics evidence pipeline described in `docs/ai-governance/08-monitoring-and-metrics.md`.

---
title: "AI Governance Scope and System Boundaries"
type: "policy"
status: "approved"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
approved: "2026-02-23"
author: "SENTINEL Governance Team"
tags: ["ai-governance", "scope", "boundaries", "iso-42001", "nist-ai-rmf", "eu-ai-act"]
domain: "compliance"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# AI Governance Scope and System Boundaries

## Purpose

Define the formal boundary of the AI Management System (AIMS) so controls, risks, and evidence are consistently managed across all SENTINEL AI features. This document establishes what is governed, what is explicitly excluded, and the interfaces at which AIMS responsibility begins and ends.

## In Scope

The following components, services, and artifacts are governed by the AIMS:

- **AI-assisted recommendations and decision routing** in `backend/app/services/optimization_tier_router.py`
- **Approval and autonomous execution workflow** in `backend/app/services/approval_service.py`
- **AI monitoring and drift endpoints** in `backend/app/api/mlops.py`
- **AI chat and assistant user interfaces** in `frontend/src/components/`
- **Audit and security telemetry** tied to AI actions in `backend/app/middleware/audit_middleware.py`
- **Quality gate evaluation and enforcement** in `backend/app/services/quality_gate_evaluator.py` (14 metrics x 3 modes)
- **ML model registry and inference** in `backend/app/ml/` and `backend/app/database/repositories/`
- **Governance and compliance documentation** under `docs/ai-governance/` and `docs/compliance/`

## Exclusions

The following are explicitly **outside** the AIMS scope:

1. **Non-AI static dashboards** -- Pages and views that display sensor readings, floor plans, or historical charts without AI-generated content or recommendations.
2. **Third-party model internals** -- Where SENTINEL consumes outputs from external AI providers (e.g., Claude API for chat), only the integration interface, prompt design, and output handling are in scope. The internal workings of third-party models are managed as supplier risk only (see `docs/09-security/third-party-security-register.md`).
3. **Historical/archived features** -- Deprecated or decommissioned AI features that are no longer deployed or accessible to users.
4. **Physical BMS hardware** -- Physical controllers (Siemens Desigo, Honeywell, Johnson Controls), sensors, actuators, and network infrastructure are managed by the host BMS vendor. SENTINEL sends setpoints and commands via protocol interfaces; the host BMS executes them.

## Boundaries

### Organizational Boundary

The AIMS covers the SENTINEL development and operations team:

- **AI Engineering Lead** -- Model development, quality gates, tier routing, safety rules
- **Compliance Lead** -- Policy, audit, risk classification, regulatory alignment
- **Operations Lead** -- Deployment modes, incident response, BMS coordination
- **Security Lead** -- Access control, encryption, audit trail integrity, supplier risk

Stakeholders outside this team (building tenants, host BMS vendors, facilities management clients) interact with SENTINEL outputs but are not AIMS-governed roles.

### Technical Boundary

| Layer | In AIMS Scope | Interface Point |
|-------|---------------|-----------------|
| Backend services | `backend/app/services/`, `backend/app/ml/`, `backend/app/api/` | FastAPI endpoints |
| Frontend components | `frontend/src/components/` (AI-facing) | React UI |
| Data stores | Supabase, Redis cache, JSON fallback files | Database connections |
| Monitoring stack | MLOps endpoints, drift detection, health scoring | `/api/mlops/*` |
| Runner service | `runner/` (RLM analysis engine) | Port 8010 API contract |

### Data Boundary

| Data Category | Governed By AIMS | Retention |
|---------------|------------------|-----------|
| Ingestion data (BACnet/Modbus/DALI readings) | Yes -- from point of ingestion | Per data governance policy |
| Model outputs (recommendations, predictions) | Yes | 180 days minimum |
| Decision logs (PARASITE decisions, approvals) | Yes | 180 days minimum |
| Evidence artifacts (audit logs, drift reports) | Yes | Per compliance retention schedule |
| Operator/technician PII | Yes -- POPIA-governed | Per privacy policy |

### Interface Boundaries

SENTINEL communicates with host BMS systems through well-defined protocol interfaces:

| Protocol | Direction | AIMS Responsibility |
|----------|-----------|---------------------|
| BACnet IP | Bidirectional | SENTINEL sends setpoints; host BMS executes. AIMS governs the decision to send, not the execution. |
| Modbus TCP/RTU | Bidirectional | Same as BACnet -- SENTINEL commands, host BMS acts. |
| DALI-2 (via Tridonic) | Bidirectional | SENTINEL provides cross-system coordination and predictive maintenance. Tridonic handles native DALI capabilities (daylight harvesting, occupancy dimming). |
| HTTP/REST | Outbound | API calls to third-party services (Claude API, monitoring). Governed at integration interface. |

## Applicable Standards

This AIMS is designed to align with the following standards and frameworks:

| Standard | Applicability | Status |
|----------|---------------|--------|
| **ISO/IEC 42001:2023** | Primary AIMS framework -- clauses 4-10 mapped in `02-control-mapping-iso42001.md` | Active alignment |
| **NIST AI RMF 1.0** | Supplementary risk management framework -- mapped in `03-control-mapping-nist-airmf.md` | Active alignment |
| **EU AI Act** | Readiness obligations for potential EU deployment -- mapped in `04-eu-ai-act-readiness.md` | Readiness phase |
| **POPIA (South Africa)** | Data protection for operator/technician PII | Active compliance |
| **ISO/IEC 27001** | Information security management (referenced for security controls) | Informative reference |

## Intended Use

- Assist operators and technicians with recommendations, triage, diagnostics, and controlled automation.
- Optimize building performance while enforcing safety, compliance, and auditability.
- Provide evidence-based decision support across simulation, shadow, and live control modes.

## Prohibited Use

- Fully unsupervised critical actions outside approved control tiers
- Use of AI outputs as legal or safety authority without required human validation
- Any use case that violates prohibited-practice rules in internal EU AI Act policy
- Processing of personal data beyond the stated purpose without explicit consent
- Deployment in life-safety systems without independent safety certification

## Roles and Ownership

| Role | Responsibility | Named Position |
|------|---------------|----------------|
| **AIMS Owner** | Overall accountability for AI governance | Information Security Officer |
| **Technical Control Owner** | Model lifecycle, quality gates, safety rules | AI Engineering Lead |
| **Operational Owner** | Deployment modes, incident response, BMS coordination | Facilities Operations Lead |
| **Regulatory Owner** | Policy, audit, risk classification | Compliance Lead |

## Review Cadence

- **Annual formal review** -- Full scope reassessment, boundary validation, and sign-off renewal
- **Quarterly check** -- KPI review against AI Management Policy objectives (see `ai-management-policy.md`)
- **Triggered review** -- Required on:
  - Major architecture change (new AI feature, new deployment mode, new protocol)
  - AI-related incident at severity High or Critical
  - Regulatory change affecting AI governance obligations
  - Significant change in organizational structure or risk appetite

## Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Compliance Lead | _________________ | ____/____/________ | _________________ |
| AI Engineering Lead | _________________ | ____/____/________ | _________________ |
| Information Security Officer | _________________ | ____/____/________ | _________________ |

> **Note:** This document moves from `draft` to `approved` status upon completion of all signatures above. Digital signatures or documented email approvals are acceptable as evidence.

## Linked Artifacts

- `docs/ai-governance/ai-management-policy.md` -- Central AIMS policy with measurable objectives
- `docs/ai-governance/01-risk-classification.md` -- AI use-case risk register
- `docs/ai-governance/02-control-mapping-iso42001.md` -- ISO 42001 control mapping
- `docs/ai-governance/03-control-mapping-nist-airmf.md` -- NIST AI RMF mapping
- `docs/ai-governance/04-eu-ai-act-readiness.md` -- EU AI Act readiness assessment
- `docs/ai-governance/05-model-and-data-governance.md` -- Model cards and data sheets
- `docs/ai-governance/06-human-oversight-and-approval.md` -- Human oversight requirements
- `docs/ai-governance/07-incident-and-rollback.md` -- Incident response and rollback
- `docs/ai-governance/08-monitoring-and-metrics.md` -- Monitoring and metrics
- `docs/ai-governance/management-review-template.md` -- Quarterly review template
- `docs/ai-governance/nonconformity-capa-register.md` -- Nonconformity and CAPA register

## Document History

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 0.1.0 | 2026-02-23 | SENTINEL Governance Team | Initial draft |
| 1.0.0 | 2026-02-23 | SENTINEL Governance Team | Upgraded to approved: added Exclusions, Boundaries (organizational, technical, data, interface), Applicable Standards, Approval section, document history |

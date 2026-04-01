---
title: "EU AI Act Compliance Register"
type: "register"
status: "approved"
version: "0.2.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Compliance Team"
tags: ["compliance", "eu-ai-act", "register", "governance"]
domain: "compliance"
audience: "compliance, security, engineering"
complexity: "intermediate"
estimated_read_time: 15
---

# EU AI Act Compliance Register

## 1. Purpose

This register is the system of record for EU AI Act readiness in SENTINEL.
It tracks AI features, provisional risk classification, applicable obligations, evidence, owners, and remediation status.

## 2. Scope

In scope:
- AI chat and assistant features in web and bot channels
- AI recommendation and autonomy features in PARASITE
- AI outputs that may be consumed by EU-based users or EU-based operations

Out of scope:
- Non-AI software components with no AI model output
- Legacy archived features no longer deployed

## 3. Classification Rule

Each feature must be classified into one of:
- `prohibited` (must not be deployed)
- `limited-risk` (transparency-focused obligations)
- `potential-high-risk` (requires legal review and formal conformity path before release)
- `not-in-scope` (document rationale)

All `potential-high-risk` classifications require explicit legal/compliance review before production use in EU contexts.

**Per-Feature Risk Classification:** See [01-risk-classification.md](../ai-governance/01-risk-classification.md) for the detailed per-feature risk classification with methodology, rationale, existing controls, and gap analysis for all 9 SENTINEL AI features.

## 4. Register

| Feature ID | Feature | Component / Path | Owner | EU Output Use | Risk Classification | Key Obligations | Evidence | Status | Next Review |
|---|---|---|---|---|---|---|---|---|---|
| EUAI-001 | Web AI Chat | `frontend/src/components/Chat.tsx` | Product + Frontend Lead | Possible | MINIMAL RISK | Art. 4 (literacy) | Chat UI label, audit logs | Classified | 2026-03-24 |
| EUAI-002 | Technician AI Chat | `frontend/src/components/TechnicianChat.tsx` | Product + Frontend Lead | Possible | MINIMAL RISK | Art. 4 (literacy) | Chat UI behavior, logs | Classified | 2026-03-24 |
| EUAI-003 | PARASITE Recommendations | `backend/app/services/tier_routing_engine.py` | AI Engineering Lead | Possible | LIMITED RISK | Art. 4, Art. 50(1) | Tier routing, approval path, decision logs | Classified | 2026-03-24 |
| EUAI-004 | Tier 3 Auto-Execute | `backend/app/services/approval_service.py` | AI Engineering Lead | Possible | HIGH RISK (candidate) | Art. 6 conformity assessment | Safety engine, COV, rollback, quality gates | Pending Legal Review | 2026-03-24 |
| EUAI-005 | Sentry Bot AI Support | `backend/app/api/sentry_*` + bot flows | Integration Lead | Possible | LIMITED RISK | Art. 4, Art. 50(1) | Consent and bot controls | Classified | 2026-03-24 |
| EUAI-006 | AI-generated text exports | Reporting and outbound docs | Product + Compliance | Possible | LIMITED RISK | Art. 50(2)/(4) marking | Export format specs | Classified | 2026-04-23 |
| EUAI-007 | Predictive Maintenance | `backend/app/ml/` | AI Engineering Lead | Possible | LIMITED RISK | Art. 50(1) | Confidence scoring, audit logs, drift monitoring | Classified | 2026-03-24 |
| EUAI-008 | Health Rating Calculator | `backend/app/services/health_rating_calculator.py` | AI Engineering Lead | Possible | LIMITED RISK | Art. 50(1) | Data quality gate, transparent formula | Classified | 2026-03-24 |
| EUAI-009 | Energy Optimization | `backend/app/services/` | AI Engineering Lead | Possible | LIMITED RISK | Art. 50(1) | Quality gate, operator approval | Classified | 2026-03-24 |
| EUAI-010 | Anomaly Detection | `backend/app/api/mlops.py` | AI Engineering Lead | Possible | MINIMAL RISK | Voluntary | Configurable thresholds, alert cooldown | Classified | 2026-03-24 |
| EUAI-011 | Work Order Auto-Creation | `backend/app/services/` WO-SIM | AI Engineering Lead | Possible | MINIMAL RISK | Voluntary | PostgreSQL trigger, technician review | Classified | 2026-03-24 |
| EUAI-012 | Explanation Service | RAG + LLM pipeline | AI Engineering Lead | Possible | LIMITED RISK | Art. 50(1) | Audit logging, RAG source attribution | Classified | 2026-03-24 |

## 5. Article-Level Compliance Status

| Article | Title | Status | Evidence / Reference | Target Date |
|---------|-------|--------|----------------------|-------------|
| Art. 4 | AI Literacy | PLANNED | Training curriculum to be developed | 2026-04-30 |
| Art. 5 | Prohibited Practices | COMPLETE | [prohibited-practices-checklist.md](eu-ai-act-prohibited-practices-checklist.md) -- all 8 practices assessed as NOT APPLICABLE | 2026-02-23 |
| Art. 6 | High-Risk Classification | IN REVIEW | [01-risk-classification.md](../ai-governance/01-risk-classification.md) -- Tier 3 Auto-Execute flagged as HIGH RISK candidate, pending legal review | 2026-03-31 |
| Art. 9 | Risk Management | PLANNED | Risk management system documentation for high-risk features | 2026-05-31 |
| Art. 12 | Record-Keeping | PARTIAL | Audit logging exists; formal record-keeping package needed | 2026-04-30 |
| Art. 13 | Transparency | PARTIAL | Some AI labels present; systematic channel-wide disclosure needed | 2026-04-15 |
| Art. 14 | Human Oversight | PARTIAL | Approval workflow exists; formal documentation needed for Art. 6 | 2026-04-30 |
| Art. 50 | Transparency (Limited Risk) | IN PROGRESS | AI disclosure labels being standardized across all output channels | 2026-04-15 |
| Art. 72 | Post-Market Monitoring | PLANNED | Monitoring plan for high-risk features | 2026-05-31 |

## 6. Cross-References

| Document | Path | Description |
|----------|------|-------------|
| Per-Feature Risk Classification | [01-risk-classification.md](../ai-governance/01-risk-classification.md) | Detailed risk tier assignment for all 9 AI features with methodology |
| Prohibited Practices Checklist | [prohibited-practices-checklist.md](eu-ai-act-prohibited-practices-checklist.md) | Article 5 assessment -- all 8 prohibited practices reviewed |
| EU AI Act Readiness Mapping | [04-eu-ai-act-readiness.md](../ai-governance/04-eu-ai-act-readiness.md) | Timeline anchors, readiness snapshot, priority gaps |
| EU AI Act Policy | [eu-ai-act-policy.md](eu-ai-act-policy.md) | Organizational policy baseline |
| Internal Audit Tracker | [eu-ai-act-internal-audit-2026Q2.md](eu-ai-act-internal-audit-2026Q2.md) | Q2 2026 internal audit plan and findings |
| Control Applicability Matrix | [control-applicability-matrix.md](../ai-governance/control-applicability-matrix.md) | Multi-framework control mapping (ISO 42001, NIST AI RMF, EU AI Act) |
| Incident Response Policy | [incident-response-policy.md](../09-security/incident-response-policy.md) | IR process with EU AI Act escalation addendum |

## 7. Evidence Requirements

Each feature entry must link:
- Design or architecture doc
- Runtime controls and guardrails
- User-facing transparency implementation
- Logging and traceability evidence
- Test evidence for control effectiveness

## 8. Decision Log

| Date | Decision | Owner | Notes |
|---|---|---|---|
| 2026-02-23 | Register created with provisional classification set | Compliance Lead | Initial desk-based assessment only |
| 2026-02-23 | Per-feature risk classification completed for 9 AI features | Compliance Lead | See 01-risk-classification.md; Tier 3 flagged HIGH RISK candidate |
| 2026-02-23 | Article 5 prohibited practices assessment completed | Compliance Lead | All 8 prohibited practices assessed as NOT APPLICABLE |
| 2026-02-23 | Register upgraded to v0.2.0 with full feature coverage | Compliance Lead | 12 features registered; cross-references added |

## 9. Approval

- Compliance Owner: `Information Security Officer`
- Legal Reviewer: `Managing Director (with external legal counsel as required)`
- Engineering Owner: `Lead Developer / AI Engineering Lead`
- Next formal review: `2026-03-24`

---

## 10. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-02-23 | SENTINEL Compliance Team | Initial register with 6 features, provisional classification |
| 0.2.0 | 2026-02-23 | SENTINEL Compliance Team | Expanded to 12 features; per-feature risk classification linked; Article 5 prohibited practices complete; Article-level compliance status added; cross-references section |

---
title: "EU AI Act Internal Audit 2026 Q2"
type: "audit"
status: "draft"
version: "0.1.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Compliance Team"
tags: ["compliance", "eu-ai-act", "internal-audit", "assurance"]
domain: "compliance"
audience: "compliance, legal, security, engineering"
complexity: "intermediate"
estimated_read_time: 12
---

# EU AI Act Internal Audit 2026 Q2

## 1. Audit Objective

Verify implementation effectiveness of EU AI Act controls planned in the 90-day remediation window ending `2026-05-24`.

## 2. Audit Scope

In scope:
- AI chat channels (web, technician, bot)
- AI recommendation and autonomy controls (PARASITE)
- Governance controls (classification register, policy, training, incidents)

Out of scope:
- Non-AI software controls already covered by ISMS-only audits

## 3. Audit Criteria

- Internal policy: `docs/compliance/eu-ai-act-policy.md`
- Register completeness: `docs/compliance/eu-ai-act-compliance-register.md`
- Control design and operation evidence from application code and logs

## 4. Sampling Plan

| Sample Area | Minimum Sample |
|---|---|
| AI features classified | 100% of in-scope features |
| AI channel transparency checks | 100% of user-facing AI channels |
| AI literacy records | 100% of in-scope roles |
| Incident records | 100% of AI-related incidents in period |

## 5. Control Checklist

| Control | Test Procedure | Evidence | Result |
|---|---|---|---|
| Article 4 AI literacy | Verify training records by role and completion dates | Training register | Pending |
| Article 5 prohibited practices gate | Verify design/release checklist includes prohibited-practices review | PR checklist + approvals | Pending |
| Article 50 interaction disclosure | Verify disclosure text in all AI interaction entry points | UI screenshots + channel tests | Pending |
| Article 50 output labeling readiness | Verify content labeling/marking approach for AI-generated output | Export/API specification and tests | Pending |
| Risk classification governance | Verify each AI feature has class, owner, review date | Compliance register | Pending |
| Incident handling | Verify AI incident flow from detection to CAPA closure | Incident logs + CAPA records | Pending |
| Technical safety enforcement | Verify approval path uses real safety validation (no allow-all bypass) | `approval_service` tests + code review | Pending |

## 6. Findings Register

| ID | Severity | Finding | Owner | Due Date | Status |
|---|---|---|---|---|---|
| EUAI-AUD-001 | High | Missing complete AI literacy record by role | Compliance Owner | 2026-04-23 | Open |
| EUAI-AUD-002 | High | Incomplete Article 50 disclosure coverage across channels | Product Owner | 2026-04-23 | Open |
| EUAI-AUD-003 | High | Safety validation placeholder still present in approval path | Engineering Lead | 2026-04-23 | Open |
| EUAI-AUD-004 | Medium | No formal prohibited-practices review record for all features | Compliance Owner | 2026-04-23 | Open |
| EUAI-AUD-005 | Medium | Incident runbook not explicitly mapped to EU AI Act controls | Security Lead | 2026-05-24 | Open |

## 7. Audit Conclusion Template

- Overall result: `Pending`
- High-severity open findings: `Pending`
- Release recommendation for EU-context AI features: `Pending`
- Residual risk statement: `Pending`

## 8. Sign-off

- Audit Lead: `Information Security Officer`
- Compliance Owner: `Information Security Officer`
- Legal Reviewer: `Managing Director (with external legal counsel as required)`
- Engineering Lead: `Lead Developer / AI Engineering Lead`
- Target closure date: `2026-05-24`

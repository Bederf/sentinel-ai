---
title: "AI Incident and Rollback Governance"
type: "guide"
status: "draft"
version: "0.1.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
tags: ["ai-governance", "incident-response", "rollback", "resilience"]
domain: "compliance"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# AI Incident and Rollback Governance

## Scope

This runbook addendum covers AI-specific incidents: unsafe recommendations, erroneous autonomous actions, model drift failures, and observability/control outages.

## Incident Severity

| Severity | Example | Mandatory Response |
|---|---|---|
| Low | Incorrect advisory text, no action executed | Ticket + review in next governance cycle |
| Medium | Approval workflow malfunction, delayed detection | Same-day triage, corrective action owner assigned |
| High | Unsafe execution attempt blocked by controls | Immediate incident response, formal RCA |
| Critical | Unsafe execution reached field action or legal trigger | Immediate rollback/kill switch, executive/legal escalation |

## Mandatory Response Steps

1. Contain: disable affected automation path or downgrade mode.
2. Preserve evidence: logs, metrics snapshots, correlation IDs, approvals.
3. Assess impact: safety, operations, financial, regulatory.
4. Recover: rollback model/prompt/config and verify control health.
5. Correct: root cause analysis and corrective/preventive action.

## Evidence to Archive

- `docs/ai-governance/evidence/audit-logs-samples/`
- `docs/ai-governance/evidence/rca-postmortems/`
- `docs/ai-governance/evidence/drift-reports/`

## Linked Policies

- `docs/09-security/incident-response-policy.md`
- `docs/compliance/eu-ai-act-policy.md`

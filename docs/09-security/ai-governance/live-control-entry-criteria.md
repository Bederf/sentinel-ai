---
title: "Live-Control Entry Criteria Checklist"
type: "checklist"
status: "active"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
tags: ["ai-governance", "live-control", "entry-criteria", "quality-gate", "checklist"]
domain: "compliance"
audience: "all"
complexity: "advanced"
estimated_read_time: 10
---

# Live-Control Entry Criteria Checklist

## 1. Purpose

This document defines the mandatory criteria that must be satisfied before any SENTINEL AI feature may transition from `shadow_live` mode to `live_control` (automatic) mode. No feature may enter `live_control` without documented evidence that every criterion in this checklist has been met.

This checklist implements the mode discipline requirements defined in the [`ai-management-policy.md`](ai-management-policy.md) (Section 3.3) and the quality gate enforcement described in [`08-monitoring-and-metrics.md`](08-monitoring-and-metrics.md).

### 1.1 Relationship to Other Documents

| Document | Relationship |
|----------|-------------|
| [`ai-management-policy.md`](ai-management-policy.md) | Policy requiring mode discipline and phased rollout |
| [`08-monitoring-and-metrics.md`](08-monitoring-and-metrics.md) | KPI definitions and monitoring thresholds |
| [`01-risk-classification.md`](01-risk-classification.md) | Risk classification that determines which features require this checklist |
| [`06-human-oversight-and-approval.md`](06-human-oversight-and-approval.md) | Oversight model that live_control modifies |
| [`competence-training-register.md`](competence-training-register.md) | Training completion evidence referenced in criterion 5 |

---

## 2. Entry Criteria Checklist

Each criterion must be satisfied and evidenced before sign-off. The "Evidence Required" column specifies what artifact must be collected.

### 2.1 Quality Gate Performance

| # | Criterion | Threshold | Evidence Required |
|---|-----------|-----------|-------------------|
| 1 | Quality gate pass rate in `shadow_live` | >= 99% for 30 consecutive days | Quality gate dashboard export or log query showing daily pass rates for the 30-day window |
| 2 | Zero safety violations in `shadow_live` | 0 safety interlock triggers for 30 consecutive days | Safety violation log filtered to the feature scope for the 30-day window |
| 3 | Model drift alerts resolved | No active critical drift alerts at time of sign-off | Drift monitoring dashboard screenshot or alert log showing all critical alerts resolved |
| 4 | Feedback capture rate in `shadow_live` | >= 97% for the 30-day evaluation period | MLOps health report showing `feedback_capture_rate_7d_pct` >= 97% across all weeks |

### 2.2 Personnel Readiness

| # | Criterion | Threshold | Evidence Required |
|---|-----------|-----------|-------------------|
| 5 | All in-scope personnel completed AI literacy training | 100% completion per [`competence-training-register.md`](competence-training-register.md) | Training register showing all in-scope roles trained and assessed |
| 6 | Operator residual risk disclosure acknowledged | All operators who will interact with `live_control` features have signed the residual risk disclosure | Signed acknowledgement records per [`residual-risk-disclosure.md`](residual-risk-disclosure.md) |

### 2.3 Governance Approval

| # | Criterion | Threshold | Evidence Required |
|---|-----------|-----------|-------------------|
| 7 | Architecture Board approval recorded | Formal approval decision documented | Meeting minutes or approval record with attendees, decision, and date |
| 8 | Risk classification reviewed and current | Feature risk classification reviewed within 30 days of sign-off | Updated risk classification entry in [`01-risk-classification.md`](01-risk-classification.md) with review date |

### 2.4 Operational Readiness

| # | Criterion | Threshold | Evidence Required |
|---|-----------|-----------|-------------------|
| 9 | Incident response runbook tested | Tabletop exercise completed for AI-specific incident scenario | Tabletop exercise report with participants, scenario, findings, and action items |
| 10 | Rollback procedure tested and documented | Rollback from `live_control` to `shadow_live` tested successfully | Rollback test report showing procedure, execution time, and confirmation of clean reversion |
| 11 | Kill switch functionality verified | Equipment-level, site-level, and global kill switches tested | Kill switch test log with timestamps and confirmation of AI disengagement |
| 12 | Monitoring and alerting configured | All 14 quality gate metrics have active alerting with appropriate thresholds | Alerting configuration export or screenshot showing metric coverage |

---

## 3. Evidence Pack Requirements

Before sign-off, the following evidence pack must be assembled and stored in `docs/ai-governance/evidence/live-control-entry/`:

| # | Artifact | Format | Retention |
|---|----------|--------|-----------|
| 1 | Quality gate 30-day report | PDF or markdown export | 5 years |
| 2 | Safety violation log (30-day window) | CSV or log export | 5 years |
| 3 | Drift alert resolution record | Screenshot or log export | 5 years |
| 4 | Feedback capture rate report | MLOps health export | 5 years |
| 5 | Training completion summary | Register extract | 5 years |
| 6 | Residual risk acknowledgements | Signed records | 5 years |
| 7 | Architecture Board approval record | Meeting minutes | 5 years |
| 8 | Risk classification review record | Register entry with date | 5 years |
| 9 | Tabletop exercise report | Markdown report | 5 years |
| 10 | Rollback test report | Markdown report | 5 years |
| 11 | Kill switch test log | Test execution record | 5 years |
| 12 | Alerting configuration evidence | Screenshot or config export | 5 years |

---

## 4. Approval Authority

Transition to `live_control` requires **joint sign-off** from both:

1. **AI Engineering Lead** -- Confirms technical readiness (criteria 1-4, 10-12)
2. **Compliance Lead** -- Confirms governance and personnel readiness (criteria 5-9)

Neither party may sign off alone. If either party identifies an unresolved issue, the transition is blocked until the issue is resolved.

### 4.1 Sign-Off Record

```
-----------------------------------------------------------------
LIVE-CONTROL ENTRY -- SIGN-OFF RECORD
-----------------------------------------------------------------

Feature:             ___________________________________
Site:                ___________________________________
Date:                ___________________________________

Evaluation Period:   From ______________ to ______________

Criteria Assessment:
  [ ] 1. Quality gate pass rate >= 99% (30 days)
  [ ] 2. Zero safety violations (30 days)
  [ ] 3. Model drift alerts resolved
  [ ] 4. Feedback capture rate >= 97%
  [ ] 5. AI literacy training 100% complete
  [ ] 6. Residual risk disclosures acknowledged
  [ ] 7. Architecture Board approval recorded
  [ ] 8. Risk classification reviewed and current
  [ ] 9. Incident response tabletop completed
  [ ] 10. Rollback procedure tested
  [ ] 11. Kill switch functionality verified
  [ ] 12. Monitoring and alerting configured

Evidence Pack Location: ________________________________

Decision:  [ ] APPROVED for live_control
           [ ] DEFERRED -- reason: ______________________

AI Engineering Lead:
  Name:       ___________________________________
  Signature:  ___________________________________
  Date:       ___________________________________

Compliance Lead:
  Name:       ___________________________________
  Signature:  ___________________________________
  Date:       ___________________________________

-----------------------------------------------------------------
```

---

## 5. Post-Entry Monitoring

After entering `live_control`, the following ongoing obligations apply:

| Obligation | Frequency | Owner |
|-----------|-----------|-------|
| Quality gate metric review | Weekly | AI Engineering Lead |
| Safety violation audit | Weekly | Compliance Officer |
| Model drift assessment | Daily (automated) | MLOps pipeline |
| Feedback capture rate check | Weekly | AI Engineering Lead |
| Training refresh compliance | Quarterly | Compliance Officer |
| Full re-evaluation against this checklist | Annual or on material change | AI Engineering Lead + Compliance Lead |

If any criterion falls below its threshold after entering `live_control`, the system must be reverted to `shadow_live` until the criterion is restored. This reversion is automatic for criteria 1-4 (enforced by the quality gate evaluator) and manual for criteria 5-12.

---

## 6. Document Control

| Field | Value |
|-------|-------|
| **Document owner** | AI Engineering Lead |
| **Review cycle** | Annual or on material change to quality gate policy |
| **Approval authority** | AI Engineering Lead + Compliance Lead |
| **Classification** | Internal |

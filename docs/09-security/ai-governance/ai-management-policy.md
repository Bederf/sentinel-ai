---
title: "AI Management Policy"
type: "policy"
status: "approved"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
approved: "2026-02-23"
author: "SENTINEL Governance Team"
tags: ["ai-governance", "policy", "iso-42001", "kpi", "aims"]
domain: "compliance"
audience: "all"
complexity: "intermediate"
estimated_read_time: 12
---

# AI Management Policy

## 1. Purpose

This policy establishes the governance framework for all AI systems within the SENTINEL BMS Intelligence Platform. It defines mandatory requirements for risk classification, model governance, deployment discipline, quality assurance, human oversight, auditability, and incident response.

The policy ensures that AI features are developed, deployed, and operated in a manner that is safe, transparent, accountable, and aligned with organizational values and regulatory obligations.

## 2. Scope

This policy applies to all AI systems, models, prompts, and automated decision-making features within the AIMS boundary defined in [`00-scope-and-system-boundaries.md`](00-scope-and-system-boundaries.md).

For a detailed description of what is in scope, excluded, and the system boundaries, refer to the approved scope document.

## 3. Policy Statements

### 3.1 Risk Classification Before Deployment

All AI features **must** be risk-classified before deployment to any environment. Each use case is assessed across impact severity, automation level, user exposure, and regulatory sensitivity.

- Risk classifications are recorded in the AI Risk Classification Register ([`01-risk-classification.md`](01-risk-classification.md))
- No AI feature may enter `shadow_live` or `live_control` mode without a completed risk classification record
- Risk classifications must be reviewed when the feature scope, automation level, or data sources change

### 3.2 Model Cards Before Production Use

Every model deployed in production **must** have a completed model card documenting its purpose, training data, evaluation metrics, known limitations, and safety considerations.

- Model card requirements are defined in [`05-model-and-data-governance.md`](05-model-and-data-governance.md)
- Model cards are stored in `docs/ai-governance/evidence/model-cards/`
- Model card updates are required on every material change to model architecture, training data, or deployment scope

### 3.3 Mode Discipline

All AI features follow a strict deployment progression:

```
simulation --> shadow_live --> supervised --> automatic (live_control)
```

- **Simulation**: Full pipeline runs against simulated data. No real device interaction.
- **Shadow_live**: Full pipeline runs against live data. No device writes. Outputs logged for comparison.
- **Supervised**: Recommendations presented to operators for manual approval before execution.
- **Automatic (live_control)**: Approved tiers execute within quality gates and safety rules.

Detailed mode-by-mode write policies and rollout checklists are defined in [`write-policy-and-rollout.md`](../08-ai-ml/write-policy-and-rollout.md).

### 3.4 Quality Gate Enforcement

Quality gates **must** pass before live_control activation. The quality gate evaluates 14 metrics across 3 operational modes (simulation, shadow_live, live_control):

- **PASS**: Full pipeline including approved automation tiers
- **WARN**: Tier 3 suppressed, approval queue active
- **FAIL**: All device writes blocked (fail-closed)

In `live_control` mode, any metric with state `NA` is treated as `FAIL` (fail-closed for missing signals).

### 3.5 Human Oversight for Tier 2+ Recommendations

All Tier 2 and above recommendations **require** human oversight:

- **Tier 1** (advisory): Logged, no action required
- **Tier 2** (approval-gated): Requires explicit operator approval before execution
- **Tier 3** (controlled autonomy): Executes only when quality gate is PASS, safety rules pass, and risk classification permits

Human oversight requirements are detailed in [`06-human-oversight-and-approval.md`](06-human-oversight-and-approval.md).

### 3.6 Audit Trail for All AI Decisions

Every AI decision **must** be audited with a correlation ID enabling full traceability:

- Decision records include: mode, site_id, device_id, point_name, proposed_value, current_value, rule IDs hit, gate snapshot ID
- Stored in `parasite_decisions` table and `audit_log`
- Retention: minimum 180 days
- Encryption at rest for audit log integrity (Fernet AES-128-CBC + HMAC-SHA256)

### 3.7 AI-Specific Incident Response

Incident response procedures include AI-specific escalation paths for unsafe recommendations, erroneous autonomous actions, model drift failures, and observability outages.

- Incident severity levels and mandatory response steps defined in [`07-incident-and-rollback.md`](07-incident-and-rollback.md)
- Kill switches available at global, per-site, and per-equipment granularity
- Mean time to rollback target: under 5 minutes

## 4. Measurable Objectives / KPIs

The following Key Performance Indicators are monitored to measure AIMS effectiveness. These KPIs map directly to existing quality gate metrics and operational telemetry.

| KPI ID | Objective | Metric | Target (shadow_live) | Target (live_control) | Source | Review Frequency |
|--------|-----------|--------|----------------------|-----------------------|--------|-----------------|
| KPI-01 | Quality gate reliability | Quality gate pass rate | >= 95% | >= 99% | `quality_gate_evaluator.py` | Weekly |
| KPI-02 | Recommendation effectiveness | Recommendation acceptance rate | >= 70% | >= 80% | `ml_feedback_records` | Monthly |
| KPI-03 | Model stability | Drift critical alerts (24h window) | <= 2 | 0 | `mlops.py` drift endpoint | Daily |
| KPI-04 | Feedback loop health | Feedback capture rate (7-day) | >= 90% | >= 97% | `feedback_capture_rate_7d_pct` | Weekly |
| KPI-05 | Safety compliance | Safety violation count per quarter | 0 | 0 | Safety boundary scanner | Quarterly |
| KPI-06 | Audit completeness | AI decisions with complete audit trail | >= 95% | 100% | `audit_middleware.py` | Monthly |
| KPI-07 | Incident response speed | Mean time to rollback | < 10 min | < 5 min | Incident response logs | Per incident |

### KPI Measurement Rules

- KPIs are calculated from production telemetry, not self-reported estimates
- If a KPI cannot be measured (source unavailable), it is treated as a nonconformity
- KPI trends (improving/stable/degrading) are reported at each quarterly management review
- Targets may be adjusted through the management review process with documented rationale

## 5. Roles and Responsibilities

### 5.1 AI Engineering Lead

- Owns model lifecycle from development through production
- Maintains quality gate thresholds and tier routing logic
- Ensures model cards are completed and current
- Provides technical input to risk classifications
- Reports KPI-01, KPI-02, KPI-03, KPI-04 at management reviews

### 5.2 Compliance Lead

- Owns AIMS documentation and policy maintenance
- Leads risk classification reviews
- Manages nonconformity and CAPA register
- Coordinates audit preparation and evidence collection
- Reports KPI-05, KPI-06 at management reviews

### 5.3 Operations Lead

- Owns deployment mode transitions (simulation to live_control)
- Manages kill switch activation and incident containment
- Coordinates with host BMS vendors on interface boundaries
- Reports KPI-07 at management reviews

### 5.4 Security Lead

- Owns audit trail integrity and encryption controls
- Manages third-party AI supplier risk assessments
- Reviews access control for AI administrative functions
- Provides security input to incident response

## 6. Compliance and Enforcement

### 6.1 Policy Violations

Violations of this policy are handled through the nonconformity and corrective action process documented in [`nonconformity-capa-register.md`](nonconformity-capa-register.md).

### 6.2 Exceptions

Temporary exceptions to policy requirements must be:
- Documented with justification and risk acceptance
- Approved by the AIMS Owner (Information Security Officer)
- Time-limited (maximum 90 days)
- Tracked in the CAPA register with a remediation plan

## 7. Review and Approval

### 7.1 Review Schedule

| Review Type | Frequency | Participants | Output |
|-------------|-----------|--------------|--------|
| **KPI review** | Monthly | AI Engineering Lead, Compliance Lead | KPI dashboard update |
| **Management review** | Quarterly | All role owners + AIMS Owner | Management review record (see [`management-review-template.md`](management-review-template.md)) |
| **Formal policy review** | Annual | All role owners + AIMS Owner + executive sponsor | Updated policy version |
| **Triggered review** | As needed | Relevant role owners | Amendment or exception record |

### 7.2 Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| AIMS Owner (ISO) | _________________ | ____/____/________ | _________________ |
| AI Engineering Lead | _________________ | ____/____/________ | _________________ |
| Compliance Lead | _________________ | ____/____/________ | _________________ |
| Operations Lead | _________________ | ____/____/________ | _________________ |

> **Note:** This policy is effective upon signature by the AIMS Owner. All role owners must acknowledge the policy within 30 days of approval.

## Related Documents

- [`00-scope-and-system-boundaries.md`](00-scope-and-system-boundaries.md) -- AIMS scope and boundaries
- [`01-risk-classification.md`](01-risk-classification.md) -- AI risk classification register
- [`02-control-mapping-iso42001.md`](02-control-mapping-iso42001.md) -- ISO 42001 control mapping
- [`03-control-mapping-nist-airmf.md`](03-control-mapping-nist-airmf.md) -- NIST AI RMF mapping
- [`04-eu-ai-act-readiness.md`](04-eu-ai-act-readiness.md) -- EU AI Act readiness
- [`05-model-and-data-governance.md`](05-model-and-data-governance.md) -- Model and data governance
- [`06-human-oversight-and-approval.md`](06-human-oversight-and-approval.md) -- Human oversight
- [`07-incident-and-rollback.md`](07-incident-and-rollback.md) -- Incident response and rollback
- [`08-monitoring-and-metrics.md`](08-monitoring-and-metrics.md) -- Monitoring and metrics
- [`management-review-template.md`](management-review-template.md) -- Quarterly review template
- [`nonconformity-capa-register.md`](nonconformity-capa-register.md) -- CAPA register
- [`../08-ai-ml/write-policy-and-rollout.md`](../08-ai-ml/write-policy-and-rollout.md) -- Mode-by-mode write policy

## Document History

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 1.0.0 | 2026-02-23 | SENTINEL Governance Team | Initial approved version with 7 measurable KPIs, 7 policy statements, 4 role definitions, and review cadence |

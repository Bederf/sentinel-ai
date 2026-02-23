---
title: "Nonconformity and Corrective Action (CAPA) Register"
type: "register"
status: "active"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
tags: ["ai-governance", "nonconformity", "capa", "corrective-action", "iso-42001"]
domain: "compliance"
audience: "management"
complexity: "intermediate"
estimated_read_time: 6
---

# Nonconformity and Corrective Action (CAPA) Register

## Purpose

Track nonconformities identified in the AI Management System (AIMS), their root causes, corrective actions, and closure evidence. This register supports ISO 42001 clause 10.1 (Nonconformity and corrective action) and feeds into the quarterly management review.

## How to Use This Register

1. **Raise a nonconformity** when a gap, failure, or deviation from AIMS policy is identified
2. **Assign an owner** responsible for root cause analysis and corrective action
3. **Set a due date** based on severity (critical: 30 days, major: 60 days, minor: 90 days)
4. **Document root cause** using appropriate analysis method (5 Whys, fishbone, etc.)
5. **Implement corrective action** and record evidence of completion
6. **Verify effectiveness** at the next management review -- confirm the nonconformity did not recur
7. **Close** with evidence reference when corrective action is verified effective

## Severity Definitions

| Severity | Definition | Response Time |
|----------|-----------|---------------|
| **Critical** | Nonconformity that could lead to unsafe AI behavior, data breach, or regulatory violation | 30 days |
| **Major** | Nonconformity that materially weakens a control or creates audit risk | 60 days |
| **Minor** | Nonconformity that is a documentation gap or process improvement opportunity | 90 days |

## CAPA Register

| NC-ID | Date Raised | Severity | Description | Root Cause | Corrective Action | Owner | Due Date | Status | Closure Evidence |
|-------|-------------|----------|-------------|------------|-------------------|-------|----------|--------|------------------|
| NC-001 | 2026-02-23 | Major | Model cards not yet completed for active models. Six models (AHU, CHILLER, FCU, UPS, GENERATOR, DALI) are in the ML model registry without completed model cards as required by AI Management Policy section 3.2. | Model card template and process established but not yet executed for existing models that pre-date the governance framework. | Complete model cards for all 6 active models using the template in `05-model-and-data-governance.md`. Populate from existing model metadata in `ml_models` table and `model_thresholds`. | AI Engineering Lead | 2026-04-15 | Open | |
| NC-002 | 2026-02-23 | Major | Fairness/bias baseline analysis not performed. No formal bias assessment exists for any AI use case, as required for potential-high-risk classifications (RISK-004) and EU AI Act readiness. | Fairness analysis was not part of the original development process. Framework for bias assessment not yet defined. | Define fairness metrics relevant to BMS domain (e.g., equitable comfort optimization across zones, unbiased equipment prioritization). Perform baseline assessment for RISK-004 (Tier 3 execution) first. | Compliance Lead | 2026-05-06 | CLOSED | `docs/ai-governance/fairness-bias-baseline.md` -- Fairness/bias baseline assessment completed 2026-02-23. Covers all 6 models, 4 equity dimensions, data bias assessment, baseline metrics. Model cards (CHILLER, AHU, FCU) updated with fairness sections. Verified by: ML Lead (pending signature). |
| NC-003 | 2026-02-23 | Minor | Residual risk disclosure not published for operators. Operators using AI features do not receive a formal disclosure of known AI limitations, residual risks, and appropriate reliance levels. | Risk classification register documents gaps internally but no operator-facing disclosure artifact has been created. | Create operator-facing residual risk disclosure document covering each AI use case. Integrate disclosure into onboarding and feature documentation. Publish at `docs/ai-governance/evidence/risk-disclosures/`. | Operations Lead | 2026-05-13 | Open | |

## Summary Statistics

| Metric | Value |
|--------|-------|
| Total nonconformities raised | 3 |
| Open | 2 |
| In Progress | 0 |
| Closed | 1 |
| Overdue | 0 |
| Critical | 0 |
| Major | 2 |
| Minor | 1 |

## Source of Nonconformities

These initial nonconformities were identified from the gap analysis documented in:

- [`02-control-mapping-iso42001.md`](02-control-mapping-iso42001.md) -- Priority Gaps section
- [`01-risk-classification.md`](01-risk-classification.md) -- Immediate Gaps section
- [`04-eu-ai-act-readiness.md`](04-eu-ai-act-readiness.md) -- Readiness obligations

## Review History

| Review Date | Reviewer | NCs Reviewed | Actions Taken |
|-------------|----------|-------------|---------------|
| 2026-02-23 | SENTINEL Governance Team | NC-001, NC-002, NC-003 | Initial register creation with pre-populated gaps from compliance analysis |

## Document History

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 1.0.0 | 2026-02-23 | SENTINEL Governance Team | Initial register with 3 pre-populated nonconformities from gap analysis |
| 1.1.0 | 2026-02-23 | SENTINEL Governance Team | NC-002 closed: fairness/bias baseline assessment completed |

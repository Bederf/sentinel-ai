---
title: "Nonconformity and Corrective Action (CAPA) Register"
type: "register"
status: "active"
version: "1.4.0"
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
| NC-001 | 2026-02-23 | Major | Model cards not yet completed for active models. Six models (AHU, CHILLER, FCU, UPS, GENERATOR, DALI) are in the ML model registry without completed model cards as required by AI Management Policy section 3.2. | Model card template and process established but not yet executed for existing models that pre-date the governance framework. | Complete model cards for all 6 active models using the template in `05-model-and-data-governance.md`. Populate from existing model metadata in `ml_models` table and `model_thresholds`. | AI Engineering Lead | 2026-04-15 | CLOSED | `docs/ai-governance/model-cards/` -- All 6 model cards completed 2026-02-23 (AHU, CHILLER, FCU, UPS, GENERATOR, DALI). Fairness sections added to CHILLER, AHU, FCU cards. Verified by: AI Engineering Lead (pending signature). |
| NC-002 | 2026-02-23 | Major | Fairness/bias baseline analysis not performed. No formal bias assessment exists for any AI use case, as required for potential-high-risk classifications (RISK-004) and EU AI Act readiness. | Fairness analysis was not part of the original development process. Framework for bias assessment not yet defined. | Define fairness metrics relevant to BMS domain (e.g., equitable comfort optimization across zones, unbiased equipment prioritization). Perform baseline assessment for RISK-004 (Tier 3 execution) first. | Compliance Lead | 2026-05-06 | CLOSED | `docs/ai-governance/fairness-bias-baseline.md` -- Fairness/bias baseline assessment completed 2026-02-23. Covers all 6 models, 4 equity dimensions, data bias assessment, baseline metrics. Model cards (CHILLER, AHU, FCU) updated with fairness sections. Verified by: ML Lead (pending signature). |
| NC-003 | 2026-02-23 | Minor | Residual risk disclosure not published for operators. Operators using AI features do not receive a formal disclosure of known AI limitations, residual risks, and appropriate reliance levels. | Risk classification register documents gaps internally but no operator-facing disclosure artifact has been created. | Create operator-facing residual risk disclosure document covering each AI use case. Integrate disclosure into onboarding and feature documentation. Publish at `docs/ai-governance/evidence/risk-disclosures/`. | Operations Lead | 2026-05-13 | CLOSED | `docs/ai-governance/residual-risk-disclosure.md` -- Residual risk disclosure completed 2026-02-23. Covers all 10 AI use cases (RISK-001 through RISK-010), residual risk levels, operator guidance, and appropriate reliance levels. Verified by: Operations Lead (pending signature). |
| NC-004 | 2026-02-23 | Major | Tabletop exercise (TABLETOP-001) identified 5 actions requiring corrective measures. Key findings: (1) No automated model rollback -- rollback is manual via database update. (2) Training data pipeline lacks automated sensor health validation, allowing corrupted data into retraining. (3) Incident response process lacks AI-specific playbook section. (4) Tier routing does not detect high-confidence wrong predictions. (5) No model rollback duration metric in Prometheus. | Tabletop exercise revealed gaps in automation and incident procedures that were not apparent from documentation review alone. The platform's shadow-mode posture masked the absence of operational automation. | Implement the 5 tabletop actions: (1) Automate model rollback CLI/API endpoint (Action 1). (2) Add training data validation gate with sensor health checks (Action 4, Critical). (3) Update incident response process with AI-specific playbook (Action 3). (4) Investigate prediction consistency checks for tier routing (Action 5). (5) Add rollback duration histogram metric (Action 2). | AI Engineering Lead | 2026-04-15 | OPEN | Action 3 CLOSED 2026-02-23: AI Model Incident Playbook added to `docs/09-security/incident-response-process.md` Section 10.4 (v1.1). Covers model rollback procedure, training data quarantine, quality gate verification, post-incident AI review. 4 actions remain open (1, 2, 4, 5) with assigned owners and due dates. Action 4 (training data validation) is Critical priority. Ref: `docs/ai-governance/incident-tabletop-report.md` Section 6. |
| NC-005 | 2026-02-23 | Minor | NIST AI RMF control-effectiveness review identified 3 Partially Effective controls: (1) GV 6.1 -- Grafana dashboards not configured for governance metrics; alert routing not wired to live notification channel. (2) MS 2.11 -- Only 1 of 3 stress test scenarios executed. (3) MG 3.1 -- CAPA effectiveness verification not yet exercised (no management review cycle completed). | Platform is in shadow mode with limited operational history. Monitoring infrastructure (Prometheus) is instrumented but visualization and alerting layers are not yet deployed. Stress test programme is in its first cycle. | (1) Deploy Grafana dashboard for AI governance metrics and wire alert routing to operational notification channel. (2) Execute Scenarios 2 and 3 tabletop exercises by Q2 2026. (3) Conduct first management review including CAPA effectiveness verification. | ML Operations Engineer | 2026-06-30 | OPEN | Ref: `docs/ai-governance/nist-control-effectiveness-review.md`. GV 6.1 requires Grafana deployment (infrastructure dependency). MS 2.11 and MG 3.1 are time-dependent (require operational cycles). |
| NC-006 | 2026-02-23 | Minor | EU AI Act assurance review identified 3 compliance gaps: (1) Article 4 -- Training completion records not collected; no competence assessments on file despite training materials existing. (2) Article 50 -- SSE streaming endpoints use headers only for AI provenance, not body-level metadata. (3) Articles 52/53 -- Compliance register still at v0.2.0; EU database registration not evaluated. | Training materials were created as governance documentation but delivery and evidence collection were deferred until operational deployment. SSE provenance was a technical oversight. Register maturity reflects the youth of the compliance programme. | (1) Deliver AI literacy training to Site S002 operations team and collect signed attendance records. (2) Add `ai_provenance` field to SSE event data payload for streaming endpoints. (3) Complete compliance register review and promote to v1.0.0. Evaluate voluntary EU database registration. | Compliance Lead | 2026-05-01 | OPEN | Ref: `docs/ai-governance/eu-ai-act-assurance-review.md`. Gaps G-4.1 (training delivery), G-50.1 (SSE provenance), G-52.2 (register maturity). All Minor severity -- no regulatory non-compliance for Limited Risk classification. |

## Summary Statistics

| Metric | Value |
|--------|-------|
| Total nonconformities raised | 6 |
| Open | 3 |
| In Progress | 0 |
| Closed | 3 |
| Overdue | 0 |
| Critical | 0 |
| Major | 3 |
| Minor | 3 |

## Source of Nonconformities

### Phase 1 (NC-001 through NC-003)

Identified from the gap analysis documented in:

- [`02-control-mapping-iso42001.md`](02-control-mapping-iso42001.md) -- Priority Gaps section
- [`01-risk-classification.md`](01-risk-classification.md) -- Immediate Gaps section
- [`04-eu-ai-act-readiness.md`](04-eu-ai-act-readiness.md) -- Readiness obligations

### Phase 3 (NC-004 through NC-006)

Identified from Phase 3 assurance reviews (Phase 116):

- [`incident-tabletop-report.md`](incident-tabletop-report.md) -- Actions Log (NC-004)
- [`nist-control-effectiveness-review.md`](nist-control-effectiveness-review.md) -- Partially Effective controls (NC-005)
- [`eu-ai-act-assurance-review.md`](eu-ai-act-assurance-review.md) -- Compliance gaps (NC-006)

## Review History

| Review Date | Reviewer | NCs Reviewed | Actions Taken |
|-------------|----------|-------------|---------------|
| 2026-02-23 | SENTINEL Governance Team | NC-001, NC-002, NC-003 | Initial register creation with pre-populated gaps from compliance analysis |
| 2026-02-23 | SENTINEL Governance Team | NC-004, NC-005, NC-006 | Phase 3 assurance review findings: tabletop actions (NC-004), NIST effectiveness gaps (NC-005), EU AI Act compliance gaps (NC-006). NC-004 classified Major; NC-005, NC-006 classified Minor. |

## Document History

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 1.0.0 | 2026-02-23 | SENTINEL Governance Team | Initial register with 3 pre-populated nonconformities from gap analysis |
| 1.1.0 | 2026-02-23 | SENTINEL Governance Team | NC-002 closed: fairness/bias baseline assessment completed |
| 1.2.0 | 2026-02-23 | SENTINEL Governance Team | NC-001 closed: all 6 model cards completed. NC-003 closed: residual risk disclosure published. All 3 Phase 1 CAPAs now closed. |
| 1.3.0 | 2026-02-23 | SENTINEL Governance Team | Phase 3 assurance findings: NC-004 (tabletop actions, Major, OPEN), NC-005 (NIST effectiveness gaps, Minor, OPEN), NC-006 (EU AI Act gaps, Minor, OPEN). No high/critical CAPAs -- NC-004 is Major with actions tracked. |
| 1.4.0 | 2026-02-23 | SENTINEL Governance Team | NC-004 partial closure: Action 3 (AI incident playbook) CLOSED -- Section 10.4 added to incident response process v1.1. 4 actions remain open. Evidence directories populated with README indexes. |

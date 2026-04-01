---
title: "AIMS Management Review Template"
type: "template"
status: "approved"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
tags: ["ai-governance", "management-review", "template", "iso-42001"]
domain: "compliance"
audience: "management"
complexity: "intermediate"
estimated_read_time: 8
---

# AIMS Management Review Template

## Purpose

This template structures the quarterly AI Management System (AIMS) review meeting. It ensures consistent coverage of KPI performance, risk status, nonconformities, and improvement actions as required by ISO 42001 clause 9.3.

## Meeting Details

| Field | Value |
|-------|-------|
| **Review Period** | Q____ 20____ (____/____ to ____/____) |
| **Meeting Date** | ____/____/________ |
| **Chair** | AIMS Owner (Information Security Officer) |
| **Attendees** | |
| **Minutes Taken By** | |
| **Next Review Date** | ____/____/________ |

---

## 1. KPI Dashboard

Performance against AI Management Policy objectives ([`ai-management-policy.md`](ai-management-policy.md), Section 4).

| KPI ID | Objective | Target | Current Value | Trend | Status | Notes |
|--------|-----------|--------|---------------|-------|--------|-------|
| KPI-01 | Quality gate pass rate (live_control) | >= 99% | ____% | _____ | _____ | |
| KPI-01 | Quality gate pass rate (shadow_live) | >= 95% | ____% | _____ | _____ | |
| KPI-02 | Recommendation acceptance rate | >= 80% | ____% | _____ | _____ | |
| KPI-03 | Drift critical alerts (24h) in live_control | 0 | ____ | _____ | _____ | |
| KPI-04 | Feedback capture rate (7-day) | >= 97% (live) | ____% | _____ | _____ | |
| KPI-05 | Safety violation count (quarter) | 0 | ____ | _____ | _____ | |
| KPI-06 | Audit trail completeness | 100% (live) | ____% | _____ | _____ | |
| KPI-07 | Mean time to rollback | < 5 min (live) | ____ min | _____ | _____ | |

**Trend key:** Improving / Stable / Degrading

**Status key:** On Target / At Risk / Off Target

### KPI Commentary

_Summarize significant movements, root causes for off-target KPIs, and planned corrective actions._

---

## 2. Risk Summary

Status of AI risk classifications from the Risk Classification Register ([`01-risk-classification.md`](01-risk-classification.md)).

| Risk ID | Use Case | Current Classification | Change Since Last Review | Open Gaps | Action Required |
|---------|----------|------------------------|--------------------------|-----------|-----------------|
| RISK-001 | Operator AI chat | limited-risk | | | |
| RISK-002 | Technician diagnosis | limited-risk | | | |
| RISK-003 | Tiered optimization | limited-risk | | | |
| RISK-004 | Tier 3 execution | potential-high-risk | | | |
| RISK-005 | Drift/alert decisions | limited-risk | | | |
| RISK-006 | AI-generated reports | limited-risk | | | |

### New or Emerging Risks

_Document any new AI use cases, changes in deployment mode, or external factors affecting risk posture._

---

## 3. Nonconformities

Summary of open and recently closed nonconformities from the CAPA Register ([`nonconformity-capa-register.md`](nonconformity-capa-register.md)).

| Status | Count |
|--------|-------|
| Open | ____ |
| In Progress | ____ |
| Closed This Quarter | ____ |
| Overdue | ____ |

### Open Nonconformity Details

| NC-ID | Description | Owner | Due Date | Status | Blocker? |
|-------|-------------|-------|----------|--------|----------|
| | | | | | |

---

## 4. CAPA Status

Corrective and preventive action effectiveness.

| Metric | Value |
|--------|-------|
| Total CAPAs raised (cumulative) | ____ |
| CAPAs closed on time | ____% |
| CAPAs overdue | ____ |
| Repeat nonconformities | ____ |

### Effectiveness Review

_For CAPAs closed this quarter, assess whether the corrective action prevented recurrence._

---

## 5. Operational Mode Status

Current deployment mode per site.

| Site | Current Mode | Quality Gate Status | Days in Current Mode | Target Mode | Target Date |
|------|-------------|---------------------|----------------------|-------------|-------------|
| S002 | simulation | | | | |

### Mode Transition Requests

_Document any requests to transition to the next deployment mode, with evidence of readiness criteria met._

---

## 6. Audit and Compliance Updates

| Topic | Status | Notes |
|-------|--------|-------|
| ISO 42001 control mapping coverage | ____% controls with evidence | |
| NIST AI RMF alignment status | | |
| EU AI Act readiness actions | | |
| Internal audit findings | | |
| External audit findings | | |
| Regulatory changes to monitor | | |

---

## 7. Improvement Actions from Previous Review

| Action ID | Description | Owner | Due Date | Status | Evidence |
|-----------|-------------|-------|----------|--------|----------|
| | | | | | |

---

## 8. Decisions and Actions

Record all decisions made and actions assigned during this review.

| Decision/Action ID | Date | Description | Owner | Due Date | Priority |
|--------------------|------|-------------|-------|----------|----------|
| | | | | | |

---

## 9. Next Review

| Field | Value |
|-------|-------|
| **Next Review Date** | ____/____/________ |
| **Agenda Items to Carry Forward** | |
| **Pre-meeting Preparation Required** | |

---

## Sign-off

| Role | Name | Signature | Date |
|------|------|-----------|------|
| AIMS Owner | _________________ | _________________ | ____/____/________ |
| AI Engineering Lead | _________________ | _________________ | ____/____/________ |
| Compliance Lead | _________________ | _________________ | ____/____/________ |
| Operations Lead | _________________ | _________________ | ____/____/________ |

---

## Document History

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 1.0.0 | 2026-02-23 | SENTINEL Governance Team | Initial template with 9 review sections, KPI dashboard, and decision tracking |

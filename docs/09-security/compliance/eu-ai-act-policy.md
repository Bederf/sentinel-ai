---
title: "EU AI Act Policy"
type: "policy"
status: "draft"
version: "0.1.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Compliance Team"
tags: ["compliance", "eu-ai-act", "policy", "governance"]
domain: "compliance"
audience: "all"
complexity: "intermediate"
estimated_read_time: 15
---

# EU AI Act Policy

## 1. Purpose

This policy defines how SENTINEL designs, deploys, monitors, and governs AI features for alignment with the EU AI Act.

## 2. Policy Objectives

- Prevent deployment of prohibited AI practices
- Ensure users are informed when interacting with AI
- Build role-based AI literacy across teams
- Maintain auditable records for AI decisions and controls
- Escalate potential high-risk use cases before release

## 3. Governance and Ownership

| Role | Responsibility |
|---|---|
| Compliance Owner | Owns EU AI Act register and reviews |
| Legal Reviewer | Confirms classification and legal interpretation |
| Engineering Lead | Implements technical controls and evidence |
| Product Owner | Ensures user transparency and UX controls |
| Security Lead | Ensures logging, incident process, and control assurance |

## 4. Mandatory Requirements

### 4.1 AI Literacy (Article 4)

- All relevant personnel must complete AI literacy training for their role.
- Training must be tracked in an auditable register.
- New joiners must complete training within 30 days.

### 4.2 Prohibited Practices (Article 5)

- No AI feature may be released before prohibited-practices review.
- The review result must be attached to the feature record in the EU AI Act register.
- Any detected prohibited pattern requires immediate block and escalation.

### 4.3 Transparency (Article 50)

- User-facing AI channels must disclose that the user is interacting with an AI system.
- AI-generated output shared externally must support content labeling/marking controls where required.
- Product and Engineering must maintain test evidence that transparency controls are active.

### 4.4 Risk Classification and Escalation

- Every AI feature must be classified and recorded in `eu-ai-act-compliance-register.md`.
- Any `potential-high-risk` classification requires legal review before production release.
- High-risk trigger decisions must be documented with rationale and approver.

### 4.5 Incident and Corrective Action

- AI incidents must be logged, triaged, and tracked to closure.
- Root cause and corrective action evidence is mandatory for material incidents.
- Repeated incident patterns require management escalation.

## 5. Control Evidence

Minimum evidence for each in-scope AI feature:
- Feature classification record
- User transparency evidence (UI text, API behavior, screenshots)
- Runtime control evidence (guardrails, approvals, logging)
- Test evidence and verification date
- Assigned owner and review date

## 6. Metrics

| Metric | Target |
|---|---|
| In-scope AI features classified | 100% |
| Relevant staff AI literacy completion | 100% |
| AI channels with disclosure control enabled | 100% |
| Open high-severity EU AI Act findings | 0 |

## 7. Review and Change Control

- Policy review cadence: quarterly minimum
- Triggered review: new AI feature, architecture change, legal update, major incident
- Policy exceptions require Compliance Owner and Legal Reviewer approval

## 8. Related Records

- `docs/compliance/eu-ai-act-compliance-register.md`
- `docs/compliance/eu-ai-act-internal-audit-2026Q2.md`
- `docs/09-security/incident-response-policy.md`

## 9. Implementation Ownership and Deadlines

| Workstream | Owner | Target Date |
|---|---|---|
| Feature classification complete | Compliance Owner + Engineering Lead | 2026-03-24 |
| AI literacy controls implemented | Compliance Owner | 2026-04-23 |
| Transparency controls deployed in all AI channels | Product Owner + Engineering Lead | 2026-04-23 |
| Internal audit execution and closure plan | Audit Lead | 2026-05-24 |

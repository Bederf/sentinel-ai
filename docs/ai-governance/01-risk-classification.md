---
title: "AI Risk Classification Register"
type: "register"
status: "approved"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
tags: ["ai-governance", "risk", "classification", "eu-ai-act", "nist-ai-rmf"]
domain: "compliance"
audience: "all"
complexity: "intermediate"
estimated_read_time: 15
---

# AI Risk Classification Register

## 1. Classification Methodology

### 1.1 EU AI Act Risk Tiers

The EU AI Act (Regulation (EU) 2024/1689) establishes four risk tiers for AI systems:

| Tier | Label | Description | Obligation Level |
|------|-------|-------------|------------------|
| **1** | **Unacceptable (Prohibited)** | AI practices that pose a clear threat to safety, livelihoods, or rights (Article 5) | Must not be deployed |
| **2** | **High Risk** | AI systems listed in Annex III or safety components of Annex I products (Article 6) | Full conformity assessment, CE marking, post-market monitoring |
| **3** | **Limited Risk** | AI systems with transparency obligations (Article 50) | Must disclose AI interaction, label AI-generated content |
| **4** | **Minimal Risk** | AI systems with no specific regulatory obligations | Voluntary codes of conduct encouraged |

### 1.2 Assessment Criteria

Each SENTINEL AI feature was assessed against these factors:

1. **Impact severity** -- Could the AI output cause physical harm, financial loss, or legal exposure?
2. **Automation level** -- Is the system advisory-only, approval-gated, or fully autonomous?
3. **User exposure** -- Does the output interact with end-users who may not know it is AI-generated?
4. **Regulatory sensitivity** -- Does the feature fall within an Annex III high-risk category?
5. **Existing controls** -- What safety interlocks, quality gates, and human oversight mechanisms are in place?

### 1.3 Classification Decision Process

1. Feature owner identifies the AI feature and its operational scope.
2. Compliance team maps the feature against EU AI Act Annex III categories.
3. If Annex III applies, the feature is classified HIGH RISK; otherwise, assess transparency obligations (Article 50).
4. For features with transparency obligations, classify as LIMITED RISK.
5. For features with no specific obligations, classify as MINIMAL RISK.
6. Document rationale, existing controls, and gaps for each classification.
7. Compliance Lead and Product Lead sign off on final classification.

**Note on Annex III**: SENTINEL operates in the building management / facilities management domain. The system does not fall within any of the eight Annex III high-risk categories (biometrics, critical infrastructure safety components, education, employment, essential services, law enforcement, migration, or administration of justice). However, Tier 3 Auto-Execute is flagged as a HIGH RISK *candidate* due to its autonomous actuation of building systems, which could present safety-critical scenarios. This classification is precautionary and pending formal legal review.

---

## 2. Per-Feature Risk Classification

### 2.1 Classification Summary

| Feature ID | Feature | EU AI Act Tier | Sign-off Status |
|------------|---------|----------------|-----------------|
| RISK-001 | Predictive Maintenance | LIMITED RISK | CLASSIFIED |
| RISK-002 | Optimization Recommendations | LIMITED RISK (with safety overlay) | CLASSIFIED |
| RISK-003 | Auto-Execute Tier 3 | HIGH RISK (candidate) | PENDING REVIEW |
| RISK-004 | AI Chat | MINIMAL RISK | CLASSIFIED |
| RISK-005 | Health Rating Calculator | LIMITED RISK | CLASSIFIED |
| RISK-006 | Work Order Auto-Creation | MINIMAL RISK | CLASSIFIED |
| RISK-007 | Anomaly Detection | MINIMAL RISK | CLASSIFIED |
| RISK-008 | Energy Optimization | LIMITED RISK | CLASSIFIED |
| RISK-009 | Explanation Service | LIMITED RISK | CLASSIFIED |

### 2.2 Detailed Classification

#### RISK-001: Predictive Maintenance

| Attribute | Value |
|-----------|-------|
| **Component** | `backend/app/ml/`, failure predictions, RUL estimation |
| **Risk Tier** | LIMITED RISK |
| **Article** | Article 50 -- transparency obligations |
| **Automation Mode** | Advisory only -- predictions displayed to operators |
| **Impact Severity** | Low-to-medium -- incorrect prediction may delay maintenance, but human review is required before action |
| **Rationale** | Generates probabilistic failure predictions and remaining useful life estimates. Output is informational and always reviewed by a qualified technician before any maintenance action. No autonomous actuation. |
| **Existing Controls** | Confidence scoring with minimum thresholds (Tier 2 >= 0.4, Tier 3 >= 0.6); quality gate evaluation; audit logging of all predictions; model drift monitoring |
| **Gaps** | Formal transparency text on prediction screens ("AI-generated prediction") |
| **Sign-off** | CLASSIFIED |

#### RISK-002: Optimization Recommendations

| Attribute | Value |
|-----------|-------|
| **Component** | `backend/app/services/optimization_tier_router.py`, `tier_routing_engine.py` |
| **Risk Tier** | LIMITED RISK (with safety overlay) |
| **Article** | Article 50 -- transparency obligations |
| **Automation Mode** | Advisory + approval-gated (Tiers 1-2 require operator approval) |
| **Impact Severity** | Medium -- incorrect recommendations could affect comfort or energy costs, but safety interlocks prevent harm |
| **Rationale** | Generates setpoint change and scheduling recommendations. All recommendations pass through the Safety Engine and require operator approval (Tier 1/2). Financial impact is bounded by quality gates. |
| **Existing Controls** | Safety Engine validation; quality gate with 14 metrics; tier routing with confidence thresholds; operator approval workflow; rollback capability |
| **Gaps** | Model/data cards not yet complete; formal AI disclosure label on recommendation UI |
| **Sign-off** | CLASSIFIED |

#### RISK-003: Auto-Execute Tier 3

| Attribute | Value |
|-----------|-------|
| **Component** | `backend/app/services/approval_service.py`, PARASITE Tier 3 pipeline |
| **Risk Tier** | HIGH RISK (candidate) |
| **Article** | Article 6 -- potential conformity assessment requirement |
| **Automation Mode** | Controlled autonomy -- autonomous setpoint writes within safety boundaries |
| **Impact Severity** | High -- autonomous actuation of building systems (HVAC, lighting) could affect occupant safety and comfort |
| **Risk Assessment Rationale** | This feature autonomously writes setpoint changes to building control systems. While SENTINEL does not fall within Annex III categories, the autonomous nature of physical actuation in occupied buildings warrants a precautionary HIGH RISK classification. Failure modes include incorrect temperature setpoints affecting vulnerable occupants, energy system disruption, or cascading equipment failures. |
| **Existing Controls** | (1) Safety Engine with SAFETY_LIMITS boundary scanning; (2) Quality gate fail-closed enforcement in live_control mode; (3) Rollback path for every autonomous action; (4) Change-of-value (COV) monitoring post-execution; (5) 1-hour cooldown between autonomous actions on same equipment; (6) shadow_live mode blocks execution with 409; (7) Tier 3 confidence threshold >= 0.6 |
| **Gaps for Article 6 Conformity** | (a) Formal risk management system documentation per Annex IV; (b) Technical documentation package for conformity assessment; (c) Automated logging to meet record-keeping requirements (Article 12); (d) Post-market monitoring plan (Article 72); (e) Explicit human oversight mechanism documentation (Article 14); (f) External legal review to confirm whether Annex III truly applies |
| **Sign-off** | PENDING REVIEW -- requires formal legal/compliance determination |

#### RISK-004: AI Chat

| Attribute | Value |
|-----------|-------|
| **Component** | `frontend/src/components/Chat.tsx`, `TechnicianChat.tsx`, Sentry Bot |
| **Risk Tier** | MINIMAL RISK |
| **Article** | Voluntary codes of conduct encouraged; Article 50(1) disclosure recommended |
| **Automation Mode** | Advisory only -- conversational queries and explanations, no autonomous actions |
| **Impact Severity** | Low -- incorrect responses may cause confusion but cannot trigger any physical action |
| **Rationale** | Provides conversational guidance about building systems, equipment status, and maintenance history. All responses are informational. No write operations are triggered from chat responses. Users can verify information against dashboards and operational data. |
| **Existing Controls** | Audit logging of all conversations; role-based access control; no write-path from chat to control systems |
| **Gaps** | None identified for minimal risk tier; AI disclosure label recommended as best practice |
| **Sign-off** | CLASSIFIED |

#### RISK-005: Health Rating Calculator

| Attribute | Value |
|-----------|-------|
| **Component** | `backend/app/services/health_rating_calculator.py` |
| **Risk Tier** | LIMITED RISK |
| **Article** | Article 50 -- transparency obligations |
| **Automation Mode** | Automated scoring, advisory display |
| **Impact Severity** | Low-to-medium -- health scores inform maintenance prioritization, but technicians make final decisions |
| **Rationale** | Computes equipment health using a 5-component weighted formula (baseline 35%, service 20%, runtime 20%, fault 15%, trend 10%). Scores are displayed on dashboards for operator review. No autonomous actions are triggered directly from health scores alone. |
| **Existing Controls** | Data quality gate (mode-specific confidence: sim/shadow/live); transparent formula with documented weights; health/risk separation enforcement at import level |
| **Gaps** | Formal transparency text explaining score composition to operators |
| **Sign-off** | CLASSIFIED |

#### RISK-006: Work Order Auto-Creation

| Attribute | Value |
|-----------|-------|
| **Component** | `backend/app/services/`, WO-SIM generation pipeline |
| **Risk Tier** | MINIMAL RISK |
| **Article** | Voluntary codes of conduct; no specific obligations |
| **Automation Mode** | Automated creation, human execution |
| **Impact Severity** | Low -- creates work items in the system; a human technician reviews and executes all physical work |
| **Rationale** | Automatically generates work orders (WO-SIM) when equipment health drops below thresholds. The work order is an administrative artifact; no physical action occurs until a technician accepts and performs the work. |
| **Existing Controls** | PostgreSQL trigger-based creation; technician assignment by specialty; work order review before execution; audit trail |
| **Gaps** | None identified for minimal risk tier |
| **Sign-off** | CLASSIFIED |

#### RISK-007: Anomaly Detection

| Attribute | Value |
|-----------|-------|
| **Component** | `backend/app/api/mlops.py`, drift detection, threshold alerts |
| **Risk Tier** | MINIMAL RISK |
| **Article** | Voluntary codes of conduct; no specific obligations |
| **Automation Mode** | Monitoring and alerting only |
| **Impact Severity** | Low -- alerts notify operators of potential issues; no autonomous remediation |
| **Rationale** | Detects data drift, threshold violations, and anomalous sensor readings. Generates alerts for operator review. All response actions require human decision-making. |
| **Existing Controls** | Configurable thresholds; alert cooldown periods; transition-only alerts (no alert spam); operator dashboard |
| **Gaps** | None identified for minimal risk tier |
| **Sign-off** | CLASSIFIED |

#### RISK-008: Energy Optimization

| Attribute | Value |
|-----------|-------|
| **Component** | `backend/app/services/`, tariff-aware scheduling, energy consumption model |
| **Risk Tier** | LIMITED RISK |
| **Article** | Article 50 -- transparency obligations (financial impact) |
| **Automation Mode** | Advisory -- recommends scheduling changes; operator approves |
| **Impact Severity** | Medium -- incorrect tariff analysis could lead to suboptimal energy costs; financial impact is bounded and reversible |
| **Rationale** | Analyzes energy consumption patterns and tariff structures to recommend scheduling optimizations. Recommendations have financial impact (energy cost savings). All recommendations require operator approval. |
| **Existing Controls** | Quality gate evaluation; operator approval for all schedule changes; historical comparison baselines; cost rate validation (R5/kWh commercial default) |
| **Gaps** | Formal AI disclosure on energy recommendation screens; model card for energy consumption model |
| **Sign-off** | CLASSIFIED |

#### RISK-009: Explanation Service

| Attribute | Value |
|-----------|-------|
| **Component** | RAG + LLM explanation pipeline |
| **Risk Tier** | LIMITED RISK |
| **Article** | Article 50 -- must disclose AI-generated content |
| **Automation Mode** | Advisory -- generates natural-language explanations of AI decisions |
| **Impact Severity** | Low -- explanations support understanding, but operators verify against operational data |
| **Rationale** | Uses retrieval-augmented generation (RAG) and LLM to produce human-readable explanations of AI recommendations and predictions. Output is clearly AI-generated text and must be labeled as such per Article 50. |
| **Existing Controls** | Audit logging; RAG source attribution; no write-path from explanations to control systems |
| **Gaps** | Consistent "AI-generated" labeling across all explanation output channels |
| **Sign-off** | CLASSIFIED |

---

## 3. Risk Distribution Summary

| Risk Tier | Count | Features |
|-----------|-------|----------|
| HIGH RISK (candidate) | 1 | Auto-Execute Tier 3 |
| LIMITED RISK | 5 | Predictive Maintenance, Optimization Recommendations, Health Rating Calculator, Energy Optimization, Explanation Service |
| MINIMAL RISK | 3 | AI Chat, Work Order Auto-Creation, Anomaly Detection |
| Prohibited | 0 | See [Prohibited Practices Checklist](../compliance/eu-ai-act-prohibited-practices-checklist.md) |

---

## 4. Immediate Gaps (Aggregate)

| Gap | Affected Features | Priority | Target Date |
|-----|-------------------|----------|-------------|
| Formal legal review for Tier 3 high-risk classification | RISK-003 | Critical | 2026-03-31 |
| AI disclosure labels on all user-facing AI outputs | RISK-001, RISK-002, RISK-005, RISK-008, RISK-009 | High | 2026-04-15 |
| Model/data cards for ML models | RISK-002, RISK-008 | Medium | 2026-04-30 |
| Conformity assessment documentation (if RISK-003 confirmed high-risk) | RISK-003 | High | 2026-05-31 |
| Human oversight documentation per Article 14 | RISK-003 | High | 2026-04-30 |

---

## 5. Required Evidence (Per Feature)

Each classified feature must maintain:

- Classification decision record with owner and date
- Linked technical control evidence (code paths, configuration)
- Monitoring metric proving control operation
- Review log and next review date
- For HIGH RISK: conformity assessment documentation per Annex IV

---

## 6. Approval

| Role | Name | Date | Status |
|------|------|------|--------|
| Compliance Lead | ___________________ | ____-__-__ | Pending |
| Product Lead | ___________________ | ____-__-__ | Pending |
| AI Engineering Lead | ___________________ | ____-__-__ | Pending |
| Legal Reviewer | ___________________ | ____-__-__ | Pending (required for RISK-003) |

**Next formal review:** 2026-03-31

---

## 7. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-02-23 | SENTINEL Governance Team | Initial draft with 6 use cases |
| 1.0.0 | 2026-02-23 | SENTINEL Governance Team | Per-feature classification for 9 AI features; classification methodology; HIGH RISK assessment for Tier 3; gap analysis |

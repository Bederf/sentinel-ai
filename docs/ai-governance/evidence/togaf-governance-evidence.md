---
title: "TOGAF Governance Evidence Bundle"
type: "evidence"
status: "Draft"
version: "1.0.0"
date: "2026-02-23"
owner: "Architecture Lead"
author: "SENTINEL Architecture Office"
tags: ["togaf", "governance", "evidence", "compliance", "architecture", "phase-3"]
domain: "compliance"
audience: "all"
complexity: "intermediate"
estimated_read_time: 15
---

# TOGAF Governance Evidence Bundle

## Coverage Summary

| Metric | Value |
|--------|-------|
| **Total Governance Elements** | 5 |
| **Elements with Evidence** | 5 |
| **Evidence Coverage** | 100% |
| **ADM Phases Mapped** | 8 of 8 (Preliminary + A through H) |
| **Architecture Repository Sections** | 6 of 6 (governance, landscapes, principles, reference, roadmaps, standards) |

---

## 1. Architecture Board Charter

### Evidence

| # | Evidence Artifact | Path | Exists |
|---|------------------|------|--------|
| 1 | Architecture Board Charter | `docs/architecture-repository/governance/architecture-board-charter.md` | Yes |
| 2 | Board Minutes Template | `docs/architecture-repository/governance/architecture-board-minutes-template.md` | Yes |
| 3 | Architecture Capability Model | `docs/architecture-repository/governance/architecture-capability.md` | Yes |

### Compliance Assessment

The SENTINEL Architecture Board (SAB) charter establishes governance aligned with TOGAF Architecture Board requirements:

| TOGAF Requirement | SENTINEL Implementation | Status |
|------------------|------------------------|--------|
| **Board purpose and scope** | Charter Section 1 defines purpose: governs architectural decisions, standards compliance, and change control | Implemented |
| **Membership and voting** | 5 voting members defined (Architecture Lead as Chair, Backend Lead, Frontend Lead, Security Lead, AI Engineering Lead) with non-voting invited participants | Implemented |
| **Meeting cadence** | Monthly operational review (60 min), quarterly strategic review (90 min), ad-hoc as needed | Implemented |
| **Standing agenda** | 5-item agenda: previous actions, ADR review, standards compliance, roadmap review, risk/debt | Implemented |
| **Decision authority** | Approve/reject ADRs, grant exceptions, prioritize tech debt, escalate safety-critical decisions | Implemented |
| **Quorum rules** | 3 of 5 voting members including Chair; provisional decisions without quorum require ratification | Implemented |
| **Decision-making process** | Proposal, discussion, vote (simple majority), tie-break (Chair), record with rationale | Implemented |
| **Decision categories** | Standard, Significant, and Critical categories with escalating approval requirements | Implemented |
| **Minutes and records** | Template provided; stored in `docs/architecture-repository/governance/minutes/`; reviewed at next meeting | Implemented |
| **Charter review** | Annual review or triggered by organizational change, regulatory requirement, or effectiveness concern | Implemented |

**Gap Notes:** None. Charter is comprehensive and covers all TOGAF Architecture Board requirements. Minutes directory exists but has not yet accumulated operational records as the board was recently established.

---

## 2. ADM Phase Mapping

### Evidence

| # | Evidence Artifact | Path | Exists |
|---|------------------|------|--------|
| 1 | TOGAF ADM Mapping - SENTINEL | `docs/architecture-repository/governance/adm-mapping-sentinel.md` | Yes |
| 2 | Architecture Roadmap 2026 | `docs/architecture-repository/roadmaps/architecture-roadmap-2026.md` | Yes |

### Compliance Assessment

Each TOGAF ADM phase is mapped to SENTINEL artifacts with evidence links and accountable owners:

| ADM Phase | Mapped | Primary Evidence | Accountable Owner | Review Frequency |
|-----------|--------|-----------------|-------------------|-----------------|
| **Preliminary** | Yes | `docs/09-security/information-security-framework.md`, `docs/architecture-repository/governance/architecture-capability.md`, `docs/architecture-repository/governance/architecture-board-charter.md` | Architecture Lead | Annually |
| **A: Architecture Vision** | Yes | `README.md`, `docs/02-architecture/system-overview.md`, `.planning/PROJECT.md`, `.planning/ROADMAP.md` | Architecture Lead | Quarterly |
| **B: Business Architecture** | Yes | `docs/04-features/`, `docs/10-operations/aegis-phase0-daily-ops.md`, `docs/15-business-context/` | Operations Lead | Quarterly |
| **C: Information Systems** | Yes | `docs/03-api-reference/`, `docs/08-ai-ml/`, `docs/02-architecture/system-overview.md` | Backend Lead + AI Engineering Lead | Monthly |
| **D: Technology Architecture** | Yes | `docker-compose.yml`, `Caddyfile`, `infra/` | Backend Lead + Security Lead | Monthly |
| **E: Opportunities and Solutions** | Yes | `compliance.md`, `.planning/` | Architecture Lead | Monthly |
| **F: Migration Planning** | Yes | `.planning/phases/`, `supabase/migrations/`, `docs/08-ai-ml/write-policy-and-rollout.md` | AI Engineering Lead | Per release |
| **G: Implementation Governance** | Yes | `backend/app/services/quality_gate_evaluator.py`, `.planning/phases/` | AI Engineering Lead | Per sprint |
| **H: Architecture Change Management** | Yes | `backend/app/api/mlops.py`, `.planning/MILESTONES.md`, `.planning/ROADMAP.md` | Architecture Lead + Security Lead | Monthly |

**Gap Notes:** None. All 8 ADM phases (Preliminary + A through H) are mapped to maintained SENTINEL artifacts with accountable owners and review frequencies.

---

## 3. Architecture Capability Model

### Evidence

| # | Evidence Artifact | Path | Exists |
|---|------------------|------|--------|
| 1 | Architecture Capability Model | `docs/architecture-repository/governance/architecture-capability.md` | Yes |
| 2 | Competence Training Register (architecture roles) | `docs/ai-governance/competence-training-register.md` | Yes |

### Compliance Assessment

The architecture capability model defines the minimum capability required to govern SENTINEL platform evolution:

| TOGAF Capability Element | SENTINEL Implementation | Status |
|-------------------------|------------------------|--------|
| **Architecture Board definition** | Board name, cadence, core members defined; links to full charter | Implemented |
| **Decision scope** | Architecture principles, high-impact design changes, AI governance control changes, cross-module integration | Implemented |
| **Change approval rules** | Tier 3 changes require board review; safety/rollback changes require dual sign-off (Engineering + Compliance); regulatory changes require evidence update | Implemented |
| **Model lifecycle rules** | Versioned model release records, pre-release validation evidence, rollback triggers and ownership | Implemented |
| **Risk review cadence** | Monthly risk review across ISO 42001/NIST AI RMF/EU AI Act; quarterly control-effectiveness summary | Implemented |
| **Required records** | Architecture decisions log, control change approvals, exceptions register, review minutes | Implemented |

**Gap Notes:** Capability model is currently at version 0.1.0 (draft status). Should be promoted to version 1.0.0 after first Architecture Board meeting confirms the model is operating as documented.

---

## 4. Architecture Repository Structure

### Evidence

| # | Evidence Artifact | Path | Exists |
|---|------------------|------|--------|
| 1 | Architecture Repository README | `docs/architecture-repository/README.md` | Yes |
| 2 | Governance Directory | `docs/architecture-repository/governance/` | Yes |
| 3 | Landscapes Directory | `docs/architecture-repository/landscapes/` | Yes |
| 4 | Principles Directory | `docs/architecture-repository/principles/` | Yes |
| 5 | Reference Directory | `docs/architecture-repository/reference/` | Yes |
| 6 | Roadmaps Directory | `docs/architecture-repository/roadmaps/` | Yes |
| 7 | Standards Directory | `docs/architecture-repository/standards/` | Yes |

### Compliance Assessment

The architecture repository is organized according to TOGAF architecture repository structure:

| Repository Section | Directory | Contents | Status |
|-------------------|-----------|----------|--------|
| **Governance** | `docs/architecture-repository/governance/` | Architecture Board Charter, ADM Mapping, Architecture Capability Model, Board Minutes Template | Complete (4 files) |
| **Landscapes** | `docs/architecture-repository/landscapes/` | Current State Landscape | Complete (1 file) |
| **Principles** | `docs/architecture-repository/principles/` | Architecture Principles | Complete (1 file) |
| **Reference** | `docs/architecture-repository/reference/` | Reference Architecture - SENTINEL | Complete (1 file) |
| **Roadmaps** | `docs/architecture-repository/roadmaps/` | Architecture Roadmap 2026 | Complete (1 file) |
| **Standards** | `docs/architecture-repository/standards/` | Standards Catalog | Complete (1 file) |

### Detailed Repository Contents

```
docs/architecture-repository/
  README.md
  governance/
    adm-mapping-sentinel.md
    architecture-board-charter.md
    architecture-board-minutes-template.md
    architecture-capability.md
  landscapes/
    current-state-landscape.md
  principles/
    architecture-principles.md
  reference/
    reference-architecture-sentinel.md
  roadmaps/
    architecture-roadmap-2026.md
  standards/
    standards-catalog.md
```

**Gap Notes:** None. All 6 repository sections are populated with at least one maintained artifact. The repository structure directly follows TOGAF architecture repository conventions.

---

## 5. Compliance Assessment -- SENTINEL Architecture Decisions vs TOGAF ADM

### Evidence

| # | Evidence Artifact | Path | Exists |
|---|------------------|------|--------|
| 1 | ADM Mapping | `docs/architecture-repository/governance/adm-mapping-sentinel.md` | Yes |
| 2 | Architecture Principles | `docs/architecture-repository/principles/architecture-principles.md` | Yes |
| 3 | Standards Catalog | `docs/architecture-repository/standards/standards-catalog.md` | Yes |
| 4 | Current State Landscape | `docs/architecture-repository/landscapes/current-state-landscape.md` | Yes |
| 5 | Reference Architecture | `docs/architecture-repository/reference/reference-architecture-sentinel.md` | Yes |
| 6 | Compliance Programme (gap tracking) | `compliance.md` | Yes |
| 7 | Planning Phases (migration evidence) | `.planning/phases/` | Yes |
| 8 | Milestone History | `.planning/MILESTONES.md` | Yes |

### Compliance Assessment

The following assessment evaluates how SENTINEL architecture decisions align with TOGAF ADM phases:

| ADM Phase | Alignment Assessment | Evidence of Compliance |
|-----------|---------------------|----------------------|
| **Preliminary** | Strong alignment. Governance framework, board charter, and capability model are established and linked. Security framework provides the organizational context. | Charter approved (v1.0.0), capability model drafted (v0.1.0), information security framework in place |
| **A: Architecture Vision** | Strong alignment. Product vision documented in README and system overview. Planning artefacts (PROJECT.md, ROADMAP.md) define strategic direction. | System overview maintained, project roadmap current, milestone tracking active through v19.0 |
| **B: Business Architecture** | Good alignment. Core use cases documented in feature specifications. Business context includes CTO alignment evidence. Operational workflows defined. | 29+ feature documents in `docs/04-features/`, business context in `docs/15-business-context/`, daily ops documented |
| **C: Information Systems** | Strong alignment. API reference, AI/ML documentation, and system overview provide comprehensive application and data architecture. Model and data governance framework covers AI-specific data architecture. | 70+ API endpoint routers, model governance framework, 3 data sheets, 6 model cards |
| **D: Technology Architecture** | Good alignment. Runtime stack defined via Docker Compose, Caddyfile, and infrastructure scripts. Security controls documented. | Docker Compose configuration, Caddy reverse proxy, infrastructure deployment scripts |
| **E: Opportunities and Solutions** | Strong alignment. Compliance programme consolidates gap backlog with owners and target dates. Planning directory tracks remediation themes. | `compliance.md` with consolidated gap backlog, `.planning/` with phase-based delivery |
| **F: Migration Planning** | Strong alignment. Phase sequencing tracked in `.planning/phases/`. Database migrations versioned in `supabase/migrations/`. Mode rollout policy defines deployment progression. | 116+ planning phases, numbered SQL migrations, 4-mode rollout checklist |
| **G: Implementation Governance** | Strong alignment. Quality gates enforce implementation standards. Sprint-level architecture reviews via planning phases. | Quality gate evaluator with 14 metrics, per-phase planning and summary documents |
| **H: Architecture Change Management** | Good alignment. Drift monitoring via MLOps API. Milestone history tracks changes. Roadmap maintained with version increments. | MLOps drift endpoints, milestone v9.0 through v19.0 tracked, roadmap with quarterly reviews |

### Overall TOGAF Governance Maturity Assessment

| Maturity Dimension | Level | Rationale |
|-------------------|-------|-----------|
| **Architecture Board** | Established | Charter approved, membership defined, meeting cadence set, decision process documented |
| **ADM Mapping** | Established | All 8 phases mapped with evidence links and accountable owners |
| **Architecture Repository** | Established | 6 sections populated with maintained artifacts |
| **Architecture Principles** | Established | Principles documented and referenced in standards catalog |
| **Change Management** | Developing | Drift monitoring and milestone tracking in place; formal change request process not yet exercised at scale |

---

## Cross-Reference: TOGAF Governance to Other Frameworks

TOGAF governance artifacts also support compliance with ISO 42001 and EU AI Act requirements:

| TOGAF Artifact | ISO 42001 Control | EU AI Act Article | NIST AI RMF |
|---------------|-------------------|-------------------|-------------|
| Architecture Board Charter | ISO-A.2.3 (Roles and authorities) | -- | NIST-GV-1.2 (Governance) |
| ADM Mapping | ISO-A.6.1 (Lifecycle management) | Art.9 (Risk management) | NIST-GV-1.2 (Governance) |
| Architecture Capability Model | ISO-A.2.3 (Roles and authorities) | -- | -- |
| Architecture Principles | ISO-A.2.2 (AI policy) | -- | NIST-GV-1.5 (Risk tolerance) |
| Standards Catalog | ISO-A.6.1 (Lifecycle management) | Art.15 (Accuracy/robustness) | NIST-MS-1.1 (Quality gates) |
| Quality Gate Evaluator (Phase G) | ISO-A.4.2 (Risk treatment) | Art.9 (Risk management) | NIST-MS-1.1 (Quality gates) |

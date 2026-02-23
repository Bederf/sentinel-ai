---
title: "TOGAF ADM Mapping - SENTINEL"
type: "architecture"
status: "active"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Architecture Office"
tags: ["togaf", "adm", "architecture", "governance"]
domain: "general"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# TOGAF ADM Mapping - SENTINEL

This map ties TOGAF ADM phases to existing SENTINEL artifacts and operating controls. Each phase includes evidence links to maintained implementation artifacts that demonstrate the phase is actively governed.

| ADM Phase | SENTINEL Implementation | Primary Evidence | Evidence Links |
|---|---|---|---|
| Preliminary | Governance framework, policies, roles | `docs/09-security/information-security-framework.md` | [`architecture-capability.md`](architecture-capability.md), [`architecture-board-charter.md`](architecture-board-charter.md) |
| A: Architecture Vision | Product vision, priorities, operating model | `README.md`, `docs/02-architecture/system-overview.md` | [`PROJECT.md`](../../../PROJECT.md), [`ROADMAP.md`](../../../ROADMAP.md) |
| B: Business Architecture | Core use cases, user journeys, operational workflows | `docs/04-features/`, `docs/10-operations/aegis-phase0-daily-ops.md` | [`docs/15-business-context/`](../../15-business-context/), [`docs/04-features/`](../../04-features/) |
| C: Information Systems (Data/Application) | AI services, APIs, RAG, model and data governance | `docs/03-api-reference/`, `docs/08-ai-ml/` | [`docs/02-architecture/system-overview.md`](../../02-architecture/system-overview.md), [`docs/03-api-reference/`](../../03-api-reference/) |
| D: Technology Architecture | Runtime stack, observability, security controls | `docker-compose.yml`, `infrastructure/` | [`docker-compose.yml`](../../../docker-compose.yml), [`Caddyfile`](../../../Caddyfile), [`infra/`](../../../infra/) |
| E: Opportunities and Solutions | Gap remediation themes and bundled work | `.planning/`, compliance gap backlogs | [`compliance.md`](../../../compliance.md), [`.planning/`](../../../.planning/) |
| F: Migration Planning | Phase sequencing, mode rollout, database migrations | `.planning/phases/`, `supabase/migrations/` | [`docs/08-ai-ml/write-policy-and-rollout.md`](../../08-ai-ml/write-policy-and-rollout.md), [`supabase/migrations/`](../../../supabase/migrations/) |
| G: Implementation Governance | Quality gates, approvals, release checks | `backend/app/services/quality_gate_evaluator.py` | [`.planning/phases/`](../../../.planning/phases/), [`STATE.md`](../../../STATE.md) |
| H: Architecture Change Management | Drift monitoring, incidents, control updates | `backend/app/api/mlops.py` | [`MILESTONES.md`](../../../MILESTONES.md), [`ROADMAP.md`](../../../ROADMAP.md) |

## Phase Accountability

| ADM Phase | Accountable Owner | Review Frequency |
|-----------|------------------|-----------------|
| Preliminary | Architecture Lead | Annually |
| A: Architecture Vision | Architecture Lead | Quarterly |
| B: Business Architecture | Operations Lead | Quarterly |
| C: Information Systems | Backend Lead + AI Engineering Lead | Monthly |
| D: Technology Architecture | Backend Lead + Security Lead | Monthly |
| E: Opportunities and Solutions | Architecture Lead | Monthly |
| F: Migration Planning | AI Engineering Lead | Per release |
| G: Implementation Governance | AI Engineering Lead | Per sprint |
| H: Architecture Change Management | Architecture Lead + Security Lead | Monthly |

## Immediate Actions

- ~~Add evidence links to each ADM phase~~ -- DONE (2026-02-23)
- ~~Add review dates and accountable owners to each mapped evidence item~~ -- DONE (2026-02-23)
- Keep each ADM phase linked to at least one maintained artifact.
- Use this map as the exam-to-operations bridge for TOGAF Foundation.
- Review evidence link validity at each Architecture Board operational review.

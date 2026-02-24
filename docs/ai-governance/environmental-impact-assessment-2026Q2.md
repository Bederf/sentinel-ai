---
title: "Environmental Impact Assessment (2026 Q2)"
type: "assessment"
status: "draft"
version: "0.1.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
tags: ["ai-governance", "environmental-impact", "energy", "carbon"]
domain: "compliance"
audience: "architecture-board, compliance, operations"
complexity: "intermediate"
estimated_read_time: 12
---

# Environmental Impact Assessment (2026 Q2)

## 1. Purpose

Assess operational energy and carbon impact of SENTINEL AI and supporting observability controls, and define measurable reduction actions.

## 2. System Boundary

Included:
- Local AI inference path (`Ollama` on host/SBC target profile)
- Cloud AI path (Anthropic/Z.ai) when cross-border consent is active
- Backend API and governance services
- Monitoring stack required for control-effectiveness evidence (`Prometheus`, `Grafana`, `Loki`, `Promtail`)

Excluded:
- Client-owned building equipment energy (BMS plant loads)
- Third-party provider datacenter internals beyond reported usage factors

## 3. Assessment Window

- Baseline window: `2026-03-01` to `2026-03-31`
- Review window: `2026-04-01` to `2026-05-31`
- Final board submission target: `2026-06-10`

## 4. Method and Data Sources

| Source | What is measured | Collection path |
|---|---|---|
| Host system metrics | CPU/RAM/disk/network utilization for AI + backend | Node exporter + Prometheus |
| AI request telemetry | Local vs cloud routing volume, token/cost proxy | `backend/app/api/metrics.py` + service logs |
| Monitoring stack usage | Prometheus/Loki/Grafana resource overhead | Container stats + Prometheus |
| Cloud provider usage | Model/token consumption estimates | Provider billing/API usage exports |

Carbon conversion factors:
- Electricity conversion factor: `TBD` (South Africa grid factor to be fixed for this report)
- Cloud usage factor basis: `TBD` (provider-published estimate references)

## 5. Baseline Metrics (to be populated)

| Metric | Value | Unit | Evidence |
|---|---:|---|---|
| Total local AI inference hours | TBD | hours | Prometheus query export |
| Total cloud AI requests | TBD | requests | AI routing metrics |
| Monitoring stack average power proxy | TBD | kWh/day | Host + container metrics |
| Estimated total monthly energy | TBD | kWh | Calculation sheet |
| Estimated total monthly emissions | TBD | kgCO2e | Calculation sheet |

## 6. Findings (initial)

- Local-only routing is expected to reduce cross-border compute dependency for production SBC deployments.
- Monitoring controls add overhead but are required for audit-grade evidence and safety/compliance signaling.
- Cloud fallback should be constrained to documented high-value use cases.

## 7. Reduction Plan (proposed)

| Action | Owner | Target Date | KPI |
|---|---|---|---|
| Enforce local-first routing profile in production | AI Engineering Lead | 2026-04-15 | >= 85% local route ratio |
| Optimize metric cardinality and scrape interval | Platform/SRE Lead | 2026-04-30 | <= 15% monitoring overhead vs baseline |
| Add low-power model profile for SBC deployment | AI Engineering Lead | 2026-05-15 | >= 20% lower inference energy per request |
| Monthly environmental KPI review in management cadence | Compliance Lead | 2026-05-31 | 2 consecutive monthly reports completed |

## 8. Risks and Assumptions

- Pending confirmation of electricity emission factor can shift total CO2e estimate.
- Cloud provider reporting granularity may require approximation methods.
- SBC hardware profile may differ from current hybrid development host.

## 9. Sign-off

| Role | Name | Date | Decision |
|---|---|---|---|
| Compliance Lead | TBD | TBD | Pending |
| Platform/SRE Lead | TBD | TBD | Pending |
| Architecture Board Chair | TBD | TBD | Pending |

## 10. Revision History

| Version | Date | Author | Changes |
|---|---|---|---|
| 0.1.0 | 2026-02-23 | SENTINEL Governance Team | Initial assessment structure and measurement plan |

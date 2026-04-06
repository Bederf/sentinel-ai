---
title: "Intent Engineering Framework"
type: "architecture"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# Intent Engineering Framework
### SENTINEL | AI-Powered Building Intelligence

---

## What is Intent Engineering?

Intent engineering is the discipline of defining **what an organization needs to achieve** before selecting or designing AI systems. Instead of starting with "let's use AI," you start with "here's what must happen" — and engineer the intelligence layer to deliver on those intents.

It reverses the typical technology adoption model. The AI becomes a mechanism, not a strategy.

---

## The Three-Layer Model

**Layer 1 — Business Intent**
The outcome statement. What the executive team needs to see on a dashboard or in a board report.

- "Zero unplanned critical equipment failures across the portfolio"
- "20% reduction in energy expenditure within 18 months"
- "100% regulatory compliance with real-time audit readiness"
- "Data-driven CapEx decisions replacing age-based assumptions"
- "Any facility manager can query building performance in plain language"

**Layer 2 — Operational Intent**
The specific operational behaviour required to fulfil the business intent. This is where building operations and facility management teams live.

- Predict equipment failures 30+ days in advance with confidence scoring
- Optimize HVAC schedules hourly based on occupancy, weather, and tariff signals
- Surface anomalies ranked by business impact, not just severity
- Auto-generate work orders routed to the right vendor with SLA tracking
- Flag non-compliance proactively with recommended corrective actions
- Provide real-time asset condition scoring across the entire portfolio

**Layer 3 — System Intent**
What SENTINEL actually orchestrates under the hood to deliver Layers 1 and 2.

- Sensor data ingestion and normalization from heterogeneous BMS infrastructure
- ML model routing (optimization tier) — selecting the right model for the right problem
- Alert prioritization engine with business context weighting
- Conversational interface (RLM integration) for natural language building queries
- Feedback loops — model performance continuously refined from operational outcomes
- Observability infrastructure — Grafana dashboards, logging, and performance metrics

---

## REMS Intent Map

| Business Intent | Operational Intent | SENTINEL System Intent |
|---|---|---|
| Eliminate unplanned downtime | Predict failures 30 days out, auto-schedule maintenance | Predictive ML models on equipment telemetry, automated work order generation |
| Reduce energy costs by 20% | Hourly HVAC/lighting optimization, demand-side management | Energy optimization algorithms, tariff-aware scheduling, renewable integration |
| Portfolio-wide visibility | Single dashboard across 600+ properties, anomaly ranking | Data aggregation layer, anomaly detection models, business impact scoring |
| Regulatory compliance | Proactive non-compliance alerts, audit-ready reporting | Compliance rule engine, automated report generation, OHS tracking |
| Informed CapEx decisions | Asset condition scoring, lifecycle cost modelling | ML-driven remaining useful life estimates, repair-vs-replace recommendations |
| Operational accessibility | Plain language building queries for non-technical staff | Conversational AI layer (RLM), natural language to BMS query translation |

---

## Why Intent Engineering Matters

**Without it:** Organizations buy AI tools, generate dashboards nobody uses, and revert to reactive maintenance within 12 months. The technology leads the strategy.

**With it:** Every AI capability maps directly to a measurable business outcome. Adoption is natural because the system answers questions people are already asking. The strategy leads the technology.

---

## The SENTINEL Difference

SENTINEL is built as an **intent engine**. It doesn't just bolt analytics onto a BMS — it starts with what the business needs to achieve and orchestrates the data, models, and actions to fulfil those intents across the entire property portfolio.

Each intent is traceable from board-level outcome → operational behaviour → system capability. Nothing runs without a reason. Everything is measurable.

---

## Intent Delivery Status

> Cross-referenced against SENTINEL v27.0 capability audit (2026-02-25)

| Business Intent | Layer 3 Delivery | Status | Evidence |
|---|---|---|---|
| Eliminate unplanned downtime | LSTM + Autoencoder + 5 RF classifiers, RUL calculator, auto WO creation | **PRODUCTION** | 50+ tests, 5-component health scoring, fault classification pipeline |
| Reduce energy costs by 20% | CP-SAT MIP dispatcher, TOU tariffs, Solar+BESS, Modbus TCP writes | **PRODUCTION** | 70+ tests, Sprint 0 hardware pilot active, kill switch validated |
| Portfolio-wide visibility | Site aggregation, anomaly detection, alert prioritization | **IMPLEMENTED** | Per-site works; cross-site pattern learning not yet built |
| Regulatory compliance | OHS/fire/legionella/electrical/lift checklists, POPIA, audit trail | **IMPLEMENTED** | 472-line test suite, encryption, consent guards |
| Informed CapEx decisions | Budget tracking + variance analysis only | **PARTIAL** | Monthly OPEX works; no replace-vs-repair, no NPV/lifecycle cost |
| Operational accessibility | Claude AI chat with 15+ tools, streaming SSE, local-only | **IMPLEMENTED** | Chat functional; no approval workflow, WhatsApp not activated |

### Key Gaps to Close

1. **CapEx Planning Module** — The weakest link. REMS manages billions in assets but SENTINEL only tracks monthly operating budgets. Need: lifecycle cost engine, replace-vs-repair decision model, NPV/IRR calculations.
2. **Portfolio-Wide ML** — All models run per-site. For 600 branches: need cross-site degradation patterns, fleet benchmarking, centralized anomaly correlation.
3. **Vendor Performance** — Work orders route to technicians but no vendor scoring, SLA benchmarking, or contractor performance tracking at scale.
4. **Conversational Approval Workflow** — Chat is read-only advisory. Need: "approve this setpoint change" → human confirms → SENTINEL executes.

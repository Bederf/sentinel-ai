---
title: "Stage promotion evidence flow"
type: "spec"
status: "approved"
version: "1.0.0"
created: "2026-02-21"
updated: "2026-02-21"
author: "Sentinel Development Team"
tags: ["promotion", "evidence", "thresholds", "dwell", "commissioning"]
related: ["109C-site-002-mode-policy-dry-run.md", "109D-operational-flows-index.md"]
domain: "bms"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 6
---

# Stage promotion evidence flow

Defines how promotion decisions are formed from measured telemetry and commissioning state.

## Entry condition

System runs scheduled policy evaluation for current stage with a configured next stage.

## Evidence sources

- Monitoring snapshot ingestion KPIs
- Control KPI conflict counters
- Commissioning scorecard state
- Quality gate status
- State tracker dwell timestamps

## Deterministic steps

1. Collect snapshot and derive metric bundle.
2. Evaluate all entry thresholds for next stage.
3. If any threshold fails, clear candidate stage and hold.
4. If all pass, start or continue candidate dwell timer.
5. Enforce minimum dwell duration.
6. Enforce anti-flap re-promotion stability window.
7. If all conditions hold, emit `would_promote`.
8. Persist new stage and clear candidate/violation timers.

## Exit condition

- Promotion decision emitted and state updated, or
- Hold decision emitted with blocking reason code(s).

## Flow diagram

```mermaid
flowchart TD
    A[Scheduler tick] --> B[Collect monitoring + commissioning + quality gate]
    B --> C[Evaluate entry thresholds]
    C -->|Fail| D[Hold stage and record entry failures]
    C -->|Pass| E[Start/continue candidate dwell timer]
    E --> F{Min dwell met?}
    F -->|No| G[Hold with promotion_dwell reason]
    F -->|Yes| H{Re-promotion stability window met?}
    H -->|No| I[Hold with repromotion_stability reason]
    H -->|Yes| J[Decision: would_promote]
    J --> K[Persist promoted stage and clear timers]
```

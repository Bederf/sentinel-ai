---
title: "Automatic fail-closed demotion flow"
type: "spec"
status: "approved"
version: "1.0.0"
created: "2026-02-21"
updated: "2026-02-21"
author: "Sentinel Development Team"
tags: ["fail-closed", "automatic", "demotion", "safety", "site-002"]
related: ["109C-site-002-mode-policy-dry-run.md", "109D-operational-flows-index.md"]
domain: "bms"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 6
---

# Automatic fail-closed demotion flow

Defines deterministic behavior when automatic mode violates hard safety/data quality gates.

## Entry condition

Current stage is `automatic` and one or more fail-closed gates fail:

- freshness threshold fail
- coverage threshold fail
- provenance threshold fail
- conflict threshold fail
- quality gate status not allowed

## Deterministic actions

1. Evaluate fail-closed rules.
2. Emit decision `would_fail_closed_demote`.
3. Set target stage to `supervised`.
4. Set write action to `stop_writes`.
5. Persist stage state and demotion timestamp.
6. Emit operational alert and audit event.
7. Start requalification window (anti-flap timer).

## Exit condition

System remains in `supervised` until supervised stage promotion rules pass continuously for required dwell + stability windows.

## Audit expectations

- Decision event with failed rule IDs
- Stage transition event (`automatic` -> `supervised`)
- Control action status set to stop writes

## Flow diagram

```mermaid
flowchart TD
    A[Automatic stage active] --> B[Evaluate fail-closed gates]
    B -->|All pass| C[Hold automatic]
    B -->|Any fail| D[Decision: would_fail_closed_demote]
    D --> E[Set write action: stop_writes]
    E --> F[Demote to supervised]
    F --> G[Persist state and last_demoted_at]
    G --> H[Emit alert + audit event]
    H --> I[Start 24h requalification stability window]
```

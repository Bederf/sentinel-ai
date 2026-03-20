---
title: "SENTINEL Architecture Principles"
type: "policy"
status: "draft"
version: "0.2.0"
created: "2026-02-23"
updated: "2026-03-16"
author: "SENTINEL Architecture Office"
tags: ["architecture", "principles", "governance"]
related:
  - "architecture-repository/principles/building-operating-lifecycle.md"
  - "05-integrations/simbiot-concept-connector.md"
domain: "general"
audience: "all"
complexity: "beginner"
estimated_read_time: 7
---

# SENTINEL Architecture Principles

1. Safety and fail-closed behavior takes precedence over optimization.
2. Architecture decisions must be evidence-based and auditable.
3. Services must expose clear ownership and operational boundaries.
4. Security, privacy, and compliance controls are built in by default.
5. Changes to AI behavior require traceability and rollback paths.
6. Platform evolution should favor reuse over one-off custom design.
7. A building is an independent runtime entity. SENTINEL never owns building operation; it overlays it.
8. The only supported operational boundary is `building -> BMS source -> SIMBIOT -> SENTINEL`.
9. The lifecycle simulation engine is a BMS source for a building, not part of SENTINEL.
10. `site_processing = off` means disconnected: no reads, no ingest, no writes, no control actions.
11. Production deployment is one SENTINEL instance per building, running in isolation.
12. Any future multi-site console is read-only by default and must not become the operational control plane.

## Boundary Rules

### Canonical runtime flow

```text
building -> real BMS or lifecycle simulation -> SIMBIOT adapter -> SENTINEL
```

### Ownership

- The building owns equipment, schedules, points, alarms, and runtime state.
- The BMS source owns telemetry and control surfaces exposed for that building.
- SIMBIOT owns protocol connectivity, discovery, ingestion, and command transport.
- SENTINEL owns analytics, storage, ML, recommendations, workflow, and optional control decisions.

### Required separation

- The lifecycle engine must be treated as a simulated BMS source.
- SENTINEL must not call the lifecycle engine directly as an internal subsystem.
- SENTINEL behavior must remain the same whether the upstream source is a live BMS or a simulation-backed adapter.
- Module activation is a SENTINEL concern only. Unsupported building systems may exist on the BMS and still be ignored.

### Processing semantics

- When `site_processing` is off, the SENTINEL instance behaves as if the building connection has been removed.
- When `site_processing` is on, SENTINEL may connect to the BMS source, ingest allowed data, and execute only licensed and enabled module behavior.

## Operating Lifecycle

The canonical stage model for one building is documented in
[building-operating-lifecycle.md](/opt/bms-intelligence/docs/architecture-repository/principles/building-operating-lifecycle.md).

Short form:

```text
disconnected
  -> commissioning
  -> shadow_live + monitor
  -> live_control + monitor
  -> live_control + human_in_loop
  -> live_control + auto_execute
```

Module add-ons such as solar, water, and security expand system scope inside that lifecycle. They do not replace it.

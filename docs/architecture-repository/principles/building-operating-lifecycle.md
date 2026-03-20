---
title: "Building Operating Lifecycle"
type: "policy"
status: "draft"
version: "0.1.0"
created: "2026-03-16"
updated: "2026-03-16"
author: "SENTINEL Architecture Office"
tags: ["architecture", "operations", "lifecycle", "simbiot", "ai-control"]
related:
  - "architecture-repository/principles/architecture-principles.md"
  - "05-integrations/simbiot-concept-connector.md"
  - "08-ai-ml/agent-contract.md"
  - "08-ai-ml/write-policy-and-rollout.md"
domain: "general"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# Building Operating Lifecycle

This document defines the canonical operating lifecycle for one deployed SENTINEL instance serving one building.

It answers one question:

```text
How does a building move from "exists but dark" to "fully autonomous control"
without breaking the platform boundary or skipping safety?
```

## 1. Runtime Model

The runtime boundary does not change at any stage:

```text
building -> BMS source -> SIMBIOT -> SENTINEL
```

Where:

- `building` is the real site and its physical systems
- `BMS source` is either the live BMS or the lifecycle simulation acting as a simulated BMS
- `SIMBIOT` is the only connection, discovery, ingestion, and command boundary
- `SENTINEL` is the overlay for storage, ML, recommendations, approvals, and optional control

Rules:

- One SENTINEL instance serves one building in production.
- `site_processing = off` means disconnected from the building for runtime operations.
- Commissioning sessions may temporarily discover a disconnected building through SIMBIOT, but this does not mean the site is operationally active.
- Module activation is a SENTINEL decision. If the BMS exposes unsupported systems, those points are ignored.

## 2. Two Control Axes

The lifecycle uses two separate axes.

### Axis A: BMS ingestion mode

| Ingestion mode | Meaning | Writes |
|---|---|---|
| `simulation` | Simulated BMS source for development, demos, or synthetic buildings | Simulated only |
| `shadow_live` | Live building ingest with no real writes | No real writes |
| `live_control` | Live building ingest with production-grade quality gates | Writes allowed only if control tier and safety permit |

### Axis B: Control tier

| Control tier | Meaning | Operator role |
|---|---|---|
| `monitor` | Read-only and recommendation-only | Operator reviews but SENTINEL does not write |
| `human_in_loop` | Supervised controls | Operator approves each action |
| `auto_execute` | Autonomous controls | SENTINEL executes bounded actions automatically |

### Required interpretation

- `shadow_live` is for proving ingest quality and recommendation correctness without writes.
- `live_control + monitor` is the correct state for recommendation-only production use.
- `live_control + human_in_loop` is the correct state for supervised controls.
- `live_control + auto_execute` is the correct state for bounded autonomous control.

## 3. Lifecycle Stages

### Stage 0: Building Exists, Disconnected

State:

- The building record exists.
- Equipment and site metadata may exist.
- `site_processing = off`.
- No runtime reads, no ingest, no writes.

Interpretation:

- The building is commissioned in the real world but SENTINEL is not yet attached.
- If the building uses the lifecycle simulation, the simulation is only a potential BMS source, not part of SENTINEL.

### Stage 1: Commissioning and Discovery

Purpose:

- Connect SENTINEL to the building through SIMBIOT.
- Discover controllers, points, and metadata.
- Normalize naming, location, and equipment mapping.

State:

- Commissioning session active through SIMBIOT.
- `site_processing` may still be off for runtime operations.
- Discovery, mapping correction, and approval are allowed.
- No operational ML writes or control writes.

Required steps:

1. Connect to the BMS source through SIMBIOT.
2. Run discovery and point ingestion.
3. Convert raw BMS naming into SENTINEL equipment and point structure.
4. Review and approve mappings.
5. Confirm module scope for the building.

Output:

- Clean equipment inventory
- Approved point mappings
- Site-specific module set
- Site ready for runtime ingest

### Stage 2: Passive Baseline Collection

Purpose:

- Start collecting trustworthy building data.
- Build enough history for quality gates, baselines, and early model fitting.

State:

- `site_processing = on`
- `ingestion_mode = shadow_live`
- `control_tier = monitor`
- No real writes

Behavior:

- SIMBIOT reads live data.
- SENTINEL stores and analyzes only enabled-module data.
- Quality gates, commissioning scorecards, truth checks, and mapping coverage are measured continuously.
- Recommendations may be generated internally, but no live device writes occur.

Typical duration:

- Days to weeks, depending on signal quality and equipment coverage.

Promotion requirement:

- Site must satisfy commissioning and quality gate thresholds before moving to `live_control`.

### Stage 3: Recommendation-Only Production

Purpose:

- Show the operator useful AI recommendations without giving SENTINEL write authority.

State:

- `site_processing = on`
- `ingestion_mode = live_control`
- `control_tier = monitor`

Behavior:

- Strict production-grade quality gates apply.
- SENTINEL shows recommendations, savings opportunities, and explanations.
- The operator implements changes manually in the building or BMS.
- M&V confirms whether the recommendations are useful.

This is the correct operating state when the client wants:

- analytics
- recommendations
- human-managed control changes
- no direct BMS writes from SENTINEL

### Stage 4: Supervised Controls

Purpose:

- Let SENTINEL send changes to the BMS, but only after human approval.

State:

- `site_processing = on`
- `ingestion_mode = live_control`
- `control_tier = human_in_loop`

Behavior:

- Recommendations still appear first.
- Every write must pass:
  - module gate
  - control mode gate
  - quality gate
  - safety boundary validation
  - approval workflow
- Operator can approve or defer each action.
- Audit and rollback paths must remain active.

This is the first real write-capable production stage.

### Stage 5: Autonomous Controls

Purpose:

- Allow bounded automatic execution where the client has sufficient trust and the site has demonstrated stability.

State:

- `site_processing = on`
- `ingestion_mode = live_control`
- `control_tier = auto_execute`

Behavior:

- Only actions allowed by policy may auto-execute.
- Quality gate must remain strict and fail closed.
- Safety checks must run before and at execution time.
- COV/readback verification and rollback remain mandatory.
- Operator notifications continue even when approval is no longer required.

Permanent restrictions:

- High-risk or critical actions should remain human-gated unless a separate policy explicitly allows otherwise.
- Site kill switch, equipment blocklists, and emergency stop must always override autonomous behavior.

## 4. Module Rollout Rules

Modules do not define the lifecycle stage. They change what data and controls are in scope inside a stage.

### Base rule

- If a module is not active for the site, SIMBIOT/SENTINEL ignores that subsystem even if the BMS exposes it.

Examples:

- No solar module: solar and BESS points are ignored.
- No water module: water telemetry is ignored.
- No control add-on: write paths for that subsystem remain blocked.

### Add-on activation pattern

When a new subsystem is installed later, for example solar:

1. Enable the module for that site.
2. Discover or ingest the new points through SIMBIOT.
3. Validate mappings and coverage.
4. Re-baseline the new subsystem.
5. Include the subsystem in recommendations first.
6. Only later allow supervised or autonomous control for that subsystem.

This means module rollout is incremental and per-building.

## 5. ML Rollout Rules

ML maturity also progresses in stages.

### Early phase

- Use baseline models and anomaly detection conservatively.
- Focus on data quality, mapping accuracy, and operator trust.

### Mid phase

- Train site-specific behavior models from the building's own history.
- Use measured outcomes to improve ranking and recommendation confidence.

### Mature phase

- Use closed-loop outcome data from approved or autonomous actions.
- Keep feedback capture, rollback rate, and M&V accuracy as promotion and retention signals.

Hard rule:

- A building should never jump to autonomous control just because a model exists.
- Promotion depends on operational evidence, not model availability alone.

## 6. Safe Promotion Path

The intended promotion sequence is:

```text
disconnected
  -> commissioning
  -> shadow_live + monitor
  -> live_control + monitor
  -> live_control + human_in_loop
  -> live_control + auto_execute
```

Demotion is always allowed:

- bad data quality
- failed commissioning gate
- unsafe behavior
- high rollback rate
- client request
- module deactivation

Demotion effects:

- `auto_execute` -> `human_in_loop`
- `human_in_loop` -> `monitor`
- `live_control` -> `shadow_live`
- or full disconnect with `site_processing = off`

## 7. What This Means Operationally

For a newly onboarded client:

1. Connect the building through SIMBIOT and complete discovery.
2. Start with passive ingest and baseline collection.
3. Move into recommendation-only production once data quality is proven.
4. Add supervised controls only after the client wants direct actioning.
5. Add autonomous controls only after measured evidence and trust exist.
6. Add solar, water, security, or other subsystems later as independent module expansions.

That is the canonical SENTINEL operating lifecycle.

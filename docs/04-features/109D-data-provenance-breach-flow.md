---
title: "Data provenance breach flow"
type: "spec"
status: "approved"
version: "1.0.0"
created: "2026-02-21"
updated: "2026-02-21"
author: "Sentinel Development Team"
tags: ["provenance", "live-mode", "breach", "containment", "quality-gate"]
related: ["109C-site-002-mode-policy-dry-run.md", "109D-operational-flows-index.md"]
domain: "bms"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 6
---

# Data provenance breach flow

Defines response when non-live provenance (file/manual) appears in live stages.

## Entry condition

Current stage is `shadow_live`, `supervised`, or `automatic` and:

- `file_manual_sources > 0`, or
- quality gate fails provenance-related rules.

## Deterministic actions

1. Flag provenance breach.
2. Emit critical alert (`json_in_live` semantics).
3. Mark stage violation timer.
4. Evaluate stage-specific demotion rule:
- `shadow_live`: demote to `commissioning` after sustained exit violation.
- `supervised`: demote to `shadow_live` after sustained exit violation.
- `automatic`: immediate fail-closed demotion to `supervised`.
5. Log containment outcome and pending recovery actions.

## Recovery actions

1. Remove or disable non-live source(s).
2. Reconfirm live protocol sources active.
3. Re-run policy evaluations through dwell + stability windows.

## Flow diagram

```mermaid
flowchart TD
    A[Live stage active] --> B[Detect file/manual source]
    B --> C[Raise critical provenance alert]
    C --> D[Start or continue violation timer]
    D --> E{Stage == automatic?}
    E -->|Yes| F[Immediate fail-closed demote to supervised]
    E -->|No| G{Exit violation dwell met?}
    G -->|No| H[Hold with breach violation reason]
    G -->|Yes| I[Demote per stage policy]
    F --> J[Containment + source remediation]
    I --> J
    J --> K[Requalify through thresholds and dwell windows]
```

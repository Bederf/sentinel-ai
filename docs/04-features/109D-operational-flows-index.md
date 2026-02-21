---
title: "Operational flow pack for deterministic onboarding and closed-loop control"
type: "reference"
status: "approved"
version: "1.1.0"
created: "2026-02-21"
updated: "2026-02-21"
author: "Sentinel Development Team"
tags: ["flows", "operations", "onboarding", "quality-gates", "maintenance", "ml-feedback"]
related:
  [
    "109C-site-002-mode-policy-dry-run.md",
    "109D-fail-closed-demotion-flow.md",
    "109D-stage-promotion-evidence-flow.md",
    "109D-data-provenance-breach-flow.md",
    "109D-operator-override-rollback-flow.md",
    "109D-maintenance-closed-loop-flow.md",
    "109D-ml-feedback-training-readiness-flow.md"
  ]
domain: "bms"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 8
---

# Phase 109D: Operational flow pack

This document indexes the six supporting operational flows that complement Phase 109C deterministic stage policy.

## Flow set

1. [Automatic fail-closed demotion flow](109D-fail-closed-demotion-flow.md)
2. [Stage promotion evidence flow](109D-stage-promotion-evidence-flow.md)
3. [Data provenance breach flow](109D-data-provenance-breach-flow.md)
4. [Operator override and rollback flow](109D-operator-override-rollback-flow.md)
5. [Maintenance closed-loop flow](109D-maintenance-closed-loop-flow.md)
6. [ML feedback and training-readiness flow](109D-ml-feedback-training-readiness-flow.md)

Site-002 implementation note:

- Guided inspection is scoped to major equipment first (Tier A/B/C policy) and is documented in
  `109D-maintenance-closed-loop-flow.md` and `../05-integrations/SIMBIOT_ONBOARDING_CHECKLIST.md`.

## Diagram files

Mermaid source files are stored under:

- `docs/02-architecture/diagrams/109D-fail-closed-demotion-flow.mmd`
- `docs/02-architecture/diagrams/109D-stage-promotion-evidence-flow.mmd`
- `docs/02-architecture/diagrams/109D-data-provenance-breach-flow.mmd`
- `docs/02-architecture/diagrams/109D-operator-override-rollback-flow.mmd`
- `docs/02-architecture/diagrams/109D-maintenance-closed-loop-flow.mmd`
- `docs/02-architecture/diagrams/109D-ml-feedback-training-readiness-flow.mmd`

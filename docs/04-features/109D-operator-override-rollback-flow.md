---
title: "Operator override and rollback flow"
type: "spec"
status: "approved"
version: "1.0.0"
created: "2026-02-21"
updated: "2026-02-21"
author: "Sentinel Development Team"
tags: ["operator", "supervised", "approval", "override", "rollback"]
related: ["109D-operational-flows-index.md", "APPROVAL_WORKFLOW.md"]
domain: "bms"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 6
---

# Operator override and rollback flow

Defines supervised decisioning when recommended changes require operator confirmation.

## Entry condition

- Recommendation mode is supervised, and
- recommendation is eligible for operator review.

## Decision path

1. Recommendation generated with context and confidence.
2. Operator reviews impact, risk, and reason codes.
3. Operator action:
- approve
- reject
- approve with override parameters
4. System logs approval decision.
5. If applied and post-action verification fails, rollback path executes.

## Rollback path

1. Detect verification failure or safety violation.
2. Execute rollback action (or schedule rollback work order when direct revert not available).
3. Emit rollback audit and incident event.
4. Feed outcome into recommendation and feedback scoring.

## Exit condition

- Recommendation resolved as applied, rejected, or rolled back with evidence attached.

## Flow diagram

```mermaid
flowchart TD
    A[Recommendation created] --> B[Operator review in supervised mode]
    B --> C{Operator decision}
    C -->|Reject| D[Log rejection reason and close recommendation]
    C -->|Approve| E[Apply planned action]
    C -->|Approve override| F[Apply override action]
    E --> G[Post-action verification]
    F --> G
    G -->|Pass| H[Log success and close]
    G -->|Fail| I[Execute rollback path]
    I --> J[Log rollback and incident]
    J --> K[Feed outcome to feedback loop]
```

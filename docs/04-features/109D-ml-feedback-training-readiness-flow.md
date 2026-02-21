---
title: "ML feedback and training-readiness flow"
type: "spec"
status: "approved"
version: "1.0.0"
created: "2026-02-21"
updated: "2026-02-21"
author: "Sentinel Development Team"
tags: ["ml-feedback", "training-readiness", "quality-gates", "retraining", "closed-loop"]
related: ["109D-operational-flows-index.md", "45-03-mlops-monitoring.md", "../08-ai-ml/ai-recommendation-system.md"]
domain: "bms"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 6
---

# ML feedback and training-readiness flow

Defines how recommendation outcomes become ML feedback and retraining signals.

## Entry condition

Recommendation reaches a terminal operational outcome:

- applied and verified
- rejected
- rolled back
- expired

## Deterministic steps

1. Capture outcome event and context payload.
2. Deduplicate feedback event by idempotency key.
3. Aggregate feedback quality metrics (coverage, lag, success rate).
4. Evaluate training-readiness gates by mode.
5. If readiness passes and cooldown rules allow, trigger retraining scheduler.
6. Store retraining decision and model health outcome.

## Exit condition

- Feedback accepted and retraining deferred, or
- feedback accepted and retraining triggered with traceable reason code.

## Flow diagram

```mermaid
flowchart TD
    A[Recommendation outcome recorded] --> B[Build feedback payload]
    B --> C[Idempotent dedup check]
    C -->|Duplicate| D[Discard duplicate and log]
    C -->|New| E[Persist feedback event]
    E --> F[Update feedback quality metrics]
    F --> G[Evaluate mode-aware training-readiness gates]
    G -->|Not ready| H[Defer retraining with reason]
    G -->|Ready| I[Check retraining cooldown]
    I -->|In cooldown| H
    I -->|Eligible| J[Trigger retraining scheduler]
    J --> K[Store retraining decision and model status]
```

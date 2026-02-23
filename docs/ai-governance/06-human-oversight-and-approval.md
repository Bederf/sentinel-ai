---
title: "Human Oversight and Approval Controls"
type: "policy"
status: "draft"
version: "0.1.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
tags: ["ai-governance", "human-oversight", "approval", "operations"]
domain: "compliance"
audience: "all"
complexity: "intermediate"
estimated_read_time: 9
---

# Human Oversight and Approval Controls

## Oversight Principle

AI recommendations can support operations, but critical actions require accountable human review unless explicitly approved for bounded automation.

## Oversight Tiers

| Tier | Action Type | Human Requirement | Evidence |
|---|---|---|---|
| Tier 1 | Advisory only | No execution authority | Advisory event logs |
| Tier 2 | Approval required before execution | Operator/manager approval mandatory | Approval records + timestamps |
| Tier 3 | Controlled autonomous path | Pre-approved guardrails + post-action review | Decision logs + rollback readiness |

## Approval Requirements

- Approver identity and role captured
- Decision rationale captured
- Safety validation result captured
- Time-to-approve metric captured

## Escalation Triggers

- Repeated failed safety validations
- Drift-critical alert affecting autonomous decisions
- Tool-call failures above threshold
- Unusual cost spike or comfort degradation

## Open Gap

- Replace any placeholder safety validation path with full rule-engine enforcement before autonomous execution.

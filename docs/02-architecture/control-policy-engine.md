---
title: "Control Policy Engine"
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

# Control Policy Engine

**Phase 145** | **Status**: Implemented

## Overview

The Control Policy Engine is the central enforcement point for all AI control actions.
The LLM proposes; the policy engine decides.

```
LLM Reasoning
       ↓
Control Policy Engine    ← this layer
       ↓
TierRouting → Safety → Approval → Execution
```

**Critical Rule**: The LLM outputs `ProposedAction`, never `ExecuteAction`.
Chat is the interface. The control engine is separate.

## Three Control Modes

| Mode | IngestionMode | control_tier | Behavior |
|------|--------------|--------------|----------|
| **RECOMMEND** | SIMULATION | monitor | Advisory only. No write tools registered. |
| **SUPERVISED** | SHADOW_LIVE | human_in_loop | Writes require human approval. |
| **FULL_CONTROL** | LIVE_CONTROL | auto_execute | Auto-execute within policy limits. |

## Command Envelope Pattern

Every control action is wrapped in a `CommandEnvelope` before execution:

```python
CommandEnvelope(
    envelope_id="CMD-a1b2c3d4e5f6",
    proposed_action={"point": "chw_supply_temp", "value": 7.5},
    target_equipment="S002-CHILLER-B1-001",
    control_mode=ControlMode.SUPERVISED,
    policy_check_passed=True,
    previous_state={"point": "chw_supply_temp", "value": 7.0},
    rollback_command={"equipment_id": "...", "point": "...", "value": 7.0},
    requires_approval=True,
)
```

Guarantees: **traceable**, **reversible**, **policy-checked**.

## Policy Checks (in order)

1. **Mode check** — RECOMMEND blocks all writes
2. **Setpoint limits** — value within min/max for equipment type
3. **Ramp rate limits** — change not too rapid (e.g., 1°C/10min for chiller)
4. **Lockout windows** — not during restricted hours
5. **Rate limiting** — max auto-executions per hour per equipment
6. **Previous state capture** — store current value for rollback
7. **Rollback command generation** — revert command ready

## Per-Asset Control Policies

Stored in `backend/app/data/control_policies.json`:

| Equipment | Key Limits | Max Auto/Hour |
|-----------|-----------|---------------|
| CHILLER | CHW supply 5-12°C, ramp 1°C/10min | 3 |
| AHU | Supply air 12-22°C, ramp 2°C/10min | 5 |
| FCU | Zone setpoint 16-28°C | 10 |
| VAV | Zone 18-26°C, damper 0-100% | 10 |
| BESS | Charge power -50 to 50 kW | 3 |
| DALI | Brightness 0-100% | 20 |
| GEN | Requires ATS available | 2 |

## Mode-Aware Tool Gating

In **RECOMMEND** mode, write tools are not available to the LLM at all:

```python
engine.get_available_tools()
# RECOMMEND: ["get_equipment_status", "get_hybrid_context", "search_documents", ...]
# SUPERVISED/FULL_CONTROL: [...read tools..., "write_device_point", "set_hvac_setpoint", ...]
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/control/mode` | Current mode and available tools |
| GET | `/api/control/policies` | List all asset policies |
| GET | `/api/control/policies/{type}` | Get policy for equipment type |
| GET | `/api/control/envelopes/active` | Active command envelopes |
| GET | `/api/control/envelopes/{id}` | Specific envelope |
| POST | `/api/control/envelopes/{id}/rollback` | Roll back a command |

## Key Files

- `backend/app/models/control_policy.py` — ControlMode, CommandEnvelope, AssetControlPolicy
- `backend/app/services/control_policy_engine.py` — Central enforcement engine
- `backend/app/data/control_policies.json` — Default per-asset policies
- `backend/app/api/control_policy.py` — API router
- `backend/tests/services/test_control_policy_engine.py` — 21 tests
- `backend/tests/services/test_phase145_wiring.py` — 16 wiring tests

## Wiring (Active)

- **MCP Tool Gating**: `simbiot_server.call_tool()` checks `get_control_mode()` before
  allowing any mutating tool. Writes are **fail-closed**: blocked unless mode is explicitly
  SUPERVISED or FULL_CONTROL and the policy engine loads cleanly.
- **Fail-closed for writes**: If the policy engine cannot load, times out, or returns an
  unknown mode, mutating tools return `CONTROL_ENGINE_UNAVAILABLE`. Writes require an
  explicit allow, not the absence of a deny.
- **Fail-open for reads**: Policy engine errors do not block read tools.
- **Command Envelope**: Every write that passes the mode gate gets wrapped in a
  `CommandEnvelope` via `evaluate_action()`. This enforces setpoint limits, ramp rates,
  rate limits, and captures before-state for rollback. In SUPERVISED mode, the envelope
  returns `APPROVAL_REQUIRED` with an `envelope_id` for the approval workflow.

## Integration Points

- **Settings** (IngestionMode): Determines control mode
- **MCP Server** (`simbiot_server.py`): Tool gating enforcement point
- **TierRoutingEngine**: Confidence-based tier after policy check
- **SafetyEngine**: Safety validation after policy approval
- **ApprovalService**: Human approval workflow in SUPERVISED mode
- **AEGIS** (Sprint 0): BESS-specific double-flag gating extends this pattern

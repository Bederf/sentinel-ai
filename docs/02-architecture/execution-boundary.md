---
title: Execution Boundary — Device Write Paths
date: 2026-03-28
status: active
---

# Execution Boundary — Device Write Paths

## The Rule

All advisory/supervised/autonomous writes triggered by SENTINEL intelligence
must go through `execution_service.execute_command()`.

Direct calls to `device_manager.write_device_value()` are only permitted in the
approved exceptions listed below.

---

## Paths That Use execute_command() (Centralized)

| Path | File | Source tag |
|------|------|-----------|
| Tier 2 human approval | `services/approval_service.py` → `execute_approval()` | `"advisory"` |
| Tier 3 autonomous execution | `services/approval_service.py` → `auto_execute_recommendation()` | `"auto_execute"` |

These paths enforce: **write → COV verify → audit** on every call, including failure.

---

## Approved Direct Writes (Not Routing Through execute_command)

These have documented reasons for staying direct. Each should be reviewed before
wiring into `execute_command()`.

| File | Call site | Reason |
|------|-----------|--------|
| `services/emergency_handler.py:279` | Safety failsafe restore | Emergency path — must not block on verification; speed is safety |
| `services/fire_hvac_coordinator.py:214,324,364,677,691` | Fire system overrides | Life-safety priority-1 writes; COV verification is secondary to speed |
| `api/devices.py:432` | Manual device control endpoint | Operator override; has its own auth guard (`require_role`) |
| `services/remote_command_service.py:270,447,540` | Remote command execution | Has its own audit trail via `_log_command_execution()` |
| `mcp/simbiot_server.py:582,3099` | MCP tool calls | Dev/debug surface; not in operator control loop |
| `services/chat_tools.py:222` | Chat-driven control | Advisory context; Sentry operator tool |
| `services/bms_control_bridge.py:193` | BMS bridge layer | Wrapper service; delegates audit to caller |
| `services/command_executor.py:280` | Comfort preset executor | Batch setpoint writes; uses its own verification loop |
| `services/autonomous_decision_engine.py:418` | ADE direct control | Pre-approval-service path; needs Phase 2 review |

---

## Disabled Paths (Safety Gated)

| File | Lines | Status |
|------|-------|--------|
| `api/optimization.py:648,1066,1566,1668` | `should_auto_apply = False` | DISABLED — `TODO-PHASE2` marker |

---

## Next Migration Candidates

Priority order for wiring remaining paths through `execute_command()`:

1. **`services/autonomous_decision_engine.py:418`** — AI-driven write, no COV or audit guarantee
2. **`services/chat_tools.py:222`** — operator chat writes, no read-back
3. **`api/devices.py:432`** — manual endpoint, COV gap

**Not candidates (intentional):** emergency_handler, fire_hvac_coordinator —
these are life-safety paths where write speed takes priority over verification pipeline.

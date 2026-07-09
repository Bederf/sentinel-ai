# ADR-003: LoopState v1

**Status:** Accepted (ratified 2026-07-09) | **Date:** 2026-07-09
**Invariants touched:** INV-2, INV-3, INV-8, INV-11, INV-12
**Conventions:** inherits schema conventions from ADR-001.
**Amended 2026-07-09** (same day, pre-implementation, no producer existed — no version bump): added the state-taxonomy section on ratification feedback; `goal.source` clarified as an authority reference into the vault. Semantics of stored fields unchanged.

## Context

The Mission Loop's six responsibilities (goal management, phase selection, execution control, reflection, learning, termination) all require durable state that survives session loss. INV-3 requires every loop to expose Input → Execution → Output → Exit → Escalate; LoopState is that contract made persistent for the Mission layer. INV-2 places goal ownership here — engines never hold or mutate the goal.

## Decision

Define **LoopState v1**: the single mutable "where are we" record for one mission. One file per mission, rewritten atomically on every transition. Checkpoints (ADR-002) embed frozen copies of it.

### Fields — required

| Field | Type | Description |
|---|---|---|
| `schema` | string | `"gsd.loop-state"` |
| `schema_version` | int | `1` |
| `mission_id` | string | Unique id |
| `goal` | object | `{statement, source, accepted_at}` — traceability **snapshot** of the accepted objective (the Input of the loop contract). `source` is an authority reference (vault path, e.g. `sentinel-vault/01-Control/mission-goals.md#...`, or `user:direct`). The authoritative goal lives at the source, not here; changing the mission means updating the vault authority and re-accepting, never editing this field in place (INV-2). |
| `status` | enum | `active` \| `paused` \| `completed` \| `failed` \| `escalated` |
| `current_phase` | string\|null | Phase ref currently executing; null between phases |
| `phases` | array | `[{ref, status: pending\|running\|completed\|failed\|skipped, contract_id, attempts}]` — the working plan, in order |
| `budget` | object | `{tokens_used, tokens_limit, time_used_seconds, time_limit_seconds, phase_retries_used, phase_retries_limit}` — limits null when unenforced |
| `last_checkpoint_id` | string\|null | Most recent Checkpoint (ADR-002) |
| `created_at` / `updated_at` | timestamp | |

### Fields — optional

| Field | Type | Description |
|---|---|---|
| `escalation` | object | Required when `status = escalated`: `{reason, failure_point, next_action}` — the Escalate leg of the loop contract (INV-3, INV-7 semantics) |
| `pause` | object | Required when `status = paused`: `{reason: user_interrupt\|budget\|awaiting_input, resumable: bool}` (INV-8 clean stop) |
| `notes` | string | Human-readable context |

### State taxonomy — what `.gsd/state/` may contain

Three kinds of "state" exist in the system; only the first is admissible here:

1. **Execution state ✅** — progress of executing work: current position, per-phase status and attempts, budget *consumption*, escalation. This is what LoopState is.
2. **Mission knowledge ❌** — the objective and roadmap *themselves* are human-authored knowledge and live in the vault (INV-11). LoopState's `goal` and `phases[]` record acceptance and progress *against* them for auditability (INV-5: on whose authority work ran) — they are snapshots referencing the vault authority, never the authority.
3. **Runtime environment state ❌** — loaded prompts, model configuration, caches, routing tables. Never persisted anywhere under `.gsd/`; the environment is reconstructed from configuration on every run, not restored from state files.

### Loop-contract mapping (INV-3)

Input = `goal` · Execution = `current_phase` + `phases[]` · Output = `phases[].contract_id` → ExecutionContracts · Exit = `status: completed|failed` · Escalate = `status: escalated` + `escalation`.

## Producer / Consumer

- **Producer:** Mission Controller only. Execution Engines never write LoopState (INV-1/INV-2 boundary); they report via ExecutionContract, and the controller folds results in.
- **Consumers:** Mission Controller (resume, next-phase selection), stall/health monitoring, human inspection ("what is the mission doing right now?").

## Storage & lifecycle

`.gsd/state/mission-{mission_id}.json`

- Exactly one current file per mission; **atomic rewrite** (temp + fsync + rename) on every transition — a reader never sees a torn state.
- Mutable by design — history and audit live in checkpoints (ADR-002) and contracts (ADR-001), not here. LoopState answers "now"; checkpoints answer "how we got here."
- On mission completion the file remains (status `completed`) until archived with its checkpoints.

## Consequences

- Recovery order is defined: prefer LoopState if readable and consistent with the latest checkpoint's `seq`; otherwise reconstruct from the latest checkpoint (self-sufficient by ADR-002).
- Budget fields exist from v1 even though enforcement is roadmap-later — producers record usage now, so enforcement lands as a policy change, not a schema change.
- `phases[].attempts` gives phase-level retry classification (transient vs fatal) a place to live.

# ADR-002: Checkpoint v1

**Status:** Accepted (ratified 2026-07-09) | **Date:** 2026-07-09
**Invariants touched:** INV-5, INV-8, INV-10, INV-11, INV-12
**Conventions:** inherits schema conventions from ADR-001.

## Context

INV-10 requires state to be checkpointed *before* irreversible actions, and INV-8 requires a clean stop on human interrupt. Today nothing persists loop position: a crashed or interrupted mission loses all progress that lived in conversation context (`--resume` is explicitly deferred in GSD Master v3). Resume (roadmap step 4) is impossible without a defined checkpoint artifact.

## Decision

Define **Checkpoint v1**: an immutable, self-sufficient snapshot of mission progress. Self-sufficient means it **embeds a full LoopState copy** (ADR-003) rather than referencing `.gsd/state/` — resume must work even if the mutable state file is corrupt or lost.

### Fields — required

| Field | Type | Description |
|---|---|---|
| `schema` | string | `"gsd.checkpoint"` |
| `schema_version` | int | `1` |
| `checkpoint_id` | string | Unique id |
| `mission_id` | string | Mission this checkpoint belongs to |
| `seq` | int | Monotonic per mission, starting at 1 — gaps indicate loss |
| `created_at` | timestamp | |
| `reason` | enum | `phase_boundary` \| `pre_irreversible` \| `user_interrupt` \| `budget_pause` \| `escalation` |
| `loop_state` | object | Full embedded LoopState v1 snapshot (ADR-003) |
| `git_ref` | string\|null | Repo HEAD commit at checkpoint time; null if repo-less |
| `contracts_completed` | array | ExecutionContract ids completed so far in this mission |

### Fields — optional

| Field | Type | Description |
|---|---|---|
| `pending_action` | object | Required when `reason = pre_irreversible`: `{description, target, initiated_by}` — what is about to happen. On resume, presence of a trailing `pre_irreversible` checkpoint with no successor means the action's outcome is UNKNOWN and must be verified before continuing. |
| `note` | string | Human-readable context |

## Producer / Consumer

- **Producer:** the loop owner — Mission Controller at phase boundaries, interrupts, budget pauses, and before any irreversible action. (Execution Engines checkpoint internally with their own mechanisms; this schema governs the Mission layer. GSD-internal adoption may follow later without schema change.)
- **Consumers:** resume logic (Mission Controller restart, `gsd:resume-work`), human audit.

## Storage & lifecycle

`.gsd/checkpoints/{mission_id}/ckpt-{seq:04d}-{checkpoint_id}.json`

- **Append-only, never mutated or deleted** during a mission (INV-5, INV-10).
- Write protocol: write to temp file, fsync, rename — a checkpoint either fully exists or doesn't.
- The checkpoint for an irreversible action is written and durable **before** the action executes (INV-10); doing it in the other order is an invariant violation.
- Retention: checkpoints of a completed mission may be archived after the mission's final contract is written; never pruned mid-mission.

## Consequences

- Embedding LoopState duplicates data across checkpoints — accepted cost; checkpoints are small (KB) and self-sufficiency beats normalization for recovery artifacts.
- The `seq` gap rule gives a cheap corruption check at resume time.
- `pre_irreversible` + `pending_action` gives resume logic a deterministic answer to the hardest recovery question: "did the side effect happen?" — the answer is always "verify before assuming."

# ADR-005: MetricsSnapshot v1

**Status:** Accepted (ratified 2026-07-09) | **Date:** 2026-07-09
**Invariants touched:** INV-5, INV-11, INV-12 (+ v4 decision 4: telemetry is plumbing, not a feature)
**Conventions:** inherits schema conventions from ADR-001.

## Context

Strategic review (every N phases), confidence calibration, and "is the system getting better?" all need longitudinal facts: outcomes, durations, tokens, retries, regressions per phase. Today these exist only inside individual contract reports and the transient heartbeat at `~/.serena/logs/gsd-heartbeat-{phase}.jsonl`. There is no queryable series.

## Decision

Define **MetricsSnapshot v1**: one append-only JSONL record per completed work unit, emitted at the phase boundary by folding the ExecutionContract into a flat, query-friendly row.

**Principle: store facts, not aggregates.** Success rates, averages, and trends are computed by consumers at read time — stored aggregates go stale and can't be re-derived per-window.

### Fields — required (one JSONL line per record)

| Field | Type | Description |
|---|---|---|
| `schema` | string | `"gsd.metrics-snapshot"` |
| `schema_version` | int | `1` |
| `snapshot_id` | string | Unique id |
| `mission_id` | string\|null | Null for standalone (non-mission) phase runs |
| `work_unit_ref` | string | Phase ref |
| `contract_id` | string | Source ExecutionContract (ADR-001) |
| `engine` | string | Copied from contract — enables cross-engine comparison |
| `ts` | timestamp | Snapshot time (= contract `completed_at`) |
| `outcome` | enum | `completed` \| `validation_failed` \| `execution_failed` |
| `failure_point` | string\|null | Copied from contract |
| `duration_seconds` | number | |
| `tokens_used` | int | 0 when unknown |
| `attempt` | int | Which attempt at this work unit (from LoopState `phases[].attempts`) |
| `gates_passed` / `gates_total` | int | From contract `gates[]` |
| `regressions_caught` | int | 0 when engine doesn't report it |
| `stalls_detected` | int | 0 when engine doesn't report it |

## Producer / Consumer

- **Producer:** Mission Controller, immediately after receiving an ExecutionContract (one contract → exactly one snapshot). For standalone GSD runs outside a mission, GSD Master may emit the snapshot itself — same schema, `mission_id: null`.
- **Consumers:** Strategic Review phases, human dashboards, future confidence-governor calibration ("do confidence scores correlate with outcomes?"), reflection.

## Storage & lifecycle

`.gsd/metrics/snapshots.jsonl` — single append-only stream, one line per record. Never rewritten; corrupt trailing line (crash mid-append) is truncated on next write after being logged.

### Heartbeat telemetry (relocation noted, not enacted)

Per v4 decision 4, the existing stall-detector heartbeat is *plumbing gaining a persistent home*, not a new schema. Roadmap step 5 relocates the stream from `~/.serena/logs/gsd-heartbeat-{phase}.jsonl` to `.gsd/metrics/heartbeat-{phase}.jsonl`, keeping its current line format (`{phase, status/event, ts, agent}`). This ADR reserves the path; the move itself is roadmap step 5, and `gsd:stall-detector` + `master-v3` paths update together when it lands. Heartbeat lines are operational telemetry, not MetricsSnapshots — the two streams stay separate.

## Consequences

- The metrics the mission-loop design called for (success rate, autonomous completion %, average retries, regression rate) become one `jq`/pandas query over a JSONL file.
- Denormalizing a few contract fields into the row trades bytes for queryability — accepted; the `contract_id` link preserves the full record.
- Cross-engine comparison (GSD Master vs future adapters) is built in via the `engine` field, supporting the Execution Engine Interface goal (INV-4 context, though this ADR doesn't itself touch that invariant).

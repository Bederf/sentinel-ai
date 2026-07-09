# ADR-001: ExecutionContract v1

**Status:** Accepted (ratified 2026-07-09) | **Date:** 2026-07-09
**Invariants touched:** INV-3, INV-4, INV-6, INV-7, INV-11, INV-12

## Context

Every invocation of an Execution Engine must yield a contract (INV-6) — it is the sole channel through which the Mission layer perceives execution. GSD Master v3 already emits a 28-field contract (`skills/gsd/master-v3.md` `<execution_contract>`), but it is a flat, GSD-specific, prompt-rendered YAML block: the Mission Controller would have to know GSD internals (waves, strategies, reconciliation) to parse it, violating INV-4 (engines replaceable without changing the controller).

## Decision

Define **ExecutionContract v1**: a JSON artifact with an engine-agnostic **required core** and an optional **`engine_detail`** extension object for engine-specific fields. The Mission Controller reads only the core; dashboards and humans may read `engine_detail`.

### Schema conventions (normative for all five runtime schemas, ADR-001..005)

1. Format: JSON, UTF-8, one artifact per file (JSONL for append-only streams).
2. Every artifact carries `schema` (dotted type id) and `schema_version` (integer) — INV-12.
3. Timestamps: ISO 8601 UTC (`2026-07-09T14:00:00Z`).
4. **Compatibility policy:** consumers MUST tolerate unknown fields (forward-tolerant reads). Producers MUST emit every required field. Adding an optional field is allowed within a version. Removing/renaming a required field, or changing a field's semantics, requires a version bump and a documented migration.
5. Identifiers: `{type}-{utc-compact-ts}-{4-char-suffix}` (e.g., `ec-20260709T140000Z-a1b2`).

### Fields — required core

| Field | Type | Description |
|---|---|---|
| `schema` | string | `"gsd.execution-contract"` |
| `schema_version` | int | `1` |
| `contract_id` | string | Unique id (convention 5) |
| `engine` | string | Engine id, e.g. `"gsd-master-v3"`, `"claude-code"`, `"human-team"` |
| `engine_version` | string | Engine implementation version |
| `work_unit` | object | `{type: "phase", ref: "220", artifact_root: "vault"}` — what was executed |
| `status` | enum | `completed` \| `validation_failed` \| `execution_failed` |
| `failure_point` | string\|null | Named failure point; MUST be non-null when status ≠ completed (INV-7) |
| `next_action` | string\|null | Concrete resolution command; MUST be non-null when status ≠ completed (INV-7) |
| `started_at` / `completed_at` | timestamp | Run boundaries |
| `duration_seconds` | number | Wall-clock duration |
| `gates` | array | `[{name, passed: bool}]` — every gate the engine ran, in order |
| `work_completed` | object | `{units_attempted: int, units_completed: int}` (plans for GSD) |
| `tokens` | object | `{budget: int, used: int}` — 0 when unknown |
| `artifacts` | array | Paths/refs produced (commits, files, evidence bundle id) |

### Fields — optional

| Field | Type | Description |
|---|---|---|
| `task_id` | string | Harness task id if one exists |
| `evidence_bundle_id` | string | Link to EvidenceBundle (ADR-004) |
| `confidence` | object | Reserved for ConfidenceReport (future ADR; INV-9 applies) |
| `engine_detail` | object | Engine-specific fields; opaque to the Mission Controller |

### GSD Master v3 field mapping

Core: `status`→`status`; `failure_point`/`next_action` unchanged; `started_at`/`completed_at`/`duration_seconds` unchanged; `pre_flight_passed`, `architecture_challenge_passed`, `wave_execution_passed`, `paranoid_review_passed` → `gates[]` entries; `plans_executed`/`plans_completed` → `work_completed`; `token_budget`/`actual_tokens_used` → `tokens`; `task_id` → optional `task_id`.

`engine_detail` (GSD-specific): `strategy`, `waves`, `workflows_enabled`, `subagent_count`, `convergence_method`, `adversarial_agents_count`, `plan_dependency_edges`, `reconciliation_events`, `regressions_caught`, `reviewer_model`, `autonomy_mix`, `stalls_detected`, `pre_flight_baseline_tests`, `pre_flight_blockers`.

## Producer / Consumer

- **Producer:** the Execution Engine (GSD Master natively; other engines via adapter).
- **Consumers:** Mission Controller (core only), MetricsSnapshot aggregation (ADR-005), Reflection, human audit.

## Storage & lifecycle

`.gsd/contracts/{work_unit_ref}/{contract_id}.json` — written once at run end, immutable thereafter (INV-5 audit trail; INV-11 runtime store). A run that crashes before writing a contract is detected by its checkpoint/heartbeat absence, not by a partial contract.

## Consequences

- GSD Master's report format gains a machine-readable twin; the human Markdown report remains but is derived from the JSON, not the source of truth.
- Engine adapters have a small, explicit target: populate the core, dump the rest into `engine_detail`.
- `failure_point`/`next_action` become schema-enforced, not conventions (INV-7).

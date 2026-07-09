# .gsd/ — GSD Runtime State

Machine-readable runtime artifacts for the GSD autonomous engineering system. **Transient execution state only** — persistent engineering knowledge (decisions, lessons, ADRs, specs) lives in the vault (`sentinel-vault/`), never here (INV-11).

Contents are gitignored; only this README is tracked.

## Layout

| Directory | Artifact | Schema | ADR |
|---|---|---|---|
| `state/` | `mission-{id}.json` — one mutable LoopState per mission, atomic rewrite | `gsd.loop-state` v1 | ADR-003 |
| `checkpoints/` | `{mission_id}/ckpt-{seq:04d}-{id}.json` — immutable, append-only, self-sufficient | `gsd.checkpoint` v1 | ADR-002 |
| `contracts/` | `{work_unit_ref}/{contract_id}.json` — one immutable ExecutionContract per engine run | `gsd.execution-contract` v1 | ADR-001 |
| `evidence/` | `{contract_id}/manifest.json` + hashed raw items | `gsd.evidence-bundle` v1 | ADR-004 |
| `metrics/` | `snapshots.jsonl` (append-only) + `heartbeat-{phase}.jsonl` (reserved, roadmap step 5) | `gsd.metrics-snapshot` v1 | ADR-005 |

## Ownership

Two producers, disjoint zones — neither writes the other's:

- **Execution Engine** (GSD Master or adapter) → `contracts/`, `evidence/`, `metrics/` — products of execution belong to the engine.
- **Mission Controller** → `state/`, `checkpoints/` — progress governance belongs to the controller. Engines never read or write LoopState (INV-1/INV-2 boundary).

## Rules

- Every artifact carries `schema` + `schema_version` (INV-12). No ad-hoc JSON.
- Contracts, checkpoints, and evidence bundles are **never mutated or deleted mid-mission** (INV-5, INV-10).
- `state/` holds **execution state only** — progress of work (position, statuses, attempts, budget consumption). The objective and roadmap themselves are vault knowledge; LoopState's `goal` is a traceability snapshot referencing the vault authority (ADR-003 state taxonomy).
- **No runtime environment state anywhere under `.gsd/`** — loaded prompts, model config, caches, routing are reconstructed from configuration each run, never persisted here.
- No `memory/` directory — lessons learned go to the vault. If you're about to write knowledge here, stop (INV-11).
- Schema definitions and compatibility policy: `docs/12-development/gsd-master/adr-00{1..5}-*.md`
- Invariants: `docs/12-development/gsd-master/system-invariants.md`

# ADR-004: EvidenceBundle v1

**Status:** Accepted (ratified 2026-07-09) | **Date:** 2026-07-09
**Invariants touched:** INV-5, INV-6, INV-11, INV-12
**Conventions:** inherits schema conventions from ADR-001.

## Context

Reviews in GSD are evidence-driven, and INV-5 requires every autonomous action to be reconstructable. Today the evidence behind a "review passed" verdict (test output, diffs, reviewer findings) evaporates with the session — the contract asserts `paranoid_review_passed: true` but nothing can substantiate it later. An ExecutionContract without inspectable evidence is a claim, not a record.

## Decision

Define **EvidenceBundle v1**: a manifest + raw-file directory that captures the evidence a contract's verdicts rest on. The manifest is the schema'd artifact; raw files are stored beside it and integrity-hashed.

### Manifest fields — required

| Field | Type | Description |
|---|---|---|
| `schema` | string | `"gsd.evidence-bundle"` |
| `schema_version` | int | `1` |
| `bundle_id` | string | Unique id |
| `contract_id` | string | The ExecutionContract (ADR-001) this evidence substantiates |
| `created_at` | timestamp | |
| `items` | array | One entry per evidence file — see below |

### `items[]` entry — required per item

| Field | Type | Description |
|---|---|---|
| `type` | enum | `test_run` \| `diff` \| `review` \| `command_output` \| `log` \| `screenshot` \| `report` |
| `path` | string | Relative path within the bundle directory |
| `sha256` | string | Hash of the file at capture time — tamper-evidence |
| `producer` | string | Which component captured it (e.g. `gsd-master-v3/step6`, `validator-teammate`) |
| `captured_at` | timestamp | |
| `summary` | string | One line: what this item shows (e.g. `"pytest: 412 passed, 0 failed"`) |
| `verdict_ref` | string\|null | Gate name in the contract this item supports (e.g. `paranoid_review`); null for context items |

## Producer / Consumer

- **Producers:** Execution Engine steps that generate verdicts (pre-flight baseline, reconciliation, paranoid review) and Validation-loop teammates (test runs, lint, diffs). The engine assembles the bundle and writes the manifest last, then links it via the contract's `evidence_bundle_id`.
- **Consumers:** independent Reviewer (evaluates outcomes without trusting the executor's self-report — the anti-self-deception path), Mission Controller reflection, human audit.

## Storage & lifecycle

```
.gsd/evidence/{contract_id}/
├── manifest.json          # this schema
├── test-baseline.txt      # raw items, named by producer
├── review-findings.md
└── ...
```

- Raw items are written as they are captured; the manifest is written **once, last** — a bundle without a manifest is incomplete by definition and must not be cited by a contract.
- Immutable after manifest write (INV-5). Hash mismatch on read = escalate, don't repair.
- Large/binary evidence (>10 MB) is summarized into a small item plus a pointer; `.gsd/` is a state store, not blob storage.
- Retention follows the parent contract (archived together).

## Consequences

- "Evidence-driven review" becomes literal: the Reviewer's input is the bundle, not the executor's narrative.
- The `verdict_ref` link means every `gates[].passed: true` in a contract can name the files that prove it.
- Modest write overhead per phase (copying test output and diffs) — accepted; these files already exist transiently.

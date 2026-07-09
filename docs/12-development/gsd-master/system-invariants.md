# GSD System Invariants

**Version:** 1.0 | **Ratified:** 2026-07-09 | **Status:** Active

This document is the constitution of the GSD autonomous engineering system (Mission Controller + Execution Engines + supporting loops). Unlike ADRs, which explain *why* a decision was made and can be superseded, invariants define what must **always remain true** regardless of future refactoring, model upgrades, or new execution engines.

Position in the documentation stack:

1. **Vision** — why the platform exists
2. **Architectural Invariants** — this document; rules that never change
3. **ADRs** — why specific design decisions were made (must not contradict invariants)
4. **Interfaces** — contracts between components
5. **Implementations** — GSD Master, Mission Controller, etc.

Design sources: `mission-loop-architecture` memory (Step 0 proposal) + v4 Runtime Layer Decisions ratified 2026-07-09.

---

## A. Separation of Control

### INV-1 — The Mission Controller never edits source code directly

The Mission Loop governs *between* work units, never *within* them. All code changes flow through an Execution Engine.

- **Rationale:** The strategic/operational boundary is the system's core architectural contribution. A controller that "just fixes one thing" has collapsed the boundary and become an unauditable second executor.
- **Violation looks like:** Mission Controller calling Edit/Write on repo files; a "quick fix" applied during phase evaluation.

### INV-2 — Execution Engines never decide project goals

An Execution Engine receives a structured work unit and executes it. It may escalate ("this phase seems wrong"), but the decision to change goals, reorder phases, or abandon a mission belongs to the Mission Controller (and ultimately the human).

- **Rationale:** Prevents responsibility leakage upward. An executor that silently redefines its objective destroys goal traceability.
- **Violation looks like:** GSD Master rewriting phase acceptance criteria mid-run; an engine skipping a phase because it "judged it unnecessary."

### INV-3 — Every loop implements the uniform contract: Input → Execution → Output → Exit → Escalate

All five layers (Mission, Phase, Wave, Execution/Ralph, Validation) expose the same contract shape.

- **Rationale:** Composability. A parent loop needs to know only the contract, never the child's internals.
- **Violation looks like:** A loop with no defined Escalate condition (failures disappear); a loop whose Exit condition is "the model decides it's done" with no checkable criterion.

### INV-4 — Execution Engines are replaceable without changing the Mission Controller

GSD Master is the *reference implementation* of the Execution Engine Interface, not "the engine." Claude Code, Codex CLI, OpenHands, or a human team must be pluggable via an adapter that satisfies the same contract.

- **Rationale:** Couples the Mission layer to a contract, not a product. This is what makes the architecture durable across tooling churn.
- **Violation looks like:** Mission Controller reading GSD-internal files (wave state, teammate logs) instead of the Execution Contract; GSD-specific fields required by the controller with no interface equivalent.

---

## B. Auditability

### INV-5 — Every autonomous action is auditable

Any action taken without a human in the loop must leave a record sufficient to reconstruct *what* was done, *when*, *by which component*, and *on whose authority* (which goal/phase authorized it).

- **Rationale:** SENTINEL is a live production system controlling physical buildings. Autonomy without audit is not acceptable at any layer, including the meta-layer that builds the system.
- **Violation looks like:** A retry that leaves no trace it happened; state mutated in memory only; an agent action attributable to no phase.

### INV-6 — Every execution produces an Execution Contract

No work unit completes silently. Every invocation of an Execution Engine yields a contract (status, metrics, artifacts, failure point if any) conforming to the canonical schema (ExecutionContract v1+).

- **Rationale:** The contract is the sole channel through which the Mission layer perceives execution. If it's optional, the Mission layer is blind.
- **Violation looks like:** A phase that "finished" but has no contract on disk; a crashed run with neither contract nor checkpoint.

### INV-7 — Failures terminate at named failure points with a `next_action`

Every failure mode has an explicit, named failure point and a machine-readable next action. Silent retry loops and unnamed failures are prohibited.

- **Rationale:** Elevated from GSD Master's existing design strength. Named failure points are what make escalation deterministic and retries classifiable (transient vs fatal).
- **Violation looks like:** A generic "phase failed" with no failure point; unbounded retry without classification; an error swallowed and reported as success.

---

## C. Human Authority

### INV-8 — Human override is always possible

At every layer, a human can pause, redirect, or terminate the system, and the system must stop cleanly (checkpointing state per INV-10).

- **Rationale:** Graded autonomy is only safe if the grade can be set to zero at any moment.
- **Violation looks like:** A loop that cannot be interrupted without corrupting state; an approval gate that can be configured away without an explicit human decision.

### INV-9 — Confidence is advisory, not authoritative

ConfidenceReports inform the Mission layer's next action; they never bypass a human approval gate. High confidence lowers friction, it does not grant authority.

- **Rationale:** Confidence is self-reported by the same class of system being governed. Treating it as authority is self-certification.
- **Violation looks like:** `overall_confidence ≥ 0.8` auto-approving an Architecture Challenge blocker; confidence thresholds substituted for a required human gate.

---

## D. State & Persistence

### INV-10 — State changes are checkpointed before irreversible actions

Before any action that cannot be undone (external side effects, deletions, publishes, deployments), current loop state is persisted so the system can resume from the pre-action point.

- **Rationale:** Resumability is a design goal (v4 roadmap step 4); it is only achievable if checkpointing precedes irreversibility, not follows it.
- **Violation looks like:** A deploy performed with the only record of intent in conversation context; a checkpoint written after the side effect it describes.

### INV-11 — One knowledge system: vault for knowledge, `.gsd/` for runtime state

Persistent engineering knowledge (decisions, lessons, ADRs, specs, phase history) lives in the vault. Transient execution state (LoopState, Checkpoints, ExecutionContracts, evidence, metrics) lives in `.gsd/`. There is no third store, and neither store duplicates the other's content.

- **Rationale:** Ratified 2026-07-09. A second long-lived memory store diverges from the vault; runtime state scattered into Markdown documentation is unparseable. The boundary is the mental model.
- **Violation looks like:** A `.gsd/memory/` directory; lessons-learned files under `.gsd/`; machine-consumed JSON state committed into vault notes.

### INV-12 — Every runtime artifact conforms to a versioned canonical schema

No runtime artifact (ExecutionContract, Checkpoint, LoopState, EvidenceBundle, MetricsSnapshot) exists without a schema declaring: version, required fields, compatibility policy, producer, consumer. Artifacts carry their schema version.

- **Rationale:** Ratified 2026-07-09 (schema-first milestone). Directories are cheap; schemas are expensive. Unversioned artifacts make resume-after-upgrade undefined behavior.
- **Violation looks like:** Ad-hoc JSON written to `.gsd/state/` with no schema; a schema changed without a version bump; a consumer parsing fields not in the producer's declared schema.

---

## Enforcement

- **ADR gate:** every ADR must state which invariants it touches and demonstrate compliance; an ADR that contradicts an invariant is rejected or the invariant is formally amended first.
- **Review gate:** phase reviews (Architecture Challenge, precheck) check changed components against this list.
- **Escalation:** any component detecting an invariant violation at runtime escalates immediately (INV-3's Escalate path); it does not work around it.

## Amendment Policy

Invariants change only by explicit human decision, recorded here with date, rationale, and the ADRs affected. Additions are appended with new numbers; existing numbers are never reused or renumbered. Superseded invariants are struck through, never deleted.

## Changelog

- **1.0 (2026-07-09)** — Initial ratification. INV-1..10 from the mission-loop-architecture Step 0 proposal; INV-11..12 from the v4 Runtime Layer Decisions (vault/`.gsd/` boundary, schema-first).

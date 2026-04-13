---
title: GSD Pipeline Architecture
category: development
created: 2026-03-14
updated: 2026-04-12
phase: 155-156
---

# GSD Pipeline Architecture

The GSD (Get Shit Done) master pipeline orchestrates phase execution through wave-based plan scheduling with iterative self-correction (Ralph Loop) and multi-agent verification.

## Pipeline Stages

```
Discovery → Planning → [2b] Physical Scan → [3] Architecture Challenge → Execution (Ralph Loop) → [5] Control Validation → [6] Paranoid Review → Documentation
```

Each stage operates on a different information source to maintain orthogonal validation.

## Orchestration Model

The `gsd:master` skill coordinates phase execution:

1. **Discover plans** in the phase directory
2. **Group by wave** (from plan frontmatter)
3. **Architecture Challenge** — pre-execution pressure test (Explore agent)
4. **Execute waves** — each plan runs via Ralph Loop with teammates
5. **Paranoid Review** — post-execution edge-case discovery (Explore agent)
6. **Update docs** — system documentation for shipped features

### Wave Execution

Plans within a wave run in parallel. Waves execute sequentially. Each plan spawns as an independent agent with full Ralph Loop context.

### Execution Modes

Plans are classified by complexity score (assessed in the Root Cause Packet on first iteration):

| Score | Mode | Teammates | Use Case |
|-------|------|-----------|----------|
| 1-2 | Skip teammates | None | CRUD, scaffolding, simple pipelines |
| 3-4 | Standard | 4 agents | Multi-service integration, schema changes |
| 5-6 | Full Ralph | 4 agents + escalation | Math/heuristics, concurrency, distributed state |

**Dynamic escalation:** If runtime signals appear (test failure, cross-module dependency, schema change, retry), execution mode upgrades one level regardless of initial score.

## Verification Layers (Orthogonal Validation)

Each verification layer checks the system from a **different model of truth**. No two layers verify the same assumption.

| Layer | Model of Truth | Information Source |
|-------|---------------|-------------------|
| Architecture Challenge | Design principles | Plans + PROJECT.md + KEY_LEARNINGS.md |
| Teammate 1: Validator | Implementation behavior | Runtime output (compile, lint, test) |
| Teammate 2: Progress | Execution trajectory | Git log vs plan task count |
| Teammate 3: Code Reviewer | Code correctness + invariants | Diff patterns + CLAUDE.md + system laws |
| Teammate 4: Spec Guard | Plan specification | Plan spec vs actual changes |
| Rule 5: Adversarial Check | Failure discovery | Edge-case inputs + invariant validation |
| Paranoid Review | User-facing behavior | Error handling, display, config, concurrency |

### Why Orthogonal

If two layers validate the same model, they cannot catch each other's mistakes. This leads to:

- **Correlated validation** — tests validate plan, reviews validate tests, confidence rises but defects escape
- **Metric drift** — pipeline optimizes measured metrics instead of actual correctness

Orthogonal validation prevents both by ensuring at least one layer evaluates from a different assumption space.

### Boundary Rules

- **Validator** must NOT read the plan — evidence comes from runtime only
- **Reviewer** must NOT check plan alignment — that is Spec Guard's job
- **Spec Guard** must NOT judge code quality — that is the Reviewer's job

## Architecture Challenge

Pre-execution checkpoint that catches "building the wrong thing" before code is written.

Checks: single points of failure, error path coverage, display correctness, simplest approach, config validation, intent classification.

**Pre-report verification:** Before reporting a BLOCKER, the challenge agent must search plans and codebase for existing mitigations. Only report if unaddressed.

## Paranoid Review

Post-execution checkpoint that catches what tests miss.

Checks: silent error swallowing, state consistency, user-facing display (timezones, sort order, null handling), config sensitivity, rate limits, concurrency races, scope drift.

## Ralph Loop (Iterative Execution)

Each plan executes via Ralph Loop — an iterative cycle where each iteration:

1. Checks progress (git log + file existence)
2. Spawns teammates (unless first iteration or low complexity)
3. Acts on teammate findings (fix regressions, review blocks, spec drift)
4. Works on next incomplete task
5. Commits atomically

The loop continues until all tasks complete or iteration budget exhausts.

### Iteration Budget

| Complexity | Tasks | Max Iterations |
|------------|-------|----------------|
| Simple | 2-3 | 6-9 (tasks x 3) |
| Standard | 2-3 | 8-12 (tasks x 3-4) |
| TDD | 2-3 | 10-15 (tasks x 5) |
| Complex | 2-3 | 10-15 (tasks x 4-5) |

## v1.1 Security Gate Chain (2026-04-12)

Four security gates added to the pipeline. Gates run at orchestrator level — not inside Ralph Loop (complexity scoring cannot skip them).

| Step | Gate | Output Fields | Hard Stop Trigger |
|------|------|--------------|-------------------|
| 2b | Physical Scan | `physical_impact: true/false` | None (detection only) |
| 3 | Architecture Challenger | `exploitability_band`, `confidence_score`, `physical_safety_verified` | `physical_safety_verified: false` |
| 5 | Control Validator | `contamination_clean`, `gate_status`, `contamination_physical_block` | `contamination_physical_block: true` or `gate_status: BLOCK` + `physical_impact` |
| 6 | Paranoid Review | Standard findings | Only reached if all gates pass |

**Hard stop policy:** Regular BLOCKERs are user-overridable. Physical safety gates are not — safety interlock bypass and credential-in-physical-path are non-negotiable halts.

**Physical=YES files** (from `docs/09-security/control-matrix.md` Section B): `services/approval_service.py`, `services/safety_interlocks.py`, `services/quality_gate_evaluator.py`, `services/tier_routing_engine.py`, `api/approval_workflow.py`, `api/remote_commands.py`, `api/autonomous.py`, `api/optimization.py`

**Contamination checks (Step 5):** credential leak, unsafe RNG, hardcoded network addresses, cross-wave copied blocks (sha256sum fingerprint), scratch file residue.

**Gate verdicts log:** `docs/improvement-loops/{date}-gate-verdicts.md` — populated after each Physical=YES phase for calibration tracking.

## Known Pipeline Risks

### 1. Complexity Drift
Static scoring estimates complexity before execution. Runtime behavior may differ.
**Mitigation:** Dynamic escalation on runtime signals.

### 2. Correlated Validation
Tests validate plan, reviews validate tests — all check same assumptions.
**Mitigation:** Orthogonal validation with explicit boundary rules per layer.

### 3. Metric Drift (Goodhart's Law)
Pipeline optimizes measured metrics instead of actual system quality.
**Mitigation:** Adversarial checks and invariant validation provide external correctness signals not derived from the plan.

## File Locations

| File | Purpose |
|------|---------|
| `~/.claude/commands/gsd/master.md` | Orchestrator skill |
| `~/.claude/commands/gsd/ralph-plan.md` | Ralph loop runner |
| `~/.claude/get-shit-done/templates/ralph-gsd-prompt.md` | Execution template (canonical source) |
| `~/.claude/get-shit-done/templates/summary.md` | Summary template |
| `~/.claude/get-shit-done/workflows/execute-phase.md` | Wave execution workflow |
| `~/.claude/get-shit-done/references/principles.md` | GSD principles |

## Related

- [Development Patterns](./DEVELOPMENT_PATTERNS.md) — code-level patterns enforced by the pipeline
- [tool-use-best-practices](./tool-use-best-practices.md) — MCP tool usage patterns

---
title: GSD Master v3.0 — Dynamic Workflows (MVP)
---

Overview
- Step 0: Load phase metadata (no structural validation)
- Step 1: Create orchestration task (TaskCreate → task_id)
- Step 2: Strategy selection by scope
- Step 3: Architecture Challenge (scoped, optional)
- Step 3.5: Load plan-dependencies.json (vault)
- Step 4: Build DAG (plans + depends_on)
- Step 5: Execute DAG-respecting waves (topological levels)
- Step 6: Paranoid Review (Opus)
- Step 7: Return execution contract (expanded)
- Step 8: Fast-path for COMPLETED

Strategy Selection
```
≤3 plans        → FIXED_WAVES (1 agent/plan)
≤8 plans        → DYNAMIC_LIGHT (1 agent/plan)
≤20 plans       → DYNAMIC_FULL (2 agents/plan, convergence — deferred)
>20 plans       → DYNAMIC_MASSIVE (3 agents/plan + adversarial — deferred)
```

Dynamic Workflows (MVP)
- DAG-based scheduling from plan-dependencies.json
- Waves derived from topological levels
- Reconciliation after each wave (if ≥2 nodes)
- Stall detector integration between waves
- Paranoid Review after all waves

Execution Contract (v3 additions)
```
workflows_enabled: boolean
strategy: FIXED_WAVES | DYNAMIC_LIGHT | DYNAMIC_FULL | DYNAMIC_MASSIVE
subagent_count: number
convergence_method: string
adversarial_agents_count: number
token_budget: number
actual_tokens_used: number
plan_dependency_edges: number
reconciliation_events: number
reviewer_model: opus
autonomy_mix: string (ralph=N, standard=N)
stalls_detected: number
```

Plan Dependencies File
- Path: `sentinel-vault/00-GSD-Phases/Phase-{N}/plan-dependencies.json`
- See separate spec in this folder.

Deferred (Phase 212+)
- Convergence/adversarial agents
- Token accounting enforcement
- /goal integration and resume flags

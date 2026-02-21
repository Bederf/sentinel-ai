---
title: "Site-002 deterministic mode policy dry-run"
type: "spec"
status: "approved"
version: "1.1.0"
created: "2026-02-21"
updated: "2026-02-21"
author: "Sentinel Development Team"
tags: ["site-002", "onboarding", "ingestion", "monitoring", "fail-closed", "scheduler"]
related:
  [
    "phase-implementations.md",
    "ai-assisted-onboarding.md",
    "../05-integrations/SIMBIOT_ONBOARDING_CHECKLIST.md",
    "../10-operations/monitoring-stack.md"
  ]
domain: "bms"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 10
---

# Phase 109C: Site-002 deterministic mode policy dry-run

Phase 109C introduces a deterministic promotion and demotion policy for Site-002 onboarding stages. This phase is **observability-only** and does not execute control writes.

For maintenance and technician workflows, Site-002 uses a separate deterministic scope policy:
major-equipment-first guided inspection (Tier A/B/C) as documented in
`109D-maintenance-closed-loop-flow.md` and `../05-integrations/SIMBIOT_ONBOARDING_CHECKLIST.md`.

## Scope

- Define stage thresholds in policy JSON
- Evaluate rules against live monitoring KPIs
- Persist stage state for dwell windows and anti-flap logic
- Run every 5 minutes in scheduler
- Log decisions only

Out of scope:

- No automatic `INGESTION_MODE` mutation
- No enforced control path changes
- No write execution based on policy outcome

## Stage flow

`commissioning -> shadow_live -> supervised -> automatic`

## Threshold policy

Policy file: `backend/app/data/policies/site-002-mode-policy.json`

### 1) `commissioning -> shadow_live`

- `commissioning_all_gates_passed = true`
- `consecutive_pass_days >= 2`
- `truth_check_required = true`

### 2) `shadow_live -> supervised`

- Promotion dwell: `>= 12h`
- Promotion thresholds:
- `freshness_hours <= 2.0`
- `match_coverage_pct >= 95.0`
- `error_rate_pct <= 1.0`
- `file_manual_sources <= 0`
- `commissioning_all_gates_passed = true`
- `consecutive_pass_days >= 2`
- `quality_gate_status in [pass, warn]`
- Exit thresholds (demote to `commissioning` after `>= 2h` sustained violation):
- `freshness_hours <= 4.0`
- `match_coverage_pct >= 90.0`
- `error_rate_pct <= 2.0`
- `file_manual_sources <= 0`

### 3) `supervised -> automatic`

- Promotion dwell: `>= 24h`
- Promotion thresholds:
- `freshness_hours <= 0.5`
- `match_coverage_pct >= 98.0`
- `error_rate_pct <= 0.5`
- `file_manual_sources <= 0`
- `conflict_events_24h <= 0`
- `commissioning_all_gates_passed = true`
- `consecutive_pass_days >= 2`
- `quality_gate_status in [pass]`
- Exit thresholds (demote to `shadow_live` after `>= 1h` sustained violation):
- `freshness_hours <= 2.0`
- `match_coverage_pct >= 95.0`
- `error_rate_pct <= 1.0`
- `file_manual_sources <= 0`
- `conflict_events_24h <= 1`

### 4) `automatic` fail-closed condition

Immediate demotion to `supervised` with decision `would_fail_closed_demote` and `write_action=stop_writes` when any fail-closed threshold is violated:

- `freshness_hours <= 1.0`
- `match_coverage_pct >= 97.0`
- `file_manual_sources <= 0`
- `conflict_events_24h <= 0`
- `quality_gate_status in [pass]`

## Anti-flapping stability rule

After any demotion, promotion is blocked for:

- `repromotion_stability_hours = 24`

This prevents rapid stage oscillation.

## Runtime components

- Policy definition: `backend/app/data/policies/site-002-mode-policy.json`
- Evaluator: `backend/app/services/site_mode_policy_service.py`
- Scheduler job registration: `backend/app/services/background_scheduler.py`
- Startup wiring: `backend/app/startup/events.py`
- State file output: `backend/app/data/policies/site-002-mode-policy-state.json`

## Decision outputs

Evaluator returns one of:

- `hold`
- `would_promote`
- `would_demote`
- `would_fail_closed_demote`

Each response includes:

- `state_before`
- `state_after`
- `target_stage`
- `reasons[]`
- `write_action` (`none` or `stop_writes`)

## Verification

```bash
# Load policy
cd /opt/bms-intelligence/backend
python3 - <<'PY'
from app.services.site_mode_policy_service import SiteModePolicyService
svc = SiteModePolicyService()
print(svc.load_policy("site-002")["version"])
PY

# Run unit tests
pytest tests/services/test_site_mode_policy_service.py -q

# Inspect persisted dry-run state
cat app/data/policies/site-002-mode-policy-state.json
```

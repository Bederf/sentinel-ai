---
title: "Site-002 deterministic mode policy"
type: "spec"
status: "approved"
version: "1.3.0"
created: "2026-02-21"
updated: "2026-06-05"
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

# Phase 109C: Site-002 deterministic mode policy

Phase 109C drives Site-002 through a deterministic promotion and demotion lifecycle. Policy evaluation runs every 5 minutes. With `dry_run: false`, the policy actively writes stage transitions to Supabase and blocks manual operator advancement when policy gates are not satisfied.

## Scope

- Define stage thresholds in policy JSON
- Evaluate rules against live monitoring KPIs every 5 minutes
- Persist stage state for dwell windows and anti-flap logic
- Promote/demote automatically when `dry_run: false` (writes to Supabase)
- Block manual phase advancement when policy gates are not satisfied (via `PATCH /api/sites/{site_id}/phase`)
- Sync promoted stage back to Supabase `sites.onboarding_phase`

Out of scope:

- No direct `INGESTION_MODE` mutation from this service
- No enforced control path changes based on policy outcome
- No write execution based on policy outcome (write safety is handled by the quality gate in the control pipeline)

## Stage flow

`commissioning -> shadow_live -> advisory -> supervised -> automatic`

The `advisory` stage was added in policy `v1.1.0` and sits between `shadow_live` and `supervised`.

## Calendar maturity gate (v1.3.0)

Each mode transition has a `min_calendar_days` requirement based on the site's building type. The clock starts when the site enters the current mode (`stage_entered_at` timestamp in the policy state file). This ensures the system observes enough operational variation before allowing promotion.

Building type → minimum calendar days per mode:

| Mode Transition | Office | Hospital |
|----------------|--------|----------|
| `shadow_live -> advisory` | 30 days | 60 days |
| `advisory -> supervised` | 30 days | 60 days |

The `stage_entered_at` timestamp is set automatically whenever the site's `current_stage` changes (promotion, demotion, or sync from Supabase). Implemented in `SiteModePolicyService._load_state()` and all stage transition points in `evaluate_site()`.

## Threshold policy

Policy files: `backend/app/data/policies/site-{id}-mode-policy.json` (per-site configuration)

### 1) `commissioning -> shadow_live`

- `commissioning_all_gates_passed = true`
- `consecutive_pass_days >= 2`
- `truth_check_required = true` — requires operator to submit a passing truth check via `POST /api/buildings/{site_id}/truth-check`

### 2) `shadow_live -> advisory`

- Promotion dwell: `>= 12h`
- Promotion thresholds:
  - `freshness_hours <= 2.0`
  - `match_coverage_pct >= 95.0`
  - `error_rate_pct <= 1.0`
  - `file_manual_sources <= 0`
  - `commissioning_all_gates_passed = true`
  - `consecutive_pass_days >= 2`
  - `min_calendar_days >= N` — calendar days in current stage (per building type)
  - `quality_gate_status in [pass, warn]`
- Exit thresholds (demote to `shadow_live` after `>= 2h` sustained violation):
  - `freshness_hours <= 4.0`
  - `match_coverage_pct >= 90.0`
  - `error_rate_pct <= 2.0`
  - `file_manual_sources <= 0`

### 3) `advisory -> supervised`

- Promotion dwell: `>= 24h`
- Promotion thresholds:
  - `freshness_hours <= 1.0`
  - `match_coverage_pct >= 97.0`
  - `error_rate_pct <= 1.0`
  - `file_manual_sources <= 0`
  - `conflict_events_24h = 0`
  - `commissioning_all_gates_passed = true`
  - `consecutive_pass_days >= 2`
  - `min_calendar_days >= N` — calendar days in current stage (per building type)
  - `quality_gate_status in [pass, warn]`
- Exit thresholds (demote to `shadow_live` after `>= 2h` sustained violation):
  - `freshness_hours <= 3.0`
  - `match_coverage_pct >= 92.0`
  - `error_rate_pct <= 1.5`
  - `file_manual_sources <= 0`

### 4) `supervised -> automatic`

- Promotion dwell: `>= 24h`
- Promotion thresholds:
  - `freshness_hours <= 0.5`
  - `match_coverage_pct >= 98.0`
  - `error_rate_pct <= 0.5`
  - `file_manual_sources <= 0`
  - `conflict_events_24h = 0`
  - `commissioning_all_gates_passed = true`
  - `consecutive_pass_days >= 2`
  - `quality_gate_status in [pass]` — note: `warn` is not accepted at this stage
- Exit thresholds (demote to `shadow_live` after `>= 1h` sustained violation):
  - `freshness_hours <= 2.0`
  - `match_coverage_pct >= 95.0`
  - `error_rate_pct <= 1.0`
  - `file_manual_sources <= 0`
  - `conflict_events_24h <= 1`

### 5) `automatic` fail-closed condition

Immediate demotion to `supervised` with decision `would_fail_closed_demote` and `write_action=stop_writes` when any fail-closed threshold is violated:

- `freshness_hours <= 1.0`
- `match_coverage_pct >= 97.0`
- `file_manual_sources <= 0`
- `conflict_events_24h = 0`
- `quality_gate_status in [pass]`

## Severity filtering for `safety_violations_24h`

`safety_violations_24h` (included in `conflict_events_24h`) counts only **CRITICAL-level** safety rejections from SENTINEL's audit log. WARNING-level and unclassified entries are excluded.

This means:

- A WARNING-level safety rejection (`escalation_level = "warning"`) does **not** block stage advancement
- A CRITICAL-level safety rejection (`escalation_level = "critical"`) **does** block advancement past the `advisory -> supervised` gate (where `conflict_events_24h = 0` is required)
- Normal BMS alarms are **not** counted — this metric tracks only SENTINEL's own safety decisions, not external BMS alarm states

This behavior is implemented in `MonitoringService._collect_control_kpis()` (filters on `entry.escalation_level == "critical"`) and `AuditLogEntry.escalation_level` (field added in `audit_log.py`).

## Anti-flapping stability rule

After any demotion, promotion is blocked for `repromotion_stability_hours = 24`.

This prevents rapid stage oscillation.

## Manual advancement gate

`PATCH /api/sites/{site_id}/phase` (the OnboardingPhaseSettings UI component) validates the current stage's promotion entry thresholds **before** writing to Supabase. If any gate has not passed, the request is rejected with `400` and structured detail:

```json
{
  "error": "Policy gates not satisfied",
  "current_stage": "commissioning",
  "requested": "shadow_live",
  "gates_pass": false,
  "failed_gates": [
    {"rule": "truth_check_passed", "passed": false, "actual": false, "expected": true},
    {"rule": "consecutive_pass_days_min", "passed": false, "actual": 0, "expected": 2}
  ],
  "message": "Policy gates not satisfied for commissioning. Cannot advance until all gates pass. Failed: truth_check_passed, consecutive_pass_days_min."
}
```

The frontend displays this as a Sonner error toast: *"Site mode advancement blocked."* with the detail message.

Implementation:
- `SiteModePolicyService.get_gate_status()` — evaluates current stage entry thresholds, returns per-gate pass/fail
- `update_site_phase()` — calls `get_gate_status()` before writing; raises `HTTPException(400)` on gate failure
- `OnboardingPhaseSettings.tsx` — catches the error, shows `toast.error()` with specific failed gates

## Runtime components

- Policy definition: `backend/app/data/policies/site-002-mode-policy.json`
- Policy state: `backend/app/data/policies/site-002-mode-policy-state.json`
- Evaluator: `backend/app/services/site_mode_policy_service.py`
  - `evaluate_site()` — called every 5 min by scheduler; promotes/demotes when `dry_run: false`
  - `get_gate_status()` — called by `update_site_phase()` to gate manual advancement
- Scheduler job registration: `backend/app/services/background_scheduler.py`
- Startup wiring: `backend/app/startup/events.py`
- Phase transition API: `backend/app/api/sites.py` → `PATCH /api/sites/{site_id}/phase`

## Authority model (Phase 202)

- **Supabase `sites.onboarding_phase` is authoritative.** The PATCH endpoint and settings page write directly to Supabase.
- **State file follows Supabase.** `SiteModePolicyService._sync_state_from_supabase()` reads the Supabase phase on every `evaluate_site()` and `get_gate_status()` call. If the state file diverges, it's overwritten to match Supabase.
- **Settings page gated by password.** Site mode changes require admin password unlock (`POST /api/auth/verify-settings-password`). The dropdown uses a hold-to-confirm button (2-second hold) to prevent accidental changes.
- **Mode change syncs optimization settings.** When `onboarding_phase` is updated, `optimization_settings.mode` and `optimization_settings.control_tier` are automatically set to match:
  - `commissioning`/`shadow_live` → `monitor`
  - `advisory` → `advisory`
  - `supervised` → `supervised`
  - `automatic` → `automatic`

## Decision outputs

Evaluator returns one of:

- `hold`
- `would_promote`
- `would_demote`
- `would_fail_closed_demote`

Each response includes `state_before`, `state_after`, `target_stage`, `reasons[]`, `write_action` (`none` or `stop_writes`).

## Verification

```bash
# Load policy
cd /opt/bms-intelligence/backend
python3 - <<'PY'
from app.services.site_mode_policy_service import SiteModePolicyService
svc = SiteModePolicyService()
print(svc.load_policy("site-002")["version"])
PY

# Check current gate status
python3 - <<'PY'
import asyncio
from app.services.site_mode_policy_service import SiteModePolicyService
svc = SiteModePolicyService()
async def check():
    result = await svc.get_gate_status("site-002")
    print(result)
asyncio.run(check())
PY

# Inspect persisted policy state
cat app/data/policies/site-002-mode-policy-state.json

# Run unit tests
pytest tests/services/test_site_mode_policy_service.py -q
```

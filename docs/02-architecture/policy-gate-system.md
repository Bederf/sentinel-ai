---
title: "Policy Gate System Architecture"
type: "architecture"
status: "verified"
version: "1.0.0"
created: "2026-05-17"
updated: "2026-05-17"
tags: ["policy", "gates", "phase-promotion", "trust-ladder"]
domain: "backend"
audience: "developers"
complexity: "advanced"
estimated_read_time: 15
---

# Policy Gate System Architecture

## Overview

The policy gate system controls phase progression through the SENTINEL Trust Ladder (shadow → advisory → supervised → automatic). Gates are **prerequisites, not automation** — the system tells operators when they're ready, but humans decide when to promote.

## Core Principle

> **Gates are evaluated, not enforced. The operator has final authority.**

## Architecture

### 1. Gate Definition (Supabase: `phase_promotion_gates`)

**Source of truth:** Database table with one row per gate per transition.

```sql
SELECT * FROM phase_promotion_gates
WHERE site_id = 'site-002'
AND from_phase = 'shadow_live'
AND to_phase = 'advisory';
```

**Schema:**
- `site_id`: Which site this gate applies to
- `from_phase` / `to_phase`: Which transition this gate guards
- `gate_name`: Metric to evaluate (e.g., "ml_hours_ingested")
- `gate_type`: "threshold", "boolean", "count"
- `threshold_value`: Numeric threshold (e.g., 72)
- `operator`: ">=", "<=", ">", "<", "==", "==true", "==false"
- `enabled`: true/false (can disable without deleting)

### 2. Gate Evaluation (`GateEvaluationService`)

**File:** `backend/app/services/gate_evaluation_service.py`

**Flow:**
```
PATCH /api/sites/{site_id}/phase → advisory
  ↓
GateEvaluationService.evaluate_promotion(site_id, from_phase, to_phase)
  ↓
1. get_promotion_gates() → fetch from Supabase
2. _fetch_current_metrics() → query live data
3. _evaluate_gate() → for each gate:
   - Resolve metric value (e.g., sites.ml_hours_ingested)
   - Apply operator (e.g., 23.9 >= 72?)
   - Return pass/fail
4. gates_pass = all(gate.passed for gate in gates)
```

**Supported Metrics:**
- `ml_hours_ingested`: Total ML training hours (cumulative counter in `sites.ml_hours_ingested`, computed from persisted base + wall-clock time since process start — NOT a query against `equipment_sensor_readings` which has 24h retention)
- `bridge_connected`: BMS bridge connectivity boolean
- `anomaly_scores_writing`: Count of recent anomaly writes
- `freshness_hours_max`: Max data age in hours
- `match_coverage_min_pct`: Equipment match percentage
- `error_rate_max_pct`: Ingestion error rate
- `time_in_advisory_days`: Days in current phase
- `recommendations_generated`: Count of recommendations created
- `no_safety_violations_30d`: Boolean safety check
- `bridge_connected_uptime_pct`: Bridge availability
- And more...

**Operators:**
- `>=`, `<=`, `>`, `<`: Threshold comparison
- `==`, `!=`: Equality
- `==true`, `==false`: Boolean checks
- `in`: Membership in allowed_values list

### 3. Phase Transitions

#### shadow_live → advisory (4 gates)
All must pass:
1. `bridge_connected == true`
2. `freshness_hours_max <= 4.0`
3. `ml_hours_ingested >= 72`
4. `anomaly_scores_writing > 0` (in last 30min)

#### advisory → supervised (5 gates)
All must pass:
1. `time_in_advisory_days >= 30`
2. `ml_hours_ingested >= 500`
3. `recommendations_generated >= 50`
4. `no_safety_violations_30d == true`
5. `bridge_connected_uptime_pct >= 0.90`

#### supervised → automatic (6 gates)
All must pass:
1. `ml_hours_ingested >= 2000`
2. `approval_accuracy >= 0.85`
3. `false_positive_rate <= 0.10`
4. `recommendations_approved >= 30`
5. `no_safety_violations_7d == true`
6. `human_approved_autonomous == true`

### 4. Auto-Promotion vs Manual Promotion

#### Auto-Promotion (`PhasePromotionEvaluator`)

**File:** `backend/app/services/phase_promotion_evaluator.py`

**Schedule:** Runs every 5 minutes via `background_scheduler.py`

**Behavior:**
```python
# Evaluates gates for current phase
result = await evaluator.evaluate_site(site_id, current_phase)

if result.eligible:
    # Sets readiness flag ONLY
    client.table("sites").update({
        "phase_promotion_ready": True,
        "phase_promotion_ready_since": datetime.now().isoformat(),
        "phase_promotion_target": to_phase,
    })

    # Sends Telegram notification
    await notification_service.send_alert_direct(
        title=f"SENTINEL Phase Ready — {site_id}",
        body=f"Ready to advance: {from_phase} → {to_phase}",
    )

    # DOES NOT call promotion API
```

**Key Point:** Auto-promotion only **surfaces readiness**. It never flips the phase.

#### Manual Promotion (Operator via Settings)

**Flow:**
1. Operator sees readiness alert or checks dashboard
2. Goes to Settings → Site Mode
3. Holds button to confirm promotion
4. Frontend calls: `PATCH /api/sites/{site_id}/phase`
5. Backend re-evaluates gates (for logging)
6. Backend writes phase to Supabase (regardless of gate status)
7. Audit trail logged to `phase_transition_log`

**Override Behavior:**
```python
# In sites.py PATCH endpoint
gate_status = await policy_service.get_gate_status(site_id)

if gate_status.get("gates_pass") is False:
    # Log warning but don't block
    logger.warning(
        f"Manual phase change by user for {site_id}: "
        f"Policy gates not passed. User override applied."
    )

# Always proceed with phase update
client.table("sites").update({
    "onboarding_phase": requested_phase
}).eq("code", site_id).execute()
```

**Operator has authority** to override gate status from Settings page.

### 5. Dwell Timer (Safety Gate)

**Purpose:** Prevents flapping (violation → pass → violation → pass)

**Mechanism:**
```json
{
  "current_stage": "shadow_live",
  "candidate_stage": "advisory",
  "candidate_since": "2026-05-10T00:02:00Z",
  "dwell_hours": 24
}
```

**Logic:**
- Gates first pass → set `candidate_stage`, `candidate_since`
- Gates fail → set `violation_stage`, `violation_since`
- Violation lasts > `min_violation_hours` → demote to fallback stage
- Candidate lasts > `dwell_hours` → `ready_for_<target_phase>` = true

**Minimum Dwell Times:**
- commissioning → shadow_live: 0h
- shadow_live → advisory: 12h
- advisory → supervised: 24h
- supervised → automatic: 24h

### 6. State Machine

**File:** `backend/app/data/policies/{site_id}-mode-policy-state.json`

**Example (site-002):**
```json
{
  "site_id": "site-002",
  "current_stage": "advisory",
  "candidate_stage": "supervised",
  "candidate_since": "2026-05-17T10:51:11.619340+00:00",
  "violation_stage": null,
  "violation_since": null,
  "last_demoted_at": null,
  "last_evaluated_at": "2026-05-17T12:33:54.186845+00:00"
}
```

**State Flow:**
```
Evaluate gates every 5 min
    ↓
Gates fail ────────→ Set violation_stage, start violation_since timer
    │                           ↓
    │                   Violation > min_violation_hours
    │                           ↓
    │                   Demote to fallback_stage
    │
    └───────→ Gates pass
                  ↓
          Clear violation
                  ↓
          Set candidate_stage
                  ↓
          Candidate > dwell_hours
                  ↓
          ready_for_<target_phase> = true
                  ↓
          Operator promotes via Settings
```

### 7. Testing the Gate System

**Query live gate state:**
```sql
-- What gates exist for S002 shadow_live → advisory?
SELECT gate_name, threshold_value, operator, enabled
FROM phase_promotion_gates
WHERE site_id = 'site-002'
AND from_phase = 'shadow_live'
AND to_phase = 'advisory'
AND enabled = true;

-- What's the current metric for ml_hours?
SELECT ml_hours_ingested
FROM sites
WHERE code = 'site-002';

-- Does it pass the gate?
-- 23.9 >= 72? → No, FAIL
```

**Check readiness via API:**
```bash
curl http://localhost:9095/api/sites/site-002/phase-status
# Returns: gates_pass, which_gates_fail, ready_for_<phase>, time_to_ready
```

### 8. Key Files

| File | Purpose |
|------|---------|
| `backend/app/services/gate_evaluation_service.py` | Evaluates gates against live metrics |
| `backend/app/services/phase_promotion_evaluator.py` | Auto-evaluation, sets readiness flags |
| `backend/app/services/site_mode_policy_service.py` | Policy state management, dwell timers |
| `backend/app/api/sites.py` | PATCH endpoint for manual promotion |
| `backend/app/data/policies/{site_id}-mode-policy.json` | Gate definitions per phase |
| `backend/app/data/policies/{site_id}-mode-policy-state.json` | Current state machine state |

### 9. Frontend Integration

**Settings Page:** `frontend/src/components/settings/OnboardingPhaseSettings.tsx`

- Shows current phase from `sites` table
- Allows promotion to next phase (one-way only)
- Uses 2-second hold-to-confirm for safety
- Invalidates cache after successful promotion

**Cache Management:**
```typescript
// After phase update
queryClient.invalidateQueries({ queryKey: ['buildings-list'] });
queryClient.invalidateQueries({ queryKey: ['site', selectedSiteId] });
```

### 10. Summary

| Aspect | Behavior |
|--------|----------|
| **Gate Storage** | Supabase `phase_promotion_gates` table |
| **Gate Logic** | AND (all gates must pass) |
| **Auto-Promotion** | Sets readiness flag, sends alert, does NOT flip phase |
| **Manual Promotion** | Operator decides, can override gate status |
| **Dwell Timer** | Prevents flapping, requires sustained gate passage |
| **Rollback** | Automatic demotion if violations persist |
| **Audit Trail** | All transitions logged to `phase_transition_log` |

## Client Explanation

**Peter Marshall asks:** "Can the system auto-promote without us knowing?"

**Response:** "No. The policy evaluator runs every 5 minutes and checks gates, but it only sets a 'ready' flag and sends a Telegram alert. The actual phase flip requires a human operator to go into Settings, review the gate status, and hold a button for 2 seconds to confirm. Gates are prerequisites, not automation."

**Peter asks:** "What if we want to promote before gates pass?"

**Response:** "Operators can override. The Settings page allows manual promotion regardless of gate status. The system logs a warning but respects the human decision. This is intentional — we trust operators to use judgment in edge cases."

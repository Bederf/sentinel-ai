---
title: "AEGIS phase 0 daily ops mode runbook"
type: "guide"
status: "approved"
version: "1.1.0"
created: "2026-02-22"
updated: "2026-02-22"
tags: ["aegis", "operations", "bess", "phase-0", "runbook"]
related: ["../06-safety-compliance/aegis-phase1-entry-gate.md", "../05-integrations/aegis-site-002-discovery.md"]
domain: "solar"
audience: "operators"
complexity: "intermediate"
estimated_read_time: 18
---

# AEGIS Phase 0 Daily Ops Mode Runbook

**Version:** 1.1
**Status:** ACTIVE — Phase 0A (Simulation) in progress

---

## 0 Phase progression

AEGIS activation is gated through three phases. Each uses the same runbook and tracker, distinguished by `data_mode`.

| Phase | Data source | Writes | data_mode | Pass criteria |
|-------|------------|--------|-----------|---------------|
| **0A** | Lifecycle simulation | Hard-blocked | `simulation` | 14 clean days: zero illegal states, zero unresolved tripwires >24h, all audit fields present, dispatch patterns match expected tariff/SoC behaviour |
| **0B** | Live BMS telemetry (read-only) | Hard-blocked | `live-read` | 14 clean days: same as 0A plus — real BESS SoC/temp/power values plausible, constraint triggers match actual equipment limits, approval SLA < 5 min on real data |
| **1** | Live BMS telemetry | Controlled writes | N/A | Phase 1 gate document signed off (see [AEGIS phase 1 entry gate](../06-safety-compliance/aegis-phase1-entry-gate.md)) |

**Rules:**
- 0A evidence and 0B evidence are kept in **separate tracker files** (or separate row blocks with distinct `data_mode` values) — simulation results never count as live-read evidence
- A phase cannot start until the previous phase passes
- If a phase fails (blocker detected), reset the day counter and restart that phase
- Phase 0A runs now against the lifecycle simulation; Phase 0B starts when live Modbus read is confirmed
- Default 0A tracker file: `docs/10-operations/aegis-phase0-14day-tracker.csv`

---

## 1 Daily ops checklist

Run once per day, same time daily. Mark `data_mode` on every tracker row.

### A Open dashboard and capture baseline

1. Call dashboard on port 9095
   GET http://localhost:9095/api/parasite/aegis/dashboard?site_id=site-002
2. Screenshot KPI block and pending proposals list.
3. Record KPIs in your 14 day tracker

   * proposals_24h
   * approved_24h
   * rejected_24h
   * blocked_24h
   * avg_response_time_s
4. Record gate fields explicitly from a sample decision

   * quality_gate_status (routing time)
   * quality_gate_status_final (final for audit)

### B Clear the pending queue

1. Pending only
   GET http://localhost:9095/api/parasite/aegis/dashboard?site_id=site-002&approval_outcome=pending
2. For each pending proposal

   * Open decision
     GET http://localhost:9095/api/parasite/decisions/{decision_id}
   * Required audit fields must exist

     * proposal_id
     * command_hash
     * approval_outcome (pending ok)
     * quality_gate_status
     * quality_gate_status_final (can be pending early in lifecycle)
     * block_reason_code (AEGIS_WRITE_BLOCKED in Phase 0)
   * Sanity check

     * dispatch_action_type matches context
     * target_soc_pct within limits
     * constraints_evaluated present
3. Approve or reject

   * Approve if operationally sensible
   * Reject if any required field missing, gate failed, or repeated command with no change

### C Tripwire review and response

Tripwires:

* gate_fail
* repeated_hash

Daily:

1. Pull tripwire events from the actual emit_decision_event sink used in ops.
2. For each tripwire

   * assign owner
   * record action taken
   * record resolved_at
3. If any critical tripwire stays open more than 24h, tag as Phase 1 blocker.

Bind to sink

* If sink is a table: query by event_type and created_at, report by age
* If sink is a log file: grep last 24h then group by proposal_id and age
* If sink is stdout only: route it to file or table before Phase 1

**Current sink:** JSONL log file at `/var/log/sentinel/decisions.log` via the `sentinel.decisions` Python logger (see section 6 below for auto-reporting commands).

### D Reporting semantics lock check

These semantics must not drift.

* APPROVED means human approved
* BLOCKED means no physical write attempted and is expected in Phase 0
* APPROVED plus BLOCKED is a valid Phase 0 terminal state
* EXECUTED must not exist for AEGIS BESS in Phase 0
* cov_verified must never be true for AEGIS BESS in Phase 0

### E Audit field freeze check

Pick 3 random AEGIS decisions from last 24h.
Confirm:

* contributing_factors.proposal_id equals JSONL dispatch aegis_proposal_id
* contributing_factors.command_hash present
* contributing_factors.approval_outcome present
* contributing_factors.quality_gate_status present
* contributing_factors.quality_gate_status_final present
* contributing_factors.block_reason_code equals AEGIS_WRITE_BLOCKED

If any fail, stop and fix before continuing the 14 day run.

### F End of day snapshot

Save:

* dashboard screenshot
* pending list at close of day
* tripwires list with age and status
* one exported decision JSON showing all frozen audit fields

---

## 2 SQL report templates

Assumes Postgres with JSONB contributing_factors.

### A Daily KPI rollup

```sql
select
  site_id,
  count(*) filter (where (contributing_factors->>'proposal_source') = 'aegis') as proposals_24h,
  count(*) filter (
    where (contributing_factors->>'proposal_source') = 'aegis'
      and (contributing_factors->>'approval_outcome') = 'approved'
  ) as approved_24h,
  count(*) filter (
    where (contributing_factors->>'proposal_source') = 'aegis'
      and (contributing_factors->>'approval_outcome') = 'rejected'
  ) as rejected_24h,
  count(*) filter (
    where (contributing_factors->>'proposal_source') = 'aegis'
      and write_status = 'blocked'
  ) as blocked_24h,
  avg(
    extract(epoch from (approved_at::timestamptz - created_at::timestamptz))
  ) filter (
    where (contributing_factors->>'proposal_source') = 'aegis'
      and approved_at is not null
  ) as avg_approve_response_time_s
from parasite_decisions
where site_id = 'site-002'
  and created_at::timestamptz >= now() - interval '24 hours'
group by site_id;
```

### B Pending proposals older than 30 minutes SLA check

This is your cutover enforcement query.

```sql
select
  count(*) as pending_over_30m
from parasite_decisions
where site_id = 'site-002'
  and (contributing_factors->>'proposal_source') = 'aegis'
  and coalesce(contributing_factors->>'approval_outcome', 'pending') = 'pending'
  and created_at::timestamptz < now() - interval '30 minutes';
```

Optional detail list:

```sql
select
  id,
  created_at,
  equipment_code,
  (contributing_factors->>'proposal_id') as proposal_id,
  (contributing_factors->>'dispatch_action_type') as dispatch_action_type,
  (contributing_factors->>'command_hash') as command_hash,
  (contributing_factors->>'quality_gate_status') as quality_gate_status,
  (contributing_factors->>'quality_gate_status_final') as quality_gate_status_final
from parasite_decisions
where site_id = 'site-002'
  and (contributing_factors->>'proposal_source') = 'aegis'
  and coalesce(contributing_factors->>'approval_outcome', 'pending') = 'pending'
  and created_at::timestamptz < now() - interval '30 minutes'
order by created_at asc
limit 200;
```

### C Audit field completeness check

Must return zero rows.

```sql
select
  id,
  created_at,
  equipment_code
from parasite_decisions
where site_id = 'site-002'
  and (contributing_factors->>'proposal_source') = 'aegis'
  and created_at::timestamptz >= now() - interval '24 hours'
  and (
    (contributing_factors->>'proposal_id') is null
    or (contributing_factors->>'command_hash') is null
    or (contributing_factors->>'quality_gate_status') is null
    or (contributing_factors->>'quality_gate_status_final') is null
    or (contributing_factors->>'block_reason_code') is null
    or (contributing_factors->>'approval_outcome') is null
  );
```

### D Phase 0 illegal state checks

All must return zero rows.

Illegal writes or executed states:

```sql
select id, created_at, write_status, decision_type
from parasite_decisions
where site_id = 'site-002'
  and (contributing_factors->>'proposal_source') = 'aegis'
  and created_at::timestamptz >= now() - interval '24 hours'
  and (
    write_status in ('success', 'failed')
    or decision_type ilike '%executed%'
  );
```

Illegal COV verified true:

```sql
select id, created_at, write_status, cov_verified
from parasite_decisions
where site_id = 'site-002'
  and (contributing_factors->>'proposal_source') = 'aegis'
  and created_at::timestamptz >= now() - interval '24 hours'
  and cov_verified is true;
```

---

## 3 API report template with port 9095

### A Dashboard pull

```bash
curl -s "http://localhost:9095/api/parasite/aegis/dashboard?site_id=site-002" | jq .
```

### B Pending only

```bash
curl -s "http://localhost:9095/api/parasite/aegis/dashboard?site_id=site-002&approval_outcome=pending" \
| jq '.pending_proposals[] | {id, created_at, equipment_code, write_status, contributing_factors}'
```

### C KPI extract for your tracker

```bash
curl -s "http://localhost:9095/api/parasite/aegis/dashboard?site_id=site-002" | jq '.kpis'
```

---

## 4 Tripwire sink configuration

The `emit_decision_event` function writes structured JSON via the `sentinel.decisions` Python logger. This logger is configured to write to:

**Primary:** `/var/log/sentinel/decisions.log` (one JSON object per line, appended)

If Promtail/Loki is configured, events are also shipped to Grafana for dashboard queries.

---

## 5 Tripwire auto-reporting commands

### A Open tripwires with age (last 24h)

```bash
# All tripwire events from last 24h, with age in minutes
jq -r --arg cutoff "$(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%S)" '
  select(.stage | startswith("aegis.tripwire"))
  | select(.timestamp > $cutoff)
  | {
      stage,
      age_minutes: (((now - (.timestamp | sub("\\+00:00$";"Z") | fromdate)) / 60) | floor),
      proposal_id: .details.command_hash,
      command_hash: .details.command_hash,
      correlation_id,
      decision_id,
      site_id,
      last_seen: .timestamp
    }
' /var/log/sentinel/decisions.log
```

### B Summary: count by tripwire type

```bash
jq -r --arg cutoff "$(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%S)" '
  select(.stage | startswith("aegis.tripwire"))
  | select(.timestamp > $cutoff)
  | .stage
' /var/log/sentinel/decisions.log | sort | uniq -c | sort -rn
```

### C Oldest unresolved tripwire (Phase 1 blocker check)

```bash
# If any tripwire is older than 24h, it blocks Phase 1
jq -r --arg cutoff "$(date -u -d '48 hours ago' +%Y-%m-%dT%H:%M:%S)" '
  select(.stage | startswith("aegis.tripwire"))
  | select(.timestamp > $cutoff)
  | select(.timestamp < (now - 86400 | todate))
  | {stage, age_hours: (((now - (.timestamp | sub("\\+00:00$";"Z") | fromdate)) / 3600) | floor), correlation_id, decision_id}
' /var/log/sentinel/decisions.log
```

If this returns any rows, those tripwires are Phase 1 blockers per section 1C rule 3.

---

## 6 Log file verification

The `sentinel.decisions` logger is already configured in `backend/app/logging_config.py`:

* **Production:** `/var/log/sentinel/decisions.log` (RotatingFileHandler, 10 MB, 5 backups)
* **Local dev fallback:** `backend/app/data/logs/decisions.log`
* **Format:** JSON lines (`%(message)s` — each line is a complete JSON object)

Verify:
```bash
ls -la /var/log/sentinel/decisions.log
tail -1 /var/log/sentinel/decisions.log | jq .
```

If the file doesn't exist, check that `setup_logging()` is called at app startup (it's invoked in `app/main.py`).

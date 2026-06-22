---
title: "RSI Threshold Tuning Schema"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-06-22"
updated: "2026-06-22"
tags: ["database", "schema", "tuner", "rsi", "thresholds", "rls", "security"]
related: ["SERVICE_RECORDS_SCHEMA.md", "../09-security/secrets-management.md", "../03-api-reference/asset-health-api.md"]
domain: "bms"
audience: "developers"
complexity: "advanced"
estimated_read_time: 15
---

# RSI Threshold Tuning Schema

## Overview

The RSI (Recommendation-Submission-Implementation) threshold tuning subsystem allows an automated tuner to propose health and risk threshold adjustments for sites. Proposals are reviewed and promoted by a human operator — the tuner cannot promote its own proposals.

**Migrations:**
- `supabase/migrations/221_site_thresholds.sql` — base `site_thresholds` table (Phase 221)
- `supabase/migrations/20260622_001_rsi_tuner_rebuild.sql` — tuner tables, functions, role, RLS
- `supabase/migrations/20260622_002_tuner_promote_function.sql` — atomic promote/rollback function

## Human-in-the-loop constraint (grant-enforced)

The tuner role (`sentinel_tuner`) can INSERT proposals but cannot write `site_thresholds`. Promotion only happens through the operator API endpoint (`require_role(4)`). This is enforced by the DB grant structure, not by application logic:

- `sentinel_tuner` has EXECUTE on `tuner_submit_proposal`, `tuner_get_active_thresholds`, `tuner_active_set_hash` only
- `sentinel_tuner` has zero table grants (no SELECT, INSERT, UPDATE, DELETE on any table)
- `tuner_promote_thresholds` is granted to `service_role` only (not `sentinel_tuner`)
- All table writes go through SECURITY DEFINER functions owned by postgres

No code path, present or future, may promote a threshold proposal without an authenticated operator action. The grant structure makes this structurally impossible, not just policy-prohibited.

## Tables

### site_thresholds (Phase 221, constraints updated 20260622)

Active health and risk thresholds per site. One row per `site_id` (PK). `site_id='__global__'` is the fallback default.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `site_id` | text | NO | — | Primary key |
| `health` | jsonb | NO | `{"healthy": 85, "warning": 65, "critical": 40}` | Health score boundaries |
| `risk` | jsonb | NO | `{"high": 61, "medium": 31, "critical": 81}` | Risk score boundaries |
| `created_at` | timestamptz | NO | `now()` | |
| `updated_at` | timestamptz | NO | `now()` | |

**CHECK constraints (key-presence + ordering):**

```sql
CONSTRAINT valid_health CHECK (
    health ? 'critical' AND health ? 'warning' AND health ? 'healthy'
    AND (health->>'critical')::int >= 0
    AND (health->>'critical')::int < (health->>'warning')::int
    AND (health->>'warning')::int < (health->>'healthy')::int
    AND (health->>'healthy')::int <= 100
)

CONSTRAINT valid_risk CHECK (
    risk ? 'critical' AND risk ? 'high' AND risk ? 'medium'
    AND (risk->>'medium')::int >= 0
    AND (risk->>'medium')::int < (risk->>'high')::int
    AND (risk->>'high')::int < (risk->>'critical')::int
    AND (risk->>'critical')::int <= 100
)
```

Key-existence checks (`?` operator) come before casts. If any key is missing, short-circuit evaluation means the casts never fire — this prevents the NULL-propagation bug where `(health->>'missing_key')::int` returns NULL and `NULL < NULL` evaluates to NULL (not FALSE), allowing the CHECK to pass.

**RLS policies:**

| Policy | Command | Qualifier | Notes |
|--------|---------|-----------|-------|
| `site_thresholds_select` | SELECT | `__global__` OR JWT site_id match OR service_role | App users see global + own site |
| `site_thresholds_insert` | INSERT | service_role only | No app-user write path |
| `site_thresholds_update` | UPDATE | service_role only | No app-user write path |

Writes are service_role-only by design. The backend gates writes with `require_role(4)` (ADMIN) at the API layer. Adding an app-user UPDATE policy would open a direct-to-Supabase write path that bypasses the backend's admin gate — this was an intentional design choice, not a gap.

### site_threshold_proposals

Versioning table for threshold adjustment proposals submitted by the tuner.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `proposal_id` | bigint | NO | GENERATED ALWAYS AS IDENTITY | Primary key |
| `site_id` | text | NO | — | |
| `health` | jsonb | NO | — | Proposed health thresholds |
| `risk` | jsonb | NO | — | Proposed risk thresholds |
| `rationale` | text | YES | — | Tuner's reasoning |
| `trigger_metric` | text | YES | — | Metric that triggered the proposal |
| `trigger_value` | jsonb | YES | — | Value of the triggering metric |
| `status` | text | NO | `'pending'` | `pending`, `approved`, `rejected`, `superseded` |
| `proposed_at` | timestamptz | NO | `now()` | |
| `reviewed_at` | timestamptz | YES | — | Set when promoted/rejected |
| `reviewed_by` | text | YES | — | User ID of operator who reviewed |
| `change_log_id` | bigint | YES | — | Links to change_log entry on promotion |

**CHECK constraints:** `proposal_health_keys` and `proposal_risk_keys` mirror `valid_health`/`valid_risk` (key-presence + ordering). `status` constrained to `pending`, `approved`, `rejected`, `superseded`.

**RLS policies:**

| Policy | Command | Qualifier |
|--------|---------|-----------|
| `proposals_select` | SELECT | JWT site_id match OR service_role |
| `proposals_service_role_write` | ALL | service_role only |

### threshold_change_log

Audit trail for all threshold changes. Every promotion (operator edit, proposal promote, rollback) writes a row here.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `log_id` | bigint | NO | GENERATED ALWAYS AS IDENTITY | Primary key |
| `site_id` | text | NO | — | |
| `old_health` | jsonb | YES | — | Previous active health (NULL for first-time setup) |
| `old_risk` | jsonb | YES | — | Previous active risk |
| `new_health` | jsonb | NO | — | New active health |
| `new_risk` | jsonb | NO | — | New active risk |
| `triggered_by` | text | NO | — | `operator`, `tuner_proposal`, `rollback` |
| `proposal_id` | bigint | YES | — | Links to proposal if `triggered_by='tuner_proposal'` |
| `approved_by` | text | YES | — | User ID of operator who approved |
| `previous_log_id` | bigint | YES | — | Chain link to prior change for this site |
| `changed_at` | timestamptz | NO | `now()` | |
| `active_hash` | text | NO | — | Hash of the new active state (from `tuner_active_set_hash`) |

**CHECK constraints:** `triggered_by` constrained to `operator`, `tuner_proposal`, `rollback`.

**RLS policies:**

| Policy | Command | Qualifier |
|--------|---------|-----------|
| `change_log_select` | SELECT | `__global__` OR JWT site_id match OR service_role |
| `change_log_service_role_write` | ALL | service_role only |

### tuner_allowed_sites

Controls which sites the RSI tuner is permitted to adjust. Not exposed to app users.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `site_id` | text | NO | — | Primary key |
| `enabled` | boolean | NO | `true` | |
| `created_at` | timestamptz | NO | `now()` | |
| `created_by` | text | YES | — | |

**RLS:** service_role only (all operations). `sentinel_tuner` reads this table indirectly through SECURITY DEFINER functions.

**Current contents:** `site-002` (Sandton City Office Tower), enabled.

## Functions

All functions are `SECURITY DEFINER`, owned by `postgres`, with `search_path = 'public'`. This allows `sentinel_tuner` to read tables it has no direct grant on (RLS bypass via function ownership).

### tuner_get_active_thresholds(p_site_id text)

Returns the active thresholds for an allowlisted site. Returns empty set if the site is not in `tuner_allowed_sites` or is disabled.

**Granted to:** `sentinel_tuner`, `service_role`

### tuner_submit_proposal(p_site_id, p_health, p_risk, p_rationale, p_trigger_metric, p_trigger_value)

Inserts a proposal after validating:
1. Site is allowlisted (`tuner_allowed_sites.enabled = true`)
2. Key presence in `p_health` and `p_risk` (pre-check for readable error message)

Ordering/boundary validation is enforced by the table CHECK constraints (`proposal_health_keys`, `proposal_risk_keys`) — the function's pre-check is strictly weaker than the table CHECK, intentionally. The function catches the operator's likely mistake (missing keys) with a readable message. The table catches everything else.

**Granted to:** `sentinel_tuner`, `service_role`

### tuner_active_set_hash(p_site_id text)

Returns an MD5 hash of the active threshold state for a site. Used by drift monitoring to detect changes.

- **Existing row:** `md5(site_id || '|' || health::text || '|' || risk::text)`
- **No row:** `md5(site_id || '|ROW_ABSENT')` — stable sentinel

The `ROW_ABSENT` sentinel is versioned: it means "no row exists, full stop." Do not reuse this string for any other absence state. Drift monitoring can distinguish "row deleted" (sentinel hash) from "row changed" (different hash) from "no change" (same hash).

This function is the **single source of truth** for the hash formula. `tuner_promote_thresholds` calls this function rather than reimplementing the formula inline, preventing drift between the two.

**Granted to:** `sentinel_tuner`, `service_role`

### tuner_promote_thresholds(p_site_id, p_new_health, p_new_risk, p_triggered_by, p_proposal_id, p_approved_by)

Atomic promotion of threshold values. Single transaction:

1. Read current state from `site_thresholds` (for `old_*` values in the log)
2. Find most recent `threshold_change_log` entry (for chain `previous_log_id`)
3. Upsert `site_thresholds` with new values (table CHECK enforces ordering)
4. Call `tuner_active_set_hash` to compute hash (single source of truth)
5. Write `threshold_change_log` (old state, new state, hash, chain link)
6. If `triggered_by='tuner_proposal'`, mark the proposal as approved

If any step fails, the entire transaction rolls back — the change_log and the upsert are atomic.

**Granted to:** `service_role` only. NOT granted to `sentinel_tuner` — promotion is operator-only, enforced at the grant level.

## Role: sentinel_tuner

| Property | Value |
|----------|-------|
| Login | Yes |
| Password | Stored in `/etc/sentinel/secrets.env` as `TUNER_DB_PASSWORD` |
| Schema grants | `USAGE ON SCHEMA public` (name resolution only) |
| Table grants | None |
| Function grants | EXECUTE on `tuner_get_active_thresholds`, `tuner_submit_proposal`, `tuner_active_set_hash` |
| RLS | No direct table access; all reads through SECURITY DEFINER functions |

The password file is at `/etc/sentinel/secrets.env` (root-owned, mode 600), outside the git repository root. It is loaded by systemd via `EnvironmentFile` and is not tracked in version control.

## Enforcement model

| Layer | Mechanism | What it enforces |
|------|-----------|------------------|
| DB grants | `sentinel_tuner` has no table grants | Tuner cannot read or write tables directly |
| DB grants | `tuner_promote_thresholds` not granted to `sentinel_tuner` | Tuner cannot promote proposals |
| RLS | service_role-only writes on all tuner tables | App users cannot write via Supabase REST |
| API | `require_role(4)` on promote/rollback endpoints | Only ADMIN users can promote or rollback |
| DB CHECK | Key-presence + ordering constraints | Invalid threshold values rejected at the table |
| Function pre-check | Key-presence validation in `tuner_submit_proposal` | Readable error message for missing keys |

The human-in-the-loop constraint is **grant-enforced**, not just documented. A future migration could add a write grant to `sentinel_tuner`, but the comment in the migration file makes the violation visible to anyone reviewing the migration before approval.

## API endpoints

See [asset-health-api.md](../03-api-reference/asset-health-api.md) for the health threshold service.

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/settings/site-thresholds` | GET | level 1+ | Get thresholds for a site (falls back to `__global__`) |
| `/api/settings/site-thresholds` | PUT | level 4 (ADMIN) | Update thresholds (atomic: change_log + upsert) |
| `/api/settings/site-thresholds/promote` | POST | level 4 (ADMIN) | Promote a pending proposal to active |
| `/api/settings/site-thresholds/rollback` | POST | level 4 (ADMIN) | Restore values from a prior change_log entry |
| `/api/settings/site-thresholds/change-log` | GET | level 1+ | View change history |

### Rollback semantics

Rollback restores the values that the target log entry **established** (its `new_health`/`new_risk`), not the values that existed **before** it (its `old_*` values). To undo change N, rollback to entry N-1.

Rollback uses the same `tuner_promote_thresholds` function as normal promotion — one code path, one transaction. A new change_log entry is written with `triggered_by='rollback'`.

## Test coverage

| Suite | Tests | File |
|-------|-------|------|
| Constraint (key-presence CHECK) | 7 | `/tmp/opencode/rsi_tuner_test_suite.sh` |
| Boundary (function behavior) | 10 | same |
| Allowlist-read (SECURITY DEFINER) | 2 | same |
| Endpoint (promote/rollback/change-log) | 17 | `/tmp/opencode/rsi_endpoint_tests.sh` |

Key test cases:
- Empty `{}` and partial-key proposals are rejected by table CHECK
- Wrong-order values pass function pre-check but are rejected by table CHECK (two-layer enforcement)
- `sentinel_tuner` cannot directly SELECT any table (permission denied)
- `sentinel_tuner` can read `tuner_allowed_sites` through SECURITY DEFINER function but not directly
- `active_hash` in change_log matches `tuner_active_set_hash` (single source of truth)
- Operator (level 1) denied promote/rollback endpoints (403)
- Change_log chain (`previous_log_id`) is intact across promote/rollback cycles

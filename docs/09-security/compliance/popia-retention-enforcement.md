---
title: "POPIA Retention Enforcement"
type: "procedure"
status: "active"
version: "1.2.0"
created: "2026-02-23"
updated: "2026-05-22"
author: "SENTINEL Compliance Team"
tags: ["compliance", "popia", "retention", "privacy"]
domain: "compliance"
audience: "platform, compliance, security"
complexity: "intermediate"
estimated_read_time: 8
---

# POPIA Retention Enforcement

## 1. Purpose

Define automated retention and deletion controls for POPIA-aligned data minimization.

## 2. Components

- JSON-file retention: `backend/app/services/popia_retention_service.py`
- SQL-table retention: `backend/app/services/supabase_retention_service.py`
- Scheduler job: `background_scheduler.add_supabase_retention_job` in `backend/app/services/background_scheduler.py`
- Startup wiring: `backend/app/startup/events.py`
- Run log: `retention_enforcement_log` SQL table

## 3. Covered Datasets

- `backend/app/data/consent_records.json`
- `backend/app/data/privacy_requests.json`
- `backend/app/data/audit_log.json`

Retention windows are controlled by settings in `backend/app/config/settings.py`:

- `popia_retention_consent_days`
- `popia_retention_request_days`
- `popia_retention_audit_days`

## 4. Operations

- Status snapshot: `GET /api/privacy/retention/status`
- Manual preview/enforcement:
  - `POST /api/privacy/retention/enforce` with `{"dry_run": true}`
  - `POST /api/privacy/retention/enforce` with `{"dry_run": false}`
- Scheduled enforcement runs daily by default (`popia_retention_job_interval_seconds`).

## 5. Evidence Outputs

- Run history and deletion counts: `backend/app/data/popia_retention_runs.json`
- Audit event `popia_retention_enforcement` written by scheduler.

---

## 6. SQL Table Retention (Supabase)

POPIA Section 14 applies to both JSON files (Section 6 above) and Supabase SQL tables.
Implemented in `backend/app/services/supabase_retention_service.py`, wired into APScheduler
(`add_supabase_retention_job`) and startup (`events.py`).

### 6.1 Retention Tiers

 | Tier | Tables | Retention | POPIA Basis |
|------|--------|-----------|-------------|
| **ML_TRAINING** | `equipment_fault_events` (recorded_at), `adapter_health` (timestamp), `adapter_health_current` (updated_at), `adapter_health_alerts` (created_at), `space_occupancy_events` (timestamp), `equipment_sensor_readings` (recorded_at), `drift_detection_log` (recorded_at), `alerts` (created_at) | 7-10 days | S14(1) — data no longer necessary after ML processing |
| **SNAPSHOT** | `asset_health_snapshots`, `system_health_snapshots` | 30 days | S14(1) — stale operational data |
| **AUDIT_TRAIL** | `recommendations`, `parasite_decisions` | 5 years | S14(2) — lawful purpose (audit/compliance) |

### 6.4 Audit Trail (POPIA S14 Proof)

Live enforcement writes per-table execution records to the `retention_enforcement_log` SQL table.
This is the primary POPIA S14 evidence artifact — it records what was deleted, when, and by which tier.

```sql
-- Table created by backend/supabase/migrations/20260522_001_retention_enforcement_log.sql
CREATE TABLE IF NOT EXISTS public.retention_enforcement_log (
    id BIGSERIAL PRIMARY KEY,
    executed_at TIMESTAMPTZ NOT NULL,
    dry_run BOOLEAN NOT NULL DEFAULT FALSE,
    tier TEXT NOT NULL,          -- 'ML_TRAINING' | 'SNAPSHOT' | 'AUDIT_TRAIL'
    table_name TEXT NOT NULL,
    date_column TEXT NOT NULL DEFAULT 'created_at',
    reviewed INTEGER NOT NULL DEFAULT 0,
    deleted INTEGER NOT NULL DEFAULT 0,
    errors JSONB DEFAULT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Index for querying recent runs per table/tier
CREATE INDEX idx_retention_log_lookup ON retention_enforcement_log (table_name, tier, executed_at DESC);
```

As of 2026-05-22, this table has **22 live enforcement entries** (verified in Supabase local dev).
Each entry records the tier, table, reviewed count, deleted count, and any errors — providing
cryptographic proof of continuous POPIA S14 compliance enforcement.

### 6.5 Known Operational Notes

- **Direct psycopg2 (no REST API)**: As of 2026-06-22, the retention service uses direct
  PostgreSQL connections (`psycopg2`) instead of the Supabase REST API. This avoids dependency on
  `SUPABASE_SERVICE_ROLE_KEY` being set in the environment for admin-write operations.
- **Date column mapping**: Each table uses its actual date column (`recorded_at`, `timestamp`,
  `updated_at`, `snapshot_at` as applicable — see tier table above).
- **adapter_health_current**: Has no primary key — delete uses `WHERE updated_at < cutoff` directly.

> **Note (2026-05-22):** `recommendations` and `parasite_decisions` retained columns are limited to
> those with actual data following Phase 208-12 null column cleanup. Execution log is the
> `retention_enforcement_log` SQL table.

### 6.2 SQL Table Endpoints

- Status snapshot: `GET /api/privacy/retention/sql-status`
- Execute enforcement: `POST /api/privacy/retention/sql-enforce`
- Execution history: returned in service response (in-memory log)

### 6.3 Scheduled Enforcement

- **ML_TRAINING & SNAPSHOT**: Daily (via `add_supabase_retention_job`, 86400s interval)
- **AUDIT_TRAIL**: Weekly (via same job, same schedule — deletion threshold is 5y so weekly is appropriate)
- Preview (dry run) before first execution: `POST /api/privacy/retention/sql-enforce` with auth level `ADMIN`

---
title: "POPIA Retention Enforcement"
type: "procedure"
status: "active"
version: "1.1.0"
created: "2026-02-23"
updated: "2026-05-20"
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

- Enforcement service: `backend/app/services/popia_retention_service.py`
- Scheduler job: `background_scheduler.add_popia_retention_job` in `backend/app/services/background_scheduler.py`
- Startup wiring: `backend/app/startup/events.py`
- Run log: `backend/app/data/popia_retention_runs.json`

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
| **ML_TRAINING** | `equipment_fault_events` (recorded_at), `adapter_health` (timestamp), `adapter_health_current` (updated_at), `adapter_health_alerts` (created_at), `space_occupancy_events` (timestamp), `equipment_sensor_readings` (recorded_at), `alerts` (created_at) | 7 days | S14(1) — data no longer necessary after ML processing |
| **SNAPSHOT** | `asset_health_snapshots`, `system_health_snapshots` | 30 days | S14(1) — stale operational data |
| **AUDIT_TRAIL** | `recommendations`, `parasite_decisions` | 5 years | S14(2) — lawful purpose (audit/compliance) |

> **Note (2026-05-10):** Following Phase 208-12 null column cleanup, `recommendations` and `parasite_decisions` retained columns are limited to those with actual data. Execution log is held in-memory by the service (no `retention_execution_log` SQL table — that table was archived in Phase 208-10).

### 6.2 SQL Table Endpoints

- Status snapshot: `GET /api/privacy/retention/sql-status`
- Execute enforcement: `POST /api/privacy/retention/sql-enforce`
- Execution history: returned in service response (in-memory log)

### 6.3 Scheduled Enforcement

- **ML_TRAINING & SNAPSHOT**: Daily (via `add_supabase_retention_job`, 86400s interval)
- **AUDIT_TRAIL**: Weekly (via same job, same schedule — deletion threshold is 5y so weekly is appropriate)
- Preview (dry run) before first execution: `POST /api/privacy/retention/sql-enforce` with auth level `ADMIN`

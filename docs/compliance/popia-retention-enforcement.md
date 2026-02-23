---
title: "POPIA Retention Enforcement"
type: "procedure"
status: "active"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
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

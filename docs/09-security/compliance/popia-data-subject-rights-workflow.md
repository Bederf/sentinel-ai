---
title: "POPIA Data Subject Rights Workflow"
type: "procedure"
status: "active"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Compliance Team"
tags: ["compliance", "popia", "dsr", "privacy"]
domain: "compliance"
audience: "compliance, operations, engineering"
complexity: "intermediate"
estimated_read_time: 8
---

# POPIA Data Subject Rights Workflow

## 1. Purpose

Define the operational workflow for POPIA rights requests (access, correction, deletion, objection, portability, consent withdrawal) with measurable SLA tracking.

## 2. System Components

- API endpoints: `backend/app/api/privacy.py`
- Workflow service and register: `backend/app/services/privacy_request_service.py`
- Storage register: `backend/app/data/privacy_requests.json`

## 3. SLA

- Default SLA: 30 days (`popia_dsr_sla_days` in `backend/app/config/settings.py`)
- Requests are auto-marked `expired` after due date if not closed.

## 4. Workflow

1. Data subject request is submitted via `POST /api/privacy/requests`.
2. Request is stored with:
   - hashed subject identifier
   - request type/channel/details
   - `created_at`, `due_at`, initial status `pending`
3. Operations/compliance triage and update via `POST /api/privacy/requests/{request_id}/status`.
4. Closure requires status and outcome summary with optional evidence references.
5. Metrics are reviewed via:
   - `GET /api/privacy/requests`
   - `GET /api/privacy/requests-metrics`

## 5. Evidence Outputs

- Request register export: `backend/app/data/privacy_requests.json`
- SLA metrics snapshot endpoint: `GET /api/privacy/requests-metrics`

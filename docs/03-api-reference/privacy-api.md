---
title: "Privacy & Consent API Reference"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Development Team"
tags: ["api", "privacy", "popia", "consent", "dsr", "retention"]
domain: "compliance"
audience: "developers, compliance, operations"
complexity: "intermediate"
estimated_read_time: 12
---

# Privacy & Consent API Reference

POPIA runtime controls are split into two API groups:

- `/api/consent` for consent lifecycle records.
- `/api/privacy` for data subject rights (DSR) workflow and retention automation.

## Overview

| API Group | Purpose | Primary Files |
|---|---|---|
| Consent API | Record/check/withdraw PI, retention, and cross-border consent | `backend/app/api/consent.py`, `backend/app/services/consent_service.py` |
| Privacy API | DSR request workflow, SLA tracking, retention status/enforcement | `backend/app/api/privacy.py`, `backend/app/services/privacy_request_service.py`, `backend/app/services/popia_retention_service.py` |

## Authentication Model

| Endpoint Group | Auth Requirement |
|---|---|
| `/api/consent/*` | No route-level auth in API layer (expected channel or gateway control) |
| `/api/privacy/requests*` | `AUTHENTICATED` for read/create, `OPERATOR` for status updates |
| `/api/privacy/retention/*` | `OPERATOR` for status, `ADMIN` for enforce |

## Consent API (`/api/consent`)

### Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/consent/record` | Record immutable consent decision |
| GET | `/api/consent/check/{subject_id}/{consent_type}` | Check active consent for one type |
| POST | `/api/consent/withdraw` | Withdraw an active consent type |
| GET | `/api/consent/history/{subject_id}` | Full consent history for data subject |
| GET | `/api/consent/stats` | Aggregate consent metrics |
| GET | `/api/consent/export` | Export records for audit windows |
| GET | `/api/consent/templates` | Channel consent templates |

### Consent Types

- `pi_processing`
- `data_retention`
- `cross_border_transfer`

### Example

```bash
curl -X POST http://localhost:9095/api/consent/record \
  -H "Content-Type: application/json" \
  -d '{
    "data_subject_id": "+27821234567",
    "platform": "whatsapp",
    "consent_type": "cross_border_transfer",
    "consent_given": true
  }'
```

## Privacy API (`/api/privacy`)

### DSR Workflow Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/privacy/requests` | Create data subject request with due date |
| GET | `/api/privacy/requests` | List requests (optional status/overdue filters) |
| GET | `/api/privacy/requests/{request_id}` | Get one request |
| POST | `/api/privacy/requests/{request_id}/status` | Update workflow status and evidence links |
| GET | `/api/privacy/requests-metrics` | SLA and status metrics |

### DSR Status Values

- `pending`
- `in_progress`
- `fulfilled`
- `rejected`
- `cancelled`
- `expired`

### Retention Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/privacy/retention/status` | Overdue snapshot by dataset |
| POST | `/api/privacy/retention/enforce` | Enforce or preview retention policy (`dry_run`) |

### Example (create DSR request)

```bash
curl -X POST http://localhost:9095/api/privacy/requests \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "request_type": "access",
    "channel": "web",
    "details": "Send my personal data export"
  }'
```

### Example (retention dry run)

```bash
curl -X POST http://localhost:9095/api/privacy/retention/enforce \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'
```

## Runtime POPIA Enforcement (Related Endpoints)

Consent gates are also enforced on ingress endpoints:

- WhatsApp inbound webhook: `POST /api/whatsapp/webhooks`
- Telegram/Sentry work order response: `POST /api/sentry/work-order/response`
- Telegram OCR flow: `POST /api/sentry/ocr/process-service-sheet`

Cloud model routing is blocked without `cross_border_transfer` consent and falls back to local models:

- `POST /api/chat`
- `POST /api/hybrid-chat`

## Data Stores and Evidence

| Artifact | Path |
|---|---|
| Consent records | `backend/app/data/consent_records.json` |
| Privacy request register | `backend/app/data/privacy_requests.json` |
| Retention run log | `backend/app/data/popia_retention_runs.json` |

## POPIA Settings

Configured in `backend/app/config/settings.py`:

- `popia_require_cross_border_consent`
- `popia_dsr_sla_days`
- `popia_retention_enabled`
- `popia_retention_consent_days`
- `popia_retention_request_days`
- `popia_retention_audit_days`
- `popia_retention_job_interval_seconds`

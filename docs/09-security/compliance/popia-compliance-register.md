---
title: "POPIA Compliance Register"
type: "register"
status: "draft"
version: "0.1.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Compliance Team"
tags: ["compliance", "popia", "privacy", "south-africa", "register"]
domain: "compliance"
audience: "compliance, security, engineering"
complexity: "intermediate"
estimated_read_time: 12
---

# POPIA Compliance Register

## 1. Purpose

This register tracks POPIA control status for SENTINEL and records pass/fail outcomes with technical evidence and gaps.

Assessment date: `2026-02-23`  
Reference baseline reviewed: `/opt/aimthelaw` POPIA documentation and service patterns.

## 2. Scope

In scope:
- Personal information processed by SENTINEL channels (web, WhatsApp, Telegram, API)
- Consent and cross-border transfer controls
- Data subject rights operations
- Retention/deletion, auditability, breach response

Out of scope:
- Non-personal BMS telemetry with no data subject linkage

## 3. Control Status (Pass/Fail)

| POPIA Area | Status | Evidence | Exact Gap |
|---|---|---|---|
| Accountability and governance ownership | PASS | `docs/09-security/data-privacy-policy.md`, `docs/09-security/information-security-framework.md` | None critical |
| Security safeguards (technical and organizational) | PASS | `docs/09-security/information-security-policy.md`, `docs/09-security/incident-response-policy.md`, `backend/app/services/audit_logger.py` | None critical |
| Breach response and regulator notification process | PASS | `docs/09-security/incident-response-process.md`, `docs/09-security/incident-response-policy.md` | None critical |
| Consent capture service and API availability | PASS | `backend/app/services/consent_service.py`, `backend/app/api/consent.py`, `backend/app/api/registrars/operations.py` | Endpoint is active; channel enforcement still incomplete (see next row) |
| Consent enforcement in live ingestion/chat channels | PASS | `backend/app/api/whatsapp_webhooks.py`, `backend/app/api/sentry_webhooks.py`, `backend/app/services/popia_consent_guard.py` | Runtime consent gate active for WhatsApp and Telegram ingress |
| Data subject rights operations (access/correction/deletion workflow) | PASS | `backend/app/api/privacy.py`, `backend/app/services/privacy_request_service.py`, `docs/compliance/popia-data-subject-rights-workflow.md` | SLA-tracked register and status workflow implemented |
| Retention and deletion enforcement | PASS | `backend/app/services/popia_retention_service.py`, `backend/app/services/background_scheduler.py`, `docs/compliance/popia-retention-enforcement.md` | Automated policy enforcement job + run logs implemented |
| Cross-border transfer runtime control | PASS | `backend/app/api/chat.py`, `backend/app/api/hybrid_chat.py`, `backend/app/services/hybrid_ai_service.py` | Cloud routing now blocked without `cross_border_transfer` consent; local fallback enforced |
| POPIA-specific operational evidence pack | PARTIAL | `docs/compliance/popia-compliance-register.md`, `docs/compliance/popia-data-subject-rights-workflow.md`, `docs/compliance/popia-retention-enforcement.md` | Monthly evidence cadence still pending |

## 4. Priority Remediation Backlog

| ID | Gap | Owner | Target Date | Evidence Target |
|---|---|---|---|---|
| POPIA-001 | Enforce consent checks in WhatsApp/Telegram ingestion before PI processing | Backend Lead | 2026-03-15 | Completed 2026-02-23: `backend/app/api/whatsapp_webhooks.py`, `backend/app/api/sentry_webhooks.py` |
| POPIA-002 | Enforce cross-border consent in cloud model routing (fallback to local model when absent/withdrawn) | AI Engineering Lead | 2026-03-22 | Completed 2026-02-23: `backend/app/api/chat.py`, `backend/app/api/hybrid_chat.py`, `backend/app/services/hybrid_ai_service.py` |
| POPIA-003 | Implement data subject request register/API with 30-day SLA tracking | Compliance Lead + Backend Lead | 2026-04-05 | Completed 2026-02-23: `backend/app/api/privacy.py`, `backend/app/services/privacy_request_service.py` |
| POPIA-004 | Implement automated retention/deletion enforcement job for PI datasets | Platform/SRE Lead | 2026-04-19 | Completed 2026-02-23: `backend/app/services/popia_retention_service.py`, scheduler wiring in `backend/app/startup/events.py` |
| POPIA-005 | Create POPIA audit evidence pack index and monthly review cadence | Compliance Lead | 2026-03-31 | Open |

## 5. Immediate Next Actions (30 Days)

1. Run first monthly POPIA control-effectiveness review and file evidence snapshot.
2. Validate retention automation in production (`dry_run=true` then `dry_run=false`).
3. Add board-level POPIA KPI view (open requests, overdue, SLA compliance, deletions).

## 6. Revision History

| Version | Date | Author | Changes |
|---|---|---|---|
| 0.1.0 | 2026-02-23 | SENTINEL Compliance Team | Initial POPIA pass/fail register and remediation backlog |

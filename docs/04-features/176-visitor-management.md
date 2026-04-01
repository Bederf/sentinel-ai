---
title: "Phase 176: Visitor Management Module"
type: "spec"
status: "approved"
version: "1.0.0"
created: "2026-04-01"
updated: "2026-04-01"
tags: ["visitor-management", "security", "access-control", "reception", "whatsapp"]
related: ["../03-api-reference/visitor-management-api.md", "../05-integrations/visitor-management-integrations.md", "../05-integrations/ccure-9000-integration.md"]
domain: "security"
audience: "operators"
complexity: "intermediate"
estimated_read_time: 10
---

# Phase 176: Visitor Management Module

Deterministic visitor identity and orchestration. SENTINEL acts as the decision engine — C-CURE is enforcement only, Active Directory is identity source, Outlook is intent source, reception is execution only.

## Problem

Receptionists make ad-hoc decisions about who to allow in. There is no deterministic identity, no automated host notification, and no audit trail for visitor movements. Visitor management is manual and ambiguous.

## Solution

A token-based visitor flow where every visitor action is traceable, every access decision is policy-enforced, and the host is always in the loop.

### CORE PRINCIPLES

1. SENTINEL is the decision engine
2. C-CURE is enforcement only
3. Active Directory is identity source (not location)
4. Outlook is intent source
5. Reception is execution only (no logic)
6. No free-text host selection anywhere

---

## Visit Lifecycle

```
CREATED ────────────────────────────────────────────────────────────► EXPIRED
    │                                                                     ▲
    │ (scan)                                                             │
    ▼                                                                     │
ARRIVED ──────► REGISTERED ◄──── (visitor registers at reception)        │
    │                    │                                              │
    │                    │ (WhatsApp YES from host)                     │
    │                    ▼                                              │
    │                APPROVED ──────► (reception issues card) ────► ACTIVE
    │                                                             ▲
    │                                                             │
    └────── (WhatsApp NO from host) ────► DENIED ──────────────────┘
    │
    └────── (explicit cancel) ────► CANCELLED
```

### Status Definitions

| Status | Meaning |
|--------|---------|
| `CREATED` | Outlook event received, QR + PIN sent to visitor |
| `ARRIVED` | Visitor scanned at reception (QR or PIN) |
| `REGISTERED` | Visitor name/photo captured by reception |
| `APPROVED` | Host approved via WhatsApp YES reply |
| `DENIED` | Host denied via WhatsApp NO reply (or explicit) |
| `ACTIVE` | Access card issued, visitor is on premises |
| `EXPIRED` | Past `meeting_end + 60 minutes` |
| `CANCELLED` | Explicitly cancelled by host or system |

### Card Issuance Rules

Card can be issued when visit is in `REGISTERED` **or** `APPROVED` status:
- `REGISTERED` = visitor registered at reception, host pre-approved via Outlook
- `APPROVED` = visitor registered, host approved via WhatsApp reply

---

## End-to-End Flow

```
1. Organizer creates Outlook calendar event with external attendee
   │
2. SENTINEL Outlook listener (MS Graph API, 5-min poll)
   │
3. External attendee detected → Visit created with:
   - UUID token (QR payload)
   - 6-digit PIN (fallback)
   - QR code (UUID only, no PII)
   │
4. Visitor email sent with QR code + PIN
   │
5. Visitor arrives → scans QR or enters PIN at reception kiosk
   │
6. Policy engine validates:
   - Token/PIN exists
   - Within time window (meeting_start - 30min to meeting_end + 60min)
   - Not expired, cancelled, or denied
   │
7. Visit status → ARRIVED
   │
8. Visitor registers: name + photo (+ optional vehicle, ID number)
   │
9. Visit status → REGISTERED
   │
10. Host receives WhatsApp: "Your visitor has arrived. Reply YES to approve."
    │
11. Host replies YES → Visit status → APPROVED
    Host replies NO → Visit status → DENIED
    │
12. Reception issues access card
    │
13. C-CURE receives access grant for visitor
    │
14. All events audit-logged (SCAN, REGISTER, APPROVE, DENY, ACCESS_ISSUED, EXPIRED)
```

---

## Policy Engine Rules

### Scan Policy (8 rules)
1. Must have token OR PIN — else 400
2. Token/PIN must exist — else 404
3. Visit must not be expired — else 410
4. Meeting must have started (within 30min window) — else 403
5. Status must not be CANCELLED — else 410
6. Status must not be DENIED — else 403
7. Status must not be EXPIRED — else 410
8. VALID → allow scan

### Registration Policy
- Expired visits cannot register
- Cancelled visits cannot register
- Already-active visits cannot re-register

### Access Issue Policy
- Visit must be in `REGISTERED` or `APPROVED` status
- DENIED visits are blocked
- EXPIRED visits are blocked

---

## Security Properties

| Property | Implementation |
|----------|---------------|
| QR contains no PII | UUID token only |
| PIN is 6 digits | Random, zero-padded |
| Webhook signature | Twilio HMAC-SHA1 verified |
| Host lookup | Mobile number normalisation |
| Audit log | Append-only, FileLock thread-safe |
| Race condition | Atomic conditional update on status change |

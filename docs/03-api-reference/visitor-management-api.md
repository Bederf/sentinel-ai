---
title: "Visitor Management API"
type: "api"
status: "approved"
version: "1.3.0"
created: "2026-04-01"
updated: "2026-04-03"
tags: ["visitor-management", "api", "reception", "access-control"]
related: ["../04-features/176-visitor-management.md", "../05-integrations/visitor-management-integrations.md"]
domain: "api"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 8
---

# Visitor Management API

Base path: `/api/reception`

## POST /api/reception/scan

Scan a visitor's QR code or enter their PIN at reception.

**Auth:** Bearer token (any role)

### Request

```json
// Option 1: QR scan (token)
{ "token": "550e8400-e29b-41d4-a716-446655440000" }

// Option 2: PIN fallback
{ "pin": "042871" }
```

### Response 200

```json
{
  "visit": {
    "id": "uuid",
    "token": "uuid",
    "pin": "042871",
    "visitor_email": "visitor@example.com",
    "visitor_name": null,
    "host_email": "host@company.com",
    "host_name": "Jane Smith",
    "building_id": "site-001",
    "meeting_start": "2026-04-01T09:00:00Z",
    "meeting_end": "2026-04-01T10:00:00Z",
    "status": "arrived",
    "visitor_photo": null,
    "visitor_vehicle": null,
    "visitor_id_number": null,
    "access_card_id": null,
    "qr_code": "data:image/png;base64,...",
    "created_at": "2026-04-01T08:00:00Z",
    "updated_at": "2026-04-01T08:30:00Z"
  },
  "building_name": "Fairlands Head Office",
  "time_window_valid": true
}
```

### Error Responses

| Code | Condition |
|------|-----------|
| 400 | Neither token nor pin provided |
| 400 | Both token and pin provided |
| 404 | Token/pin not found |
| 403 | Meeting has not started yet |
| 410 | Visit expired or cancelled |

---

## POST /api/reception/register

Capture visitor details at reception. Updates **existing** visit only.

**Auth:** Bearer token (any role)

### Request

```json
{
  "token": "550e8400-e29b-41d4-a716-446655440000",
  "visitor_name": "John Doe",
  "photo": "data:image/jpeg;base64,...",
  "vehicle": "White Toyota Hilux GP 1234",
  "id_number": "9001011234087"
}
```

### Response 200

```json
{
  "visit": { ... },
  "message": "Visitor registered successfully"
}
```

### Error Responses

| Code | Condition |
|------|-----------|
| 404 | Token not found |
| 409 | Already registered |
| 409 | Not yet scanned (must scan before registering) |

---

## POST /api/reception/issue-card

Issue an access card to a registered visitor. Wires to C-CURE.

**Auth:** Bearer token (operator or above)

### Request

```json
{
  "token": "550e8400-e29b-41d4-a716-446655440000",
  "access_card_id": "VIS-550E8400"
}
```

### Response 200

```json
{
  "visit_id": "uuid",
  "status": "active",
  "access_card_id": "VIS-550E8400"
}
```

### Error Responses

| Code | Condition |
|------|-----------|
| 404 | Token not found |
| 400 | Visitor not registered |
| 403 | Host denied access |

---

## POST /api/whatsapp/whatsapp/visit/reply

Twilio WhatsApp webhook for host YES/NO replies.

**Auth:** Twilio HMAC-SHA1 signature (X-Twilio-Signature header)

### Twilio Form Payload

```
Body=YES&From=whatsapp:+27821234567
```

### Response (TwiML)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>✅ Approved. Your visitor (John Doe) has been cleared.</Message>
</Response>
```

### Error Responses

| Code | Condition |
|------|-----------|
| 403 | Invalid Twilio signature |

---

## POST /api/visits/rsvp

Handle visitor RSVP (accept/decline) to a calendar invite. Used by n8n when a `METHOD:REPLY` iTip is received, and by the Google Calendar webhook when a visitor accepts/declines.

**Auth:** `X-Sentry-API-Key` header (sentry bot API key)

### Request

```json
{
  "external_event_id": "gcal-jo9janvjg81oje3koc5npr4cko",
  "response": "accepted",
  "visitor_email": "visitor@example.com"
}
```

`external_event_id` format:
- Google Calendar: `gcal-{eventId}`
- Microsoft Graph: `{eventId}` (raw Graph event ID)
- IMAP/ICS (n8n): `n8n-ics-{UID}`

### Response 200 (accepted)

```json
{
  "success": true,
  "visit_id": "uuid",
  "status": "created",
  "qr_code": "data:image/png;base64,...",
  "message": "Visit accepted — confirmation email will be sent"
}
```

### Response 200 (declined)

```json
{
  "success": true,
  "visit_id": "uuid",
  "status": "cancelled",
  "qr_code": null,
  "message": "Visit declined"
}
```

### Error Responses

| Code | Condition |
|------|-----------|
| 400 | Invalid response value (must be 'accepted' or 'declined') |
| 403 | Visitor email does not match pending visit |
| 404 | No pending visit found for external_event_id |

---

## GET /api/visits/qr/{token}

Serve the QR code PNG for a visit token. No auth — token is the secret.

**Auth:** None (token is secret)

### Response 200

`image/png` — raw PNG bytes

### Error Responses

| Code | Condition |
|------|-----------|
| 400 | Invalid token format |
| 404 | Visit not found or has no QR code |

---

## Data Model

### VisitStatus (enum)

| Value | Meaning |
|-------|---------|
| `pending` | Invite received, visitor has not yet accepted |
| `created` | Visitor accepted, QR/PIN sent, waiting for arrival |
| `arrived` | Visitor scanned at reception |
| `registered` | Visitor details captured |
| `approved` | Host approved via WhatsApp |
| `denied` | Host or system denied |
| `active` | Access card issued |
| `expired` | Past time window |
| `cancelled` | Explicitly cancelled |

### BuildingMap

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `name` | string | Human-readable name |
| `outlook_location_string` | string | Matches Outlook room name |
| `site_id` | string | SENTINEL site identifier |

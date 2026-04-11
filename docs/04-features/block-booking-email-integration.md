---
title: "Block Booking Email Integration — n8n Configuration"
type: "reference"
status: "active"
version: "1.0.0"
created: "2026-04-11"
updated: "2026-04-11"
tags: ["sentinel", "n8n", "block-booking", "fairlands", "integration"]
related: ["space-intelligence-ghost-booking-pipeline", "03-api-reference/block-bookings-api"]
domain: "bms"
audience: ["devops", "fnb-it"]
complexity: "intermediate"
estimated_read_time: 10
---

# Block Booking Email Integration — n8n Configuration

## Overview

The SENTINEL block booking detection pipeline monitors incoming meeting room reservation emails from Fairlands Resource Scheduler via n8n and triggers ghost room + block booking overlap detection.

**Current Status:** n8n workflow active; awaiting FNB IT configuration to send production booking confirmation emails.

---

## Workflow Configuration

### Identification

| Property | Value |
|----------|-------|
| Workflow Name | SENTINEL — Block Booking Email Ingest |
| Workflow ID | `xR12CDjsX74PQp4S` |
| Status | Active |
| Last Updated | 2026-04-01 |
| IMAP Credential | SENTINEL Rooms IMAP (ID: `sNX9nInYH8ZZkftL`) |
| Backend Endpoint | `POST http://127.0.0.1:9095/api/block-bookings/ingest` |

### Architecture

```
Fairlands Resource Scheduler
    │
    ▼ (email notifications)
rooms@sentinel-ai.co.za
    │
    ▼ n8n IMAP Trigger
New Booking Email (polls every ~60s)
    │
    ▼ Filter: Contains booking keywords
Is Booking Confirmation?
    ├─ YES ──→ Extract .ics or raw email body
    │          Build Ingest Payload
    │          POST to /api/block-bookings/ingest
    │          Log Result
    │
    └─ NO ──→ Log Skipped
```

---

## Email Configuration for FNB IT

### Incoming Email Address

**`rooms@sentinel-ai.co.za`**

This is the email address the n8n workflow monitors for booking confirmation emails from Resource Scheduler.

**Configure Resource Scheduler to send:**
- ✓ New Resource Use Notification (booking created)
- ✓ Reservation Accepted
- ✓ Reservation Cancelled
- ✓ Meeting Invitations (optional)

**Delivery method:** BCC or notification recipient list (your choice)

**Requirements:**
- Include `.ics` attachment in the email (RFC 5545 iCalendar format)
- Include booking details (room code, organiser, date/time) in email body
- Send continuously as rooms are booked/cancelled

### Outgoing Email Address

**`rooms@sentinel-ai.co.za`** (same address)

Used to send ghost booking alerts back to concierge team.

---

## Payload Structure

### Request to Backend

```json
{
  "raw_email": "From: resource-scheduler@fnb.co.za\nTo: rooms@sentinel-ai.co.za\nSubject: New Resource Use Notification\n...",
  "ics_data": "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//FNB//Resource Scheduler//EN\n...",
  "site_id": "site-002"
}
```

**Fields:**
- `raw_email` (required): Full email in RFC 822 format
- `ics_data` (optional): iCalendar attachment content
- `site_id` (auto-resolved from room codes if not provided)

### Backend Response

```json
{
  "success": true,
  "action": "booking_ingested",
  "booking_id": "uuid",
  "organiser": "user@fnb.co.za",
  "room": "Boardroom 1",
  "date": "2026-04-15",
  "parse_source": "resource_scheduler",
  "alerts_generated": 1,
  "alerts_notified": 1
}
```

---

## n8n Workflow Details

### Email Filters (OR logic)

Captures emails where subject contains ANY of:
- "New Resource Use Notification"
- "Cancelled Reservation"
- "Accepted"
- "Invitation"
- "Meeting"

### Payload Extraction

1. **Primary:** Extracts `.ics` attachment if present
2. **Fallback:** Uses email body (text/plain or HTML→text conversion)
3. **Header Extraction:** Parses From, To, Subject, Date fields
4. **Building Code Detection:** Extracts FA/FLN code from subject for diagnostics

### Deduplication

Backend uses SHA-256 hash of raw email to detect and skip duplicates (24-hour window).

---

## Diagnostic & Testing

### Check Workflow Execution

```bash
# List recent executions
curl -s -H "X-N8N-API-KEY: $N8N_API_KEY" \
  http://localhost:5678/api/v1/workflows/xR12CDjsX74PQp4S/executions | jq '.data[] | {id, finished, startedAt}'

# Get specific execution details
curl -s -H "X-N8N-API-KEY: $N8N_API_KEY" \
  http://localhost:5678/api/v1/executions/{executionId}
```

### Check Ingested Bookings

```bash
# Query ingested bookings
curl -s http://localhost:9095/api/block-bookings/bookings?site_id=site-002 \
  -H "X-Sentry-API-Key: <api_key>" | jq '.data[] | {booking_id, organiser, room, date, source}'

# Check specific booking
curl -s http://localhost:9095/api/block-bookings/bookings/site-002?from_date=2026-04-01 \
  -H "X-Sentry-API-Key: <api_key>"
```

### Check Block Booking Alerts

```bash
# List open alerts
curl -s http://localhost:9095/api/block-bookings/alerts?site_id=site-002 \
  -H "X-Sentry-API-Key: <api_key>" | jq '.alerts[] | {id, organiser_name, room_count, detected_at}'
```

### Test Webhook Directly

```bash
# Send test booking email to backend
curl -X POST http://localhost:9095/api/block-bookings/ingest \
  -H "Content-Type: application/json" \
  -H "X-Sentry-API-Key: <api_key>" \
  -d '{
    "raw_email": "From: test@fnb.co.za\nTo: rooms@sentinel-ai.co.za\nSubject: New Resource Use Notification\n...",
    "site_id": "site-002"
  }'
```

---

## Troubleshooting

### Emails Not Appearing in n8n Logs

1. **Check IMAP credential configuration** in n8n UI (Settings → Credentials → SENTINEL Rooms IMAP)
   - Verify host, port (993), username (rooms@sentinel-ai.co.za), password
2. **Check workflow is active** — status should be "Active" (green toggle)
3. **Manually trigger execution** — click "Test Workflow" button in n8n UI
4. **Check mail server connectivity** — test IMAP connection separately

### Emails Received But Not Ingested to Backend

1. **Check filter keywords** — email subject must contain one of the required keywords
2. **Check backend endpoint** — verify `http://127.0.0.1:9095` is reachable from n8n
3. **Check authentication headers** — verify `X-Sentry-API-Key` and `X-Sentry-Secret` are correct
4. **Check backend logs** — `POST /api/block-bookings/ingest` should show 200 response

### No Alerts Generated from Bookings

1. **Check booking overlap detection** — requires minimum `block_booking_min_rooms` overlapping bookings
2. **Check notification configuration** — `GET /api/block-bookings/config?site_id=site-002`
3. **Check concierge contact details** — email/WhatsApp must be configured

---

## Timeline & Status

| Date | Milestone |
|------|-----------|
| 2026-03-11 | n8n workflow created |
| 2026-03-12 | Test data ingested (synthetic bookings from Lemond Luxman) |
| 2026-04-01 | Workflow updated (filter optimization) |
| 2026-04-11 | **Configuration confirmed; ready for FNB IT handoff** |
| TBD | FNB IT configures Resource Scheduler |
| TBD | Production bookings flowing into pipeline |
| TBD | Concierge alerts operational |

---

## Related Documentation

- **Ghost Booking Pipeline:** [[space-intelligence-ghost-booking-pipeline]]
- **Block Bookings API:** [[block-bookings-api]]
- **n8n Email Pipeline:** [[n8n-email-pipeline]]
- **Fairlands Integration:** Obsidian vault → 04-features/Block-Booking-Email-Configuration.md

---

## Contacts & Escalation

**SENTINEL Team:** Responsible for n8n workflow and backend ingestion
**FNB IT:** Responsible for Resource Scheduler email configuration
**Concierge Manager:** Receives alerts and manages responses

---

**Status:** Ready for Production | **Action:** Send email address to FNB IT | **Expected Activation:** End of Week

---
title: "Plant Room Notification Pipeline"
type: "guide"
status: "approved"
version: "2.0.0"
created: "2026-03-07"
updated: "2026-03-07"
author: "Sentinel Development Team"
tags: ["plant-alerts", "desigo", "whatsapp", "twilio", "notifications", "n8n"]
domain: "bms"
audience: "operators"
complexity: "intermediate"
estimated_read_time: 10
---

# Plant Room Notification Pipeline

**Phase:** 146 | **Version:** 2.0 | **Status:** Active

## Overview

The Plant Room Notification Pipeline converts Desigo BMS fault emails into classified, stored alarms with instant WhatsApp notification via Twilio. SENTINEL acts as a read-only overlay -- it does not connect to or control Desigo.

```
Desigo BMS --> noreply@fnb.co.za email --> n8n IMAP trigger
  --> SENTINEL POST /api/plant/alerts/ingest
    --> Validate sender (403 if not authorised)
    --> Check duplicate (409 if within 1-hour dedup window)
    --> Parse subject (equipment, alarm type, status)
    --> Classify severity (very_critical / critical / non_critical / cleared)
    --> Detect equipment category (hvac, power, fire_safety, etc.)
    --> Save alarm (Supabase -> JSON fallback)
    --> Throttle check (flood detection + rate limit)
    --> Send WhatsApp via Twilio (or suppress if flooding)
```

## Architecture

### Module Structure

```
backend/app/plant/
  __init__.py
  models.py                 # DesigoBuildingAlarm, AlarmSeverity
  email_parser.py            # parse_desigo_email() -- subject + body parsing
  alarm_store.py             # 3-tier persistence (Supabase -> JSON)
  whatsapp_notifier.py       # Twilio WhatsApp API + webhook fallback
  notification_throttle.py   # Flood detection + rate limiting
  plant_alerts.py            # FastAPI router (5 endpoints)
```

### Conditional Registration

The router is only registered when `PLANT_ALERTS_ENABLED=true` in settings. Gate is in `backend/app/api/registrars/operations.py`.

## API Reference

### POST /api/plant/alerts/ingest

Parse and ingest a Desigo fault email. Validates sender, deduplicates, classifies, persists, and notifies.

**Request body:**
```json
{
  "from_address": "noreply@fnb.co.za",
  "subject": "AHU B2-AHU-01 Fail Status (Fault)",
  "body": "Building: Fairland 2\nEquipment: AHU B2-AHU-01\nAlarm: Fail Status High",
  "received_at": "2026-03-07T10:30:00Z",
  "site_id": "FLN02"
}
```

**Responses:**

| Code | Meaning |
|------|---------|
| 200  | Alarm ingested successfully |
| 400  | Empty subject |
| 403  | Sender not authorised (does not match DESIGO_SENDER_EMAIL) |
| 409  | Duplicate alarm within dedup window (1 hour) |

**200 Response:**
```json
{
  "alarm_id": "uuid-here",
  "severity": "critical",
  "equipment": "AHU B2-AHU-01",
  "notified": true,
  "cleared": false
}
```

### GET /api/plant/alerts

Return recent alarms for a site.

**Query parameters:**

| Param   | Type   | Default         | Description |
|---------|--------|-----------------|-------------|
| site_id | string | PLANT_SITE_ID   | Site identifier |
| limit   | int    | 50              | Max alarms to return |

### GET /api/plant/alerts/throttle/status

Return current throttle state -- flood detection and rate limit status.

**Response:**
```json
{
  "flood": {
    "AHU B2-AHU-01": {
      "recent_alarms": 12,
      "flood_active": true,
      "suppressed_count": 7,
      "window_minutes": 10,
      "threshold": 5
    }
  },
  "rate_limit": {
    "messages_this_hour": 8,
    "hourly_limit": 30,
    "remaining": 22
  }
}
```

### GET /api/plant/alerts/{alarm_id}

Return a single alarm by ID. Returns 404 if not found.

### POST /api/plant/alerts/{alarm_id}/acknowledge

Mark an alarm as acknowledged/notified.

**Response:**
```json
{
  "alarm_id": "uuid-here",
  "acknowledged": true
}
```

## WhatsApp Delivery (Twilio)

Notifications are delivered via the **Twilio WhatsApp API** as the primary channel, with an n8n webhook as fallback.

### Delivery Priority

1. **Twilio WhatsApp API** -- if `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`, and `TWILIO_WHATSAPP_TO` are all configured
2. **n8n webhook fallback** -- if `WHATSAPP_WEBHOOK_URL` is configured and Twilio is not

### Twilio Integration

- **Endpoint:** `POST https://api.twilio.com/2010-04-01/Accounts/{SID}/Messages.json`
- **Auth:** HTTP Basic Auth (`account_sid:auth_token`)
- **Payload:** Form data with `From` (whatsapp:+number), `To` (whatsapp:+number), `Body` (formatted message)
- **Retry:** Critical/very_critical alarms retry once on failure. Non-critical alarms do not retry.

### Message Formatting

Messages are severity-coded with emoji prefixes:

| Severity | Emoji | Label |
|----------|-------|-------|
| very_critical | Red circle x2 | URGENT -- Immediate response required |
| critical | Red circle | Action required |
| non_critical | Yellow circle | For attention |
| cleared | Green check | Fault resolved |

**Example WhatsApp message (critical):**
```
Red circle *Action required*

*Site:* FLN02
*Building:* Fairland 2
*Equipment:* Roof Atrium Extract Fan
*Alarm:* Fail Status
*Status:* Fault
*Category:* hvac
*Received:* 2026-03-07 10:30
```

## Notification Throttle

Three layers of protection against chatty BMS systems (e.g., faulty sensors oscillating, 41 FCUs alarming simultaneously):

### Layer 1: Dedup Window

Same email subject within 1 hour returns HTTP 409. Handled in `alarm_store.check_duplicate()`.

### Layer 2: Alarm Flood Detection

Per-equipment tracking: if >N alarms from the same `equipment_description` arrive within M minutes, a single flood summary is sent instead of individual alerts. Subsequent alarms are suppressed until the flood clears.

| Setting | Default | Description |
|---------|---------|-------------|
| Flood threshold | 5 alarms | Alarms from same equipment to trigger flood |
| Flood window | 10 minutes | Rolling window for flood detection |

**Flood summary message:**
```
Warning *SENTINEL -- ALARM FLOOD DETECTED*

*Roof Atrium Extract Fan* -- 47 alarms in 10 minutes

Possible sensor fault. Single notification only until resolved.
Individual alerts suppressed to prevent message flooding.
```

### Layer 3: Hourly Rate Limit

Global cap: max 30 WhatsApp messages per hour regardless of alarm volume. Prevents runaway costs and message flooding.

| Setting | Default | Description |
|---------|---------|-------------|
| Hourly limit | 30 messages | Max WhatsApp messages per hour |

### State Management

All throttle state is **in-memory** (resets on restart). This is intentional -- flood state should not persist across restarts. Alarms are still saved to Supabase/JSON regardless of throttle state.

Monitor throttle state via `GET /api/plant/alerts/throttle/status`.

## Severity Classification

| Severity | Condition | WhatsApp Format |
|----------|-----------|-----------------|
| very_critical | fire_safety + body contains "High" | Red circle x2 -- "URGENT -- Immediate response required" |
| critical | Body contains "High" OR empty body (safe default) | Red circle -- "Action required" |
| non_critical | Body contains "Low" or "Normal" | Yellow circle -- "For attention" |
| cleared | Status = "Normal" AND alarm type contains "Fail"/"Fault" | Green check -- "Fault resolved" |

## Equipment Category Mapping

| Pattern (case-insensitive) | Category |
|---------------------------|----------|
| fire damper, fd  | fire_safety |
| generator, gen, ats, ups | power |
| ahu, fcu, fpu, fan, reheat, ohs, chiller | hvac |
| pump | mechanical |
| temperature, humidity | monitoring |
| (no match) | unknown |

## Email Parsing

### Subject Format

Desigo emails follow the pattern: `{equipment_description} {alarm_type} ({status})`

Examples:
- `Roof Atrium Extract Fan Fail Status (Fault)`
- `FD B2-L3-01 Trip Status (Fault)`
- `Generator 1 Start Status (Normal)`

The parser uses keyword-anchored regex, matching group 2 against known Desigo alarm keywords: `Fail`, `Trip`, `Fault`, `Start`, `High`, `Low`, `Open`, `Closed`, `Alert`, `Alarm`, `Status`.

### Body Severity

Line 3 of the body typically contains `{description} {alarm_type} ({status}) {severity_word}` where severity_word is "High", "Low", or "Normal".

## n8n IMAP Workflow

**Workflow name:** "SENTINEL -- Desigo Fault Email Ingest"

### Node Chain

```
Poll Inbox (IMAP) --> Desigo Sender Only (IF) --> Extract Email Fields (Code)
  --> POST to SENTINEL (HTTP) --> Check Response (IF)
    --> Log Success / Log Error / Ignored (NoOp)
```

### Configuration

| Setting | Value |
|---------|-------|
| IMAP credential | `info@sentinel-ai.co.za` (shared with Email Intake workflow) |
| Sender filter | `noreply@fnb.co.za` |
| Target endpoint | `http://127.0.0.1:9095/api/plant/alerts/ingest` |
| Poll interval | Every 1 minute |

### Conflict Avoidance

The existing Email Intake workflow (Phase 131) filters OUT `noreply@` senders. The Desigo workflow ONLY processes `noreply@fnb.co.za`. Same inbox, zero overlap.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| PLANT_ALERTS_ENABLED | false | Master switch -- must be true to register the router |
| DESIGO_SENDER_EMAIL | noreply@fnb.co.za | Authorised sender address for email validation |
| PLANT_SITE_ID | FLN02 | Default site identifier for alarms |
| PLANT_BUILDING_NAME | Fairland 2 | Default building name for alarms |
| TWILIO_ACCOUNT_SID | (empty) | Twilio account SID for WhatsApp delivery |
| TWILIO_AUTH_TOKEN | (empty) | Twilio auth token |
| TWILIO_WHATSAPP_FROM | (empty) | Twilio WhatsApp sender (e.g. whatsapp:+14155238886) |
| TWILIO_WHATSAPP_TO | (empty) | Target WhatsApp number (e.g. whatsapp:+27798607245) |
| WHATSAPP_WEBHOOK_URL | (empty) | n8n webhook URL (fallback if Twilio not configured) |
| WHATSAPP_GROUP_ID | (empty) | Target WhatsApp group ID (webhook mode) |

## Data Persistence

### Supabase (Primary)

Table: `building_alarms` -- 15 columns including severity, equipment_category, notified, cleared timestamps.

### JSON Fallback

File: `backend/app/data/plant/building_alarms.json` -- array of alarm objects, used when Supabase is unavailable.

### Dedup Window

`check_duplicate(subject)` looks for matching subject within the last 1 hour. Returns true if found, preventing re-processing of the same alarm.

## Testing

52 tests across 5 test files:

| File | Tests | Coverage |
|------|-------|----------|
| `tests/plant/test_email_parser.py` | 18 | Subject parsing, severity classification, category detection |
| `tests/plant/test_alarm_store.py` | 6 | Save, retrieve, dedup, mark notified/cleared |
| `tests/plant/test_whatsapp_notifier.py` | 10 | Twilio delivery, webhook fallback, retry logic, message formatting |
| `tests/plant/test_notification_throttle.py` | 10 | Flood detection, rate limiting, flood summary, status API |
| `tests/plant/test_plant_alerts.py` | 8 | Endpoint validation, sender auth, duplicate handling, integration |

Run tests:
```bash
cd backend && pytest tests/plant/ -v
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Router not registered | Set `PLANT_ALERTS_ENABLED=true` in .env and restart backend |
| 403 on ingest | Check `DESIGO_SENDER_EMAIL` matches the actual Desigo sender address |
| WhatsApp not sending | Verify all 4 Twilio env vars are set (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`, `TWILIO_WHATSAPP_TO`) |
| Flood suppressing too aggressively | Check throttle status at `GET /api/plant/alerts/throttle/status`; restart backend to reset in-memory state |
| Duplicates not detected | Dedup window is 1 hour; alarms older than that are treated as new |
| Alarms not persisting | Check Supabase connectivity or JSON fallback directory permissions at `backend/app/data/plant/` |
| n8n not triggering | Verify IMAP credentials, mailbox name, and poll interval in n8n UI |
| Rate limit reached | 30 msgs/hour cap; wait for window to roll or restart backend to reset |

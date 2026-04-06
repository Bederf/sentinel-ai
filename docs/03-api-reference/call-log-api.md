---
title: "Call Log API"
type: "reference"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# Call Log API

## Overview

> **Phase 147 Update (2026-03-07):** Free-text complaint routing from Telegram is now handled by the backend conversation system via `POST /api/sentry/telegram/message` and `POST /api/sentry/telegram/callback`. These new endpoints handle intent classification, multi-step conversation flows with inline keyboards, and work order creation automatically. The call log endpoints below remain available for WhatsApp, mobile app, and email channels, and as a programmatic API for direct WO creation from classified complaints.

Call log endpoints support the Sentry bot's general staff defect reporting workflow. Non-technical users (office workers, cleaners, security guards) report building issues via Telegram, WhatsApp, mobile app, or email. The bot classifies the complaint against a fixed taxonomy and creates an inspection work order.

Five endpoints (3 original + 2 new):

1. **`POST /api/sentry/call-log`** — Create an inspection work order from a classified complaint
2. **`POST /api/sentry/call-log/escalate`** — Escalate an unclassifiable complaint to the facilities supervisor
3. **`GET /api/sentry/call-log/location-memory`** — Lookup last confirmed location for reporter prefill

## POST /api/sentry/call-log

Creates an inspection work order from a call-logged facilities defect. Called by the `call_log_handler.py` conversation handler after the user confirms the issue and location.

**Authentication:** Required — both `X-Sentry-Secret` and `X-Sentry-API-Key` headers.

```
X-Sentry-Secret: <configured secret>
X-Sentry-API-Key: <configured API key>
```

**Request Body:**

```json
{
  "site_id": "site-002",
  "zone_id": "Zone-208",
  "floor": "L2",
  "desk_id": "208",
  "location_text": "Desk 208, L2",
  "category": "Plumbing",
  "sub_category": "Leaking tap",
  "specialty": "plumbing",
  "priority": "medium",
  "title": "Plumbing: Leaking tap",
  "description": "Reported by Jane via Telegram.\nDiscipline: Plumbing\nSub-category: Leaking tap\nLocation: Desk 208, L2, site-002\nPriority: medium\n\nReporter's description: dripping tap near my desk\n\nCall-logged defect — inspection required.",
  "reported_by": "Jane",
  "reporter_telegram_id": "12345678",
  "reporter_phone": "+27721234567",
  "channel": "whatsapp",
  "original_message": "dripping tap near my desk"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `site_id` | string | No | Site identifier (default: `site-002`) |
| `zone_id` | string | No | Zone from desk mapping (e.g., `Zone-208`) |
| `floor` | string | No | Floor level (`L0`, `L1`, `L2`, `B1`) |
| `desk_id` | string | No | Desk number if applicable |
| `location_text` | string | No | Human-readable location description |
| `category` | string | Yes | Discipline from fixed taxonomy (e.g., `Plumbing`, `Electrical`) |
| `sub_category` | string | No | Sub-category from fixed taxonomy (e.g., `Leaking tap`) |
| `specialty` | string | No | Team specialty for routing (default: `general`) |
| `priority` | string | No | Auto-classified priority (default: `medium`) |
| `title` | string | Yes | Brief issue title (uses controlled taxonomy values) |
| `description` | string | Yes | Full description with context |
| `reported_by` | string | No | Reporter display name |
| `reporter_telegram_id` | string | No | Reporter Telegram ID for audit |
| `reporter_phone` | string | No | Reporter mobile number for location memory |
| `channel` | string | No | Source channel (`telegram`, `whatsapp`, `mobile`, `email`) |
| `original_message` | string | No | Raw user message (stored for context, not used for routing) |

### Pre-approved location gate and memory behavior

Before logging a work order, the intake flow must satisfy this gate:

1. `category` / `sub_category` / `priority` resolved from fixed taxonomy
2. Location confirmed (`desk_id` OR floor/area text)
3. User confirmation received

Location memory is used to reduce repeat questions:

1. First report: user supplies desk/location manually
2. Backend stores reporter-to-location memory after successful log
3. Next report: client can query `GET /api/sentry/call-log/location-memory` using `reporter_phone` or `reporter_telegram_id`
4. Bot/app pre-fills the location and asks for confirmation before creating the next WO

Current limitation: location is still user-confirmed. AD profile location and access-card-based location are not integrated in the current version.

**Response (200 OK):**

```json
{
  "success": true,
  "work_order_code": "WO-2026-0035",
  "work_order_id": "9eb7a45d-a31c-47c7-bb35-3251412b09cf",
  "category": "Plumbing",
  "priority": "medium",
  "location": "Desk 208, L2, Zone-208",
  "assigned_to": "John Smith",
  "technician_notified": false
}
```

| Field | Type | Description |
|-------|------|-------------|
| `success` | boolean | Always `true` on 200 |
| `work_order_code` | string | WO reference number (e.g., `WO-2026-0035`) |
| `work_order_id` | string | UUID of created work order |
| `category` | string | Discipline from request |
| `priority` | string | Priority from request |
| `location` | string | Formatted location string |
| `assigned_to` | string | Assigned technician name or `"maintenance team"` |
| `technician_notified` | boolean | Whether Telegram notification was sent to technician |

**Side effects:**

1. Creates work order in Supabase (`work_orders` table) with `service_type: "callout"` and `status: "scheduled"`
2. Assigns technician by specialty lookup in `site_technicians` table (falls back to `general` specialty)
3. Sends Telegram notification to assigned technician (if `telegram_id` configured)
4. Maps `critical` priority to `urgent` in WO system
5. Stores reporter location memory (`reporter_phone`/`reporter_telegram_id` -> last confirmed desk/location)

**Technician assignment logic:**

1. Look up building by `site_id` code
2. Query `site_technicians` for `specialty` match where `is_primary = true`
3. If no match, fall back to `general` specialty
4. If no technician found, assigns to `"maintenance team"`

**Error responses:**

| Code | Condition |
|------|-----------|
| 403 | Missing or invalid `X-Sentry-Secret` / `X-Sentry-API-Key` |
| 500 | Work order creation failed |

---

## POST /api/sentry/call-log/escalate

Escalates an unmatched complaint to the facilities supervisor. Called by the call log handler when the user's complaint doesn't match any discipline/sub-category in the fixed taxonomy.

**Authentication:** Required — both `X-Sentry-Secret` and `X-Sentry-API-Key` headers.

**Request Body:**

```json
{
  "reporter_name": "Bob",
  "reporter_telegram_id": "87654321",
  "original_message": "there is a monkey in the office",
  "reason": "No matching discipline/sub-category in call log taxonomy",
  "site_id": "site-002",
  "timestamp": "2026-02-25T10:00:00"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `reporter_name` | string | No | Reporter display name |
| `reporter_telegram_id` | string | No | Reporter Telegram ID |
| `original_message` | string | Yes | The complaint text that couldn't be classified |
| `reason` | string | No | Why it was escalated |
| `site_id` | string | No | Site identifier (default: `site-002`) |
| `timestamp` | string | No | ISO timestamp of the complaint |

**Response (200 OK):**

```json
{
  "success": true,
  "escalated": true,
  "supervisor_notified": false,
  "message": "Complaint flagged for supervisor review"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `success` | boolean | Always `true` on 200 |
| `escalated` | boolean | Always `true` |
| `supervisor_notified` | boolean | Whether Telegram notification was sent to supervisor |
| `message` | string | Human-readable status |

**Side effects:**

1. Logs warning: `[CALL_LOG_ESCALATION] Unmatched complaint from {name} ({id}): {message}`
2. Persists escalation record to `backend/app/data/call_log_escalations.json`
3. If `CALL_LOG_SUPERVISOR_TELEGRAM_ID` env var is set, sends Telegram notification to supervisor

**Escalation record format:**

```json
{
  "reporter_name": "Bob",
  "reporter_telegram_id": "87654321",
  "original_message": "there is a monkey in the office",
  "reason": "No matching discipline/sub-category in call log taxonomy",
  "site_id": "site-002",
  "timestamp": "2026-02-25T10:00:00",
  "status": "pending_review"
}
```

**Error responses:**

| Code | Condition |
|------|-----------|
| 403 | Missing or invalid `X-Sentry-Secret` / `X-Sentry-API-Key` |

---

## GET /api/sentry/call-log/location-memory

Lookup endpoint for reporter last-known location memory, used to prefill manual location confirmation on mobile channels.

**Authentication:** Required — both `X-Sentry-Secret` and `X-Sentry-API-Key` headers.

**Query parameters:**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `reporter_phone` | string | Conditional | Mobile number (recommended) |
| `reporter_telegram_id` | string | Conditional | Telegram reporter ID |

At least one of `reporter_phone` or `reporter_telegram_id` must be provided.

Use the lookup as a prefill only. Always ask the user to confirm or correct the location before logging.

**Response (found):**

```json
{
  "success": true,
  "found": true,
  "reporter_phone": "+27721234567",
  "reporter_telegram_id": "12345678",
  "reporter_name": "Jane",
  "site_id": "site-002",
  "zone_id": "Zone-208",
  "floor": "L2",
  "desk_id": "208",
  "location_text": "Desk 208, L2, Zone-208",
  "last_confirmed_at": "2026-02-27T12:20:00",
  "last_work_order_code": "WO-2026-0035"
}
```

**Response (not found):**

```json
{
  "success": true,
  "found": false,
  "reporter_phone": "+27721234567",
  "reporter_telegram_id": ""
}
```

**Error responses:**

| Code | Condition |
|------|-----------|
| 400 | Neither reporter identifier provided |
| 403 | Missing or invalid `X-Sentry-Secret` / `X-Sentry-API-Key` |

---

## Fixed Taxonomy Reference

The call log handler uses a closed set of 10 disciplines / 46 sub-categories. View the full list:

```bash
python3 $SENTRY_HOME/tools/call_log.py categories
```

Classification is done by keyword matching in Python — the LLM never decides the category. Multi-word keywords score higher for specificity. Urgency keywords (`trip`, `flooding`, `sparking`, `fire`, `gas`, etc.) automatically escalate priority.

IT-related messages (PC, laptop, WiFi, printer, software, etc.) are excluded and the user is redirected to the IT helpdesk. Facility keywords (`power`, `outlet`, `socket`, `light`) override the IT exclusion.

---

## CLI Tool Reference

The `call_log.py` CLI tool is used by the Sentry gateway:

```bash
# Classify a complaint (returns JSON)
python3 $SENTRY_HOME/tools/call_log.py classify "there is a dripping tap"

# Log a defect and create WO (only after user confirmation)
python3 $SENTRY_HOME/tools/call_log.py log \
  --desk 208 \
  --complaint "Dripping tap near my desk" \
  --user "Jane" \
  --user-id "12345678"

# Log without desk number
python3 $SENTRY_HOME/tools/call_log.py log \
  --complaint "Dripping tap in Level 2 ladies bathroom" \
  --user "Jane" \
  --user-id "12345678"

# List all disciplines and sub-categories
python3 $SENTRY_HOME/tools/call_log.py categories
```

---

---

## POST /api/sentry/telegram/message (Phase 147)

Delegates a free-text Telegram message to the backend conversation system. The backend classifies intent, manages conversation sessions, runs the appropriate flow, and sends the reply (with inline keyboards) directly to Telegram. The caller should NOT send any additional reply.

**Authentication:** Required -- both `X-Sentry-API-Key` and `X-Sentry-Secret` headers.

**Request Body:**

```json
{
  "chat_id": "123456789",
  "user_id": "987654321",
  "username": "johndoe",
  "display_name": "John Doe",
  "text": "it's too hot on level 3",
  "has_photo": false,
  "message_id": 42
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `chat_id` | string | Yes | Telegram chat ID |
| `user_id` | string | Yes | Telegram user ID |
| `username` | string | No | Telegram username |
| `display_name` | string | No | User display name |
| `text` | string | No | Message text |
| `has_photo` | boolean | No | Whether message includes a photo |
| `photo_file_id` | string | No | Telegram file ID for photo |
| `message_id` | integer | No | Telegram message ID |

**Response (200 OK):**

```json
{
  "success": true,
  "intent": "client_complaint",
  "confidence": 0.85
}
```

**Error responses:**

| Code | Condition |
|------|-----------|
| 403 | Missing or invalid `X-Sentry-Secret` / `X-Sentry-API-Key` |
| 200 | `{"success": false, "error": "blocked by prompt guard"}` -- prompt injection detected |
| 200 | `{"success": false, "requires_consent": true}` -- POPIA consent not granted |

---

## POST /api/sentry/telegram/callback (Phase 147)

Handles inline keyboard button taps (Telegram `callback_query`). Dismisses the button spinner, classifies intent from `callback_data`, and routes to the appropriate flow handler. The backend sends the next reply directly to Telegram.

**Authentication:** Required -- both `X-Sentry-API-Key` and `X-Sentry-Secret` headers.

**Request Body:**

```json
{
  "callback_query_id": "cbq-123",
  "chat_id": "123456789",
  "user_id": "987654321",
  "message_id": 42,
  "data": "complaint:category:hvac"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `callback_query_id` | string | Yes | Telegram callback query ID |
| `chat_id` | string | Yes | Telegram chat ID |
| `user_id` | string | Yes | Telegram user ID |
| `message_id` | integer | Yes | Message ID of the keyboard message |
| `data` | string | Yes | Callback data string (format: `{flow}:{action}:{value}`) |

**Response (200 OK):**

```json
{
  "success": true,
  "intent": "checklist_reply",
  "confidence": 1.0
}
```

**Error responses:**

| Code | Condition |
|------|-----------|
| 403 | Missing or invalid `X-Sentry-Secret` / `X-Sentry-API-Key` |

---

## Implementation

- Handler (legacy): `$SENTRY_HOME/handlers/call_log_handler.py`
- CLI tool (legacy): `$SENTRY_HOME/tools/call_log.py`
- Skill doc (deprecated): `$SENTRY_HOME/skills/sentry_call_logging.md`
- Backend endpoints: `backend/app/api/sentry_webhooks.py`
- Intent classifier: `backend/app/services/telegram_intent_classifier.py`
- Conversation manager: `backend/app/services/telegram_conversation_manager.py`
- Flow handlers: `backend/app/services/telegram_flow_handlers.py`
- Message sender: `backend/app/services/telegram_message_sender.py`
- Reporter memory repository: `backend/app/database/repositories/reporter_location_repository.py`
- Reporter memory fallback store: `backend/app/data/reporter_location_memory.json`
- Escalation log: `backend/app/data/call_log_escalations.json`

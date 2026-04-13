---
title: "Block Bookings API"
type: "reference"
status: "active"
version: "1.1.0"
created: "2026-03-31"
updated: "2026-04-13"
tags: ["sentinel", "documentation", "security-hardened"]
related: ["docs/09-security/control-matrix.md", "docs/improvement-loops/2026-04-13-security-gates.md"]
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 12
phase: 184
milestone: v62.4
---

# Block Bookings API

**Base path:** `/api/block-bookings`
**Module:** `block_booking` (standalone add-on, disabled by default)
**Security:** Auth required (BOT_AGENT), rate-limited (100/hour), input-validated (Phase 184 v1.1)

## Authentication & Rate Limiting

All write endpoints require `Authorization: Bearer <jwt>` with `BOT_AGENT` role or higher.
Unauthenticated requests return **401**; requests with insufficient role return **403**.
Rate limit: **100 requests/hour** per caller (AUTH-003 limiter).

## Endpoints

### Ingest Booking Email

```
POST /api/block-bookings/ingest
```

Ingest a raw booking confirmation email or ICS calendar data. Parses the booking, stores it, and triggers overlap detection.

**Request (email ingestion):**
```json
{
  "raw_email": "From: user@example.com\nTo: room@resource...\n...",
  "site_id": "site-002"
}
```

**Request (ICS ingestion — Azure AD Graph API path):**
```json
{
  "ics_data": "BEGIN:VCALENDAR\nVERSION:2.0\n...",
  "site_id": "site-002"
}
```

**Security constraints:**
| Field | Type | Limit |
|-------|------|-------|
| `raw_email` | string | Max 10 MB |
| `ics_data` | string | Max 100 KB, must start with `BEGIN:VCALENDAR` |
| `site_id` | string | Max 50 characters |

**Response (booking ingested):**
```json
{
  "success": true,
  "action": "booking_ingested",
  "booking_id": "uuid",
  "organiser": "user@example.com",
  "room": "Boardroom 1",
  "date": "2026-03-02",
  "alerts_generated": 1,
  "alerts_notified": 1
}
```

**Response (cancellation):**
```json
{
  "success": true,
  "action": "cancellation_processed",
  "removed": true
}
```

**Response (duplicate):**
```json
{
  "success": true,
  "action": "duplicate_skipped"
}
```

---

### List Open Alerts

```
GET /api/block-bookings/alerts?site_id={site_id}
```

Returns all undismissed block booking alerts for a site.

**Response:**
```json
{
  "alerts": [
    {
      "id": "uuid",
      "organiser_email": "shaun@example.com",
      "organiser_name": "Shaun Grose",
      "rooms": ["Boardroom 1", "Boardroom 2"],
      "room_count": 2,
      "overlap_window_start": "2026-03-02T09:00:00",
      "overlap_window_end": "2026-03-02T11:00:00",
      "detected_at": "2026-03-01T15:00:00",
      "notification_sent": true,
      "dismissed": false
    }
  ],
  "count": 1
}
```

---

### Get Alert Detail

```
GET /api/block-bookings/alerts/{alert_id}
```

Returns full detail for a single alert including booking IDs and dismissal info.

---

### Dismiss Alert

```
POST /api/block-bookings/alerts/{alert_id}/dismiss
```

Concierge marks an alert as handled.

**Request:**
```json
{
  "dismissed_by": "concierge@example.com"
}
```

**Response:**
```json
{
  "success": true,
  "alert_id": "uuid",
  "dismissed": true,
  "dismissed_by": "concierge@example.com"
}
```

---

### List Bookings

```
GET /api/block-bookings/bookings?site_id={site_id}&from_date=2026-03-01&to_date=2026-03-14
```

Returns all ingested bookings for a site within a date range (default: today + 14 days).

---

### Get Config

```
GET /api/block-bookings/config?site_id={site_id}
```

Returns detection thresholds and notification targets.

---

### Update Config

```
PUT /api/block-bookings/config?site_id={site_id}
```

**Request (all fields optional):**
```json
{
  "min_rooms_for_alert": 2,
  "full_day_threshold_hours": 6.0,
  "lookahead_days": 14,
  "enabled": true,
  "concierge_email": "concierge@building.co.za",
  "concierge_whatsapp": "+27821234567",
  "concierge_telegram_chat_id": "123456789"
}
```

---

### Manual Scan

```
POST /api/block-bookings/scan?site_id={site_id}
```

Triggers an overlap scan across the next N days (configured by `lookahead_days`).

**Response:**
```json
{
  "success": true,
  "days_scanned": 14,
  "alerts_generated": 2
}
```

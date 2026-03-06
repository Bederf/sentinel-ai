# Block Bookings API

**Base path:** `/api/block-bookings`
**Module:** `block_booking` (standalone add-on, disabled by default)

## Endpoints

### Ingest Booking Email

```
POST /api/block-bookings/ingest
```

Ingest a raw booking confirmation email. Parses the email, stores the booking, and triggers overlap detection.

**Request:**
```json
{
  "raw_email": "From: user@example.com\nTo: room@resource...\n...",
  "site_id": "site-002"
}
```

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

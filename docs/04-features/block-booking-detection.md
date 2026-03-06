# Block Booking Detection

**Module ID:** `block_booking` | **Category:** Space Intelligence | **Tier:** Standalone Add-on | **Default:** Disabled

---

## Problem

One person books multiple meeting rooms for the same time slot — holding capacity they can't physically use. This goes undetected until complaints escalate through FM, often reaching COO level before anyone identifies the root cause.

## Solution

SENTINEL monitors room booking confirmation emails (BCC'd from the booking system) and detects when the same organiser holds two or more rooms simultaneously. When detected, a notification is sent to the concierge immediately.

**SENTINEL does not cancel bookings. SENTINEL does not contact the organiser. SENTINEL does not make decisions.** It surfaces the pattern and tells the concierge. The concierge handles everything from there.

---

## How It Works

```
Booking System                          SENTINEL
     │                                     │
     │  BCC confirmation email             │
     ├────────────────────────────────────▶│
     │                                     │  1. Parse email (organiser, room, time)
     │                                     │  2. Dedup (SHA-256 hash)
     │                                     │  3. Store booking record
     │                                     │  4. Scan for overlaps on that date
     │                                     │  5. If same organiser holds N+ rooms
     │                                     │     simultaneously → generate alert
     │                                     │  6. Notify concierge (Telegram/WhatsApp/email)
     │                                     │
     │                              Concierge
     │                                     │
     │                                     │  Contacts organiser
     │                                     │  Releases unused rooms
     │                                     │  Dismisses alert in SENTINEL
```

## Detection Logic

1. Group all bookings by `organiser_email`
2. For each organiser, group by `booking_date`
3. For each day, find clusters of rooms with overlapping time windows
4. Overlap = `start_time_A < end_time_B AND start_time_B < end_time_A`
5. If `room_count >= min_rooms_for_alert` (default: 2), generate alert
6. De-duplicate: no new alert if an open (undismissed) alert already exists for the same organiser and date

## Notification Message

When an overlap is detected, the concierge receives:

```
Block Booking Detected — Sandton City

Shaun Grose (shaun.grose@example.com) holds 4 rooms simultaneously
on Monday, 02 March 2026:
  - Boardroom 1
  - Boardroom 2
  - Meeting Room 3A
  - Training Room B

Window: 09:00 - 17:00

One person cannot occupy multiple rooms at the same time.
Please contact the organiser to confirm which rooms are genuinely
required and release any that are not needed.

SENTINEL · Sandton City · 2026-03-02 08:45 UTC
```

Delivered via EventBus as `space.block_booking_detected` with `Importance.HIGH` (immediate delivery, not batched into daily digest).

## Email Parsing

Parses standard Outlook resource booking confirmation emails. Extracts:

| Field | Source |
|-------|--------|
| Organiser name/email | `From:` header or `Organizer:` body field |
| Room name | `Location:` body field |
| Room ID | `To:` resource mailbox address |
| Start/End time | `Start:` and `End:` body fields |
| Booking date | Derived from start time |

**Cancellations:** Subject containing "cancel", "declined", "removed", or "withdrawn" triggers removal of the corresponding booking record instead of adding a new one.

**Dedup:** SHA-256 hash of the raw email prevents duplicate ingestion.

## API Endpoints

All under `/api/block-bookings`:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/ingest` | Ingest a booking confirmation email |
| `GET` | `/alerts?site_id=` | List open (undismissed) alerts |
| `GET` | `/alerts/{id}` | Alert detail |
| `POST` | `/alerts/{id}/dismiss` | Concierge dismisses an alert |
| `GET` | `/bookings?site_id=&from_date=&to_date=` | List ingested bookings |
| `GET` | `/config?site_id=` | Get detection config |
| `PUT` | `/config?site_id=` | Update thresholds and contacts |
| `POST` | `/scan?site_id=` | Manually trigger overlap scan |

## Configuration

### Environment Variables

```bash
BLOCK_BOOKING_ENABLED=true               # Master switch
BLOCK_BOOKING_MIN_ROOMS=2                # Alert threshold
BLOCK_BOOKING_MAILBOX_EMAIL=             # IMAP mailbox (BCC'd confirmations)
BLOCK_BOOKING_MAILBOX_PASSWORD=          # IMAP password
BLOCK_BOOKING_MAILBOX_HOST=             # e.g. outlook.office365.com
BLOCK_BOOKING_CONCIERGE_EMAIL=           # Notification target
BLOCK_BOOKING_CONCIERGE_WHATSAPP=        # E.164 format
BLOCK_BOOKING_CONCIERGE_TELEGRAM_ID=     # Telegram chat ID
```

### Per-Site Config (via API)

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

## Data Model

### BookingRecord

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `site_id` | string | Building identifier |
| `organiser_email` | string | From the confirmation email |
| `organiser_name` | string | Display name |
| `room_id` | string | Room identifier (resource mailbox) |
| `room_name` | string | Human-readable room name |
| `booking_date` | date | Date of the booking |
| `start_time` | datetime | Booking start |
| `end_time` | datetime | Booking end |
| `raw_email_hash` | string | SHA-256 for dedup |
| `ingested_at` | datetime | When SENTINEL received it |
| `flagged` | bool | Included in an overlap alert |

### BlockBookingAlert

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `site_id` | string | Building identifier |
| `organiser_email` | string | Who holds the rooms |
| `organiser_name` | string | Display name |
| `overlap_window_start` | datetime | Earliest overlapping start |
| `overlap_window_end` | datetime | Latest overlapping end |
| `rooms` | list[string] | Room names involved |
| `room_count` | int | Number of simultaneous rooms |
| `booking_ids` | list[string] | BookingRecord IDs involved |
| `detected_at` | datetime | When SENTINEL detected it |
| `notification_sent` | bool | Was the concierge notified |
| `dismissed` | bool | Concierge handled it |
| `dismissed_by` | string | Who dismissed |

## Persistence

Follows SENTINEL's 3-tier fallback pattern:

1. **Supabase** — tables `block_booking_records` and `block_booking_alerts`
2. **JSON fallback** — `backend/app/data/block_bookings.json` and `block_booking_alerts.json`

## File Structure

```
backend/app/
  models/
    booking_record.py              # BookingRecord, BlockBookingAlert, BlockBookingConfig
  services/
    block_booking_detector/
      __init__.py
      email_parser.py              # Parse Outlook confirmation → BookingRecord
      booking_store.py             # 3-tier persistence
      overlap_detector.py          # Same-organiser overlap detection
      notifier.py                  # EventBus notification to concierge
  api/
    block_bookings.py              # REST endpoints

backend/tests/
  services/
    test_block_booking_detector.py # 14 tests (parser, detector, notifier)
  api/
    test_block_bookings.py         # API endpoint tests
```

## Integration

- **Email ingestion:** Wire a n8n IMAP workflow to `POST /api/block-bookings/ingest` with the raw email body
- **Notifications:** Uses existing EventBus → SentryNotificationRouter (no new notification infrastructure)
- **Module gating:** Registered as `ModuleType.BLOCK_BOOKING` standalone add-on (default disabled)

## Tests

14 unit tests covering:
- Email parsing (valid confirmation, non-booking, cancellation, dedup)
- Overlap detection (same organiser overlapping, non-overlapping, different organisers, dedup, threshold)
- Notification message formatting
- API endpoints (list alerts, dismiss alert)

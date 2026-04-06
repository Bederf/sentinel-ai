---
title: "Ghost Booking Detection Pipeline"
type: "spec"
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

# Ghost Booking Detection Pipeline

> Detects unoccupied meeting rooms during active bookings and notifies the floor concierge via WhatsApp and email.

**Version:** 1.1 | **Last Updated:** 2026-03-28

---

## Pipeline Overview

```
ESP32 + HLK-LD2410C radar
    │
    ▼ MQTT (every ~5s)
SpaceMqttListener
    │ parse payload, node→room mapping, distance filter
    ▼
SpaceEventService.process_occupancy_event()
    │
    ▼
OccupancyStore (JSON persistence)
    │
    ▼ (every 60s via BackgroundScheduler)
GhostRoomMonitor.scan_due_ghost_bookings()
    │ for each active booking in a due ghost-check window
    ▼
GhostBookingDetector.detect_ghost_booking()
    │ checks: sensor data exists → sensor alive → occupied_minutes == 0
    ▼
GhostRoomNotifier.send_ghost_booking_alert()
    ├── WhatsApp (Twilio) → concierge phone
    └── Email (SMTP) → concierge email
            │
            ▼ concierge swipe-replies yes/no
    WhatsApp webhook → process_concierge_whatsapp_reply()
    └── Updates finding status (confirmed_empty / confirmed_occupied)
```

## Detection Logic

### Booking Source
- Primary: Supabase `block_booking_records` table (ingested from Outlook emails via n8n)
- Fallback: `backend/app/data/block_bookings.json`

### Ghost Check Criteria (all must be true)
1. **Booking is active**: `start_time + grace_period < now < end_time`
2. **No existing finding**: No open `GhostBookingFinding` for this `booking_id`
3. **Sensor data exists**: `room_has_sensor_data(room_code)` returns `True`
4. **Sensor is alive**: Last event within `sensor_silence_threshold_minutes` (default: 30 min)
5. **Room is empty**: `get_occupied_minutes(room, start, now) == 0`

### Grace Period
- Default: **5 minutes** after booking start time
- Configurable via Space Settings API (`ghost_booking_grace_minutes`)

### Hourly Re-Evaluation For Long Bookings
- Ghost detection does not only run once at booking start
- For a long booking, SENTINEL opens a fresh ghost-check window at each hour boundary plus the configured grace period
- Example: `09:00-11:00` with `5` minute grace
  - first ghost window: `09:05`
  - second ghost window: `10:05`
- Within the same hour window, SENTINEL does not send duplicate fresh alerts for the same booking
- A fresh hourly alert resets the reminder cycle for that new hour window

### Booking Cancellation Behavior
- If the booking is cancelled after a ghost alert is sent, ghost processing stops for that booking
- No reminder is sent for a cancelled booking
- No hourly re-alert is sent for a cancelled booking
- If the room is booked again later, that new booking is treated as a new lifecycle with its own grace window

### Sensor Liveness
- Uses `received_at` (server clock), not `timestamp` (device clock)
- ESP32 without NTP sends `1970-01-01` timestamps — `_effective_time()` helper handles this
- Threshold: 30 minutes (configurable via `sensor_silence_threshold_minutes`)

## Notification Channels

### WhatsApp (Twilio)
- Sends ghost alert to concierge's WhatsApp number
- Message includes: room code, organiser name, booking time (SAST), grace period
- Concierge swipe-replies on the message with **yes** (occupied) or **no** (empty)
- Confirmation reply sent back: "Recorded: {room} marked {status}."

### Email (SMTP)
- **Primary**: rooms@sentinel-ai.co.za (ROOMS_SMTP_* settings)
- **Fallback**: workorder@sentinel-ai.co.za (NOTIFICATION_SMTP_* settings)
- n8n webhook attempted first, falls back to direct SMTP
- Includes: full booking details, organiser contact info, action steps

### Reminder
- If concierge hasn't responded after 15 minutes (`concierge_response_window_minutes`), a reminder is sent
- Same channels (WhatsApp + email), prefixed with "REMINDER:"
- Reminder timing is relative to the most recent fresh ghost alert for that booking window

## Radar Sensor (HLK-LD2410C)

### Hardware
- **Sensor**: Hi-Link HLK-LD2410C 24GHz mmWave radar
- **Firmware**: v2.44.25070917
- **Mounting**: Ceiling-mounted in meeting rooms
- **Controller**: ESP32 with WiFi + MQTT

### Configuration
- **Gate resolution**: 0.75m per gate (8 gates, 0-8)
- **Effective range**: 3.0m (gate 4)
- **Unmanned duration**: 15 seconds
- **Presence**: `moving OR stationary` (either triggers occupied)

### Server-Side Distance Filtering
- Valid range: **0.2m – 3.0m** (configurable in settings.py)
- Readings outside range treated as empty (suppresses hallway bleed through walls)
- Settings: `radar_distance_filter_enabled`, `radar_distance_min_m`, `radar_distance_max_m`

### MQTT Topics
- `sentinel/nodes/+/presence` — legacy topic (presence + radar fields)
- `sentinel/node/+/radar` — extended payload topic

### Payload Fields
```json
{
  "node_id": "node_001",
  "zone": "FA2-1Q4-MR25",
  "presence": true,
  "moving": true,
  "stationary": false,
  "moving_distance_cm": 101,
  "stationary_distance_cm": 102,
  "moving_energy": 80,
  "stationary_energy": 45,
  "rssi": -64,
  "uptime_s": 1443,
  "ts": 1443
}
```

## ESP32 Timestamp Fix

ESP32 nodes without NTP synchronization send `1970-01-01T00:xx:xx` timestamps (seconds since boot). The `_effective_time()` helper in `occupancy_store.py` detects this and falls back to `received_at` (server clock):

```python
def _effective_time(event: OccupancyEvent) -> datetime:
    ts = _make_naive(event.timestamp)
    if ts.year < 2020 and event.received_at:
        return _make_naive(event.received_at)
    return ts
```

Applied to: event filtering, occupied minutes calculation, vacancy start detection, sensor liveness checks.

## Concierge Reply Flow

1. Ghost alert sent with "Swipe-reply on THIS message with **yes** or **no**"
2. Concierge swipe-replies on the WhatsApp message
3. Twilio webhook → `POST /api/whatsapp/twilio` → `process_concierge_whatsapp_reply()`
4. **"yes"** → `concierge_confirm_occupied()` → status = `confirmed_occupied`
5. **"no"** → status = `confirmed_empty`
6. Confirmation sent back: "Recorded: {room} marked {status}."
7. If no reply within 15 min → reminder sent (same flow)

## Node-Room Mapping

Server-side override in `backend/app/data/space/node_room_mapping.json`:
```json
{
  "node_001": {
    "room_code": "FA2-1Q4-MR27",
    "site_id": "site-001",
    "room_type": "meeting",
    "note": "Meeting room MR27 node; uses live ghost-booking flow"
  }
}
```
Avoids reflashing ESP32 when physically moving sensors between rooms.

## Key Files

| File | Purpose |
|------|---------|
| `services/space_mqtt_listener.py` | MQTT ingestion, payload parsing, distance filtering |
| `services/space_event_service.py` | Event processing, radar field passthrough |
| `services/occupancy_store.py` | Event storage, `_effective_time()`, occupied minutes |
| `services/ghost_room_monitor.py` | Background scan (60s interval) |
| `services/ghost_booking_detector.py` | Detection logic, concierge confirm/deny |
| `services/ghost_room_notifier.py` | WhatsApp + email dispatch, SAST conversion |
| `api/whatsapp_webhooks.py` | Twilio webhook, concierge reply routing |
| `api/block_bookings.py` | Booking ingestion API, listing |
| `config/settings.py` | Radar filter params, SMTP config |
| `data/space/node_room_mapping.json` | Node→room override |
| `data/block_booking_sites.json` | Per-building concierge config |

## Configuration Reference

### settings.py
```python
# Radar distance filtering
radar_distance_filter_enabled: bool = True
radar_distance_min_m: float = 0.2
radar_distance_max_m: float = 3.0

# MQTT topics
space_mqtt_radar_topic: str = "sentinel/node/+/radar"

# Rooms SMTP (ghost alerts)
rooms_smtp_host: str = ""
rooms_smtp_port: int = 587
rooms_smtp_username: str = ""
rooms_smtp_password: str = ""
rooms_smtp_from_name: str = "SENTINEL Room Alerts"
```

### block_booking_sites.json
```json
{
  "FA2": {
    "site_id": "site-001",
    "building_name": "Fairlands 2",
    "enabled": true,
    "min_rooms_for_alert": 3,
    "concierge_email": "concierge@example.com",
    "concierge_whatsapp": "whatsapp:+27xxxxxxxxx",
    "concierge_name": "Floor Concierge"
  }
}
```

---

**See also:** [Space Intelligence Firmware Architecture](space-intelligence-firmware-architecture.md)

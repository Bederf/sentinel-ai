---
title: "SENTINEL · Space Intelligence"
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

# SENTINEL · Space Intelligence

## Phase 3 — Focus Room Continuous Occupancy Monitoring

**Rev 1.0 · March 2026**
**Fairland 2 (FNB)**

---

## Overview

Phase 3 introduces monitoring of focus rooms and single-occupancy work pods where no booking system exists.

The objective is to detect extended continuous use of a focus room beyond a recommended duration (typically 2 hours) and provide facilities teams with usage insights.

Unlike meeting rooms, focus rooms do not rely on calendar bookings. Instead, SENTINEL measures **continuous occupancy sessions** derived from mmWave radar presence signals.

---

## System Behaviour

Focus rooms operate using **session-based occupancy detection**.

A session begins when the radar sensor detects presence and ends when the room becomes vacant.

```
occupied = true  -> session start
occupied = false -> session end
```

Session duration is calculated on the backend.

---

## Occupancy Detection Hardware

Hardware remains aligned with the current ESP32 meeting-room occupancy node.

| Component | Model |
|-----------|-------|
| Radar sensor | HLK-LD2410C 24GHz mmWave presence radar |
| Microcontroller | NodeMCU-32S (ESP32) |
| Detection mode | ESP32 publishes presence events over MQTT |
| Delay | 180 second unmanned delay |

The LD2410C radar detects moving and stationary humans, including micro-movements such as breathing. This prevents false vacancy events when users sit still for long periods.

---

## Sensor Configuration

Focus rooms typically measure 2–3 metres in depth.

**Recommended radar configuration:**

**Detection range:** 3.0 metres

### Gate Sensitivity Profile

| Gate | Sensitivity |
|------|-------------|
| Gate 1 | 50 |
| Gate 2 | 80 |
| Gate 3 | 100 |
| Gate 4 | 100 |
| Gate 5 | 80 |
| Gate 6 | 0 |
| Gate 7 | 0 |
| Gate 8 | 0 |

**Unmanned delay:** 180 seconds

This configuration ensures reliable detection of seated occupants while preventing interference from corridor movement.

> **Note:** Focus rooms do not need door bleed suppression (Gates 1–2 = 0) like meeting rooms. The sensor is centred in a small room, so all near gates are active. Gates 6–8 are disabled because the room is too small for those distances to be relevant.

---

## Focus Room Session Logic

The backend calculates continuous occupancy sessions.

### Example Timeline

```
09:00  user enters room
09:01  sensor reports occupied=true
11:10  user still present
11:30  user leaves
11:33  sensor reports occupied=false (after 180s delay)

Session duration: 11:33 - 09:01 = 2h 32m
```

---

## Extended Occupancy Detection

Focus rooms typically have a recommended maximum occupancy duration of **2 hours**.

SENTINEL flags sessions exceeding this threshold and automatically notifies the concierge.

**Rule:**

```
if session_duration > 2 hours:
    mark session = extended_use
    red_light_on = true
    notify_concierge()
```

### Automatic Notification

The overstay alert fires on every MQTT event — decoupled from relay state transitions. This ensures reliable notification even after backend restarts.

**Notification channels:**
- **Telegram** — sent to concierge chat with inline buttons:
  - "Still occupied" → extends session by **+10 minutes** (updates `overstay_grace_minutes`)
  - "Room empty now" → closes session immediately, turns relay/LED off
- **WhatsApp** — sent via Twilio directly to configured number

### Concierge Flow

```
1. Session exceeds 2h → Telegram alert with buttons
2. Concierge goes to room, informs occupant
3a. Occupant asks for more time → tap "Still occupied" → +10min grace
3b. Occupant leaves → concierge opens door → tap "Room empty" → session closes
4. Buttons update to show confirmation
```

### Door State Handling

The LD2410C firmware v3.2.0 (ESP32) supports a magnetic reed switch on GPIO18:

- `door_closed: true` → gap timer **frozen** (belongings inside, session stays open)
- `door_closed: false` → normal gap tolerance applies
- `door_closed: null` → no sensor installed (D1 Mini / older firmware)

---

## Noise Filtering

Very short visits should be ignored to prevent false sessions.

**Recommended rule:**

```
if session_duration < 3 minutes:
    discard session
```

**Examples of discarded events:**
- Door opened briefly
- Cleaning inspection
- Someone checking availability

---

## Metrics Produced

Focus room monitoring produces the following analytics.

| Metric | Example |
|--------|---------|
| Average focus session duration | 42 minutes |
| Longest session | 3h 12m |
| Rooms frequently exceeding 2h | FR-02 |
| Peak focus room usage | Tuesday 10:00 |

These insights help facilities teams evaluate workspace utilisation and policy compliance.

---

## Deployment Considerations

Sensor placement differs slightly from meeting rooms.

**Recommended placement:**
- Ceiling centre of room
- Height 2.2–2.8 m
- Radar facing downward

### Typical Focus Room Layout

```
+-----------+
|           |
|     O     |    O = SENTINEL radar node
|           |
|   Desk    |
|           |
+-----------+
```

A single sensor covers the entire room. No door bleed suppression needed — the room is small enough that the sensor is always well inside the space.

---

## Future Extensions

Phase 3 creates the foundation for additional smart workspace features.

**Potential extensions:**
- Real-time focus room availability display
- Occupancy heat maps across floors
- Adaptive lighting and HVAC (tie into Phase 1 occupancy control loop)
- Usage-based cleaning schedules
- Quiet-hours enforcement (block notifications during focus sessions)

---

## Implementation Reference

### Data Model

`FocusRoomSession` in `backend/app/models/space_occupancy.py`:

| Field | Type | Description |
|-------|------|-------------|
| session_id | uuid | Unique session identifier |
| site_id | text | Multi-building support |
| room_code | text | Room identifier (e.g. FR-03) |
| room_type | text | `focus` or `meeting` |
| sensor_id | text | Hardware traceability |
| source | text | `mmwave_ld2410c` |
| start_time | timestamp | Session start (occupied=true) |
| end_time | timestamp | Session end (occupied=false), null if active |
| duration_seconds | integer | Computed on close |
| extended_use | boolean | True if duration > 7200s (2 hours) |
| created_at | timestamp | Record creation time |
| door_closed | boolean | Reed switch state: true=closed (gap frozen), null=no sensor |
| overstay_grace_minutes | integer | Concierge-granted additional minutes (default 0) |

### Service Layer

`backend/app/services/focus_room_session_service.py`:
- `process_focus_room_event()` — Event-to-session conversion
- `get_focus_room_analytics()` — Aggregated metrics (avg duration, peak hour, extended count)

`backend/app/services/occupancy_store.py` (session persistence):
- `save_session()`, `get_active_session()`, `close_session()`, `discard_session()`
- `get_sessions_for_room()`, `get_sessions_for_site()`
- `set_door_closed()` — Update door state per session
- `extend_overstay_grace()` — Add concierge-granted minutes (called via Telegram "Still occupied")

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/space/occupancy-event` | Ingest event — routes to session service when `room_type=focus` |
| GET | `/api/space/focus-sessions` | List sessions (filter by room, extended_only) |
| GET | `/api/space/focus-analytics` | Aggregated usage metrics |

### Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `focus_min_session_seconds` | 180 | Discard sessions shorter than 3 min |
| `focus_extended_use_seconds` | 7200 | Flag sessions longer than 2 hours |

### Tests

`backend/tests/services/test_focus_room_sessions.py` — 20 tests across 5 classes:
- `TestFocusRoomSessionModel` (5): lifecycle, duration computation, extended flag
- `TestFocusRoomSessionService` (7): start/close/noise/extended/duplicates/multiple
- `TestSessionStore` (4): save/retrieve/close/discard/site queries
- `TestFocusRoomAnalytics` (2): empty + populated analytics
- `TestFocusRoomAPI` (2): event routing + vacancy calculation

---

**SENTINEL · Space Intelligence · Phase 3 Focus Rooms · Rev 1.0 · March 2026**
**Fairland 2 (FNB) · Confidential**

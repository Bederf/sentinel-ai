---
title: "SENTINEL · Space Intelligence"
type: "architecture"
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

## Occupancy Data Model

**Rev 1.0 · March 2026**

---

## Entity Relationship Diagram

```
                           +----------------------+
                           |      sites           |
                           |----------------------|
                           | site_id (PK)         |
                           | site_code            |
                           | site_name            |
                           +----------+-----------+
                                      |
                                      |
                                      v
                           +----------------------+
                           |       rooms          |
                           |----------------------|
                           | room_id (PK)         |
                           | site_id (FK)         |
                           | room_code            |
                           | room_name            |
                           | room_type            |  meeting / focus
                           | floor                |
                           | capacity             |
                           +----------+-----------+
                                      |
                    +-----------------+------------------+
                    |                                    |
                    v                                    v
          +----------------------+             +----------------------+
          |       sensors        |             |      bookings        |
          |----------------------|             |----------------------|
          | sensor_id (PK)       |             | booking_id (PK)      |
          | room_id (FK)         |             | room_id (FK)         |
          | sensor_code          |             | source_system        |
          | sensor_type          |             | booked_by            |
          | model                |             | start_time           |
          | firmware_version     |             | end_time             |
          | install_location     |             | attendee_count       |
          | is_active            |             | status               |
          +----------+-----------+             +----------+-----------+
                     |                                     |
                     |                                     |
                     v                                     v
          +----------------------+             +----------------------+
          |  occupancy_events    |             | meeting_audit        |
          |----------------------|             |----------------------|
          | event_id (PK)        |             | audit_id (PK)        |
          | sensor_id (FK)       |             | booking_id (FK)      |
          | room_id (FK)         |             | room_id (FK)         |
          | event_time           |             | occupied_within_20m  |
          | occupied             |             | ghost_booking        |
          | source               |             | actual_first_seen    |
          | raw_payload          |             | actual_last_seen     |
          +----------+-----------+             | notes                |
                     |                         +----------------------+
                     |
          +----------+-----------+
          |                      |
          v                      v
+----------------------+   +----------------------+
|  meeting_sessions    |   | focus_room_sessions  |
|----------------------|   |----------------------|
| session_id (PK)      |   | session_id (PK)      |
| room_id (FK)         |   | room_id (FK)         |
| sensor_id (FK)       |   | sensor_id (FK)       |
| start_time           |   | start_time           |
| end_time             |   | end_time             |
| duration_seconds     |   | duration_seconds     |
| occupied_peak        |   | extended_use         |
| derived_from_events  |   | over_limit_minutes   |
+----------+-----------+   +----------+-----------+
           |                              |
           +---------------+--------------+
                           |
                           v
                +--------------------------+
                |    analytics_views       |
                |--------------------------|
                | room_utilization         |
                | ghost_booking_rate       |
                | avg_meeting_duration     |
                | avg_focus_duration       |
                | focus_overstay_rate      |
                | room_idle_time           |
                +--------------------------+
```

---

## How It Works

### Phase 1: Meeting Rooms

1. **bookings** gives the expected room usage (from calendar/email intake)
2. **occupancy_events** gives the actual radar signal (LD2410C OUT pin)
3. **meeting_audit** compares the two
4. Ghost booking = booking exists AND no `occupied=true` event within 20 minutes of `start_time`

### Phase 3: Focus Rooms

1. No booking table is needed for room use logic
2. **occupancy_events** are converted into **focus_room_sessions**
3. Any session over 2 hours gets `extended_use = true`

---

## Minimum Tables to Build First

For the lean demo and 5-room pilot, build these first:

| Table | Purpose |
|-------|---------|
| rooms | Room registry with type (meeting/focus) |
| sensors | Hardware inventory and firmware tracking |
| occupancy_events | Raw truth — every presence/absence change |
| bookings | Calendar bookings (meeting rooms only) |
| meeting_audit | Ghost booking + right-sizing findings |
| focus_room_sessions | Derived continuous sessions (focus rooms) |

This is enough for:
- Ghost booking detection
- 5-room pilot
- Focus room overstay in Phase 3
- Dashboard metrics

---

## Key Rules

### Meeting Room Ghost Booking

```
if booking exists
and no occupied=true event within 20 minutes of start_time
then ghost_booking = true
```

### Focus Room Overstay

```
if focus_room_session.duration_seconds > 7200
then extended_use = true
```

### Noise Filtering

```
if focus_room_session.duration_seconds < 180
then discard session (door check, cleaning, availability scan)
```

---

## Storage Strategy

Store **both** layers:

| Layer | Table | Purpose |
|-------|-------|---------|
| Raw truth | occupancy_events | Every sensor event, immutable |
| Business records | meeting_sessions, focus_room_sessions | Derived, queryable, analytics-ready |

This gives you:
- **Auditability** — raw events prove what actually happened
- **Easy reporting** — sessions are pre-computed, no reprocessing needed
- **Rule reprocessing** — change a threshold, re-derive sessions from raw events

---

## Event Flow Diagram

```
+-------------+     +-------------+     +----------+     +------------------+
| HLK-LD2410C |     | Wemos D1    |     |  WiFi    |     | SENTINEL API     |
| mmWave      +---->+ Mini        +---->+ 2.4GHz   +---->+ /api/space/      |
| OUT pin     |     | GPIO D4     |     |          |     | occupancy-event  |
+-------------+     +-------------+     +----------+     +--------+---------+
                                                                  |
                                                                  v
                                                         +--------+---------+
                                                         | occupancy_events |
                                                         | (raw storage)    |
                                                         +--------+---------+
                                                                  |
                                              +-------------------+-------------------+
                                              |                                       |
                                              v                                       v
                                    +---------+----------+                  +----------+---------+
                                    | Meeting Room Path  |                  | Focus Room Path    |
                                    |--------------------|                  |--------------------|
                                    | Compare vs booking |                  | Build sessions     |
                                    | Ghost detection    |                  | Overstay detection |
                                    | Right-sizing       |                  | Noise filtering    |
                                    | Concierge dispatch |                  | Analytics          |
                                    +---------+----------+                  +----------+---------+
                                              |                                       |
                                              v                                       v
                                    +---------+----------+                  +----------+---------+
                                    | meeting_audit      |                  | focus_room_sessions|
                                    | ghost_findings     |                  | (derived records)  |
                                    | rs_findings        |                  |                    |
                                    +--------------------+                  +--------------------+
                                              |                                       |
                                              +-------------------+-------------------+
                                                                  |
                                                                  v
                                                         +--------+---------+
                                                         |    Dashboard     |
                                                         |------------------|
                                                         | KPIs             |
                                                         | Heatmap          |
                                                         | Offender table   |
                                                         | AI recs          |
                                                         | Focus analytics  |
                                                         +------------------+
```

---

## Current Implementation Mapping

| Data Model Entity | Backend Implementation |
|-------------------|----------------------|
| sites | `app/data/buildings/` site config JSON |
| rooms | Room codes in booking records + occupancy events |
| sensors | `sensor_id` field in `OccupancyEvent` |
| bookings | `BookingRecord` in `models/booking_record.py` + `booking_store.py` |
| occupancy_events | `OccupancyEvent` in `models/space_occupancy.py` + `occupancy_store.py` |
| meeting_audit | `GhostBookingFinding` + `RightSizingFinding` in `models/space_occupancy.py` |
| focus_room_sessions | `FocusRoomSession` in `models/space_occupancy.py` + `occupancy_store.py` |
| analytics_views | `get_focus_room_analytics()` in `focus_room_session_service.py` |

### JSON Storage (current — demo/pilot)

```
backend/app/data/space/
  occupancy_events.json       # Raw events (10K cap)
  ghost_findings.json         # Ghost booking findings
  rightsizing_findings.json   # Right-sizing findings
  focus_room_sessions.json    # Focus room sessions (10K cap)
```

### Supabase Migration (production)

When moving to production, these JSON files map directly to Supabase tables. The `occupancy_store.py` functions already follow the repository pattern — swap JSON I/O for Supabase queries with no service layer changes.

---

**SENTINEL · Space Intelligence · Occupancy Data Model · Rev 1.0 · March 2026**
**Confidential**

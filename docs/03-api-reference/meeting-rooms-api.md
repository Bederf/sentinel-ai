---
title: "Meeting Rooms API"
type: "reference"
status: "active"
version: "1.0.0"
created: "2026-06-24"
updated: "2026-06-24"
tags: ["sentinel", "meeting-rooms", "space-optimization", "api"]
related: ["docs/04-features/block-booking-email-integration", "docs/03-api-reference/block-bookings-api"]
domain: "bms"
audience: ["developers", "devops"]
complexity: "beginner"
estimated_read_time: 5
---

# Meeting Rooms API

**Base path:** `/api/space/rooms`
**Module:** `space_optimization` (standalone add-on)
**Security:** Auth required (site access via `require_any_site`)

## Overview

CRUD endpoints for the `meeting_rooms` table. Rooms store metadata (name, floor, capacity, type, AV equipment) and a `keywords` array used by the `RoomsEmailIntakeService` for per-room email routing.

When `rooms@sentinel-ai.co.za` receives an email whose subject matches a room's keywords, the email is routed as a concierge signal for that specific room.

## Endpoints

### List Rooms

```
GET /api/space/rooms?site_id=site-002
```

Returns all rooms for a site, ordered by floor then name.

**Response:**
```json
{
  "rooms": [
    {
      "id": "a6c402a0-3391-4e54-8ab6-b9ea03779d14",
      "site_id": "site-002",
      "name": "Prayer Room",
      "capacity": 6,
      "floor": "L1",
      "room_type": "meeting",
      "has_av": false,
      "building_code": "FA2",
      "keywords": ["prayer", "meditation", "quiet room"],
      "created_at": "2026-05-14T05:12:09.099621+00"
    }
  ]
}
```

### Create Room

```
POST /api/space/rooms
```

**Request body:**
```json
{
  "name": "Prayer Room",
  "floor": "L1",
  "capacity": 6,
  "room_type": "meeting",
  "has_av": false,
  "building_code": "FA2",
  "keywords": ["prayer", "meditation", "quiet room", "silent"]
}
```

All fields except `name` have defaults. `room_type` defaults to `"meeting"`, `keywords` defaults to `[]`.

**Response:** `201 Created`
```json
{
  "room": { "...": "created room object" }
}
```

### Get Room

```
GET /api/space/rooms/{id}
```

**Response:**
```json
{
  "room": { "...": "room object" }
}
```

### Update Room

```
PUT /api/space/rooms/{id}
```

Accepts partial update — only included fields are changed.

**Request body:** (all fields optional)
```json
{
  "name": "Updated Room Name",
  "keywords": ["new", "keywords"]
}
```

### Delete Room

```
DELETE /api/space/rooms/{id}
```

**Response:**
```json
{
  "success": true,
  "room_id": "a6c402a0-3391-4e54-8ab6-b9ea03779d14"
}
```

## Keywords & Email Routing

Each room can have a list of custom keywords. When the `RoomsEmailIntakeService` polls `rooms@sentinel-ai.co.za`:

1. **Booking keywords** (hardcoded: "new resource use notification", "cancelled reservation", "accepted", "invitation", "meeting") → block booking pipeline
2. **Per-room keywords** (loaded from `meeting_rooms.keywords`) → if subject matches any room's keywords, the email is routed as a concierge signal to that specific room
3. **Unmatched** → general room issue signal (fallback)

### Example

If room "Prayer Room" has keywords `["prayer", "meditation", "quiet room", "silent"]`, an email with subject "Prayer room booking issue" will be routed as a prayer-room-specific signal to the concierge dashboard.

## Database Schema

```sql
CREATE TABLE meeting_rooms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id TEXT NOT NULL,
    name TEXT NOT NULL,
    capacity INTEGER NOT NULL,
    floor TEXT NOT NULL,
    room_type TEXT,
    has_av BOOLEAN,
    building_code TEXT,
    keywords TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);
```

## Frontend

Rooms can be managed from the **Space Optimization → Rooms** tab in the SENTINEL dashboard.

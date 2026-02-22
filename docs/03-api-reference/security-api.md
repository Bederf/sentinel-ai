---
title: "Security API Reference"
type: "reference"
status: "approved"
version: "2.0.0"
created: "2026-02-13"
updated: "2026-02-22"
author: "Sentinel Development Team"
tags: ["api", "security", "access-control", "occupancy", "cameras"]
domain: "security"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 10
---

# Security API Reference

**Module:** SENTINEL Security (Phases 27, 58, 69)
**Base Path:** `/api/security`
**Authentication:** AUTHENTICATED (read), OPERATOR (write)
**Rate Limit:** 30 requests/minute per endpoint (10/min for write endpoints)

## Overview

REST API for access control event monitoring, visitor management, security alerting, zone-level occupancy tracking, CCTV camera queries, and occupancy trend analysis. Provides cross-module occupancy data consumed by HVAC and Lighting modules.

## Quick Start

```bash
# Get building security status
curl http://localhost:9095/api/security/overview?site=site-002

# List access events
curl http://localhost:9095/api/security/events?site=site-002&limit=20

# Get current occupancy (for HVAC/Lighting integration)
curl http://localhost:9095/api/security/occupancy?site=site-002

# Get zone-level occupancy (Phase 69)
curl http://localhost:9095/api/security/occupancy/zone/zone_001

# Get zone cameras with stream URLs (Phase 69)
curl http://localhost:9095/api/security/cameras/zone_001
```

## Endpoint Summary

### Core endpoints (Phase 27)

| Method | Endpoint | Purpose | Auth Level |
|--------|----------|---------|-----------|
| GET | `/overview` | Building security summary | AUTHENTICATED |
| GET | `/status` | Security compliance and system health | AUTHENTICATED |
| GET | `/events` | List access events | AUTHENTICATED |
| GET | `/events/{id}` | Single event details | AUTHENTICATED |
| POST | `/events` | Record new event | OPERATOR |
| GET | `/events/anomalies` | Detect anomalous access patterns | AUTHENTICATED |
| GET | `/access-points` | List readers/locks/sensors | AUTHENTICATED |
| GET | `/access-points/{id}` | Point details | AUTHENTICATED |
| GET | `/visitors` | List visitors | AUTHENTICATED |
| POST | `/visitors` | Register visitor | OPERATOR |
| POST | `/visitors/{id}/checkin` | Check in visitor | OPERATOR |
| POST | `/visitors/{id}/checkout` | Check out visitor | OPERATOR |
| PUT | `/visitors/{id}/revoke` | Revoke access | OPERATOR |
| GET | `/alerts` | List alerts | AUTHENTICATED |
| POST | `/alerts` | Create alert | OPERATOR |
| PUT | `/alerts/{id}/acknowledge` | Acknowledge alert | OPERATOR |
| GET | `/occupancy` | Building occupancy | AUTHENTICATED |
| GET | `/occupancy/recommendations` | Occupancy-based HVAC/Lighting recommendations | AUTHENTICATED |

### Zone-level endpoints (Phase 69)

| Method | Endpoint | Purpose | Auth Level |
|--------|----------|---------|-----------|
| GET | `/occupancy/zone/{zone_id}` | Per-zone occupancy with capacity | AUTHENTICATED |
| GET | `/occupancy/floor/{floor}` | Aggregate floor occupancy | AUTHENTICATED |
| POST | `/access-event` | Receive badge event, trigger automations | OPERATOR |
| GET | `/access-log/{zone_id}` | Recent events by zone and time | AUTHENTICATED |
| GET | `/cameras/{zone_id}` | Zone cameras with stream URLs | AUTHENTICATED |
| GET | `/occupancy-trend/{zone_id}` | Hourly trend data for graphing | AUTHENTICATED |

## Core Endpoints

### GET /api/security/overview

Get building security status summary.

```bash
curl http://localhost:9095/api/security/overview?site=site-002
```

**Query Parameters:**
- `site` (string, required): Site identifier

**Response:** 200 OK
```json
{
  "total_access_events_today": 15,
  "active_visitors": 2,
  "open_alerts": 1,
  "after_hours_access_count": 3,
  "system_status": "online",
  "last_updated": "2026-02-13T16:45:00Z"
}
```

### GET /api/security/events

List access events with optional filtering.

```bash
curl "http://localhost:9095/api/security/events?site=site-002&location=Main+Entrance&limit=50"
```

**Query Parameters:**
- `site` (string, required)
- `location` (string, optional)
- `after_hours` (boolean, optional, default false)
- `limit` (integer, optional, default 100, max 1000)

**Response:** 200 OK
```json
{
  "site": "site-002",
  "event_count": 15,
  "events": [
    {
      "event_id": "EVT-001",
      "timestamp": "2026-02-13T06:30:00Z",
      "access_point": "Main Entrance",
      "person_name": "John Smith",
      "status": "granted",
      "access_type": "badge"
    }
  ]
}
```

### GET /api/security/occupancy

Get current building occupancy for HVAC/Lighting integration.

```bash
curl http://localhost:9095/api/security/occupancy?site=site-002
```

**Query Parameters:**
- `site` (string, required)

**Response:** 200 OK
```json
{
  "total_occupancy": 23,
  "by_floor": {
    "L0": 12,
    "L1": 8,
    "L2": 3
  },
  "by_zone": {
    "Zone-001": 5,
    "Zone-002": 4,
    "Zone-003": 3
  },
  "calculation": "recent_badge_access_plus_visitor_checkins",
  "last_updated": "2026-02-13T16:45:00Z"
}
```

### GET /api/security/alerts

List security alerts with filtering.

```bash
curl "http://localhost:9095/api/security/alerts?site=site-002&severity=critical"
```

**Query Parameters:**
- `site` (string, required)
- `severity` (string, optional): critical | warning | info
- `limit` (integer, optional, default 50)

**Response:** 200 OK
```json
{
  "site": "site-002",
  "alert_count": 2,
  "alerts": [
    {
      "alert_id": "ALR-001",
      "type": "after_hours",
      "timestamp": "2026-02-13T22:30:00Z",
      "location": "Server Room",
      "severity": "warning",
      "description": "Unauthorized after-hours access",
      "status": "open"
    }
  ]
}
```

## Zone-Level Endpoints (Phase 69)

### GET /api/security/occupancy/zone/{zone_id}

Get current occupancy for a specific zone, including max capacity and percent full.

```bash
curl http://localhost:9095/api/security/occupancy/zone/zone_001
```

**Path Parameters:**
- `zone_id` (string, required): Zone identifier (e.g., `zone_001`)

**Response:** 200 OK
```json
{
  "zone_id": "zone_001",
  "zone_name": "Level 1 Open Plan",
  "occupancy_count": 22,
  "badge_entries": 38,
  "badge_exits": 16,
  "max_capacity": 40,
  "percent_full": 55.0,
  "last_updated": "2026-02-22T10:30:00Z",
  "source": "badge"
}
```

### GET /api/security/occupancy/floor/{floor}

Get aggregate occupancy for all zones on a floor.

```bash
curl http://localhost:9095/api/security/occupancy/floor/L1
```

**Path Parameters:**
- `floor` (string, required): Floor identifier (e.g., `L0`, `L1`, `L2`)

**Response:** 200 OK
```json
{
  "floor": "L1",
  "total_occupancy": 22,
  "zone_count": 3,
  "zones": [
    {
      "zone_id": "zone_001",
      "zone_name": "Level 1 Open Plan",
      "occupancy_count": 22,
      "badge_entries": 38,
      "badge_exits": 16,
      "last_updated": "2026-02-22T10:30:00Z",
      "source": "badge"
    }
  ],
  "last_updated": "2026-02-22T10:30:00Z"
}
```

### POST /api/security/access-event

Receive a badge access event. Updates zone occupancy and triggers cross-module HVAC/Lighting recommendations.

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "equipment_id": "S002-ACC-101",
    "person_id": "EMP-042",
    "direction": "entry",
    "zone_id": "zone_001"
  }' \
  http://localhost:9095/api/security/access-event
```

**Request Body:**
```json
{
  "equipment_id": "S002-ACC-101",
  "person_id": "EMP-042",
  "direction": "entry",
  "timestamp": "2026-02-22T10:30:00Z",
  "zone_id": "zone_001"
}
```

- `direction`: `entry` or `exit`
- `timestamp`: Optional, defaults to current time

**Response:** 200 OK
```json
{
  "status": "processed",
  "zone_id": "zone_001",
  "direction": "entry",
  "person_id": "EMP-042",
  "current_occupancy": 23,
  "hvac_recommendation": {
    "zone_id": "zone_001",
    "zone_name": "Level 1 Open Plan",
    "occupancy": 23,
    "recommendation": null
  },
  "lighting_recommendation": null,
  "timestamp": "2026-02-22T10:30:00Z"
}
```

When occupancy drops to zero, `hvac_recommendation` and `lighting_recommendation` contain setpoint/dimming suggestions for energy savings.

### GET /api/security/access-log/{zone_id}

Get recent badge events for a specific zone within a time range.

```bash
curl "http://localhost:9095/api/security/access-log/zone_001?limit=20&last_hours=8"
```

**Path Parameters:**
- `zone_id` (string, required): Zone identifier

**Query Parameters:**
- `limit` (integer, optional, default 50, max 500)
- `last_hours` (integer, optional, default 24, max 168)

**Response:** 200 OK
```json
{
  "zone_id": "zone_001",
  "event_count": 12,
  "events": [
    {
      "timestamp": "2026-02-22T10:30:00Z",
      "person_id": "EMP-042",
      "direction": "entry",
      "granted": true
    }
  ],
  "last_hours": 8
}
```

### GET /api/security/cameras/{zone_id}

Get cameras in a specific zone with stream URLs and model information. Falls back to demo camera data when Supabase is unavailable.

```bash
curl http://localhost:9095/api/security/cameras/zone_001
```

**Path Parameters:**
- `zone_id` (string, required): Zone identifier

**Response:** 200 OK
```json
{
  "zone_id": "zone_001",
  "camera_count": 2,
  "cameras": [
    {
      "camera_id": "CAM-zone_001-NW",
      "zone_id": "zone_001",
      "name": "Camera NW - zone_001",
      "floor": "L1",
      "status": "online",
      "camera_type": "dome",
      "resolution": "1080p",
      "has_analytics": true,
      "motion_detected": false,
      "stream_url": "rtsp://cctv.local/zone_001/nw",
      "camera_model": "Hikvision DS-2CD2143G2-IU"
    }
  ]
}
```

### GET /api/security/occupancy-trend/{zone_id}

Get hourly occupancy trend data for a zone. Returns hourly entry/exit/net occupancy readings for chart rendering.

```bash
curl "http://localhost:9095/api/security/occupancy-trend/zone_001?hours=24"
```

**Path Parameters:**
- `zone_id` (string, required): Zone identifier

**Query Parameters:**
- `hours` (integer, optional, default 24, max 168)

**Response:** 200 OK
```json
{
  "zone_id": "zone_001",
  "hours": 24,
  "data_points": 24,
  "trend": [
    {
      "hour": "2026-02-21T10:00:00+00:00",
      "entries": 5,
      "exits": 2,
      "net_occupancy": 3,
      "zone_id": "zone_001"
    },
    {
      "hour": "2026-02-21T11:00:00+00:00",
      "entries": 3,
      "exits": 1,
      "net_occupancy": 2,
      "zone_id": "zone_001"
    }
  ]
}
```

## Error Responses

All endpoints return standard error format:

```json
{
  "detail": "Event EVT-999 not found"
}
```

**Common Status Codes:**

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request (invalid parameters) |
| 401 | Unauthorized (missing/invalid JWT) |
| 404 | Not Found |
| 500 | Server Error |

## Authentication

Include JWT token in Authorization header:

```bash
curl -H "Authorization: Bearer $JWT_TOKEN" \
  http://localhost:9095/api/security/events?site=site-002
```

In demo mode (`DEMO_MODE=true`), authentication is bypassed for localhost requests.

## Rate Limiting

All security endpoints are rate-limited to 30 requests/minute per user. Write endpoints (`POST /access-event`, `POST /alerts`, `POST /visitors`) are limited to 10 requests/minute.

## Related Documentation

- [Security Module Feature Spec](../04-features/58-security-module.md)
- [Security Module Integration Guide](../04-features/27-security-module-integration.md)
- [Module Registry](../13-modules/module-registry.md)
- [Security Database Schema](../07-database/69-security-module-schema.md)

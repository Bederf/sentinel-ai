# Security API Reference

**Module:** SENTINEL Security (Phase 27)
**Base Path:** `/api/security`
**Authentication:** AUTHENTICATED (read), OPERATOR (write)

## Overview

Complete REST API specification for access control event monitoring, visitor management, and security alerting. The Security module provides 20+ endpoints for real-time security monitoring across buildings.

## Quick Start

```bash
# Get building security status
curl http://localhost:9095/api/security/overview?site=site-002

# List access events
curl http://localhost:9095/api/security/events?site=site-002&limit=20

# Get current occupancy (for HVAC/Lighting integration)
curl http://localhost:9095/api/security/occupancy?site=site-002
```

## Endpoint Summary

| Method | Endpoint | Purpose | Auth Level |
|--------|----------|---------|-----------|
| GET | `/api/security/overview` | Building security summary | AUTHENTICATED |
| GET | `/api/security/events` | List access events | AUTHENTICATED |
| GET | `/api/security/events/{id}` | Single event details | AUTHENTICATED |
| POST | `/api/security/events` | Record new event | OPERATOR |
| GET | `/api/security/access-points` | List readers/locks/sensors | AUTHENTICATED |
| GET | `/api/security/access-points/{id}` | Point details | AUTHENTICATED |
| GET | `/api/security/visitors` | List visitors | AUTHENTICATED |
| POST | `/api/security/visitors` | Register visitor | OPERATOR |
| POST | `/api/security/visitors/{id}/checkin` | Check in visitor | OPERATOR |
| POST | `/api/security/visitors/{id}/checkout` | Check out visitor | OPERATOR |
| PUT | `/api/security/visitors/{id}/revoke` | Revoke access | OPERATOR |
| GET | `/api/security/alerts` | List alerts | AUTHENTICATED |
| POST | `/api/security/alerts` | Create alert | OPERATOR |
| PUT | `/api/security/alerts/{id}/acknowledge` | Acknowledge alert | OPERATOR |
| GET | `/api/security/occupancy` | Building occupancy (Phase 28 integration) | AUTHENTICATED |

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
- `after_hours` (boolean, optional)
- `limit` (integer, optional, default 50, max 1000)
- `offset` (integer, optional, default 0)

**Response:** 200 OK
```json
{
  "events": [
    {
      "event_id": "EVT-001",
      "timestamp": "2026-02-13T06:30:00Z",
      "access_point": "Main Entrance",
      "person_name": "John Smith",
      "status": "granted",
      "access_type": "badge"
    }
  ],
  "total": 50,
  "limit": 50
}
```

### GET /api/security/access-points

List all access points (readers, locks, sensors).

```bash
curl http://localhost:9095/api/security/access-points?site=site-002
```

**Query Parameters:**
- `site` (string, required)

**Response:** 200 OK
```json
{
  "access_points": [
    {
      "point_id": "AP-001",
      "location": "Main Entrance",
      "zone": "L0",
      "device_type": "reader",
      "status": "active",
      "recent_activity": {
        "last_access": "2026-02-13T16:45:00Z",
        "events_today": 12
      }
    }
  ],
  "total": 5
}
```

### GET /api/security/visitors

List active and recent visitors.

```bash
curl http://localhost:9095/api/security/visitors?site=site-002
```

**Query Parameters:**
- `site` (string, required)
- `status` (string, optional): pending | checked_in | checked_out | revoked

**Response:** 200 OK
```json
{
  "visitors": [
    {
      "visitor_id": "VIS-001",
      "name": "Alice Thompson",
      "company": "TechCorp",
      "status": "checked_in",
      "check_in_time": "2026-02-13T09:00:00Z",
      "host_contact": "john.smith@company.com"
    }
  ],
  "total": 2
}
```

### POST /api/security/visitors

Register new visitor and grant access.

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "site": "site-002",
    "name": "Alice Thompson",
    "company": "TechCorp",
    "host_contact": "john.smith@company.com",
    "access_points": ["Main Entrance", "Conference Room"],
    "visit_date": "2026-02-13"
  }' \
  http://localhost:9095/api/security/visitors
```

**Request Body:**
```json
{
  "site": "site-002",
  "name": "Alice Thompson",
  "company": "TechCorp",
  "host_contact": "john.smith@company.com",
  "access_points": ["Main Entrance"],
  "visit_date": "2026-02-13",
  "expected_duration": "2 hours"
}
```

**Response:** 201 Created
```json
{
  "visitor_id": "VIS-001",
  "status": "pending",
  "message": "Visitor registered"
}
```

### POST /api/security/visitors/{visitor_id}/checkin

Record visitor arrival.

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:9095/api/security/visitors/VIS-001/checkin
```

**Response:** 200 OK
```json
{
  "visitor_id": "VIS-001",
  "status": "checked_in",
  "check_in_time": "2026-02-13T09:00:00Z"
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
- `status` (string, optional): open | acknowledged | resolved
- `limit` (integer, optional, default 50)

**Response:** 200 OK
```json
{
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
  ],
  "total": 2
}
```

### POST /api/security/alerts

Create security alert from monitoring service.

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "site": "site-002",
    "type": "after_hours",
    "location": "Server Room",
    "severity": "warning",
    "description": "Unauthorized after-hours access"
  }' \
  http://localhost:9095/api/security/alerts
```

**Request Body:**
```json
{
  "site": "site-002",
  "type": "after_hours",
  "location": "Server Room",
  "severity": "warning",
  "description": "Unauthorized access outside business hours"
}
```

**Response:** 201 Created
```json
{
  "alert_id": "ALR-001",
  "timestamp": "2026-02-13T22:30:00Z"
}
```

### GET /api/security/occupancy

Get current building occupancy for Phase 28+ HVAC/Lighting integration.

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

**Used by Phase 28+:**
- HVAC Module: Occupancy-based setpoint control
- Lighting Module: Occupancy-based dimming and daylight harvesting

## Error Responses

All endpoints return standard error format:

```json
{
  "error": "NOT_FOUND",
  "message": "Event EVT-999 not found",
  "status": 404,
  "timestamp": "2026-02-13T16:45:00Z"
}
```

**Common Status Codes:**
| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 500 | Server Error |

## Authentication

Include JWT token in Authorization header:

```bash
curl -H "Authorization: Bearer $JWT_TOKEN" \
  http://localhost:9095/api/security/events?site=site-002
```

**Authentication Levels:**
- `AUTHENTICATED`: All read-only endpoints
- `OPERATOR`: Write operations (create events, alerts, visitors)
- `ADMIN`: Configuration

## Rate Limiting

**Default Limits:**
- Individual endpoints: 60 requests/minute per user
- Batch endpoints: 300 requests/minute per user

**Response Headers:**
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1645026600
```

## Date/Time Format

All timestamps use ISO 8601 format with UTC timezone:
- `2026-02-13T16:45:00Z`
- `2026-02-13T16:45:00.123Z`

## Pagination

Large result sets support offset-based pagination:

**Parameters:**
- `limit`: Results per page (default 50, max 1000)
- `offset`: Number of results to skip

**Example:**
```bash
# Get results 100-150
curl "http://localhost:9095/api/security/events?site=site-002&limit=50&offset=100"
```

---

**API Version:** 1.0
**Last Updated:** 2026-02-13
**Module:** SENTINEL Security (Phase 27)
**Endpoints:** 20+
**Average Response Time:** 50-150ms

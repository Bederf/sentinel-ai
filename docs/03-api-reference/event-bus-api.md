---
title: "Event Bus Monitoring API"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-03-01"
updated: "2026-03-01"
author: "Sentinel Development Team"
tags: ["event-bus", "api", "monitoring", "phase-139"]
domain: "general"
audience: "developers"
complexity: "beginner"
estimated_read_time: 5
---

# Event bus monitoring API

Read-only monitoring endpoints for the SENTINEL event bus. All endpoints are under `/api/event-bus` and registered in the operations registrar.

**Router:** `backend/app/api/event_bus_monitor.py`
**Tag:** `event-bus`

## Endpoints

### GET /api/event-bus/metrics

Returns aggregate event bus metrics for the System Health dashboard.

**Response:**

```json
{
  "status": "ok",
  "metrics": {
    "events_emitted": 142,
    "handlers_invoked": 891,
    "handler_errors": 2,
    "by_domain": {
      "sensor": 87,
      "ai": 31,
      "maintenance": 24
    },
    "by_importance": {
      "INFO": 45,
      "LOW": 12,
      "MEDIUM": 52,
      "HIGH": 28,
      "CRITICAL": 5
    },
    "subscription_count": 7,
    "history_size": 142
  }
}
```

### GET /api/event-bus/history

Query the rolling event history buffer with optional filters. Returns events most-recent-first.

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `event_type` | string | null | Filter by exact event type (e.g. `sensor.anomaly_detected`) |
| `domain` | string | null | Filter by domain (e.g. `sensor`) |
| `site_id` | string | null | Filter by site ID |
| `correlation_id` | string | null | Filter by correlation ID |
| `min_importance` | string | null | Minimum importance: `INFO`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` |
| `limit` | int | 100 | Maximum results (1-1000) |

**Response:**

```json
{
  "status": "ok",
  "count": 2,
  "events": [
    {
      "event_id": "a1b2c3d4-...",
      "event_type": "sensor.anomaly_detected",
      "source": "anomaly_detector",
      "payload": {"score": 0.87},
      "importance": {"name": "HIGH", "value": 7},
      "site_id": "site-002",
      "equipment_id": "S002-CHILLER-B1-001",
      "building_name": null,
      "timestamp": "2026-03-01T10:30:00+00:00",
      "correlation_id": null,
      "caused_by": null,
      "domain": "sensor",
      "action": "anomaly_detected"
    }
  ]
}
```

**Error response** (invalid importance value):

```json
{
  "status": "error",
  "detail": "Invalid importance: foo. Valid: INFO, LOW, MEDIUM, HIGH, CRITICAL"
}
```

### GET /api/event-bus/chain/{correlation_id}

Retrieve all events in a correlation chain, ordered by timestamp. Use this to trace a full causal sequence (e.g. anomaly -> diagnosis -> work order).

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `correlation_id` | string | The correlation ID linking the event chain |

**Response:**

```json
{
  "status": "ok",
  "correlation_id": "a1b2c3d4-...",
  "count": 3,
  "events": [
    {
      "event_id": "a1b2c3d4-...",
      "event_type": "sensor.anomaly_detected",
      "correlation_id": null,
      "caused_by": null,
      "timestamp": "2026-03-01T10:30:00+00:00"
    },
    {
      "event_id": "e5f6g7h8-...",
      "event_type": "ai.diagnosis_complete",
      "correlation_id": "a1b2c3d4-...",
      "caused_by": "a1b2c3d4-...",
      "timestamp": "2026-03-01T10:30:02+00:00"
    },
    {
      "event_id": "i9j0k1l2-...",
      "event_type": "maintenance.work_order_created",
      "correlation_id": "a1b2c3d4-...",
      "caused_by": "e5f6g7h8-...",
      "timestamp": "2026-03-01T10:30:05+00:00"
    }
  ]
}
```

### GET /api/event-bus/subscriptions

List all registered event subscriptions. Useful for debugging which handlers are active.

**Response:**

```json
{
  "status": "ok",
  "count": 7,
  "subscriptions": [
    {
      "sub_id": "uuid-...",
      "pattern": "*",
      "paused": false,
      "min_importance": "INFO",
      "site_ids": null,
      "domains": null,
      "has_filter": false
    },
    {
      "sub_id": "uuid-...",
      "pattern": "sensor.anomaly_detected",
      "paused": false,
      "min_importance": "INFO",
      "site_ids": null,
      "domains": null,
      "has_filter": false
    }
  ]
}
```

## Related documents

- [Event Bus Architecture](../02-architecture/event-bus-architecture.md) -- pub/sub design, event model, middleware, subscriber patterns

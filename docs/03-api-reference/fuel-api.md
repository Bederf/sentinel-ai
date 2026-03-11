---
title: "Fuel Tank Monitoring API Reference"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-03-11"
updated: "2026-03-11"
author: "SENTINEL Development Team"
tags: ["api", "fuel", "theft-detection", "generator", "monitoring", "alerts"]
domain: "fuel"
audience: "developers"
complexity: "beginner"
estimated_read_time: 8
---

# Fuel Tank Monitoring API Reference

REST API endpoints for fuel tank telemetry, event history, generator runtime tracking, and refill logs. Implemented in Phases 148-150 (v48.0 Fuel Tank Monitoring Module).

**Base path:** `/api/fuel`

**Feature flag:** `FUEL_MONITORING_ENABLED` (default: `true`)

**Demo site:** `site-002` (Sandton City Office Tower)

## Data Models

### FuelTank (response)

```typescript
{
  tank_id: string;           // Equipment code (e.g., "S002-TANK-EXT-001")
  site_id: string;           // Site code
  name: string;              // Human-readable name
  capacity_litres: number;   // Tank capacity
  fuel_type: string;         // "diesel" | "petrol" | "lpg"
  generator_id?: string;     // Linked generator equipment code
  latest_telemetry?: FuelTelemetry;
  days_to_empty?: number;    // Derived: linear projection
  consumption_rate_lph?: number; // Derived: litres per hour
}
```

### FuelTelemetry

```typescript
{
  tank_id: string;
  timestamp: string;         // ISO datetime
  level_pct: number;         // 0-100%
  level_litres: number;      // Absolute litres
  temperature_c: number;     // Fuel temperature
  raw_ma: number;            // Raw sensor reading (4-20 mA)
  generator_running: boolean;
  consumption_rate_lph: number;
  days_to_empty?: number;
  runtime_remaining_hrs?: number;
}
```

### FuelEvent

```typescript
{
  event_id: string;
  tank_id: string;
  timestamp: string;
  event_type: FuelEventType;
  severity: "CRITICAL" | "WARNING" | "INFO";
  message: string;
  metrics: {
    level_pct?: number;
    rate_lpm?: number;
    temperature_c?: number;
  };
}
```

### FuelEventType (enum)

```
theft_alert | leak_detected | low_fuel | refill_detected |
temp_alert | sensor_fault | runtime_complete
```

## Endpoints

### GET /api/fuel/tanks

List all fuel tanks with latest telemetry.

**Query parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `site_id` | string | — | Filter by site (optional) |

**Response:** `200 OK`

```json
{
  "tanks": [
    {
      "tank_id": "S002-TANK-EXT-001",
      "site_id": "site-002",
      "name": "External Diesel Tank",
      "capacity_litres": 10000,
      "fuel_type": "diesel",
      "generator_id": "S002-GEN-B1-001",
      "latest_telemetry": { ... },
      "days_to_empty": 14.2,
      "consumption_rate_lph": 8.5
    }
  ]
}
```

---

### GET /api/fuel/tanks/{tank_id}

Single tank detail with latest telemetry and derived fields.

**Path parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `tank_id` | string | Tank equipment code |

**Response:** `200 OK` — Single tank object (same shape as list item)

**Error:** `404 Not Found` — Unknown tank_id

---

### GET /api/fuel/tanks/{tank_id}/history

Time-series telemetry readings for a tank.

**Path parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `tank_id` | string | Tank equipment code |

**Query parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `hours` | int | 24 | Lookback window in hours |

**Response:** `200 OK`

```json
{
  "tank_id": "S002-TANK-EXT-001",
  "readings": [
    {
      "timestamp": "2026-03-11T10:00:00Z",
      "level_pct": 72.5,
      "level_litres": 7250,
      "temperature_c": 22.3,
      "consumption_rate_lph": 8.5
    }
  ]
}
```

---

### GET /api/fuel/events

Fuel events list with optional filtering.

**Query parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `site_id` | string | — | Filter by site (optional) |
| `event_type` | string | — | Filter by event type (optional) |
| `limit` | int | 50 | Max events to return |

**Response:** `200 OK`

```json
{
  "events": [
    {
      "event_id": "evt-001",
      "tank_id": "S002-TANK-EXT-001",
      "timestamp": "2026-03-11T08:30:00Z",
      "event_type": "low_fuel",
      "severity": "WARNING",
      "message": "Fuel level at 22% (below 25% threshold)",
      "metrics": { "level_pct": 22.0 }
    }
  ]
}
```

---

### GET /api/fuel/generator-runtime

Generator runtime sessions extracted from fuel telemetry.

**Query parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `site_id` | string | — | Filter by site (optional) |
| `limit` | int | 50 | Max sessions to return |

**Response:** `200 OK`

```json
{
  "sessions": [
    {
      "tank_id": "S002-TANK-EXT-001",
      "generator_id": "S002-GEN-B1-001",
      "start_time": "2026-03-10T18:00:00Z",
      "end_time": "2026-03-10T22:30:00Z",
      "duration_hours": 4.5,
      "fuel_consumed_litres": 38.2,
      "consumption_rate_lph": 8.5,
      "anomaly": false
    }
  ]
}
```

---

### GET /api/fuel/refill-log

Refill events showing tank replenishment history.

**Query parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `site_id` | string | — | Filter by site (optional) |
| `limit` | int | 50 | Max entries to return |

**Response:** `200 OK`

```json
{
  "refills": [
    {
      "tank_id": "S002-TANK-EXT-001",
      "timestamp": "2026-03-08T10:15:00Z",
      "litres_added": 5000,
      "level_before_pct": 28.0,
      "level_after_pct": 78.0
    }
  ]
}
```

## Alert Routing

FuelAlertService subscribes to fuel events on the event bus and routes notifications:

| Event Type | Alert Level | Action |
|------------|-------------|--------|
| `theft_alert` | CRITICAL | Broadcast via NotificationService (WhatsApp/Telegram) |
| `leak_detected` | CRITICAL | Broadcast via NotificationService |
| `low_fuel` (pct_2) | CRITICAL | Broadcast via NotificationService |
| `low_fuel` (pct_1) | WARNING | Broadcast via NotificationService |
| `temp_alert` | WARNING | Broadcast via NotificationService |
| `sensor_fault` | WARNING | Broadcast via NotificationService |
| `refill_detected` | INFO | Logged only (no notification) |
| `runtime_complete` | INFO | Logged only (no notification) |

## Testing

```bash
# Run all fuel tests
cd backend && pytest tests/services/test_fuel_store.py tests/services/test_fuel_mqtt_listener.py tests/services/test_fuel_event_processor.py tests/services/test_fuel_alert_service.py tests/api/test_fuel_api.py -v

# Run fuel API tests only
cd backend && pytest tests/api/test_fuel_api.py -v
```

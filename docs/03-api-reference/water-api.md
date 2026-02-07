---
title: "Water Meter API Reference"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-02-07"
updated: "2026-02-07"
author: "SENTINEL Development Team"
tags: ["api", "water", "leak-detection", "consumption", "monitoring", "sustainability"]
domain: "water"
audience: "developers"
complexity: "beginner"
estimated_read_time: 10
---

# Water Meter API Reference

REST API endpoints for water consumption monitoring, leak detection, trending analysis, and alert management. Implemented in Phase 35 (Water Meter Integration & Leak Detection).

**Base path:** `/api/water`

**Demo site:** `site-002` (Sandton City Office Tower)

## Data Models

### WaterMeter

```typescript
{
  meter_id: string;          // Unique meter identifier
  site: string;              // Building site code
  pulse_weight: number;      // Liters per pulse (default 10L)
  installation_date: string; // ISO date string
  meter_type: string;        // "main" | "submeter" | "irrigation" |
                            // "cooling" | "domestic" | "fire"
}
```

### WaterConsumption

```typescript
{
  timestamp: string;         // ISO datetime
  volume_liters: number;     // Cumulative volume
  flow_rate_lpm: number;     // Instantaneous flow rate
  pulse_count: number;       // Raw pulse count
  temperature?: number;      // Water temperature (°C)
  pressure?: number;         // Water pressure (kPa)
  meter_id: string;          // Source meter
}
```

### WaterAlert

```typescript
{
  alert_id: string;          // Unique alert identifier
  alert_type: string;        // "continuous_flow" | "unusual_pattern" | "spike"
  severity: string;          // "low" | "medium" | "high" | "critical"
  timestamp: string;         // ISO datetime when alert triggered
  resolved: boolean;         // Resolution status
  resolution?: string;       // Technician notes (if resolved)
  details: {
    flow_rate_lpm: number;   // Flow rate at alert time
    duration_minutes?: number; // Duration for continuous flow
    baseline_percent?: number; // Deviation from baseline for anomalies
    location?: string;       // Meter/equipment location
  };
}
```

### WaterTrending

```typescript
{
  site: string;
  period: "daily" | "weekly" | "monthly";
  current_period: {
    total_volume_liters: number;
    average_daily_liters: number;
    start_date: string;
    end_date: string;
  };
  previous_period: {
    total_volume_liters: number;
    average_daily_liters: number;
    start_date: string;
    end_date: string;
  };
  comparison_percent: number; // % change (positive = increase)
  trend: "increasing" | "decreasing" | "stable";
}
```

## Endpoints

### Consumption

#### GET `/api/water/consumption/{site}`

Get historical consumption data with optional date range filtering.

**Parameters:**
- `site` (path): Site identifier (e.g., `site-002`)
- `start_date` (query, optional): Start date (ISO format: `YYYY-MM-DD`)
- `end_date` (query, optional): End date (ISO format: `YYYY-MM-DD`)

**Response:** `WaterConsumption[]`

```json
[
  {
    "timestamp": "2026-02-07T14:30:00Z",
    "volume_liters": 45230.5,
    "flow_rate_lpm": 12.5,
    "pulse_count": 4523,
    "meter_id": "meter-001"
  }
]
```

**Example:**
```bash
# Last 7 days
curl localhost:9095/api/water/consumption/site-002?start_date=2026-01-31&end_date=2026-02-07

# All available data
curl localhost:9095/api/water/consumption/site-002
```

#### GET `/api/water/consumption/{site}/current`

Get latest flow rate and volume reading for a site.

**Parameters:**
- `site` (path): Site identifier

**Response:** `WaterConsumption` (latest record)

```json
{
  "timestamp": "2026-02-07T14:35:00Z",
  "volume_liters": 45245.0,
  "flow_rate_lpm": 12.5,
  "pulse_count": 4524,
  "meter_id": "meter-001",
  "site": "site-002"
}
```

**Example:**
```bash
curl localhost:9095/api/water/consumption/site-002/current
```

### Trending

#### GET `/api/water/trending/{site}`

Get trend analysis comparing current period to previous period.

**Parameters:**
- `site` (path): Site identifier
- `period` (query): Comparison period - `day` | `week` | `month` (default: `week`)

**Response:** `WaterTrending`

```json
{
  "site": "site-002",
  "period": "weekly",
  "current_period": {
    "total_volume_liters": 45000,
    "average_daily_liters": 6428,
    "start_date": "2026-02-01",
    "end_date": "2026-02-07"
  },
  "previous_period": {
    "total_volume_liters": 42000,
    "average_daily_liters": 6000,
    "start_date": "2026-01-25",
    "end_date": "2026-01-31"
  },
  "comparison_percent": 7.1,
  "trend": "increasing"
}
```

**Example:**
```bash
# Weekly comparison (default)
curl localhost:9095/api/water/trending/site-002

# Daily comparison
curl localhost:9095/api/water/trending/site-002?period=day

# Monthly comparison
curl localhost:9095/api/water/trending/site-002?period=month
```

### Alerts

#### GET `/api/water/alerts/{site}`

Get all leak alerts with optional filtering.

**Parameters:**
- `site` (path): Site identifier
- `severity` (query, optional): Filter by severity - `low` | `medium` | `high` | `critical`
- `resolved` (query, optional): Filter by resolution status - `true` | `false`
- `start_date` (query, optional): Start date (ISO format)
- `end_date` (query, optional): End date (ISO format)

**Response:** `WaterAlert[]`

```json
[
  {
    "alert_id": "alert-004",
    "alert_type": "unusual_pattern",
    "severity": "high",
    "timestamp": "2026-02-07T10:00:00Z",
    "resolved": false,
    "details": {
      "flow_rate_lpm": 22.5,
      "baseline_percent": 150,
      "location": "Main building inlet"
    }
  }
]
```

**Examples:**
```bash
# All alerts
curl localhost:9095/api/water/alerts/site-002

# Only high-severity unresolved alerts
curl localhost:9095/api/water/alerts/site-002?severity=high&resolved=false

# Alerts from last 7 days
curl localhost:9095/api/water/alerts/site-002?start_date=2026-01-31
```

#### GET `/api/water/alerts/{site}/active`

Get only active (unresolved) alerts requiring attention.

**Parameters:**
- `site` (path): Site identifier

**Response:** `WaterAlert[]` (only `resolved: false`)

```json
[
  {
    "alert_id": "alert-003",
    "alert_type": "spike",
    "severity": "medium",
    "timestamp": "2026-02-07T14:00:00Z",
    "resolved": false,
    "details": {
      "flow_rate_lpm": 45.0,
      "location": "Cooling tower makeup"
    }
  },
  {
    "alert_id": "alert-004",
    "alert_type": "unusual_pattern",
    "severity": "high",
    "timestamp": "2026-02-07T10:00:00Z",
    "resolved": false,
    "details": {
      "flow_rate_lpm": 22.5,
      "baseline_percent": 150
    }
  }
]
```

**Example:**
```bash
curl localhost:9095/api/water/alerts/site-002/active
```

#### PATCH `/api/water/alerts/{alert_id}/resolve`

Mark an alert as resolved with technician notes.

**Parameters:**
- `alert_id` (path): Alert identifier

**Request Body:**
```json
{
  "resolution": "Investigated and found stuck irrigation valve. Repaired."
}
```

**Response:** `WaterAlert` (updated)

```json
{
  "alert_id": "alert-003",
  "alert_type": "spike",
  "severity": "medium",
  "timestamp": "2026-02-07T14:00:00Z",
  "resolved": true,
  "resolution": "Investigated and found stuck irrigation valve. Repaired.",
  "details": {...}
}
```

**Example:**
```bash
curl -X PATCH localhost:9095/api/water/alerts/alert-003/resolve \
  -H "Content-Type: application/json" \
  -d '{"resolution": "Investigated and found stuck irrigation valve. Repaired."}'
```

### Ingestion Status

#### GET `/api/water/ingestion/status`

Get water ingestion service status with site registrations.

**Response:**
```json
{
  "status": "running",
  "sites": [
    {
      "site_id": "site-002",
      "meter_id": "meter-001",
      "polling_interval_seconds": 60,
      "last_reading": "2026-02-07T14:35:00Z",
      "status": "active"
    }
  ],
  "total_sites": 1,
  "active_sites": 1
}
```

**Example:**
```bash
curl localhost:9095/api/water/ingestion/status
```

## Leak Detection Algorithms

The water meter API uses three complementary algorithms for leak detection:

### 1. Continuous Flow Detection

**Trigger:** Flow > threshold (default 10 LPM) for > duration (default 30 min) during off-hours (22:00-06:00)

**Use Cases:**
- Toilet stuck flush
- Irrigation valve leak
- Underground pipe leak

**Severity:** HIGH (requires investigation same day)

**Example Alert:**
```json
{
  "alert_type": "continuous_flow",
  "severity": "high",
  "details": {
    "flow_rate_lpm": 15.0,
    "duration_minutes": 480,
    "off_hours_violation": true
  }
}
```

### 2. Statistical Anomaly (Z-Score)

**Trigger:** Current flow vs 7-day baseline, z-score > threshold (default 3.0)

**Use Cases:**
- Underground slow leak
- Meter malfunction
- Unusual consumption pattern

**Severity:**
- HIGH if z-score > 5.0
- MEDIUM if z-score 3.0-5.0

**Example Alert:**
```json
{
  "alert_type": "unusual_pattern",
  "severity": "high",
  "details": {
    "flow_rate_lpm": 22.5,
    "baseline_flow_lpm": 15.0,
    "z_score": 5.2,
    "baseline_percent": 150
  }
}
```

### 3. Spike Detection

**Trigger:** Flow increase > threshold (default 200%) from window average (default 15 min)

**Use Cases:**
- Equipment filling (cooling tower)
- Pipe burst
- Unauthorized usage

**Severity:** MEDIUM

**Example Alert:**
```json
{
  "alert_type": "spike",
  "severity": "medium",
  "details": {
    "current_flow_lpm": 80.0,
    "average_flow_lpm": 25.0,
    "increase_percent": 220
  }
}
```

## Error Responses

All endpoints may return the following error responses:

### 400 Bad Request

```json
{
  "detail": "Invalid date format. Use ISO format (YYYY-MM-DD)."
}
```

### 404 Not Found

```json
{
  "detail": "Site not found: site-999"
}
```

### 500 Internal Server Error

```json
{
  "detail": "Water ingestion service not initialized. Call ensure_water_ingestion_service_initialized()."
}
```

## Configuration

Leak detection thresholds are configurable per deployment:

```python
# backend/app/services/water_alert_service.py

CONTINUOUS_FLOW_THRESHOLD_LPM = 10.0
CONTINUOUS_FLOW_DURATION_MINUTES = 30.0
CONTINUOUS_FLOW_OFF_HOURS_START = 22
CONTINUOUS_FLOW_OFF_HOURS_END = 6

SPIKE_DETECTION_THRESHOLD_PERCENT = 200.0
SPIKE_DETECTION_WINDOW_MINUTES = 15

ZSCORE_THRESHOLD = 3.0
ZSCORE_BASELINE_DAYS = 7
```

## Rate Limiting

No rate limiting currently enforced. Consider implementing for production:

- **Recommended:** 60 requests/minute per site
- **Burst:** 10 requests/second

## Authentication

All endpoints require JWT authentication:

```bash
curl localhost:9095/api/water/consumption/site-002 \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

## Demo Data

The API returns realistic demo data when actual meter readings are unavailable:

**Site:** `site-002` (Sandton City Office Tower)
**Meter:** `S002-MTR-W-MAIN` (Elster V100, 80mm, 10L/pulse)
**History:** 8,876 consumption records over 30 days (2026-01-08 to 2026-02-07)
**Alerts:** 4 pre-configured leak scenarios (2 resolved, 2 active)

## Testing

### Manual Testing

```bash
# Test consumption endpoint
curl localhost:9095/api/water/consumption/site-002

# Test trending
curl localhost:9095/api/water/trending/site-002?period=week

# Test active alerts
curl localhost:9095/api/water/alerts/site-002/active

# Test alert resolution
curl -X PATCH localhost:9095/api/water/alerts/alert-003/resolve \
  -H "Content-Type: application/json" \
  -d '{"resolution": "Fixed leaking valve."}'

# Test ingestion status
curl localhost:9095/api/water/ingestion/status
```

### Integration Tests

```bash
# Run water API tests
pytest tests/api/test_water_api.py -v
```

## Frontend Integration

The water API client is located at `frontend/src/lib/waterApi.ts`:

```typescript
import * as waterApi from '@/lib/waterApi';

// Get current flow
const flow = await waterApi.getCurrentFlow('site-002');

// Get consumption history
const consumption = await waterApi.getConsumption(
  'site-002',
  '2026-01-31',
  '2026-02-07'
);

// Get active alerts
const alerts = await waterApi.getActiveAlerts('site-002');

// Resolve alert
await waterApi.resolveAlert('alert-003', 'Fixed leaking valve.');
```

## References

- **Feature Documentation:** `docs/04-features/35-water-meter-integration.md`
- **Backend Implementation:** `backend/app/api/water.py`
- **Frontend Client:** `frontend/src/lib/waterApi.ts`
- **Phase 35-01 Summary:** `.planning/phases/35-water-meter-integration/35-01-SUMMARY.md`
- **Phase 35-02 Summary:** `.planning/phases/35-water-meter-integration/35-02-SUMMARY.md`

---

**Last Updated:** 2026-02-07
**API Version:** 1.0.0
**Base URL:** `http://localhost:9095/api/water`

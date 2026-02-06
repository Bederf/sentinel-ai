---
title: "Time-Series API Reference"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-02-06"
updated: "2026-02-06"
author: "Sentinel Development Team"
tags: ["api", "timeseries", "influxdb", "sensor-data", "ml-training"]
domain: "bms"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 6
---

# Time-Series API Reference

Phase 42-01 Time-Series Data Infrastructure endpoints. Write and query sensor data with automatic downsampling and ML training data export.

Base path: `/api/timeseries`

## Write Data

### POST `/api/timeseries/write`

Write a single sensor reading. Auto-downsampled to 1-minute, 1-hour, and 1-day buckets.

**Request Body:**
```json
{
  "equipment_id": "S002-CHILLER-B1-001",
  "sensor_type": "chw_supply_temp",
  "value": 7.2,
  "timestamp": "2026-02-06T10:00:00Z",
  "unit": "°C",
  "tags": {"source": "bacnet"}
}
```

**Response:**
```json
{
  "success": true,
  "count": 1,
  "message": "Written to bms_raw"
}
```

### POST `/api/timeseries/write/batch`

Write multiple readings in a single batch. More efficient for bulk ingestion.

**Request Body:**
```json
{
  "readings": [
    {"equipment_id": "...", "sensor_type": "...", "value": 7.2, ...},
    {"equipment_id": "...", "sensor_type": "...", "value": 45.1, ...}
  ]
}
```

## Query Data

### GET `/api/timeseries/query/raw`

Query raw sensor data at original resolution.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| equipment_id | string | Yes | Equipment identifier |
| sensor_type | string | Yes | Sensor type |
| start | datetime | Yes | Start time (ISO 8601) |
| end | datetime | Yes | End time (ISO 8601) |

### GET `/api/timeseries/query/hourly`

Query hourly aggregated data. Returns mean values per hour, suitable for LSTM input.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| equipment_id | string | required | Equipment identifier |
| sensor_type | string | required | Sensor type |
| hours | int | 168 | Lookback hours (7 days default) |

### GET `/api/timeseries/query/ml-training`

Get data formatted for ML model training with multiple sensor types.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| equipment_id | string | required | Equipment identifier |
| sensor_types | string | required | Comma-separated sensor types |
| days | int | 180 | Historical data period |

**Response:**
```json
{
  "equipment_id": "S002-CHILLER-B1-001",
  "sensor_types": ["chw_supply_temp", "compressor_current"],
  "hours": 4320,
  "data": [...]
}
```

## Health & Status

### GET `/api/timeseries/health`

Check InfluxDB connection health.

**Response:**
```json
{
  "status": "healthy",
  "mode": "mock",
  "url": "http://localhost:8086",
  "buckets": ["bms_raw", "bms_hourly", "bms_daily"]
}
```

### GET `/api/timeseries/buckets`

List configured data buckets with retention policies.

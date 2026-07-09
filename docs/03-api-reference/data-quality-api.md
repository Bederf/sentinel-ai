---
title: "Data Quality API Reference"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-02-06"
updated: "2026-02-06"
author: "Sentinel Development Team"
tags: ["api", "data-quality", "monitoring", "alerts", "ml-training"]
domain: "bms"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 8
---

# Data Quality API Reference

Phase 42-03 Data Quality Monitoring endpoints. Sensor uptime tracking, gap detection, quality scoring, and ML training readiness assessment.

Base path: `/api/data-quality`

## Health Check

### GET `/api/data-quality/health`

Service health status.

**Response:**
```json
{
  "status": "healthy",
  "influxdb_mode": "mock",
  "active_alerts": 3,
  "timestamp": "2026-02-06T10:00:00Z"
}
```

## Equipment Quality

### GET `/api/data-quality/equipment/{equipment_id}`

Data quality metrics for a single equipment item.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| equipment_type | string | null | Equipment type hint |
| lookback_hours | int | 24 | Analysis period (1-168) |

**Response:** `EquipmentDataQuality` with sensor health, completeness percentage, and data gaps.

## Building Quality

### GET `/api/data-quality/building/{building_id}`

Aggregated data quality for all equipment in a building.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| building_name | string | null | Building name override |

### GET `/api/data-quality/report/daily`

Daily data quality report for a building.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| building_id | string | Yes | Building identifier |
| building_name | string | No | Building name |

## Alerts

### GET `/api/data-quality/alerts`

Get data quality alerts.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| equipment_id | string | null | Filter by equipment |
| alert_type | string | null | Filter by type |
| include_resolved | bool | false | Include resolved alerts |
| limit | int | 50 | Max results (1-500) |

### GET `/api/data-quality/alerts/summary`

Alert summary by type and severity.

**Response:**
```json
{
  "total_active": 5,
  "by_type": {"stale_data": 2, "data_gap": 3},
  "by_severity": {"warning": 3, "critical": 2},
  "total_history": 15
}
```

### POST `/api/data-quality/alerts/check`

Trigger alert check for all equipment. Scans for stale data, gaps, and sensor drift.

### POST `/api/data-quality/alerts/resolve`

Manually resolve an alert.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| equipment_id | string | Yes | Equipment identifier |
| sensor_type | string | Yes | Sensor type |
| alert_type | string | Yes | Alert type to resolve |

## Data Gaps

### GET `/api/data-quality/gaps/equipment/{equipment_id}`

Get all data gaps for an equipment item across all sensors.

## ML Training Readiness

### GET `/api/data-quality/training-readiness/{equipment_type}`

Assess if sufficient quality data exists for ML model training.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| minimum_equipment | int | 3 | Min equipment count |
| minimum_days | int | 180 | Min data history days |
| minimum_quality | float | 0.7 | Min quality score (0-1) |

**Response:**
```json
{
  "equipment_type": "chiller",
  "ready": true,
  "equipment_count": 5,
  "avg_quality": 0.85,
  "avg_history_days": 240,
  "issues": []
}
```

## Quality Levels

### GET `/api/data-quality/quality-levels`

Get quality level definitions and thresholds (excellent, good, fair, poor).

## Background Integrity Detection (Phase 236-02)

The **pinned-signal detector** (`backend/app/services/pinned_signal_detector.py`)
is a scheduled background job (6h cadence), not an HTTP endpoint. It catches the
telemetry failure class neither the quality gate (impossible values) nor
cross-signal conflict detection covers: signals that are individually **plausible
but frozen** — bridge defaults, dead point mappings, saturated sensors.

It evaluates `telemetry_hourly` per site in two window tiers:

| Tier | Fires when |
|------|-----------|
| `structural_7d` | a point shows a single distinct value (or <1% relative range) across the week — nonzero only (a constant-zero reads as "equipment off", not stuck) |
| `frozen_24h` | a point whose week of history proves it normally varies collapses to one distinct value over the last 24h |

Constant-by-design points (`fault_state`, `equipment_online`, `status`,
`run_status`, `staging_state`, `*_anomaly_score`) are excluded via
`backend/app/data/pinned_signal_exclusions.json` (per-site overrides supported).

**Outputs:**
- Per-point verdicts persisted to `pinned_signal_state` (consumed by inference —
  the FCU running-inference treats a pinned `fan_speed`/`valve_position` as
  unavailable; verdicts older than 18h are ignored so a decayed verdict fails open).
- A `data_integrity` advisory recommendation per affected equipment, rolled up to
  a single site-level finding (`{SITE}-TELEMETRY-INTEGRITY`) when the majority of
  a site's points are frozen (a systemic feed fault, not N sensor failures).
  Deduplicated with an 8h clear-debounce, auto-resolved when variance returns.

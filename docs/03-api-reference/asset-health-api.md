---
title: "Asset health API"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-02-20"
updated: "2026-02-20"
author: "Sentinel Development Team"
tags: ["api", "asset-health", "baseline", "deviation", "equipment", "health"]
related: ["../04-features/109A-asset-health-baseline.md", "../04-features/health-scoring-system.md", "equipment.md"]
domain: "bms"
audience: "developers"
complexity: "beginner"
estimated_read_time: 8
---

# Asset health API

REST endpoints for retrieving combined equipment health scores and baseline
status. These endpoints aggregate data from the equipment table, baseline
records, and deviation comparisons into a single response per equipment item.

Phase: 109A | Router: `backend/app/api/asset_health.py` | Tag: `asset-health`

## Endpoints

### List site asset health

```
GET /api/sites/{site_id}/assets/health-baseline
```

Returns health and baseline status for all equipment at a site.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `site_id` | `string` | Site code (e.g., `site-002`) |

**Response:** `200 OK`

```json
{
  "site_id": "site-002",
  "total": 2,
  "assets": [
    {
      "equipment_id": "S002-AHU-001",
      "equipment_name": "AHU 001",
      "equipment_type": "AHU",
      "category": "HVAC",
      "health_score": 85,
      "health_status": "warning",
      "health_source": "simulation",
      "health_updated_at": "2026-02-20T10:00:00",
      "has_active_baseline": true,
      "last_baseline_at": "2026-02-15T08:00:00",
      "total_baselines": 2,
      "baseline_source": "manual",
      "max_deviation_percent_24h": 12.5,
      "deviation_status": "normal"
    },
    {
      "equipment_id": "S002-FCU-101",
      "equipment_name": "FCU 101",
      "equipment_type": "FCU",
      "category": "HVAC",
      "health_score": 45,
      "health_status": "critical",
      "health_source": "simulation",
      "health_updated_at": null,
      "has_active_baseline": false,
      "last_baseline_at": null,
      "total_baselines": 0,
      "baseline_source": null,
      "max_deviation_percent_24h": null,
      "deviation_status": null
    }
  ]
}
```

**Notes:**

- Returns all equipment at the site regardless of baseline status
- Health status is computed via `HealthThresholdService` (not hardcoded)
- Deviation is computed from `baseline_comparisons` in the last 24 hours
- Uses 3 database queries total (1 equipment + 2 baseline bulk queries)

---

### Get equipment health detail

```
GET /api/equipment/{equipment_id}/health-baseline
```

Returns health and baseline status for a single equipment item.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `equipment_id` | `string` | Equipment code (e.g., `S002-CHILLER-B1-001`) |

**Response:** `200 OK`

```json
{
  "equipment_id": "S002-CHILLER-B1-001",
  "equipment_name": "Chiller 001",
  "equipment_type": "CHILLER",
  "category": "HVAC",
  "health_score": 92,
  "health_status": "healthy",
  "health_source": "equipment_table",
  "health_updated_at": "2026-02-20T09:30:00",
  "has_active_baseline": true,
  "last_baseline_at": "2026-02-10T14:00:00",
  "total_baselines": 3,
  "baseline_source": "bms_average",
  "max_deviation_percent_24h": 8.2,
  "deviation_status": "normal"
}
```

**Error responses:**

| Status | Condition |
|--------|-----------|
| `404` | Equipment code not found |
| `500` | Internal server error |

## Response model

`AssetHealthBaseline` — defined in `backend/app/models/asset_health.py`

| Field | Type | Description |
|-------|------|-------------|
| `equipment_id` | `string` | Equipment code |
| `equipment_name` | `string` | Display name |
| `equipment_type` | `string` | Type extracted from code (AHU, CHILLER, etc.) |
| `category` | `string` | Equipment category (HVAC, Electrical, etc.) |
| `health_score` | `integer` | Health score 0-100 |
| `health_status` | `string` | `"healthy"`, `"warning"`, or `"critical"` |
| `health_source` | `string` | `"simulation"` (demo mode) or `"equipment_table"` (live) |
| `health_updated_at` | `string?` | ISO 8601 timestamp of last health update |
| `has_active_baseline` | `boolean` | Whether an active baseline exists |
| `last_baseline_at` | `string?` | ISO 8601 timestamp of most recent baseline |
| `total_baselines` | `integer` | Total number of baselines recorded |
| `baseline_source` | `string?` | `"manual"`, `"bms_average"`, or `"mobile_sensor"` |
| `max_deviation_percent_24h` | `number?` | Maximum deviation percentage in last 24 hours |
| `deviation_status` | `string?` | `"normal"` (<=15%), `"warning"` (15-30%), `"critical"` (>=30%), or `null` |

## Health status rules

Health status is **delegated** to `HealthThresholdService` — thresholds are
configurable per equipment type, not hardcoded:

```python
# health_status is computed as:
health_status = threshold_service.get_health_status(health_score)
```

## Deviation status rules

Deviation classification is baseline-specific (independent of health thresholds):

| Max deviation (24h) | Status |
|---------------------|--------|
| No comparisons | `null` |
| <= 15% | `"normal"` |
| > 15% and < 30% | `"warning"` |
| >= 30% | `"critical"` |

## Related documents

- [Asset Health Baseline Feature](../04-features/109A-asset-health-baseline.md) — Feature specification
- [Health Scoring System](../04-features/health-scoring-system.md) — How health scores are calculated
- [Equipment API](equipment.md) — Base equipment endpoints
- [RSI Threshold Tuning Schema](../07-database/rsi-threshold-tuning-schema.md) — Threshold tables, tuner role, promote/rollback endpoints, human-in-the-loop enforcement

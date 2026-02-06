---
title: "Condition Monitoring API Reference"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-02-06"
updated: "2026-02-06"
author: "Sentinel Development Team"
tags: ["api", "condition-monitoring", "vibration", "rul", "degradation"]
domain: "bms"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 8
---

# Condition Monitoring API Reference

Phase 41-03 Condition Monitoring endpoints. Equipment trend analysis, degradation rates, remaining useful life (RUL), and fleet-wide risk assessment.

Base path: `/api/condition`

## Trend Analysis

### GET `/api/condition/trends/{equipment_id}`

Get trend analysis for all monitored elements of an equipment item.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| days | int | 90 | Lookback period (1-365) |

**Response:** `EquipmentTrendSummary` with per-element trend data, degradation rates, and overall condition.

### GET `/api/condition/trends/{equipment_id}/{element_name}`

Get detailed trend for a specific element.

**Response:**
```json
{
  "element_name": "bearing_vibration",
  "equipment_id": "S002-CHILLER-B1-001",
  "measurement_type": "vibration_rms",
  "data_points": [...],
  "degradation_rate_per_day": 0.002,
  "trend_direction": "degrading",
  "r_squared": 0.87
}
```

## Degradation Rates

### GET `/api/condition/degradation-rates/{equipment_id}`

Get degradation rates for all monitored elements.

**Response:**
```json
[
  {
    "element_name": "bearing_vibration",
    "rate_per_day": 0.002,
    "rate_per_month": 0.06,
    "unit": "mm/s",
    "confidence": 0.87
  }
]
```

## Remaining Useful Life

### GET `/api/condition/rul/{equipment_id}`

Predict remaining useful life for all elements.

**Response:** `EquipmentRUL` with per-element RUL in days and confidence intervals.

## Recommendations

### GET `/api/condition/recommendations/{equipment_id}`

Get prioritized service recommendations for degrading elements.

**Response:** `List[ServiceRecommendation]` sorted by urgency.

## Fleet Risk

### GET `/api/condition/fleet-risk`

Fleet-wide RUL risk overview, sorted by days until first threshold (ascending).

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| risk_level | string | null | Filter by risk level |
| limit | int | 20 | Max results |

## Service Schedule Optimization

### POST `/api/condition/optimize-service-schedule`

Compare condition-based vs fixed-schedule maintenance timing.

**Request Body:**
```json
{
  "equipment_ids": ["S002-CHILLER-B1-001", "S002-AHU-L2-001"],
  "fixed_interval_days": 90
}
```

## Asset Utilization

### GET `/api/condition/utilization/{equipment_id}`

Show how much of each component's usable life has been consumed.

## Cost Comparison

### GET `/api/condition/cost-comparison/{equipment_id}`

Compare fixed-schedule vs condition-based maintenance costs.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| fixed_interval_days | int | 90 | Fixed schedule interval (7-365) |

## Change Analysis

### POST `/api/condition/analyze-changes`

Run full trend analysis.

**Request Body:**
```json
{
  "equipment_id": "S002-CHILLER-B1-001",
  "element_name": "bearing_vibration"
}
```

---
title: "Energy Consumption API Reference (Phase A)"
type: "reference"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# Energy Consumption API Reference (Phase A)

**Status:** Available | **Version:** 1.0 | **Phase:** A (Energy Consumption Model)

---

## Overview

Phase A adds 11 endpoints for water consumption tracking, power meter validation, cost validation, and AI-powered financial recommendations with ROI. All endpoints support DEMO_MODE fallback.

**Base URL:** `http://localhost:9095/api`

**Related Docs:**
- [Energy API (Phase 084)](./energy-api.md) -- comparison and prediction endpoints
- [AI Recommendation System](../08-ai-ml/ai-recommendation-system.md) -- recommendation architecture
- [Water API](./water-api.md) -- zone-level water analytics

---

## Endpoint Summary

| # | Method | Path | Domain |
|---|--------|------|--------|
| 1 | GET | `/water/simulated-consumption` | Water |
| 2 | GET | `/water/tariff-info` | Water |
| 3 | POST | `/validation/power-meter` | Power Validation |
| 4 | GET | `/validation/power-meter/baseline` | Power Validation |
| 5 | GET | `/validation/power-meter/cop-adjustment` | Power Validation |
| 6 | POST | `/validation/cost` | Cost Validation |
| 7 | GET | `/validation/cost/daily` | Cost Validation |
| 8 | GET | `/validation/cost/tariff-adjustment` | Cost Validation |
| 9 | POST | `/recommendations/ai` | AI Recommendations |
| 10 | GET | `/recommendations/dashboard` | AI Recommendations |
| 11 | GET | `/recommendations/by-type` | AI Recommendations |

---

## Water Endpoints

### GET /water/simulated-consumption

Daily water consumption trends with tiered cost breakdown.

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `site_id` | string | `site-002` | Building site code |
| `days` | int | 7 | Number of days (1-365) |

**Response:**

```json
{
  "site_id": "site-002",
  "period_days": 7,
  "total_liters": 45000.0,
  "total_cost_r": 1250.50,
  "average_daily_liters": 6428.57,
  "average_daily_cost_r": 178.64,
  "daily_consumption": [
    {
      "date": "2026-02-18",
      "total_liters": 6500.0,
      "tier_1_liters": 3333.33,
      "tier_1_cost_r": 26.50,
      "tier_2_liters": 3166.67,
      "tier_2_cost_r": 39.58,
      "tier_3_liters": 0.0,
      "tier_3_cost_r": 0.0,
      "sewerage_cost_r": 41.00,
      "fixed_charge_r": 9.50,
      "total_cost_r": 116.58,
      "peak_hour_consumption_lpm": 45.2,
      "average_rate_r_liter": 0.01794
    }
  ]
}
```

### GET /water/tariff-info

Municipal water tariff structure (Johannesburg tiered pricing).

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `site_id` | string | `site-002` | Building site code |

**Response includes:** 3 tiers with rates (R/kL), sewerage charge, fixed monthly charge, annual projections.

**Tariff Tiers (Johannesburg 2024):**

| Tier | Threshold | Rate (R/kL) |
|------|-----------|-------------|
| 1 | First 100,000 L/month | R7.95 |
| 2 | 100,001-500,000 L/month | R12.50 |
| 3 | Above 500,000 L/month | R18.95 |
| Sewerage | All consumption | R6.30 |

---

## Power Validation Endpoints

### POST /validation/power-meter

Validate simulated power against real meter reading. Detects anomalies using z-score analysis.

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `site_id` | string | `site-002` | Building site code |
| `meter_id` | string | `S002-MTR-B1-HVAC` | Meter identifier |
| `simulated_power_kw` | float | 28.5 | Simulated consumption |
| `real_power_kw` | float | null | Actual meter reading (optional) |
| `simulated_hour` | int | 12 | Hour of day (0-23) |

**Response:**

```json
{
  "validation_status": "anomaly",
  "severity": "warning",
  "simulated_kw": 28.5,
  "real_kw": 32.1,
  "variance_pct": 11.2,
  "variance_direction": "under",
  "hour": 12,
  "baseline_mean_kw": 25.4,
  "zscore": 0.87,
  "recommendation": "Simulation underestimating..."
}
```

**Validation Statuses:** `normal` | `anomaly` | `critical` | `skipped`

### GET /validation/power-meter/baseline

Baseline power statistics for anomaly detection.

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `site_id` | string | `site-002` | Building site code |
| `meter_id` | string | `S002-MTR-B1-HVAC` | Meter identifier |
| `lookback_days` | int | 7 | Historical analysis period |

**Response:** `mean_kw`, `stdev_kw`, `min_kw`, `max_kw`, `p95_kw`, `samples`

### GET /validation/power-meter/cop-adjustment

COP (Coefficient of Performance) degradation detection for chillers.

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `site_id` | string | `site-002` | Building site code |
| `meter_id` | string | `S002-MTR-B1-HVAC` | Meter identifier |
| `lookback_days` | int | 30 | Analysis period |

**Response:** `current_cop` (design: 3.5), `estimated_cop`, `status` (`healthy` | `degraded` | `unknown`), `confidence`

---

## Cost Validation Endpoints

### POST /validation/cost

Validate simulated costs against real municipal invoice.

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `site_id` | string | `site-002` | Building site code |
| `month` | int | 2 | Month (1-12) |
| `year` | int | 2026 | Year |
| `real_invoice_cost_r` | float | 18500.00 | Actual invoice amount |
| `simulated_total_kwh` | float | null | Override simulated energy |
| `simulated_total_water_liters` | float | null | Override simulated water |

**Response:**

```json
{
  "validation_status": "warning",
  "severity": "warning",
  "variance_pct": 5.13,
  "variance_r": 950.75,
  "variance_direction": "over",
  "recommendation": "Simulation overestimating costs..."
}
```

**Validation Statuses:** `validated` | `warning` | `critical`

### GET /validation/cost/daily

Calculate daily cost breakdown from consumption values.

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `site_id` | string | `site-002` | Building site code |
| `energy_kwh` | float | 315.0 | Daily energy consumption |
| `water_liters` | float | 6847.0 | Daily water consumption |
| `cost_date` | string | today | Date (YYYY-MM-DD) |

**Response:** `energy_cost_r`, `water_cost_r`, `total_cost_r`, `season`

### GET /validation/cost/tariff-adjustment

Tariff multiplier recommendation based on historical variance analysis.

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `site_id` | string | `site-002` | Building site code |
| `months_analyzed` | int | 3 | Historical months to analyze |

**Response:** `adjustment_needed` (bool), `recommended_tariff_multiplier` (e.g., 1.048), `confidence`, `bias_direction`

---

## AI Recommendation Endpoints

### POST /recommendations/ai

Generate ranked financial recommendations with ROI calculations.

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `site_id` | string | `site-002` | Building site code |
| `lighting_kwh_current` | float | 185.0 | Daily lighting energy |
| `water_liters_current` | float | 6847.0 | Daily water consumption |
| `hvac_cop_current` | float | 3.5 | Chiller COP |
| `power_anomalies_count` | int | 0 | Detected anomalies |
| `cost_variance_pct` | float | 0.18 | Cost model accuracy |

**Response:**

```json
{
  "building_id": "site-002",
  "recommendation_count": 4,
  "total_annual_savings_r": 60250.00,
  "total_investment_r": 135000.00,
  "average_payback_months": 27.5,
  "recommendations": [
    {
      "rank": 1,
      "priority": "urgent",
      "type": "hvac_maintenance",
      "title": "Emergency: Chiller Maintenance Required",
      "annual_savings_r": 42025.00,
      "investment_cost_r": 15000.00,
      "payback_months": 4.3,
      "roi_pct": 280.2,
      "confidence": 0.92,
      "messaging": {
        "short": "URGENT: Maintenance needed - COP degraded 17%",
        "urgency": "critical"
      }
    }
  ]
}
```

**Recommendation Types:**

| Type | Trigger | Typical ROI |
|------|---------|-------------|
| `lighting_optimization` | Lighting > baseline | 15-25% |
| `water_efficiency` | Water > benchmark | 10-20% |
| `hvac_maintenance` | COP < 3.0 (degraded) | 200-300% |
| `occupancy_optimization` | Low occupancy detected | 20-40% |

**ROI Formula:** `payback_months = investment / (savings / 12)`, `roi_pct = (savings / investment) * 100`

### GET /recommendations/dashboard

Dashboard-ready summary with top 3 recommendations and messaging.

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `site_id` | string | `site-002` | Building site code |

**Response:** `top_recommendations` (max 3), `total_savings_r_annual`, `call_to_action`

### GET /recommendations/by-type

Detailed single recommendation with implementation guide.

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `site_id` | string | `site-002` | Building site code |
| `recommendation_type` | string | null | Filter by type |

**Response:** Full recommendation with `financials`, `metrics`, `benefits`, `risks`, `next_steps`

---

## Demo Mode Behavior

In `DEMO_MODE=true`:
- Water consumption uses repository fallback (may return empty if no demo data seeded)
- Power meter baseline returns synthetic 168-sample baseline
- Cost validation compares against default expected daily cost (R1575/day)
- AI recommendations generate based on input parameters with hardcoded benchmarks
- All endpoints return HTTP 200 with valid structure

---

## Implementation

| Component | File |
|-----------|------|
| All 11 endpoints | `backend/app/api/energy.py` |
| Power validation engine | `backend/app/services/power_meter_validation_engine.py` |
| Cost validation engine | `backend/app/services/cost_validation_engine.py` |
| AI recommendation engine | `backend/app/services/ai_recommendation_engine.py` |
| Water consumption repo | `backend/app/database/repositories/water_consumption_repository.py` |
| Integration tests | `backend/tests/api/test_energy_consumption_pipeline.py` |

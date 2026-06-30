---
title: "IPMVP M&V API"
type: "reference"
status: "active"
version: "1.0.0"
created: "2026-05-12"
updated: "2026-05-12"
tags: ["sentinel", "documentation"]
related: ["energy-api", "optimization-api"]
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# IPMVP M&V API

Implements IPMVP 2022 Edition Volume III Chapter 5 Option C (Whole Facility) and Option A (Retrofit Isolation) methodology for Measurement & Verification of energy savings.

## Overview

The M&V engine uses Ordinary Least Squares (OLS) regression to establish a baseline model of facility energy use, then compares reporting-period actuals against the baseline to compute verified savings.

**Two methodologies:**

| Option | Methodology | Use case |
|--------|-------------|----------|
| **Option C** | Whole Facility — regression baseline | Ongoing M&V for entire building |
| **Option A** | Retrofit Isolation — pre/post meter comparison | M&V for specific equipment changes |

**Key metrics:**
- `cv_rmse_pct` — Coefficient of Variation of RMSE; IPMVP uncertainty metric. Values < 20% are acceptable; > 50% are high-uncertainty
- `r_squared` — Model fit; > 0.7 is a good fit
- `savings_kwh` / `savings_cost` — Verified energy and cost savings

---

## Endpoints

### GET /api/ipmvp/{site_id}/report

Generate a full M&V report for a site and reporting period.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `site_id` | string | Site identifier, e.g. `site-002` |

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `reporting_start` | string | Required | ISO date start, e.g. `2026-01-01` |
| `reporting_end` | string | Required | ISO date end, e.g. `2026-02-28` |
| `option` | string | `C` | `C` = Whole Facility, `A` = Retrofit Isolation |
| `recommendation_id` | string | null | Required for Option A — links to specific equipment event |
| `hourly_detail` | boolean | `true` | Include per-interval savings breakdown |

**Response:**

```json
{
  "site_id": "site-002",
  "reporting_start": "2026-01-01",
  "reporting_end": "2026-02-28",
  "option": "C",
  "baseline": {
    "occupied": {
      "equation": "energy_kwh ~ OAT + hour + day_of_week + holiday",
      "coefficients": { "OAT": 2.34, "hour_10": 45.2, "day_of_week_1": -12.1 },
      "intercept": 320.5,
      "r_squared": 0.82,
      "cv_rmse_pct": 14.3,
      "n_samples": 1240
    },
    "unoccupied": {
      "equation": "energy_kwh ~ OAT + hour",
      "coefficients": { "OAT": 0.85 },
      "intercept": 85.2,
      "r_squared": 0.71,
      "cv_rmse_pct": 18.1,
      "n_samples": 480
    }
  },
  "savings": {
    "reporting_kwh": 89240,
    "baseline_kwh": 98510,
    "savings_kwh": 9270,
    "savings_cost_zar": 18540.0,
    "cv_rmse_pct": 15.2,
    "uncertainty_flag": false
  },
  "hourly_detail": [
    { "timestamp": "2026-01-01T00:00:00Z", "actual_kwh": 380, "baseline_kwh": 420, "savings_kwh": 40 },
    ...
  ]
}
```

**Uncertainty flag:** `true` when `cv_rmse_pct >= 20%`. High-uncertainty results should be reviewed before presenting as verified savings.

---

### GET /api/ipmvp/{site_id}/baseline

Train baseline models without computing savings. Use to validate model quality before running a full report.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `baseline_start` | string | ISO date start |
| `baseline_end` | string | ISO date end |

**Response:**

```json
{
  "site_id": "site-002",
  "baseline_start": "2025-10-01",
  "baseline_end": "2025-12-31",
  "occupied": {
    "period": "occupied",
    "equation": "energy_kwh ~ OAT + hour + day_of_week + holiday",
    "coefficients": { "OAT": 2.34, "hour_10": 45.2, "day_of_week_1": -12.1 },
    "intercept": 320.5,
    "r_squared": 0.82,
    "cv_rmse_pct": 14.3,
    "n_samples": 1240
  },
  "unoccupied": {
    "period": "unoccupied",
    "equation": "energy_kwh ~ OAT + hour",
    "coefficients": { "OAT": 0.85 },
    "intercept": 85.2,
    "r_squared": 0.71,
    "cv_rmse_pct": 18.1,
    "n_samples": 480
  }
}
```

**Model quality thresholds:**

| Metric | Good | Acceptable | Poor |
|--------|------|------------|------|
| `r_squared` | > 0.7 | 0.5–0.7 | < 0.5 |
| `cv_rmse_pct` | < 15% | 15–20% | > 20% |

---

### GET /api/ipmvp/{site_id}/events

Get equipment change events in a period for Option A isolation.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `start` | string | ISO date start |
| `end` | string | ISO date end |
| `system_types` | string | Comma-separated: `hvac`, `lighting`, `bess` |

**Response:**

```json
{
  "site_id": "site-002",
  "period_start": "2026-01-01",
  "period_end": "2026-01-31",
  "events": [
    {
      "event_id": "EVT-2026-001",
      "equipment_id": "CH-02",
      "event_type": "chiller_replacement",
      "timestamp": "2026-01-15T08:00:00Z",
      "description": "Chiller 2 replaced with VSD unit"
    }
  ],
  "count": 1
}
```

---

## Methodology

### Option C — Whole Facility Regression

1. **Collect baseline data** — 15-minute energy and OAT data for the baseline period (minimum 30 days)
2. **Split by occupancy** — Separate models for occupied hours (07:00–19:00 Mon–Fri) and unoccupied
3. **Exclude load shedding days** — Days with load shedding events are excluded from baseline training
4. **OLS regression** — `energy_kwh ~ OAT + hour + day_of_week + holiday`
5. **Calculate savings** — Reporting period actual vs baseline predicted; savings = baseline − actual

### Option A — Retrofit Isolation

1. **Identify equipment event** — Equipment repair, replacement, or operational change
2. **Pre-period metering** — Energy use before the change
3. **Post-period metering** — Energy use after the change
4. **Adjust for conditions** — Normalize for OAT, occupancy, operating hours
5. **Report savings** — Isolated savings attributable to the retrofit

### Load Shedding Handling

Load shedding events corrupt energy baseline data (genset running ≠ normal operation). The engine:
- Excludes all 15-min intervals on load shedding days from OLS training
- Reports `load_shedding_excluded_hours` in the report metadata
- Flags savings results where load shedding occurred during the reporting period

---

## Data Sources

| Data | Source | Storage |
|------|--------|---------|
| 15-min energy | Bridge `/ipmvp/energy` → hourly sync | `ipmvp_energy` table |
| Outdoor air temp | Bridge `/ipmvp/oat` → hourly sync | `ipmvp_oat` table |
| Equipment events | Bridge `/ipmvp/events` → hourly sync | `ipmvp_events` table |
| Load shedding | Bridge `/ipmvp/load-shedding` → hourly sync | Inferred from events |
| Tariff | Bridge `/ipmvp/tariff` → hourly sync | `ipmvp_tariff` table |
| Occupancy schedule | Bridge `/ipmvp/occupancy` → hourly sync | `ipmvp_occupancy` table |

**Sync pipeline:** `Site002DataFetcher.run_full_sync()` fetches all IPMVP endpoints from the bridge and upserts into dedicated `ipmvp_*` Supabase tables. Runs hourly via APScheduler. Rolling 7-day retention — older data auto-purged on each sync.

Bridge auth uses site-scoped bridge secrets. Prefer `BRIDGE_API_TOKEN_SITE_002` for Site 002; `BRIDGE_API_TOKEN` is legacy fallback only. Base URL comes from `BRIDGE_BASE_URL`.

---

## Implementation

- API router: `backend/app/api/ipmvp.py`
- Engine: `backend/app/services/ipmvp/ipmvp_engine.py`
- Data fetcher: `backend/app/services/ipmvp/site002_fetcher.py` (includes `persist_*()` methods + `run_full_sync()`)
- Models: `backend/app/services/ipmvp/`
- Scheduler: `background_scheduler.py` → `add_ipmvp_sync_job()` (hourly)
- Register: `backend/app/api/registrars/analytics.py` → `register_analytics_routers()`

---

## Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Invalid dates (start ≥ end) or unsupported option |
| 503 | Feature not implemented (e.g., Option A not yet available) |
| 500 | Calculation failed |

---
title: "Sustainability & ESG API"
type: "reference"
status: "approved"
version: "2.0.0"
created: "2026-02-22"
updated: "2026-02-22"
author: "Sentinel Development Team"
tags: ["sustainability", "esg", "carbon", "emissions", "api"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 8
---

# Sustainability & ESG API

REST API for carbon emissions tracking, ESG scoring, and sustainability reporting. Covers both v1 (summary/emissions/efficiency) and v2 (building-level, daily metrics, ESG) endpoints.

## v1 Endpoints

Prefixed with `/api/sustainability/{site_id}/`.

### GET /summary

Dashboard summary: current month emissions, YTD totals, trend, Green Star progress.

```bash
curl http://localhost:9095/api/sustainability/site-002/summary
```

```json
{
  "site_id": "site-002",
  "current_month": {
    "month": "2026-02",
    "scope1_kg_co2": 228.0,
    "scope2_kg_co2": 4520.0,
    "scope3_kg_co2": 1850.0,
    "total_kg_co2": 6598.0,
    "grid_kwh": 4264.0,
    "diesel_litres": 85.0,
    "hvac_kg_co2": 2862.0,
    "lighting_kg_co2": 1272.0,
    "other_kg_co2": 636.0,
    "solar_offset_kg_co2": 318.0,
    "net_scope2_kg_co2": 4202.0,
    "data_source": "simulation"
  },
  "ytd": {
    "total_co2_kg": 12500.0,
    "total_co2_tonnes": 12.5,
    "total_kwh": 85000.0
  },
  "trend": "stable",
  "target_reduction_pct": 10.0,
  "green_star": {
    "total_achieved": 67,
    "total_max": 118,
    "estimated_rating": "5-Star",
    "target_rating": "5-Star"
  }
}
```

### GET /emissions

Monthly emissions history.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `months` | int | 12 | Number of months to return |

### GET /emissions/current

Current month emissions snapshot with per-system breakdown.

### GET /emissions/breakdown

Breakdown by scope and building system (HVAC, lighting, other).

### GET /efficiency

Energy and carbon intensity with SA office benchmarks.

**Benchmarks Used:**

| Rating | Annual (kWh/m²/yr) | Monthly (kWh/m²/mo) | Source |
|--------|-------------------|---------------------|--------|
| Efficient | 120 | 10.0 | Green Star 5-6★ office |
| Typical | 170 | 14.2 | SANS 10400-XA compliant baseline |
| Poor | 230 | 19.2 | Pre-2011 stock |

**Note:** Monthly values are annual/12. See [EnergyChart Benchmark Calculation](../04-features/energy-chart-benchmark-calculation.md) for dashboard implementation details.

### GET /green-star

Green Star SA self-assessment (9 categories, 118 max points).

### PUT /green-star/{category_id}

Update a Green Star category score.

```json
{ "achieved_points": 18, "notes": "Solar PV now operational" }
```

### GET /config

Site sustainability configuration (emission factors, targets, estimates).

### PUT /config

Update site configuration.

### GET /report/export

Export sustainability report as CSV or HTML.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `format` | string | `csv` | `csv` or `html` |
| `months` | int | 12 | Months of data (1-36) |

**CSV columns:** Month, Scope 1/2/3 (kg CO2), Total, Grid kWh, Diesel L, HVAC CO2, Lighting CO2, Other CO2, Solar Offset CO2, Data Source.

**HTML report:** Styled single-page report with KPIs (YTD CO2, carbon intensity, EUI), Green Star progress, and SA benchmarks. Printable to PDF via browser.

```bash
# Download CSV
curl -o report.csv "http://localhost:9095/api/sustainability/site-002/report/export?format=csv&months=12"

# Open HTML report
open "http://localhost:9095/api/sustainability/site-002/report/export?format=html&months=12"
```

## v2 Endpoints

Building-level endpoints prefixed with `/api/v2/sustainability/buildings/{building_id}/`.

### GET /emissions/monthly

Monthly emissions aggregated from `daily_sustainability_metrics`. Falls back to `emissions_sources` table if available.

### GET /emissions/by-source

Emissions broken down by source category.

### GET /benchmark

Building performance vs SA commercial office benchmarks.

### GET /esg-metrics

ESG score with breakdown.

```json
{
  "score": 74,
  "breakdown": {
    "carbon_intensity_score": 78,
    "energy_efficiency_score": 72,
    "waste_diversion_score": 65
  }
}
```

### GET /certifications

Green Star SA certification status and targets.

## EmissionsSnapshot Schema

The `EmissionsSnapshot` model includes both original and Phase 111 fields:

| Field | Type | Description |
|-------|------|-------------|
| `month` | string | Month (YYYY-MM) |
| `site_id` | string | Site identifier |
| `scope1_kg_co2` | float | Diesel generator emissions |
| `scope2_kg_co2` | float | Grid electricity emissions (gross) |
| `scope3_kg_co2` | float | Water, waste, commuting |
| `grid_kwh` | float | Total grid electricity consumed |
| `diesel_litres` | float | Total diesel consumed |
| `hvac_kg_co2` | float | HVAC system carbon (Phase 111) |
| `lighting_kg_co2` | float | Lighting system carbon (Phase 111) |
| `other_kg_co2` | float | Other electrical carbon (Phase 111) |
| `solar_offset_kg_co2` | float | Solar generation offset (Phase 111) |
| `net_scope2_kg_co2` | float | Scope 2 after solar offset (Phase 111) |
| `actual_diesel_liters` | float? | Measured diesel (Phase 111) |
| `actual_water_kl` | float? | Measured water (Phase 111) |
| `solar_generation_kwh` | float? | Solar generation (Phase 111) |
| `data_source` | string | `estimated`, `measured`, or `simulation` (Phase 111) |

## Data Source Tracking

Every emissions calculation tracks where data came from:

| Source | Meaning |
|--------|---------|
| `estimated` | Config-based estimates (hardcoded fallback) |
| `simulation` | Data from lifecycle simulation pipeline |
| `measured` | Data from live metered sources |

The service uses real data from `daily_sustainability_metrics` first, falling back to estimates when unavailable.

## Emission Factors (SA Context)

| Factor | Value | Source |
|--------|-------|--------|
| Grid electricity | 1.06 kg CO2/kWh | Eskom IRP 2023 |
| Diesel | 2.68 kg CO2/L | DEFRA 2023 |
| Water | 0.708 kg CO2/kL | SA DWS Gauteng |
| Waste | 580 kg CO2/ton | DEFRA 2023 |
| Commuting | 4.2 kg CO2/person/day | Gauteng average |

Configurable per site via `PUT /config`.

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/api/sustainability.py` | FastAPI router (v1 + v2 endpoints) |
| `backend/app/services/sustainability_service.py` | v1 business logic, real-data queries |
| `backend/app/services/carbon_calculator.py` | v2 carbon calculations with solar offset |
| `backend/app/services/sustainability_metrics_collector.py` | Daily data collection from simulation |
| `backend/app/models/sustainability.py` | EmissionsSnapshot, DailySustainabilityWrite, DailySustainabilityMetrics |
| `frontend/src/lib/sustainabilityApi.ts` | TypeScript API client |

---
title: "Sustainability & ESG Module"
type: "guide"
status: "approved"
version: "1.0.0"
created: "2026-02-06"
updated: "2026-02-06"
author: "Sentinel Development Team"
tags: ["sustainability", "esg", "carbon", "emissions", "green-star", "energy-efficiency"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 12
---

# Sustainability & ESG Module (Phase 29)

Bolt-on module for carbon emissions tracking, energy efficiency benchmarking, and Green Star SA certification self-assessment. South African context with Eskom grid emission factors.

## Overview

The Sustainability module derives all data from **existing** sources — no new data ingestion required:
- **Energy module** — Grid electricity consumption (kWh by HVAC/lighting/other)
- **Generator service** — Diesel fuel consumption (litres per hour)
- **Building metadata** — Floor area (sqm), occupancy capacity

### Emission Scopes

| Scope | Source | Calculation | SA Factor |
|-------|--------|-------------|-----------|
| Scope 1 | Diesel generators | litres x factor | 2.68 kg CO2/L |
| Scope 2 | Grid electricity | kWh x factor | 1.06 kg CO2/kWh |
| Scope 3 | Water, waste, commuting | Estimated from config | Various |

### Emission Factor Sources

- **Grid (1.06 kg CO2/kWh)** — Eskom Integrated Resource Plan 2023. SA's coal-heavy grid yields one of the highest grid emission factors globally.
- **Diesel (2.68 kg CO2/L)** — DEFRA 2023 emission factor for diesel combustion.
- **Water (0.708 kg CO2/kL)** — SA Department of Water and Sanitation, Gauteng municipal treatment and distribution.
- **Waste (580 kg CO2/ton)** — DEFRA 2023, general commercial waste to landfill.
- **Commuting (4.2 kg CO2/person/day)** — Estimated average for Gauteng urban commuters (private car, minibus taxi, Gautrain mix).

All factors are configurable per site via the config API endpoint and stored in `backend/app/data/sustainability/emission_factors.json`.

## Architecture

```
Energy Module (existing)         Generator Service (existing)
       |                                    |
  grid kWh data                    diesel litres/hour
       |                                    |
       v                                    v
  ┌──────────────────────────────────────────────┐
  │         Sustainability Service               │
  │  - calculate_current_emissions()             │
  │  - get_emissions_history(months)             │
  │  - get_efficiency_metrics()                  │
  │  - get_green_star_assessment()               │
  │  - get_summary()                             │
  └──────────────────────────────────────────────┘
       |              |              |
  Scope 1/2/3    Benchmarks     Green Star SA
  Emissions      vs SA Office   Self-Assessment
```

### Module Integration

Registered in the bolt-on module system:
- **Module type:** `sustainability`
- **Integrates with:** Energy, HVAC, Lighting
- **Cross-module link:** `energy_sustainability_emissions` — recalculates emissions when energy data updates

## API Endpoints

All endpoints are prefixed with `/api/sustainability/{site_id}/`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/summary` | Dashboard summary: current month, YTD, trend, Green Star progress |
| GET | `/emissions` | Monthly emissions history (query: `months`, default 12) |
| GET | `/emissions/current` | Current month emissions snapshot |
| GET | `/emissions/breakdown` | Breakdown by scope and system |
| GET | `/efficiency` | Energy/carbon intensity with SA office benchmarks |
| GET | `/green-star` | Green Star SA self-assessment (9 categories) |
| PUT | `/green-star/{category_id}` | Update category score (body: `achieved_points`, `notes`) |
| GET | `/config` | Site sustainability configuration |
| PUT | `/config` | Update configuration (emission factors, targets, estimates) |

### Example: Get Summary

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
    "diesel_litres": 85.0
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

### Example: Update Green Star Score

```bash
curl -X PUT http://localhost:9095/api/sustainability/site-002/green-star/ENE \
  -H "Content-Type: application/json" \
  -d '{"achieved_points": 18, "notes": "Solar PV now operational"}'
```

## Green Star SA Office v1.1

Self-assessment tracker for the Green Star SA rating system. Categories and maximum points:

| ID | Category | Max Pts | Demo Score |
|----|----------|---------|------------|
| MAN | Management | 14 | 10 |
| IEQ | Indoor Environment Quality | 21 | 14 |
| ENE | Energy | 27 | 16 |
| TRA | Transport | 12 | 6 |
| WAT | Water | 12 | 7 |
| MAT | Materials | 14 | 5 |
| ECO | Land Use & Ecology | 8 | 3 |
| EMI | Emissions | 5 | 3 |
| INN | Innovation | 5 | 3 |
| **Total** | | **118** | **67** |

### Star Ratings

- **4-Star** (45-59 pts) — Best Practice
- **5-Star** (60-74 pts) — South African Excellence
- **6-Star** (75+ pts) — World Leadership

Demo site (Sandton City Office Tower) achieves **5-Star** with 67 points.

## SA Office Benchmarks

Efficiency metrics compared against SA commercial office benchmarks:

| Metric | Typical | Efficient |
|--------|---------|-----------|
| Energy intensity | 170 kWh/sqm/yr | 120 kWh/sqm/yr |
| Carbon intensity | 180 kg CO2/sqm/yr | 127 kg CO2/sqm/yr |

## Frontend Dashboard

Located at `frontend/src/components/sustainability/SustainabilityDashboard.tsx`.

Four sections in a scrollable view:
1. **KPI Row** — Total CO2 YTD (tonnes), Carbon Intensity (kg/sqm), Energy Intensity (kWh/sqm), Green Star Progress (pts/118)
2. **Emissions Chart** — Tremor stacked BarChart, monthly Scope 1/2/3 (12 months)
3. **Efficiency vs Benchmarks** — BarList comparing site metrics against SA typical/efficient
4. **Green Star Tracker** — Category cards with progress bars, star rating badge

Accessed via the ModularDashboard tabbed view when the sustainability module is active.

## Data Files

| File | Purpose |
|------|---------|
| `backend/app/data/sustainability/emission_factors.json` | SA emission factors (updatable per year) |
| `backend/app/data/sustainability/green_star_categories.json` | Green Star SA Office v1.1 category definitions |
| `backend/app/data/sustainability/site-002_config.json` | Demo site config (sqm, occupancy, targets) |
| `backend/app/data/sustainability/site-002_assessment.json` | Demo Green Star self-assessment scores |

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/models/sustainability.py` | Data models (EmissionFactors, EmissionsSnapshot, GreenStarAssessment, etc.) |
| `backend/app/services/sustainability_service.py` | Business logic (emissions calculation, efficiency metrics) |
| `backend/app/api/sustainability.py` | FastAPI router (9 endpoints) |
| `frontend/src/lib/sustainabilityApi.ts` | TypeScript API client |
| `frontend/src/components/sustainability/SustainabilityDashboard.tsx` | React dashboard component |
| `frontend/src/components/sustainability/index.ts` | Module export |

## Configuration

Site-specific configuration via `PUT /api/sustainability/{site_id}/config`:

```json
{
  "building_sqm": 4500,
  "occupancy_capacity": 150,
  "target_reduction_pct": 10.0,
  "monthly_water_kl": 45.0,
  "monthly_waste_tons": 2.5,
  "working_days_per_month": 22,
  "avg_occupancy_pct": 75.0,
  "emission_factors": {
    "grid_kg_co2_per_kwh": 1.06,
    "diesel_kg_co2_per_litre": 2.68,
    "water_kg_co2_per_kl": 0.708,
    "waste_kg_co2_per_ton": 580.0,
    "commute_kg_co2_per_person_day": 4.2
  }
}
```

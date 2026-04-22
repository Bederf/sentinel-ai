---
title: "Daily Sustainability Metrics Schema"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-02-22"
updated: "2026-02-22"
author: "Sentinel Development Team"
tags: ["database", "sustainability", "schema", "emissions"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 5
---

# Daily Sustainability Metrics Schema

Table: `daily_sustainability_metrics`
Migration: `backend/supabase/migrations/20260222_002_daily_sustainability_metrics.sql`

Stores daily energy, water, fuel, and emissions data per site. Populated by the `SustainabilityMetricsCollector` at the end of each simulated day, with a JSON fallback for demo mode.

## Table Structure

```sql
CREATE TABLE daily_sustainability_metrics (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id                 TEXT NOT NULL,
    date                    DATE NOT NULL,

    -- Energy breakdown (kWh)
    grid_kwh                NUMERIC(10,2) NOT NULL DEFAULT 0,
    hvac_kwh                NUMERIC(10,2) DEFAULT 0,
    lighting_kwh            NUMERIC(10,2) DEFAULT 0,
    other_kwh               NUMERIC(10,2) DEFAULT 0,
    solar_generation_kwh    NUMERIC(10,2) DEFAULT 0,
    solar_export_kwh        NUMERIC(10,2) DEFAULT 0,
    net_grid_kwh            NUMERIC(10,2) GENERATED ALWAYS AS (grid_kwh - COALESCE(solar_generation_kwh, 0)) STORED,

    -- Water (liters)
    water_liters            NUMERIC(12,1) DEFAULT 0,
    water_kl                NUMERIC(8,3) GENERATED ALWAYS AS (water_liters / 1000.0) STORED,

    -- Fuel (liters)
    diesel_liters           NUMERIC(10,2) DEFAULT 0,
    generator_runtime_hours NUMERIC(8,2) DEFAULT 0,

    -- Occupancy
    avg_occupancy_pct       NUMERIC(5,1) DEFAULT 0,
    peak_occupancy_count    INTEGER DEFAULT 0,

    -- Computed emissions (kg CO2e)
    scope1_kg_co2           NUMERIC(10,2) DEFAULT 0,
    scope2_kg_co2           NUMERIC(10,2) DEFAULT 0,
    scope3_kg_co2           NUMERIC(10,2) DEFAULT 0,
    total_kg_co2            NUMERIC(10,2) GENERATED ALWAYS AS (
        COALESCE(scope1_kg_co2, 0) + COALESCE(scope2_kg_co2, 0) + COALESCE(scope3_kg_co2, 0)
    ) STORED,

    -- Metadata
    source                  TEXT NOT NULL DEFAULT 'simulation'
                            CHECK (source IN ('simulation', 'live', 'manual')),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (site_id, date)
);
```

## Generated Columns

Three columns are computed automatically and cannot be written directly:

| Column | Formula | Purpose |
|--------|---------|---------|
| `net_grid_kwh` | `grid_kwh - solar_generation_kwh` | Net grid after solar offset |
| `water_kl` | `water_liters / 1000` | Kiloliters for emissions calc |
| `total_kg_co2` | `scope1 + scope2 + scope3` | Total daily carbon |

## Indexes

| Index | Columns | Purpose |
|-------|---------|---------|
| `idx_dsm_site_date` | `(site_id, date DESC)` | Site-level date range queries |
| `idx_dsm_building_date` | `(building_id, date DESC)` | Building-level queries |

## Emission Factor Calculations

Emissions are computed inline by `SustainabilityMetricsCollector` using frozen SA factors:

| Scope | Formula | Factor |
|-------|---------|--------|
| Scope 1 | `diesel_liters × 2.68` | Diesel combustion |
| Scope 2 | `max(0, grid_kwh - solar_kwh) × 1.06` | Net grid electricity |
| Scope 3 | `(water_kl × 0.708) + (occupancy × 4.2)` | Water + commuting |

## Source Field

| Value | Meaning |
|-------|---------|
| `simulation` | Written by lifecycle simulation pipeline |
| `live` | Written by live BMS data ingestion |
| `manual` | Written via API by operator |

## Upsert Pattern

Data is upserted on the `(site_id, date)` unique constraint:

```python
await client.table("daily_sustainability_metrics").upsert(
    metrics_dict,
    on_conflict="site_id,date"
).execute()
```

## JSON Fallback (Demo Mode)

When Supabase is unavailable, records are stored in:
`backend/app/data/sustainability/daily_metrics/{site_id}.json`

Format: JSON array of daily records matching the table columns.

## Related Tables

| Table | Relationship |
|-------|-------------|
| `sites` | `site_id` FK (normalized from buildings→sites, migration 111) |
| `energy_consumption_history` | Source for water data (energy_type='WATER') |
| `power_meters` | Source for real-time energy readings |

## Querying Examples

```sql
-- Monthly totals for a site
SELECT
    date_trunc('month', date) AS month,
    SUM(grid_kwh) AS total_grid,
    SUM(solar_generation_kwh) AS total_solar,
    SUM(total_kg_co2) AS total_emissions
FROM daily_sustainability_metrics
WHERE site_id = 'site-002'
GROUP BY 1
ORDER BY 1 DESC;

-- Per-system breakdown for current month
SELECT
    SUM(hvac_kwh) AS hvac,
    SUM(lighting_kwh) AS lighting,
    SUM(other_kwh) AS other,
    SUM(solar_generation_kwh) AS solar
FROM daily_sustainability_metrics
WHERE site_id = 'site-002'
  AND date >= date_trunc('month', CURRENT_DATE);
```

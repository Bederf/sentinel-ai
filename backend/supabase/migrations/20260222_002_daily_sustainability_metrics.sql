-- Migration: daily_sustainability_metrics
-- Phase: 111-01 (Sustainability Metrics Pipeline)
-- Purpose: Store daily energy/water/fuel/emissions data from simulation
-- Replaces hardcoded estimates in sustainability_service.py

CREATE TABLE IF NOT EXISTS daily_sustainability_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id TEXT NOT NULL,
    building_id UUID REFERENCES buildings(id),
    date DATE NOT NULL,

    -- Energy breakdown (kWh)
    grid_kwh NUMERIC(10,2) NOT NULL DEFAULT 0,
    hvac_kwh NUMERIC(10,2) DEFAULT 0,
    lighting_kwh NUMERIC(10,2) DEFAULT 0,
    other_kwh NUMERIC(10,2) DEFAULT 0,
    solar_generation_kwh NUMERIC(10,2) DEFAULT 0,
    solar_export_kwh NUMERIC(10,2) DEFAULT 0,
    net_grid_kwh NUMERIC(10,2) GENERATED ALWAYS AS (grid_kwh - COALESCE(solar_generation_kwh, 0)) STORED,

    -- Water (liters)
    water_liters NUMERIC(12,1) DEFAULT 0,
    water_kl NUMERIC(8,3) GENERATED ALWAYS AS (water_liters / 1000.0) STORED,

    -- Fuel (liters)
    diesel_liters NUMERIC(10,2) DEFAULT 0,
    generator_runtime_hours NUMERIC(8,2) DEFAULT 0,

    -- Occupancy (for commute Scope 3)
    avg_occupancy_pct NUMERIC(5,1) DEFAULT 0,
    peak_occupancy_count INTEGER DEFAULT 0,

    -- Computed emissions (kg CO2e) — denormalized for fast queries
    scope1_kg_co2 NUMERIC(10,2) DEFAULT 0,
    scope2_kg_co2 NUMERIC(10,2) DEFAULT 0,
    scope3_kg_co2 NUMERIC(10,2) DEFAULT 0,
    total_kg_co2 NUMERIC(10,2) GENERATED ALWAYS AS (
        COALESCE(scope1_kg_co2, 0) + COALESCE(scope2_kg_co2, 0) + COALESCE(scope3_kg_co2, 0)
    ) STORED,

    -- Metadata
    source TEXT NOT NULL DEFAULT 'simulation' CHECK (source IN ('simulation', 'live', 'manual')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (site_id, date)
);

CREATE INDEX idx_dsm_site_date ON daily_sustainability_metrics(site_id, date DESC);
CREATE INDEX idx_dsm_building_date ON daily_sustainability_metrics(building_id, date DESC);

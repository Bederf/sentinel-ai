-- Phase 109B: Asset Health Assessment Timeline
-- Migration: asset_health_snapshots and asset_health_daily_rollups tables
--
-- Stores per-equipment time-series health ratings from the 5-component
-- weighted formula (baseline alignment, service compliance, runtime/age,
-- fault burden, trend momentum). Daily rollups aggregate min/max/avg
-- for trend visualisation.

-- Table: asset_health_snapshots (per-equipment time-series health)
CREATE TABLE IF NOT EXISTS asset_health_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    equipment_id UUID NOT NULL REFERENCES equipment(id),
    building_id UUID REFERENCES buildings(id),
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Overall
    health_score NUMERIC(5,1) NOT NULL CHECK (health_score >= 0 AND health_score <= 100),
    health_status TEXT NOT NULL CHECK (health_status IN ('healthy', 'warning', 'critical')),
    assessment_state TEXT NOT NULL DEFAULT 'normal' CHECK (assessment_state IN ('normal', 'degraded_data', 'insufficient_data')),
    confidence TEXT NOT NULL DEFAULT 'high' CHECK (confidence IN ('high', 'medium', 'low')),

    -- Component scores (0-100)
    baseline_alignment_score NUMERIC(5,1),
    service_compliance_score NUMERIC(5,1),
    runtime_age_score NUMERIC(5,1),
    fault_burden_score NUMERIC(5,1),
    trend_momentum_score NUMERIC(5,1),

    -- Data quality gate inputs
    data_freshness_minutes NUMERIC(10,1),
    snapshot_count_24h INTEGER,
    valid_point_ratio NUMERIC(5,3),
    baseline_age_days INTEGER,

    -- Metadata
    health_source TEXT NOT NULL DEFAULT 'calculator' CHECK (health_source IN ('calculator', 'simulation', 'manual_override')),
    formula_version TEXT NOT NULL DEFAULT 'v1',

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX idx_health_snapshots_equipment_time ON asset_health_snapshots(equipment_id, snapshot_at DESC);
CREATE INDEX idx_health_snapshots_building_time ON asset_health_snapshots(building_id, snapshot_at DESC);
CREATE INDEX idx_health_snapshots_status ON asset_health_snapshots(health_status, snapshot_at DESC);

-- Table: asset_health_daily_rollups
CREATE TABLE IF NOT EXISTS asset_health_daily_rollups (
    equipment_id UUID NOT NULL REFERENCES equipment(id),
    date DATE NOT NULL,
    score_min NUMERIC(5,1),
    score_max NUMERIC(5,1),
    score_avg NUMERIC(5,1),
    status_mode TEXT,
    confidence_mode TEXT,
    snapshot_count INTEGER DEFAULT 0,

    PRIMARY KEY (equipment_id, date)
);

CREATE INDEX idx_health_rollups_date ON asset_health_daily_rollups(date DESC);

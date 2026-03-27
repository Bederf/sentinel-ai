-- Activate asset health snapshot persistence in the current site_id schema.
-- This environment skipped the earlier health snapshot rollout, so create the
-- tables using the current equipment/site model instead of the old building_id
-- version.

CREATE TABLE IF NOT EXISTS public.asset_health_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    equipment_id UUID NOT NULL REFERENCES public.equipment(id) ON DELETE CASCADE,
    site_id UUID REFERENCES public.sites(id) ON DELETE CASCADE,
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    health_score NUMERIC(5,1) NOT NULL CHECK (health_score >= 0 AND health_score <= 100),
    health_status TEXT NOT NULL CHECK (health_status IN ('healthy', 'warning', 'critical')),
    assessment_state TEXT NOT NULL DEFAULT 'normal'
        CHECK (assessment_state IN ('normal', 'degraded_data', 'insufficient_data')),
    confidence TEXT NOT NULL DEFAULT 'high' CHECK (confidence IN ('high', 'medium', 'low')),
    baseline_alignment_score NUMERIC(5,1),
    service_compliance_score NUMERIC(5,1),
    runtime_age_score NUMERIC(5,1),
    fault_burden_score NUMERIC(5,1),
    trend_momentum_score NUMERIC(5,1),
    data_freshness_minutes NUMERIC(10,1),
    snapshot_count_24h INTEGER,
    valid_point_ratio NUMERIC(5,3),
    baseline_age_days INTEGER,
    health_source TEXT NOT NULL DEFAULT 'calculator'
        CHECK (health_source IN ('calculator', 'simulation', 'manual_override')),
    formula_version TEXT NOT NULL DEFAULT 'v1',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_health_snapshots_equipment_time
    ON public.asset_health_snapshots(equipment_id, snapshot_at DESC);

CREATE INDEX IF NOT EXISTS idx_health_snapshots_site_time
    ON public.asset_health_snapshots(site_id, snapshot_at DESC);

CREATE INDEX IF NOT EXISTS idx_health_snapshots_status
    ON public.asset_health_snapshots(health_status, snapshot_at DESC);

CREATE TABLE IF NOT EXISTS public.asset_health_daily_rollups (
    equipment_id UUID NOT NULL REFERENCES public.equipment(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    score_min NUMERIC(5,1),
    score_max NUMERIC(5,1),
    score_avg NUMERIC(5,1),
    status_mode TEXT,
    confidence_mode TEXT,
    snapshot_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (equipment_id, date)
);

CREATE INDEX IF NOT EXISTS idx_health_rollups_date
    ON public.asset_health_daily_rollups(date DESC);

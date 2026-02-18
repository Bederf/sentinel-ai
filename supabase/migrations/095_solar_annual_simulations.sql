-- Phase 082: Solar Annual Simulation Results Caching
-- Creates tables for caching 365-day solar/BESS simulation results
-- Supports background task tracking and multi-year historical results

-- Cache table for 365-day simulation results
CREATE TABLE IF NOT EXISTS public.solar_annual_simulations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    site_id TEXT NOT NULL REFERENCES public.buildings(code) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    scenario TEXT NOT NULL,

    -- Full results as JSONB (monthly_data, seasonal_data, learning_curve)
    results JSONB NOT NULL,

    -- Metadata
    simulation_started_at TIMESTAMPTZ NOT NULL,
    simulation_completed_at TIMESTAMPTZ NOT NULL,
    simulation_duration_seconds INTEGER NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Unique constraint: one simulation per site/year/scenario
    UNIQUE(site_id, year, scenario)
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_solar_annual_site_year
ON public.solar_annual_simulations(site_id, year);

CREATE INDEX IF NOT EXISTS idx_solar_annual_scenario
ON public.solar_annual_simulations(scenario);

CREATE INDEX IF NOT EXISTS idx_solar_annual_created
ON public.solar_annual_simulations(created_at DESC);

-- Background task tracking table
CREATE TABLE IF NOT EXISTS public.solar_annual_tasks (
    task_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    site_id TEXT NOT NULL,
    scenario TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    progress_pct INTEGER NOT NULL DEFAULT 0,
    days_completed INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- Index for task lookup and cleanup
CREATE INDEX IF NOT EXISTS idx_solar_annual_tasks_site
ON public.solar_annual_tasks(site_id);

CREATE INDEX IF NOT EXISTS idx_solar_annual_tasks_status
ON public.solar_annual_tasks(status);

CREATE INDEX IF NOT EXISTS idx_solar_annual_tasks_started
ON public.solar_annual_tasks(started_at DESC);

-- Function to clean up old tasks (older than 7 days)
CREATE OR REPLACE FUNCTION cleanup_old_solar_tasks()
RETURNS void AS $$
BEGIN
  DELETE FROM public.solar_annual_tasks
  WHERE started_at < NOW() - INTERVAL '7 days';

  DELETE FROM public.solar_annual_simulations
  WHERE updated_at < NOW() - INTERVAL '90 days'
    AND scenario != 'grant_solar_bess_ai_annual';  -- Keep current scenario results longer
END;
$$ LANGUAGE plpgsql;

-- Enable RLS (Row Level Security)
ALTER TABLE public.solar_annual_simulations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.solar_annual_tasks ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Authenticated users can read their site's simulations
CREATE POLICY "solar_annual_read_policy"
ON public.solar_annual_simulations
FOR SELECT
USING (
  EXISTS (
    SELECT 1 FROM public.user_site_access
    WHERE user_id = auth.uid()
    AND site_id = solar_annual_simulations.site_id
  )
);

-- RLS Policy: Service role (backend) can write/update simulations
CREATE POLICY "solar_annual_write_policy"
ON public.solar_annual_simulations
FOR INSERT, UPDATE
USING (auth.role() = 'service_role');

-- Add comments for documentation
COMMENT ON TABLE public.solar_annual_simulations IS 'Cached 365-day solar/BESS simulation results with monthly/seasonal aggregations, costs, and ML learning curve';
COMMENT ON TABLE public.solar_annual_tasks IS 'Background task tracking for long-running annual simulations';
COMMENT ON COLUMN public.solar_annual_simulations.results IS 'JSONB containing: monthly_data[], seasonal_data[], learning_curve[], totals, metrics';
COMMENT ON COLUMN public.solar_annual_tasks.progress_pct IS 'Simulation progress 0-100%';
COMMENT ON COLUMN public.solar_annual_tasks.days_completed IS 'Number of days simulated (0-365)';

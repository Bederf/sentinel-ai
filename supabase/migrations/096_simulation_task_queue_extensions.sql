-- Phase 083: Simulation Task Queue Extensions
-- Extends solar_annual_tasks table to support lifecycle simulations and crash recovery
-- Adds: simulation_type (solar_annual|lifecycle), state_snapshot (JSONB), duration_minutes (REAL)

-- Add simulation_type column to distinguish simulation types
ALTER TABLE public.solar_annual_tasks
  ADD COLUMN IF NOT EXISTS simulation_type TEXT NOT NULL DEFAULT 'solar_annual'
    CHECK (simulation_type IN ('solar_annual', 'lifecycle'));

-- Add state_snapshot column for crash recovery (stores orchestrator state as JSONB)
ALTER TABLE public.solar_annual_tasks
  ADD COLUMN IF NOT EXISTS state_snapshot JSONB;

-- Add duration_minutes column for simulation duration tracking
ALTER TABLE public.solar_annual_tasks
  ADD COLUMN IF NOT EXISTS duration_minutes REAL NOT NULL DEFAULT 240.0;

-- Index for fast lookup of lifecycle simulations
CREATE INDEX IF NOT EXISTS idx_solar_annual_tasks_type
ON public.solar_annual_tasks(simulation_type);

-- Index for crash recovery (find running tasks on startup)
CREATE INDEX IF NOT EXISTS idx_solar_annual_tasks_status_type
ON public.solar_annual_tasks(status, simulation_type);

-- Update cleanup function to handle lifecycle simulations
CREATE OR REPLACE FUNCTION cleanup_old_solar_tasks()
RETURNS void AS $$
BEGIN
  -- Delete old solar_annual tasks (older than 7 days)
  DELETE FROM public.solar_annual_tasks
  WHERE started_at < NOW() - INTERVAL '7 days'
    AND simulation_type = 'solar_annual';

  -- Delete old lifecycle simulation tasks (older than 7 days)
  DELETE FROM public.solar_annual_tasks
  WHERE started_at < NOW() - INTERVAL '7 days'
    AND simulation_type = 'lifecycle';

  -- Delete old simulation results (older than 90 days, except grant scenario)
  DELETE FROM public.solar_annual_simulations
  WHERE updated_at < NOW() - INTERVAL '90 days'
    AND scenario != 'grant_solar_bess_ai_annual';
END;
$$ LANGUAGE plpgsql;

-- Update table documentation
COMMENT ON COLUMN public.solar_annual_tasks.simulation_type IS 'Type of simulation: solar_annual or lifecycle';
COMMENT ON COLUMN public.solar_annual_tasks.state_snapshot IS 'JSONB snapshot of orchestrator state for crash recovery (simulated_time, days_simulated, active_faults, recent_events, etc)';
COMMENT ON COLUMN public.solar_annual_tasks.duration_minutes IS 'Planned duration of simulation in minutes (default 240 = 4 hours)';

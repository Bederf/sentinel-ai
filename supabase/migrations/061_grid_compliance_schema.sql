-- Grid compliance monitoring schema for Phase 34, Module 8 (Solar Grid Compliance)
-- Tables for NRS 097-2-3 compliance violations and load shedding events

-- Compliance violations log
CREATE TABLE IF NOT EXISTS public.compliance_log (
  id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  timestamp TIMESTAMPTZ NOT NULL,
  system_id TEXT NOT NULL,
  parameter TEXT NOT NULL,  -- frequency, voltage, ramp_rate, current, power_factor, thd
  measured_value NUMERIC NOT NULL,
  limit_value NUMERIC NOT NULL,
  violation_type TEXT NOT NULL,  -- below_min, exceeds_max, ramp_too_fast
  severity TEXT NOT NULL,  -- critical, warning, info
  auto_action TEXT,  -- bess_discharge, solar_curtailment, standby, frequency_droop, etc.
  duration_ms INTEGER,  -- Time to resolution
  resolved BOOLEAN DEFAULT FALSE,
  resolution_time TIMESTAMPTZ
);

CREATE INDEX idx_compliance_log_timestamp ON public.compliance_log(timestamp DESC);
CREATE INDEX idx_compliance_log_system ON public.compliance_log(system_id);
CREATE INDEX idx_compliance_log_severity ON public.compliance_log(severity);
CREATE INDEX idx_compliance_log_parameter ON public.compliance_log(parameter);

-- Load shedding events
CREATE TABLE IF NOT EXISTS public.load_shed_events (
  id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  timestamp TIMESTAMPTZ NOT NULL,
  frequency_hz NUMERIC NOT NULL,
  previous_stage INTEGER NOT NULL DEFAULT 0,
  current_stage INTEGER NOT NULL,  -- 0-8, where 8 is most severe
  dispatch_action TEXT NOT NULL,  -- bess_discharge, solar_curtailment_50pct, standby_mode, ramp_up_5pct_per_min
  affected_systems TEXT[] DEFAULT ARRAY[]::TEXT[],  -- equipment IDs affected
  expected_reduction_kw NUMERIC DEFAULT 0.0
);

CREATE INDEX idx_load_shed_events_timestamp ON public.load_shed_events(timestamp DESC);
CREATE INDEX idx_load_shed_events_stage ON public.load_shed_events(current_stage);

-- Grid compliance status snapshots (for trending and dashboards)
CREATE TABLE IF NOT EXISTS public.grid_status_snapshots (
  id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  timestamp TIMESTAMPTZ NOT NULL,
  system_id TEXT NOT NULL,
  grid_code TEXT NOT NULL,  -- nrs_097_2_3, iec_61727, ieee_1547
  compliant BOOLEAN NOT NULL DEFAULT TRUE,
  frequency_hz NUMERIC NOT NULL,
  voltage_v NUMERIC NOT NULL,
  current_a NUMERIC DEFAULT 0.0,
  power_factor NUMERIC DEFAULT 1.0,
  active_violations_count INTEGER DEFAULT 0,
  last_check TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_grid_status_snapshots_timestamp ON public.grid_status_snapshots(timestamp DESC);
CREATE INDEX idx_grid_status_snapshots_system ON public.grid_status_snapshots(system_id);
CREATE INDEX idx_grid_status_snapshots_compliant ON public.grid_status_snapshots(compliant);

-- Manual override log (for emergency situations)
CREATE TABLE IF NOT EXISTS public.grid_overrides (
  id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  system_id TEXT NOT NULL,
  action TEXT NOT NULL,  -- curtailment_50pct, standby, ramp_up, etc.
  initiated_at TIMESTAMPTZ NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  manual_override BOOLEAN DEFAULT FALSE,
  override_reason TEXT
);

CREATE INDEX idx_grid_overrides_system ON public.grid_overrides(system_id);
CREATE INDEX idx_grid_overrides_expires ON public.grid_overrides(expires_at DESC);

-- Enable realtime subscriptions for compliance monitoring
ALTER TABLE public.compliance_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.load_shed_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.grid_status_snapshots ENABLE ROW LEVEL SECURITY;

-- Policies for read access (all authenticated users can read)
CREATE POLICY "Allow read compliance_log"
  ON public.compliance_log FOR SELECT
  TO authenticated
  USING (TRUE);

CREATE POLICY "Allow read load_shed_events"
  ON public.load_shed_events FOR SELECT
  TO authenticated
  USING (TRUE);

CREATE POLICY "Allow read grid_status_snapshots"
  ON public.grid_status_snapshots FOR SELECT
  TO authenticated
  USING (TRUE);

-- Service role can insert/update (for monitoring engines)
CREATE POLICY "Allow insert compliance_log"
  ON public.compliance_log FOR INSERT
  TO service_role
  WITH CHECK (TRUE);

CREATE POLICY "Allow insert load_shed_events"
  ON public.load_shed_events FOR INSERT
  TO service_role
  WITH CHECK (TRUE);

CREATE POLICY "Allow insert grid_status_snapshots"
  ON public.grid_status_snapshots FOR INSERT
  TO service_role
  WITH CHECK (TRUE);

-- Compliance report views

-- View: Compliance violations aggregated by day
CREATE OR REPLACE VIEW public.compliance_violations_by_day AS
SELECT
  DATE(timestamp) AS violation_date,
  system_id,
  parameter,
  severity,
  COUNT(*) AS violation_count
FROM public.compliance_log
GROUP BY DATE(timestamp), system_id, parameter, severity
ORDER BY violation_date DESC, system_id;

-- View: Load shedding history with duration
CREATE OR REPLACE VIEW public.load_shedding_history AS
SELECT
  timestamp,
  frequency_hz,
  previous_stage,
  current_stage,
  dispatch_action,
  affected_systems,
  expected_reduction_kw,
  COALESCE(
    LEAD(timestamp) OVER (ORDER BY timestamp) - timestamp,
    INTERVAL '0 seconds'
  ) AS duration_at_stage
FROM public.load_shed_events
ORDER BY timestamp DESC;

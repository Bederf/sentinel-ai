CREATE TABLE IF NOT EXISTS public.mv_verification_tasks (
  id text PRIMARY KEY,
  site_id text NOT NULL,
  recommendation_id text,
  applied_at timestamptz,
  measurement_window_hours double precision NOT NULL DEFAULT 2.0,
  verify_after timestamptz,
  status text NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'verified', 'failed', 'rolled_back')),
  predicted_savings_kwh double precision NOT NULL DEFAULT 0,
  predicted_savings_zar double precision NOT NULL DEFAULT 0,
  baseline_power_kw double precision,
  recommendation_systems jsonb NOT NULL DEFAULT '[]'::jsonb,
  setpoints_applied jsonb NOT NULL DEFAULT '[]'::jsonb,
  actual_power_kw double precision,
  actual_savings_kwh double precision,
  actual_savings_zar double precision,
  accuracy double precision,
  variance_pct double precision,
  comfort_violations jsonb NOT NULL DEFAULT '[]'::jsonb,
  verified_at timestamptz,
  rollback_recommended boolean NOT NULL DEFAULT false,
  notes text NOT NULL DEFAULT '',
  routing_tier text,
  control_tier text,
  effective_confidence double precision,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mv_verification_site_status ON public.mv_verification_tasks(site_id, status);

COMMENT ON TABLE public.mv_verification_tasks IS 'MV (measure-verify) verification tasks tracking recommendation outcomes.';

--

CREATE TABLE IF NOT EXISTS public.mv_verification_outcomes (
  id bigserial PRIMARY KEY,
  recommendation_id text NOT NULL,
  predicted jsonb NOT NULL DEFAULT '{}'::jsonb,
  actual jsonb NOT NULL DEFAULT '{}'::jsonb,
  accuracy double precision,
  verified_at timestamptz NOT NULL,
  notes text NOT NULL DEFAULT '',
  quality_gate_status_at_action text,
  quality_snapshot_id text,
  ingestion_mode_at_action text,
  action_time timestamptz,
  outcome_time timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mv_verification_outcomes_rec ON public.mv_verification_outcomes(recommendation_id);

COMMENT ON TABLE public.mv_verification_outcomes IS 'MV verification outcome records linking predicted vs actual results.';

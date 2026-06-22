-- Phase promotion readiness is advisory metadata only.
-- Actual onboarding phase changes remain exclusive to PATCH /api/sites/{site_id}/phase.

ALTER TABLE public.sites
  ADD COLUMN IF NOT EXISTS phase_promotion_ready BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS phase_promotion_ready_since TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS phase_promotion_target TEXT,
  ADD COLUMN IF NOT EXISTS phase_promotion_readiness JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN public.sites.phase_promotion_ready IS
  'True when all gates passed for the next phase; does not mean the phase changed.';
COMMENT ON COLUMN public.sites.phase_promotion_ready_since IS
  'Timestamp when promotion readiness was first surfaced.';
COMMENT ON COLUMN public.sites.phase_promotion_target IS
  'Next phase the site is ready for, pending manual operator PATCH.';
COMMENT ON COLUMN public.sites.phase_promotion_readiness IS
  'Detailed readiness snapshot: gates, met flags, values, thresholds, and met_at timestamp.';

CREATE TABLE IF NOT EXISTS public.phase_promotion_readiness_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id TEXT NOT NULL REFERENCES public.sites(code),
  from_phase TEXT NOT NULL,
  to_phase TEXT NOT NULL,
  met BOOLEAN NOT NULL DEFAULT TRUE,
  met_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  current_progress JSONB NOT NULL DEFAULT '{}'::jsonb,
  gate_results JSONB NOT NULL DEFAULT '[]'::jsonb,
  recorded_by TEXT NOT NULL DEFAULT 'phase_promotion_evaluator',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_phase_promotion_readiness_log_site_created
  ON public.phase_promotion_readiness_log(site_id, created_at DESC);

ALTER TABLE public.phase_promotion_readiness_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY phase_promotion_readiness_log_service_all
  ON public.phase_promotion_readiness_log
  FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

CREATE RULE phase_promotion_readiness_log_no_update AS
  ON UPDATE TO public.phase_promotion_readiness_log DO INSTEAD NOTHING;

CREATE RULE phase_promotion_readiness_log_no_delete AS
  ON DELETE TO public.phase_promotion_readiness_log DO INSTEAD NOTHING;

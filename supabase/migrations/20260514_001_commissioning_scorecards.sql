CREATE TABLE IF NOT EXISTS public.commissioning_scorecards (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id TEXT NOT NULL,
  checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  all_gates_passed BOOLEAN NOT NULL,
  scorecard_data JSONB
);

CREATE INDEX IF NOT EXISTS idx_commissioning_scorecards_site_date
  ON public.commissioning_scorecards (site_id, checked_at DESC);

COMMENT ON TABLE public.commissioning_scorecards IS 'Persistent commissioning scorecard history for consecutive-day tracking and audit';
COMMENT ON COLUMN public.commissioning_scorecards.site_id IS 'Site code or UUID (e.g. S002 or site-002)';
COMMENT ON COLUMN public.commissioning_scorecards.checked_at IS 'When the scorecard was run';
COMMENT ON COLUMN public.commissioning_scorecards.all_gates_passed IS 'Whether all 8 commissioning gates passed';
COMMENT ON COLUMN public.commissioning_scorecards.scorecard_data IS 'Full scorecard JSON for audit trail';

ALTER TABLE public.commissioning_scorecards ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access on commissioning_scorecards"
  ON public.commissioning_scorecards
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

GRANT ALL ON public.commissioning_scorecards TO service_role;
GRANT SELECT ON public.commissioning_scorecards TO authenticated, anon;

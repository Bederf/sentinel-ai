CREATE TABLE IF NOT EXISTS public.comfort_violations (
  id bigserial PRIMARY KEY,
  site_id text NOT NULL,
  equipment_id text NOT NULL,
  event_id text,
  severity text,
  description text,
  trend text,
  duration_minutes double precision,
  threshold_value double precision,
  actual_value double precision,
  violation_timestamp timestamptz NOT NULL,
  recorded_at timestamptz NOT NULL,
  signals jsonb NOT NULL DEFAULT '[]'::jsonb,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_comfort_violations_site ON public.comfort_violations(site_id);
CREATE INDEX IF NOT EXISTS idx_comfort_violations_ts ON public.comfort_violations(violation_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_comfort_violations_site_equip ON public.comfort_violations(site_id, equipment_id);

COMMENT ON TABLE public.comfort_violations IS 'Comfort zone violation events detected by EventIntelligenceService.';

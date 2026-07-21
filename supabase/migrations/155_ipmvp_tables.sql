-- IPMVP Measurement & Verification data tables
-- These store data pulled from the bridge's IPMVP endpoints for engineering analysis.

CREATE TABLE IF NOT EXISTS public.ipmvp_energy (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id TEXT NOT NULL,
  timestamp TIMESTAMPTZ NOT NULL,
  import_kwh NUMERIC,
  export_kwh NUMERIC,
  hvac_kwh NUMERIC,
  lighting_kwh NUMERIC,
  solar_generation_kwh NUMERIC,
  source TEXT DEFAULT 'bridge_ipmvp',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ipmvp_energy_site_ts
  ON public.ipmvp_energy (site_id, timestamp DESC);

ALTER TABLE public.ipmvp_energy DROP CONSTRAINT IF EXISTS ipmvp_energy_unique;
ALTER TABLE public.ipmvp_energy ADD CONSTRAINT ipmvp_energy_unique
  UNIQUE (site_id, timestamp);

COMMENT ON TABLE public.ipmvp_energy IS '15-min building energy from bridge IPMVP endpoint';

CREATE TABLE IF NOT EXISTS public.ipmvp_oat (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id TEXT NOT NULL,
  timestamp TIMESTAMPTZ NOT NULL,
  oat_celsius NUMERIC,
  source TEXT DEFAULT 'bridge_ipmvp',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ipmvp_oat_site_ts
  ON public.ipmvp_oat (site_id, timestamp DESC);

ALTER TABLE public.ipmvp_oat DROP CONSTRAINT IF EXISTS ipmvp_oat_unique;
ALTER TABLE public.ipmvp_oat ADD CONSTRAINT ipmvp_oat_unique
  UNIQUE (site_id, timestamp);

COMMENT ON TABLE public.ipmvp_oat IS 'Outdoor air temperature from bridge IPMVP endpoint';

CREATE TABLE IF NOT EXISTS public.ipmvp_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  timestamp TIMESTAMPTZ NOT NULL,
  event_type TEXT NOT NULL,
  target_id TEXT,
  value NUMERIC,
  unit TEXT,
  reason TEXT,
  source TEXT DEFAULT 'bridge_ipmvp',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ipmvp_events_site_ts
  ON public.ipmvp_events (site_id, timestamp DESC);

ALTER TABLE public.ipmvp_events DROP CONSTRAINT IF EXISTS ipmvp_events_unique;
ALTER TABLE public.ipmvp_events ADD CONSTRAINT ipmvp_events_unique
  UNIQUE (site_id, event_id);

COMMENT ON TABLE public.ipmvp_events IS 'Equipment events (setpoint changes, BESS dispatch, etc.) from bridge';

CREATE TABLE IF NOT EXISTS public.ipmvp_occupancy (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id TEXT NOT NULL,
  schedule_data JSONB NOT NULL DEFAULT '{}',
  source TEXT DEFAULT 'bridge_ipmvp',
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ipmvp_occupancy_site
  ON public.ipmvp_occupancy (site_id);

COMMENT ON TABLE public.ipmvp_occupancy IS 'Occupancy schedule and public holidays from bridge';

CREATE TABLE IF NOT EXISTS public.ipmvp_tariff (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id TEXT NOT NULL,
  tariff_data JSONB NOT NULL DEFAULT '{}',
  source TEXT DEFAULT 'bridge_ipmvp',
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ipmvp_tariff_site
  ON public.ipmvp_tariff (site_id);

COMMENT ON TABLE public.ipmvp_tariff IS 'Tariff structure from bridge';

-- RLS
ALTER TABLE public.ipmvp_energy ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ipmvp_oat ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ipmvp_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ipmvp_occupancy ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ipmvp_tariff ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "Service role full access on ipmvp_energy"
    ON public.ipmvp_energy FOR ALL TO service_role USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE POLICY "Service role full access on ipmvp_oat"
    ON public.ipmvp_oat FOR ALL TO service_role USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE POLICY "Service role full access on ipmvp_events"
    ON public.ipmvp_events FOR ALL TO service_role USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE POLICY "Service role full access on ipmvp_occupancy"
    ON public.ipmvp_occupancy FOR ALL TO service_role USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE POLICY "Service role full access on ipmvp_tariff"
    ON public.ipmvp_tariff FOR ALL TO service_role USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

GRANT ALL ON public.ipmvp_energy TO service_role;
GRANT ALL ON public.ipmvp_oat TO service_role;
GRANT ALL ON public.ipmvp_events TO service_role;
GRANT ALL ON public.ipmvp_occupancy TO service_role;
GRANT ALL ON public.ipmvp_tariff TO service_role;
GRANT SELECT ON public.ipmvp_energy TO authenticated, anon;
GRANT SELECT ON public.ipmvp_oat TO authenticated, anon;
GRANT SELECT ON public.ipmvp_events TO authenticated, anon;
GRANT SELECT ON public.ipmvp_occupancy TO authenticated, anon;
GRANT SELECT ON public.ipmvp_tariff TO authenticated, anon;

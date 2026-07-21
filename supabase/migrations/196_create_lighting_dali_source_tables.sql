CREATE TABLE IF NOT EXISTS public.lighting_sources (
  site_id text NOT NULL,
  source text NOT NULL DEFAULT 'json',
  source_config jsonb NOT NULL DEFAULT '{}'::jsonb,
  description text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (site_id, source)
);

COMMENT ON TABLE public.lighting_sources IS 'Per-site lighting data source configuration (json, mqtt, bacnet).';

--

CREATE TABLE IF NOT EXISTS public.dali_sources (
  site_id text NOT NULL,
  source text NOT NULL DEFAULT 'json',
  source_config jsonb NOT NULL DEFAULT '{}'::jsonb,
  description text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (site_id, source)
);

COMMENT ON TABLE public.dali_sources IS 'Per-site DALI data source configuration (json, mqtt, bacnet).';

CREATE TABLE IF NOT EXISTS public.block_bookings (
  id uuid PRIMARY KEY,
  site_id text NOT NULL,
  organiser_email text NOT NULL DEFAULT '',
  organiser_name text NOT NULL DEFAULT '',
  room_id text NOT NULL DEFAULT '',
  room_name text NOT NULL DEFAULT '',
  booking_date date,
  start_time timestamptz,
  end_time timestamptz,
  raw_email_hash text NOT NULL DEFAULT '',
  ingested_at timestamptz,
  flagged boolean NOT NULL DEFAULT false,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_block_bookings_site ON public.block_bookings(site_id);
CREATE INDEX IF NOT EXISTS idx_block_bookings_date ON public.block_bookings(booking_date);

COMMENT ON TABLE public.block_bookings IS 'Block booking records from email ingestion.';

--

CREATE TABLE IF NOT EXISTS public.building_maps (
  id uuid PRIMARY KEY,
  name text NOT NULL DEFAULT '',
  outlook_location_string text NOT NULL DEFAULT '',
  site_id text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_building_maps_site ON public.building_maps(site_id);

COMMENT ON TABLE public.building_maps IS 'Building name/location mappings for visit routing.';

--

CREATE TABLE IF NOT EXISTS public.optimization_scenarios (
  scenario_id text PRIMARY KEY,
  site_id text NOT NULL,
  site_name text NOT NULL DEFAULT '',
  description text NOT NULL DEFAULT '',
  scenario_data jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_optimization_scenarios_site ON public.optimization_scenarios(site_id);

COMMENT ON TABLE public.optimization_scenarios IS 'Predefined optimization scenarios for demo and analysis.';

--

CREATE TABLE IF NOT EXISTS public.optimization_profiles (
  profile_id text PRIMARY KEY,
  name text NOT NULL DEFAULT '',
  description text NOT NULL DEFAULT '',
  profile_data jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.optimization_profiles IS 'Optimization profiles with weighted objectives and thresholds.';

--

CREATE TABLE IF NOT EXISTS public.remote_ops_config (
  id bigserial PRIMARY KEY,
  config_key text NOT NULL UNIQUE,
  config_data jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.remote_ops_config IS 'Remote operations config: authorization matrix, safety guardrails, profiled users.';

--

CREATE TABLE IF NOT EXISTS public.site_document_storage_policies (
  id bigserial PRIMARY KEY,
  site_id text NOT NULL UNIQUE,
  policy_data jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.site_document_storage_policies IS 'Per-site document storage policy (local, site_network, s3, etc.).';

--

CREATE TABLE IF NOT EXISTS public.block_booking_sites (
  site_id text PRIMARY KEY,
  building_name text NOT NULL DEFAULT '',
  enabled boolean NOT NULL DEFAULT true,
  min_rooms_for_alert int NOT NULL DEFAULT 3,
  concierge_email text NOT NULL DEFAULT '',
  concierge_whatsapp text NOT NULL DEFAULT '',
  concierge_name text NOT NULL DEFAULT '',
  config_data jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.block_booking_sites IS 'Per-site block booking concierge configuration.';

CREATE TABLE IF NOT EXISTS public.site_mode_policies (
  id bigserial PRIMARY KEY,
  site_id text NOT NULL UNIQUE,
  policy_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  state_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.site_mode_policies IS 'Per-site mode policies and dry-run state (migrated from JSON files).';

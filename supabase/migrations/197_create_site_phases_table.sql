CREATE TABLE IF NOT EXISTS public.site_phases (
  site_id text PRIMARY KEY,
  current_phase text NOT NULL DEFAULT 'monitor'
    CHECK (current_phase IN ('monitor', 'advisory', 'supervised', 'autonomous', 'retired')),
  processing_enabled boolean NOT NULL DEFAULT true,
  changed_by text NOT NULL DEFAULT 'system',
  changed_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_site_phases_phase ON public.site_phases(current_phase);

COMMENT ON TABLE public.site_phases IS 'Per-site onboarding phase and processing state (migrated from JSON).';

CREATE TABLE IF NOT EXISTS public.site_phase_transitions (
  id bigserial PRIMARY KEY,
  site_id text NOT NULL REFERENCES public.site_phases(site_id) ON DELETE CASCADE,
  from_phase text NOT NULL,
  to_phase text NOT NULL,
  changed_by text NOT NULL DEFAULT 'system',
  reason text,
  transitioned_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_site_phase_transitions_site ON public.site_phase_transitions(site_id, transitioned_at DESC);

COMMENT ON TABLE public.site_phase_transitions IS 'History of site onboarding phase transitions.';

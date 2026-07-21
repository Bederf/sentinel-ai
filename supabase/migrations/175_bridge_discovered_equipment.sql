CREATE TABLE IF NOT EXISTS public.bridge_discovered_equipment (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  site_id text NOT NULL,
  bridge_code text NOT NULL,
  canonical_code text NOT NULL,
  equipment_type text,
  derived_zone_id text,
  status text NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'onboarded', 'dismissed')),
  reason text NOT NULL DEFAULT 'new_bridge_equipment',
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  seen_count integer NOT NULL DEFAULT 1,
  dismissed_at timestamptz,
  dismissed_by text,
  onboarded_at timestamptz,
  onboarded_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (site_id, canonical_code)
);

CREATE INDEX IF NOT EXISTS idx_bridge_discovered_equipment_site_status_seen
  ON public.bridge_discovered_equipment(site_id, status, last_seen_at DESC);

CREATE INDEX IF NOT EXISTS idx_bridge_discovered_equipment_site_zone_seen
  ON public.bridge_discovered_equipment(site_id, derived_zone_id, last_seen_at DESC);

COMMENT ON TABLE public.bridge_discovered_equipment IS
  'Bridge-discovered equipment that is not yet part of the Supabase-owned site inventory. Discovery does not create zones or active equipment.';

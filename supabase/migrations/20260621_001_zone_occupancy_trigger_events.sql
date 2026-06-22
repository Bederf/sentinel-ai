-- Zone occupancy trigger event store.
-- Inert event surface for future ReflexReconciliationService.

CREATE TABLE IF NOT EXISTS public.zone_occupancy_trigger_events (
    id TEXT PRIMARY KEY,
    site_id TEXT NOT NULL,
    zone_id TEXT NOT NULL,
    zone_group TEXT,
    event_type TEXT NOT NULL DEFAULT 'zone_occupancy_change',
    previous_occupied BOOLEAN NOT NULL,
    current_occupied BOOLEAN NOT NULL,
    previous_occupancy DOUBLE PRECISION,
    current_occupancy DOUBLE PRECISION,
    source TEXT,
    observed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_zone_occupancy_trigger_site_zone_observed
    ON public.zone_occupancy_trigger_events(site_id, zone_id, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_zone_occupancy_trigger_site_observed
    ON public.zone_occupancy_trigger_events(site_id, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_zone_occupancy_trigger_event_type
    ON public.zone_occupancy_trigger_events(event_type, observed_at DESC);

COMMENT ON TABLE public.zone_occupancy_trigger_events IS
    'Read-only zone occupancy transition events. Used as the future ReflexReconciliationService trigger surface.';

-- Migration: 20260413_001_concierge_signal_table.sql
-- Create concierge signal table for ghost booking, complaint, and space-optimisation signals.
-- Phase 161-04: Concierge Intelligence Dashboard

BEGIN;

CREATE TABLE IF NOT EXISTS public.signal (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_type     TEXT        NOT NULL,
    source_module   TEXT        NOT NULL DEFAULT '',
    severity        TEXT        NOT NULL DEFAULT 'low',
    confidence      NUMERIC(3,2) NOT NULL DEFAULT 0.0,
    resolution_state TEXT       NOT NULL DEFAULT 'active',
    location_ref    TEXT        NOT NULL DEFAULT '',
    summary         TEXT        NOT NULL DEFAULT '',
    metadata        JSONB       NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    site_id         TEXT        NOT NULL DEFAULT ''
);

-- Index for querying active signals by site and room
CREATE INDEX IF NOT EXISTS idx_signal_site_resolution
    ON public.signal (site_id, resolution_state);

-- Index for room-level signal queries
CREATE INDEX IF NOT EXISTS idx_signal_metadata_room_id
    ON public.signal ((metadata->>'room_id'));

-- Enable RLS
ALTER TABLE public.signal ENABLE ROW LEVEL SECURITY;

-- Allow anon/app role to read signals (dashboard reads)
CREATE POLICY "signals_read" ON public.signal
    FOR SELECT USING (true);

-- Allow authenticated role to update signals (resolve endpoint)
CREATE POLICY "signals_resolve" ON public.signal
    FOR UPDATE USING (auth.role() IN ('authenticated', 'service_role'));

COMMIT;

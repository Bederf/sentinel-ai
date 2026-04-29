-- Phase 186 Wave 3 / Option B: FCU State Tracker Persistence
-- Persists per-zone FCU state to Supabase so patterns survive restarts.
-- Schema: one row per (site_id, zone_id) — latest state only (upsert).

BEGIN;

CREATE TABLE IF NOT EXISTS fcu_zone_state (
    id BIGSERIAL PRIMARY KEY,
    site_id TEXT NOT NULL DEFAULT 'S002',
    zone_id TEXT NOT NULL,
    -- Core sensor fields
    occupancy_pct FLOAT NOT NULL DEFAULT 0,
    room_temp_c FLOAT,
    setpoint_c FLOAT,
    -- Timestamps
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    occupancy_end_time TIMESTAMPTZ,
    prev_room_temp_c FLOAT,
    prev_timestamp TIMESTAMPTZ,
    -- Inferred FCU state
    fcu_inferred_running BOOLEAN NOT NULL DEFAULT FALSE,
    -- Source tracking
    occupancy_source TEXT NOT NULL DEFAULT 'bridge',
    -- Row metadata
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_zone_state UNIQUE (site_id, zone_id)
);

CREATE INDEX IF NOT EXISTS idx_fcu_zone_state_site_zone
    ON fcu_zone_state (site_id, zone_id);

COMMENT ON TABLE fcu_zone_state IS 'Latest FCU/occupancy state per zone — written by FCUStateTracker SupabaseBackend, read on startup for cross-session continuity.';

COMMIT;

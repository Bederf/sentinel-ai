-- Phase 236-02: pinned-signal integrity detection
-- Durable per-point verdicts: is this (site, equipment, point) currently
-- pinned (plausible-but-frozen)? Consumed by the detector's finding dedup
-- and by downstream inference availability checks (FCU running inference
-- treats pinned inputs as unavailable — site-agnostic, verdict-driven).

CREATE TABLE IF NOT EXISTS pinned_signal_state (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id text NOT NULL,
    equipment_id text NOT NULL,          -- canonical equipment code (e.g. S002-AHU-201)
    point_name text NOT NULL,
    pinned boolean NOT NULL DEFAULT false,
    window_kind text,                    -- 'structural_7d' | 'frozen_24h' (null when not pinned)
    pinned_value numeric,                -- representative frozen value
    distinct_values integer,
    relative_range numeric,
    hours_evaluated integer,
    pinned_since timestamptz,
    last_evaluated_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pinned_signal_state_point_unique UNIQUE (site_id, equipment_id, point_name)
);

-- Hot path: downstream consumers fetch the currently-pinned set per site.
CREATE INDEX IF NOT EXISTS idx_pinned_signal_state_site_pinned
    ON pinned_signal_state (site_id, equipment_id)
    WHERE pinned;

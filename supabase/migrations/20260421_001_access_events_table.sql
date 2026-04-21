-- Access Events table for LD2410C/mmWave radar occupancy tracking
-- Feeds SecurityOccupancyService for building-wide occupancy aggregation

CREATE TABLE IF NOT EXISTS access_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id TEXT NOT NULL,
    zone_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('entry', 'exit', 'presence')),
    occupancy_count INTEGER DEFAULT 0,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_access_events_site_zone
    ON access_events (site_id, zone_id, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_access_events_node_recorded
    ON access_events (node_id, recorded_at DESC);

COMMENT ON TABLE access_events IS 'LD2410C/mmWave radar occupancy events per zone/node';

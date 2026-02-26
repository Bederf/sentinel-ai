-- =====================================================
-- Migration 057: Zone Ingestion System
-- Building-level zone configuration for multi-building support
-- Enables desk-based positioning with zone centroids
-- =====================================================

-- Zones table: Stores building-level zone configuration
-- Each building can have a different zone structure
CREATE TABLE IF NOT EXISTS zones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
    zone_id TEXT NOT NULL,                    -- e.g., "Zone-L1-A"
    zone_name TEXT NOT NULL,                  -- e.g., "Level 1 Zone A"
    floor TEXT NOT NULL,                      -- e.g., "L0", "L1", "L2", "B1", "G", "R"
    zone_letter TEXT,                         -- e.g., "A", "B", "C" (for zones A-E per floor)
    zone_type TEXT NOT NULL,                  -- e.g., "open_office", "meeting_room", "plant_room"
    typical_occupancy INTEGER,                -- Average number of occupants
    area_sqm DECIMAL(8,2),                    -- Zone area in square meters

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT unique_building_zone UNIQUE(building_id, zone_id),
    CONSTRAINT valid_zone_type CHECK (zone_type IN (
        'open_office', 'meeting_room', 'plant_room', 'storage',
        'stairwell', 'corridor', 'lobby', 'restroom', 'cafeteria',
        'server_room', 'comms_room', 'mechanical', 'electrical'
    ))
);

-- Extend desks table with zone_id reference and z_coord for 3D positioning
-- Add if not already present
ALTER TABLE desks ADD COLUMN IF NOT EXISTS zone_id TEXT;
ALTER TABLE desks ADD COLUMN IF NOT EXISTS z_coord DECIMAL(6,2);

-- Desk context enum (more detailed than before)
-- Tracks specific desk context for positioning and comfort analysis
-- Note: Check constraint validation happens at application level

-- Add context column if it doesn't exist
ALTER TABLE desks ADD COLUMN IF NOT EXISTS context TEXT DEFAULT 'open_plan';

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_zones_building ON zones(building_id);
CREATE INDEX IF NOT EXISTS idx_zones_zone_id ON zones(zone_id);
CREATE INDEX IF NOT EXISTS idx_desks_zone_id ON desks(zone_id);

-- Enable RLS for zones table
ALTER TABLE zones ENABLE ROW LEVEL SECURITY;

-- RLS Policies: Allow all authenticated users (can refine later)
DROP POLICY IF EXISTS "Enable read for authenticated users" ON zones;
DROP POLICY IF EXISTS "Enable insert for authenticated users" ON zones;
DROP POLICY IF EXISTS "Enable update for authenticated users" ON zones;
DROP POLICY IF EXISTS "Enable delete for authenticated users" ON zones;

CREATE POLICY "Enable read for authenticated users" ON zones
    FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "Enable insert for authenticated users" ON zones
    FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "Enable update for authenticated users" ON zones
    FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "Enable delete for authenticated users" ON zones
    FOR DELETE
    USING (auth.role() = 'authenticated');

-- Trigger for updated_at timestamp on zones table
CREATE OR REPLACE FUNCTION update_zones_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_zones_updated_at
    BEFORE UPDATE ON zones
    FOR EACH ROW
    EXECUTE FUNCTION update_zones_updated_at();

-- Trigger to update desks.updated_at when modified
-- (should already exist from migration 014, ensure it doesn't duplicate)
DROP TRIGGER IF EXISTS trigger_desks_updated_at ON desks;
CREATE TRIGGER trigger_desks_updated_at
    BEFORE UPDATE ON desks
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Comments for documentation
COMMENT ON TABLE zones IS 'Building-level zone configuration for multi-building support. Each building can have unique zone structures.';
COMMENT ON COLUMN zones.zone_id IS 'Unique zone identifier e.g., Zone-L1-A. Must be unique within building.';
COMMENT ON COLUMN zones.zone_letter IS 'Zone letter (A-E) for standard layouts or numeric suffix for plant rooms';
COMMENT ON COLUMN zones.zone_type IS 'Type of space (open_office, meeting_room, plant_room, etc.)';
COMMENT ON COLUMN desks.zone_id IS 'Building-level zone reference (e.g., Zone-L1-A). Complements hvac_zone_id.';
COMMENT ON COLUMN desks.z_coord IS 'Z coordinate (depth) for 3D positioning. Y-coord is floor height, X/Z are horizontal plane.';
COMMENT ON COLUMN desks.context IS 'Specific context for desk positioning: near_diffuser, near_window, near_printer, corner, or open_plan';

-- View: Zone Centroids (calculated from desk positions)
-- This view calculates the centroid of each zone from its desk positions
-- Used by Digital Twin for accurate equipment positioning
DROP VIEW IF EXISTS zone_centroids CASCADE;

CREATE VIEW zone_centroids AS
SELECT
    z.building_id,
    z.zone_id,
    z.floor,
    ROUND(CAST(AVG(d.x_coord) AS NUMERIC), 2) AS centroid_x,
    ROUND(CAST(AVG(d.z_coord) AS NUMERIC), 2) AS centroid_z,
    COUNT(d.id) AS desk_count,
    ROUND(CAST(AVG(d.y_coord) AS NUMERIC), 2) AS avg_y
FROM zones z
LEFT JOIN desks d ON d.zone_id = z.zone_id AND d.building_id = z.building_id
GROUP BY z.building_id, z.zone_id, z.floor;

COMMENT ON VIEW zone_centroids IS 'Calculates zone centroids from desk positions for accurate equipment positioning in 3D visualization';

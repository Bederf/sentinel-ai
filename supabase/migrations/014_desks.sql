-- =====================================================
-- Migration 014: Desks Schema
-- Workspace positions with comfort context
-- Links to buildings, HVAC zones, and lighting
-- Note: Desks are NOT counted as "assets" - they're positions
-- =====================================================

-- Desks table
CREATE TABLE desks (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  desk_id TEXT UNIQUE NOT NULL,                    -- e.g., 'L12-D001'
  building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
  hvac_zone_id UUID REFERENCES hvac_zones(id) ON DELETE SET NULL,
  floor TEXT NOT NULL,                             -- 'Level 12', 'L12', etc.

  -- Location within floor
  x_coord DECIMAL(6,2),                            -- X coordinate on floor plan
  y_coord DECIMAL(6,2),                            -- Y coordinate on floor plan
  orientation TEXT CHECK (orientation IN ('N', 'S', 'E', 'W', 'NE', 'NW', 'SE', 'SW')),

  -- Comfort context (for complaint diagnosis)
  near_window BOOLEAN DEFAULT FALSE,               -- Window proximity affects thermal comfort
  window_facing TEXT CHECK (window_facing IN ('N', 'S', 'E', 'W')),
  near_diffuser BOOLEAN DEFAULT FALSE,             -- Near HVAC diffuser
  diffuser_id TEXT,                                -- Specific diffuser ID if nearby
  near_printer BOOLEAN DEFAULT FALSE,              -- Heat source
  near_kitchen BOOLEAN DEFAULT FALSE,              -- Heat/odor source
  near_server_room BOOLEAN DEFAULT FALSE,          -- Heat source

  -- Organizational
  department TEXT,
  cost_center TEXT,
  assigned_to TEXT,                                -- Employee ID or name (optional)

  -- Lighting references (for comfort diagnosis)
  dali_zone TEXT,                                  -- DALI lighting zone
  dali_controller TEXT,                            -- Primary DALI controller ID
  luminaire_ids JSONB DEFAULT '[]',                -- Array of luminaire IDs above desk
  sensor_ids JSONB DEFAULT '[]',                   -- PIR/daylight sensor IDs

  -- Sensor reference (primary PIR sensor for this desk)
  sensor_id TEXT,

  -- Status
  occupied BOOLEAN DEFAULT FALSE,
  last_occupancy_change TIMESTAMPTZ,

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_desks_building ON desks(building_id);
CREATE INDEX idx_desks_floor ON desks(floor);
CREATE INDEX idx_desks_zone ON desks(hvac_zone_id);
CREATE INDEX idx_desks_dali_zone ON desks(dali_zone);
CREATE INDEX idx_desks_occupied ON desks(occupied) WHERE occupied = TRUE;
CREATE INDEX idx_desks_department ON desks(department);

-- Trigger for updated_at
CREATE TRIGGER update_desks_updated_at BEFORE UPDATE ON desks
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Comments for documentation
COMMENT ON TABLE desks IS 'Workspace positions with comfort context for complaint diagnosis. NOT counted as assets.';
COMMENT ON COLUMN desks.near_window IS 'Window proximity affects thermal comfort - relevant for hot/cold complaints';
COMMENT ON COLUMN desks.near_diffuser IS 'HVAC diffuser proximity - may cause draft complaints';
COMMENT ON COLUMN desks.diffuser_id IS 'Specific diffuser ID for targeted HVAC adjustments';
COMMENT ON COLUMN desks.luminaire_ids IS 'JSON array of luminaire IDs above desk for lighting analysis';
COMMENT ON COLUMN desks.sensor_ids IS 'JSON array of PIR/daylight sensor IDs for occupancy tracking';

-- Phase 4: Zone Display Mappings for Occupancy Simulation
-- Maps backend zones to frontend display zones with coordinates and occupancy limits

CREATE TABLE IF NOT EXISTS zone_display_mappings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id TEXT NOT NULL,
  zone_id TEXT NOT NULL,
  display_zone_id TEXT NOT NULL,
  display_zone_name TEXT NOT NULL,
  floor INTEGER NOT NULL,

  -- Coordinates in simulation space (for rendering 2D/3D positions)
  coordinates JSONB NOT NULL, -- {x, y, w, h} for 2D zones

  -- Occupancy limits
  max_occupancy INTEGER NOT NULL DEFAULT 10,

  -- Zone classification for behavior rules
  zone_type TEXT NOT NULL, -- 'entry', 'office', 'meeting', 'common', 'utility', 'corridor'

  -- Metadata
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),

  -- Constraints
  CONSTRAINT unique_site_display_zone UNIQUE(site_id, display_zone_id),
  CONSTRAINT valid_floor CHECK(floor >= 0 AND floor <= 4),
  CONSTRAINT valid_occupancy CHECK(max_occupancy > 0),
  CONSTRAINT valid_zone_type CHECK(zone_type IN ('entry', 'office', 'meeting', 'common', 'utility', 'corridor'))
);

-- Create index for fast lookups
CREATE INDEX idx_zone_display_mappings_site ON zone_display_mappings(site_id);
CREATE INDEX idx_zone_display_mappings_floor ON zone_display_mappings(site_id, floor);
CREATE INDEX idx_zone_display_mappings_type ON zone_display_mappings(zone_type);

-- Seed with site-002 zones (from DigitalTwin.tsx)
-- Floor 0 (Ground): Reception, Workspace-A, Common, Utility
INSERT INTO zone_display_mappings
  (site_id, zone_id, display_zone_id, display_zone_name, floor, coordinates, max_occupancy, zone_type)
VALUES
  ('site-002', 'S002-ZONE-RCP', 'zone-1', 'Reception', 0, '{"x": -2, "y": -2, "w": 4, "h": 4}'::jsonb, 6, 'entry'),
  ('site-002', 'S002-ZONE-WSP', 'zone-2', 'Workspace-A', 0, '{"x": 3, "y": 3, "w": 4, "h": 4}'::jsonb, 20, 'office'),
  ('site-002', 'S002-ZONE-COM', 'zone-4', 'Common', 0, '{"x": -2, "y": -7, "w": 4, "h": 4}'::jsonb, 8, 'common'),
  ('site-002', 'S002-ZONE-UTL', 'zone-5', 'Utility', 0, '{"x": -7, "y": 3, "w": 4, "h": 4}'::jsonb, 2, 'utility'),

  -- Floor 1 (Level 1): Meeting-1, Meeting-2, Kitchen
  ('site-002', 'S002-ZONE-MTG1', 'zone-3', 'Meeting-1', 1, '{"x": -7, "y": -7, "w": 4, "h": 4}'::jsonb, 10, 'meeting'),
  ('site-002', 'S002-ZONE-MTG2', 'zone-6', 'Meeting-2', 1, '{"x": -2, "y": -7, "w": 4, "h": 4}'::jsonb, 8, 'meeting'),
  ('site-002', 'S002-ZONE-KIT', 'zone-7', 'Kitchen', 1, '{"x": 3, "y": -7, "w": 4, "h": 4}'::jsonb, 6, 'common')
ON CONFLICT (site_id, display_zone_id) DO UPDATE SET
  updated_at = NOW();

-- Grant scenario zones (example - to be populated with actual zone data later)
-- This ensures the table is ready for occupancy queries even if zones aren't fully defined

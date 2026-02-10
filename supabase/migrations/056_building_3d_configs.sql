-- Building 3D Configuration Table
-- Stores building structure (floors) and equipment placement data for 3D visualization
-- Linked 1:1 to buildings table

CREATE TABLE building_3d_configs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  building_id UUID NOT NULL UNIQUE REFERENCES buildings(id) ON DELETE CASCADE,
  site_id TEXT NOT NULL,
  name TEXT NOT NULL,
  code TEXT,
  
  -- Floor definitions: array of {level, height, width, depth, label}
  -- Example: [{level: "G", height: 4.0, width: 50, depth: 40, label: "Ground Floor"}]
  floors JSONB NOT NULL,
  
  -- Equipment positions: array of {equipment_id, floor, x, y}
  -- x, y are in meters relative to floor origin (bottom-left corner)
  equipment_positions JSONB NOT NULL DEFAULT '[]'::jsonb,
  
  -- Zone definitions: auto-generated from equipment positions
  -- Array of {zone_id, floor, equipment_ids, type}
  zones JSONB NOT NULL DEFAULT '[]'::jsonb,
  
  -- Metadata
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  created_by TEXT,
  updated_by TEXT,
  
  CONSTRAINT valid_floors CHECK (jsonb_array_length(floors) > 0),
  CONSTRAINT valid_building_name CHECK (name != '')
);

-- Indexes for query performance
CREATE INDEX idx_building_3d_configs_building_id ON building_3d_configs(building_id);
CREATE INDEX idx_building_3d_configs_site_id ON building_3d_configs(site_id);

-- Enable RLS (Row Level Security)
ALTER TABLE building_3d_configs ENABLE ROW LEVEL SECURITY;

-- Create RLS policies (allow all for authenticated users for now)
CREATE POLICY "Enable read for authenticated users" ON building_3d_configs
  FOR SELECT
  USING (auth.role() = 'authenticated');

CREATE POLICY "Enable insert for authenticated users" ON building_3d_configs
  FOR INSERT
  WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "Enable update for authenticated users" ON building_3d_configs
  FOR UPDATE
  USING (auth.role() = 'authenticated')
  WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "Enable delete for authenticated users" ON building_3d_configs
  FOR DELETE
  USING (auth.role() = 'authenticated');

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_building_3d_configs_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_building_3d_configs_timestamp
  BEFORE UPDATE ON building_3d_configs
  FOR EACH ROW
  EXECUTE FUNCTION update_building_3d_configs_timestamp();

-- Add comment for documentation
COMMENT ON TABLE building_3d_configs IS 'Stores 3D building structure and equipment placement data for spatial visualization';
COMMENT ON COLUMN building_3d_configs.floors IS 'Array of floor definitions with dimensions and labels';
COMMENT ON COLUMN building_3d_configs.equipment_positions IS 'Equipment placement coordinates (x, y in meters) on each floor';
COMMENT ON COLUMN building_3d_configs.zones IS 'Auto-generated zone definitions inferred from equipment positions';

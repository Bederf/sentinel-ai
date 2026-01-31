-- =====================================================
-- Migration 013: HVAC Zones Schema
-- Thermal zones for comfort management and control
-- Links to buildings, contains FCU/VAV/AHU references
-- =====================================================

-- HVAC Zones table
CREATE TABLE hvac_zones (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  zone_id TEXT UNIQUE NOT NULL,                    -- e.g., 'Zone-L12-N'
  zone_name TEXT NOT NULL,                         -- e.g., 'Level 12 North'
  building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
  floor TEXT NOT NULL,                             -- L10, L11, L12, etc.

  -- HVAC equipment references
  fcu_id TEXT,                                     -- Fan Coil Unit ID
  vav_id TEXT,                                     -- Variable Air Volume damper ID
  ahu_id TEXT,                                     -- Air Handling Unit ID

  -- Sensors
  temp_sensor TEXT,                                -- Temperature sensor point name
  co2_sensor TEXT,                                 -- CO2 sensor point name
  humidity_sensor TEXT,                            -- Humidity sensor point name

  -- Zone characteristics
  typical_occupancy INTEGER,                       -- Expected number of occupants
  area_sqm INTEGER,                                -- Zone area in square meters
  priority TEXT DEFAULT 'P3' CHECK (priority IN ('P1', 'P2', 'P3', 'P4', 'P5')),

  -- Setpoints and current state
  setpoint DECIMAL(4,1) DEFAULT 22.0,             -- Target temperature
  heating_setpoint DECIMAL(4,1),                   -- Heating mode setpoint
  cooling_setpoint DECIMAL(4,1),                   -- Cooling mode setpoint
  current_temp DECIMAL(4,1),                       -- Current zone temperature
  current_humidity DECIMAL(4,1),                   -- Current humidity %
  current_co2 INTEGER,                             -- Current CO2 ppm

  -- Status
  status TEXT DEFAULT 'idle' CHECK (status IN ('running', 'idle', 'heating', 'cooling', 'fault', 'offline')),
  mode TEXT DEFAULT 'auto' CHECK (mode IN ('auto', 'heat', 'cool', 'off')),
  fan_speed TEXT DEFAULT 'auto' CHECK (fan_speed IN ('auto', 'low', 'medium', 'high', 'off')),

  -- Timestamps
  last_updated TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_hvac_zones_building ON hvac_zones(building_id);
CREATE INDEX idx_hvac_zones_floor ON hvac_zones(floor);
CREATE INDEX idx_hvac_zones_status ON hvac_zones(status);
CREATE INDEX idx_hvac_zones_priority ON hvac_zones(priority);

-- Trigger for updated_at
CREATE TRIGGER update_hvac_zones_updated_at BEFORE UPDATE ON hvac_zones
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- HVAC Zone History (time-series for analytics)
-- Note: In production, consider TimescaleDB hypertable conversion
CREATE TABLE hvac_zone_history (
  time TIMESTAMPTZ NOT NULL,
  zone_id TEXT NOT NULL,
  building_id UUID REFERENCES buildings(id) ON DELETE CASCADE,
  temp DECIMAL(4,1),
  humidity DECIMAL(4,1),
  co2 INTEGER,
  setpoint DECIMAL(4,1),
  status TEXT,
  occupancy INTEGER,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_hvac_zone_history_zone_time ON hvac_zone_history(zone_id, time DESC);
CREATE INDEX idx_hvac_zone_history_building_time ON hvac_zone_history(building_id, time DESC);

-- Comments for documentation
COMMENT ON TABLE hvac_zones IS 'HVAC thermal zones with comfort management parameters';
COMMENT ON TABLE hvac_zone_history IS 'Time-series zone condition data (consider TimescaleDB in production)';
COMMENT ON COLUMN hvac_zones.priority IS 'Load shedding priority: P1 (critical) to P5 (lowest)';
COMMENT ON COLUMN hvac_zones.fcu_id IS 'Fan Coil Unit device ID for zone control';
COMMENT ON COLUMN hvac_zones.vav_id IS 'Variable Air Volume damper ID';
COMMENT ON COLUMN hvac_zones.ahu_id IS 'Air Handling Unit serving this zone';

-- =====================================================
-- Migration 011: DALI-2 Lighting Schema
-- Tridonic Scenecom evo DA2 integration for FNB Fairlands
-- 57 controllers, 1,315 MSensor G3 PIR sensors, 619 luminaires
-- =====================================================

-- DALI Controllers (Scenecom evo DA2)
CREATE TABLE dali_controllers (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  controller_id TEXT UNIQUE NOT NULL,            -- e.g., 'DALI-L12-01'
  name TEXT NOT NULL,
  location TEXT NOT NULL,
  ip_address INET,
  bacnet_device_id INTEGER,
  channels INTEGER DEFAULT 3,
  firmware_version TEXT,
  site_id TEXT NOT NULL,                         -- For multi-site support
  last_seen TIMESTAMPTZ,
  status TEXT DEFAULT 'online' CHECK (status IN ('online', 'offline', 'degraded')),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_dali_controllers_site ON dali_controllers(site_id);
CREATE INDEX idx_dali_controllers_status ON dali_controllers(status);

CREATE TRIGGER update_dali_controllers_updated_at BEFORE UPDATE ON dali_controllers
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- DALI Luminaires (619 total for FNB Fairlands)
CREATE TABLE dali_luminaires (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  controller_id UUID NOT NULL REFERENCES dali_controllers(id) ON DELETE CASCADE,
  luminaire_id TEXT UNIQUE NOT NULL,             -- e.g., 'LUM-L12-025'
  dali_address INTEGER NOT NULL CHECK (dali_address >= 0 AND dali_address <= 63),
  channel INTEGER NOT NULL CHECK (channel >= 1 AND channel <= 3),
  name TEXT,
  location TEXT,
  zone_id TEXT NOT NULL,
  wattage INTEGER,
  current_level INTEGER DEFAULT 0 CHECK (current_level >= 0 AND current_level <= 100),
  power_consumption REAL DEFAULT 0.0,
  operating_hours INTEGER DEFAULT 0,
  fault_status BOOLEAN DEFAULT FALSE,
  last_updated TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_dali_luminaires_controller ON dali_luminaires(controller_id);
CREATE INDEX idx_dali_luminaires_zone ON dali_luminaires(zone_id);
CREATE INDEX idx_dali_luminaires_fault ON dali_luminaires(fault_status) WHERE fault_status = TRUE;

-- DALI Sensors (MSensor G3 - 1,315 PIR/Daylight sensors)
CREATE TABLE dali_sensors (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  controller_id UUID NOT NULL REFERENCES dali_controllers(id) ON DELETE CASCADE,
  sensor_id TEXT UNIQUE NOT NULL,                -- e.g., 'PIR-L12-025'
  dali_address INTEGER NOT NULL CHECK (dali_address >= 0 AND dali_address <= 63),
  channel INTEGER NOT NULL CHECK (channel >= 1 AND channel <= 3),
  location TEXT,
  zone_id TEXT NOT NULL,
  desk_id TEXT,                                  -- Maps to desk for complaint handling
  has_pir BOOLEAN DEFAULT TRUE,
  has_daylight BOOLEAN DEFAULT TRUE,
  occupancy BOOLEAN DEFAULT FALSE,
  lux_level REAL DEFAULT 0.0 CHECK (lux_level >= 0 AND lux_level <= 2000),
  fault_status BOOLEAN DEFAULT FALSE,
  last_updated TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_dali_sensors_controller ON dali_sensors(controller_id);
CREATE INDEX idx_dali_sensors_zone_occupancy ON dali_sensors(zone_id, occupancy);
CREATE INDEX idx_dali_sensors_desk ON dali_sensors(desk_id) WHERE desk_id IS NOT NULL;
CREATE INDEX idx_dali_sensors_fault ON dali_sensors(fault_status) WHERE fault_status = TRUE;

-- Occupancy History (time-series for analytics)
-- Note: In production, consider TimescaleDB hypertable conversion
CREATE TABLE occupancy_history (
  time TIMESTAMPTZ NOT NULL,
  sensor_id TEXT NOT NULL,
  zone_id TEXT NOT NULL,
  occupied BOOLEAN NOT NULL,
  lux_level REAL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_occupancy_history_sensor_time ON occupancy_history(sensor_id, time DESC);
CREATE INDEX idx_occupancy_history_zone_time ON occupancy_history(zone_id, time DESC);

-- Lighting Energy (time-series for energy analytics)
-- Note: In production, consider TimescaleDB hypertable conversion
CREATE TABLE lighting_energy (
  time TIMESTAMPTZ NOT NULL,
  controller_id TEXT NOT NULL,
  zone_id TEXT NOT NULL,
  total_watts REAL NOT NULL DEFAULT 0.0,
  active_luminaires INTEGER NOT NULL DEFAULT 0,
  avg_dim_level REAL DEFAULT 0.0 CHECK (avg_dim_level >= 0 AND avg_dim_level <= 100),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_lighting_energy_zone_time ON lighting_energy(zone_id, time DESC);
CREATE INDEX idx_lighting_energy_controller_time ON lighting_energy(controller_id, time DESC);

-- DALI Zones (logical groupings for control and reporting)
CREATE TABLE dali_zones (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  zone_id TEXT UNIQUE NOT NULL,                  -- e.g., 'Zone-L12-N'
  name TEXT NOT NULL,
  floor TEXT NOT NULL,                           -- L10, L11, L12
  site_id TEXT NOT NULL,
  area_sqm INTEGER,
  desk_count INTEGER,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_dali_zones_site ON dali_zones(site_id);
CREATE INDEX idx_dali_zones_floor ON dali_zones(floor);

CREATE TRIGGER update_dali_zones_updated_at BEFORE UPDATE ON dali_zones
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Comments for documentation
COMMENT ON TABLE dali_controllers IS 'Tridonic Scenecom evo DA2 DALI controllers for lighting automation';
COMMENT ON TABLE dali_luminaires IS 'DALI luminaires with dimming levels and fault status';
COMMENT ON TABLE dali_sensors IS 'MSensor G3 PIR/daylight sensors with occupancy and lux data';
COMMENT ON TABLE occupancy_history IS 'Time-series occupancy data for analytics (consider TimescaleDB in production)';
COMMENT ON TABLE lighting_energy IS 'Time-series lighting energy consumption (consider TimescaleDB in production)';
COMMENT ON TABLE dali_zones IS 'Logical zones for lighting control and reporting';

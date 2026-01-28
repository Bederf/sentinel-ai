-- =====================================================
-- Migration 001: Initial Schema
-- Buildings, Equipment, Alerts, and Sensors tables
-- =====================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Buildings table (replaces sites.json)
CREATE TABLE buildings (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  code TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  address TEXT,
  region TEXT,
  type TEXT CHECK (type IN ('branch', 'regional_office', 'data_center')),
  sqm INTEGER,
  floors INTEGER,
  year_built INTEGER,
  operating_hours JSONB,
  occupancy_pattern TEXT,
  latitude DECIMAL(10, 8),
  longitude DECIMAL(11, 8),
  contact_email TEXT,
  contact_phone TEXT,

  -- Optimization fields
  optimization_enabled BOOLEAN DEFAULT FALSE,
  optimization_status TEXT,
  optimization_settings JSONB,
  last_optimization TIMESTAMPTZ,
  optimization_history JSONB,
  last_recommendation JSONB,

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Equipment table (replaces equipment.json)
CREATE TABLE equipment (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  code TEXT UNIQUE NOT NULL,
  building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  manufacturer TEXT,
  model TEXT,
  capacity TEXT,
  serial_number TEXT,
  install_date DATE,
  last_service DATE,
  status TEXT CHECK (status IN ('normal', 'warning', 'critical', 'offline', 'maintenance')),
  health_score INTEGER CHECK (health_score BETWEEN 0 AND 100),
  location TEXT,

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Sensors table (within equipment)
CREATE TABLE sensors (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  code TEXT UNIQUE NOT NULL,
  equipment_id UUID NOT NULL REFERENCES equipment(id) ON DELETE CASCADE,
  type TEXT NOT NULL CHECK (type IN ('temperature', 'humidity', 'pressure', 'flow', 'energy', 'vibration')),
  unit TEXT NOT NULL,
  location TEXT,
  min_value DECIMAL(10, 2),
  max_value DECIMAL(10, 2),
  current_value DECIMAL(10, 2),

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Alerts table
CREATE TABLE alerts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  building_id UUID REFERENCES buildings(id) ON DELETE CASCADE,
  equipment_id UUID REFERENCES equipment(id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  severity TEXT CHECK (severity IN ('info', 'warning', 'critical')),
  status TEXT CHECK (status IN ('active', 'acknowledged', 'resolved')),
  title TEXT,
  message TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  acknowledged_at TIMESTAMPTZ,
  acknowledged_by TEXT
);

-- Indexes for performance
CREATE INDEX idx_equipment_building ON equipment(building_id);
CREATE INDEX idx_equipment_status ON equipment(status);
CREATE INDEX idx_equipment_health ON equipment(health_score);
CREATE INDEX idx_sensors_equipment ON sensors(equipment_id);
CREATE INDEX idx_sensors_type ON sensors(type);
CREATE INDEX idx_alerts_building ON alerts(building_id);
CREATE INDEX idx_alerts_equipment ON alerts(equipment_id);
CREATE INDEX idx_alerts_status ON alerts(status, severity);

-- Trigger function to update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updated_at
CREATE TRIGGER update_buildings_updated_at BEFORE UPDATE ON buildings
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_equipment_updated_at BEFORE UPDATE ON equipment
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_sensors_updated_at BEFORE UPDATE ON sensors
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_alerts_updated_at BEFORE UPDATE ON alerts
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Add equipment_count column to buildings for performance
ALTER TABLE buildings ADD COLUMN equipment_count INTEGER DEFAULT 0;

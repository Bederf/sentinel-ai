-- Migration: 030_fire_safety_schema.sql
-- Phase 61: Fire & Life Safety Integration
-- Creates 6 tables for fire alarm panel monitoring, smoke dampers,
-- stairwell pressurization, cause-effect matrix, and action logging.

-- Fire zones (static config, seeded from fire_system_config.json)
CREATE TABLE IF NOT EXISTS fire_zones (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  zone_id TEXT UNIQUE NOT NULL,
  zone_name TEXT NOT NULL,
  building_id UUID REFERENCES buildings(id) ON DELETE CASCADE,
  floor TEXT NOT NULL,
  zone_type TEXT NOT NULL CHECK (zone_type IN ('corridor', 'office', 'stairwell', 'plant_room', 'parking', 'server_room', 'lobby')),
  smoke_detectors INTEGER DEFAULT 0,
  heat_detectors INTEGER DEFAULT 0,
  beam_detectors INTEGER DEFAULT 0,
  manual_call_points INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Fire alarms (dynamic events)
CREATE TABLE IF NOT EXISTS fire_alarms (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  alarm_id TEXT UNIQUE NOT NULL,
  zone_id TEXT NOT NULL REFERENCES fire_zones(zone_id) ON DELETE CASCADE,
  building_id UUID REFERENCES buildings(id) ON DELETE CASCADE,
  alarm_type TEXT NOT NULL CHECK (alarm_type IN ('smoke', 'heat', 'manual', 'flow', 'fault')),
  severity TEXT NOT NULL CHECK (severity IN ('fire', 'pre_alarm', 'fault', 'supervisory')),
  description TEXT,
  acknowledged BOOLEAN DEFAULT FALSE,
  acknowledged_by TEXT,
  acknowledged_at TIMESTAMPTZ,
  cleared BOOLEAN DEFAULT FALSE,
  cleared_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Smoke dampers (dynamic state)
CREATE TABLE IF NOT EXISTS fire_dampers (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  damper_id TEXT UNIQUE NOT NULL,
  equipment_id TEXT,
  building_id UUID REFERENCES buildings(id) ON DELETE CASCADE,
  zone_id TEXT REFERENCES fire_zones(zone_id),
  floor TEXT NOT NULL,
  position INTEGER DEFAULT 100 CHECK (position >= 0 AND position <= 100),
  target_position INTEGER DEFAULT 100,
  status TEXT DEFAULT 'open' CHECK (status IN ('open', 'closed', 'transit', 'fault', 'unknown')),
  last_tested TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Stairwell pressurization (dynamic state)
CREATE TABLE IF NOT EXISTS fire_pressurization (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  stairwell_id TEXT UNIQUE NOT NULL,
  building_id UUID REFERENCES buildings(id) ON DELETE CASCADE,
  floor TEXT NOT NULL,
  current_pressure_pa DECIMAL(6,1) DEFAULT 0,
  target_pressure_pa DECIMAL(6,1) DEFAULT 50,
  fan_status TEXT DEFAULT 'off' CHECK (fan_status IN ('off', 'running', 'fault')),
  fan_speed_pct INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Cause & effect matrix (static config)
CREATE TABLE IF NOT EXISTS fire_cause_effect (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  building_id UUID REFERENCES buildings(id) ON DELETE CASCADE,
  trigger_zone TEXT NOT NULL,
  trigger_type TEXT NOT NULL,
  target_type TEXT NOT NULL CHECK (target_type IN ('hvac', 'damper', 'pressurization', 'exhaust')),
  target_id TEXT NOT NULL,
  action TEXT NOT NULL,
  delay_seconds INTEGER DEFAULT 0,
  priority INTEGER DEFAULT 1,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Fire coordination action log (audit trail)
CREATE TABLE IF NOT EXISTS fire_action_log (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  building_id UUID REFERENCES buildings(id) ON DELETE CASCADE,
  action_type TEXT NOT NULL,
  zone_id TEXT,
  device_id TEXT,
  description TEXT NOT NULL,
  mode TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_fire_zones_building ON fire_zones(building_id);
CREATE INDEX IF NOT EXISTS idx_fire_zones_floor ON fire_zones(floor);
CREATE INDEX IF NOT EXISTS idx_fire_alarms_zone ON fire_alarms(zone_id);
CREATE INDEX IF NOT EXISTS idx_fire_alarms_building ON fire_alarms(building_id);
CREATE INDEX IF NOT EXISTS idx_fire_alarms_active ON fire_alarms(cleared) WHERE cleared = FALSE;
CREATE INDEX IF NOT EXISTS idx_fire_dampers_building ON fire_dampers(building_id);
CREATE INDEX IF NOT EXISTS idx_fire_dampers_status ON fire_dampers(status);
CREATE INDEX IF NOT EXISTS idx_fire_pressurization_building ON fire_pressurization(building_id);
CREATE INDEX IF NOT EXISTS idx_fire_action_log_building ON fire_action_log(building_id);
CREATE INDEX IF NOT EXISTS idx_fire_action_log_created ON fire_action_log(created_at DESC);

-- Triggers for updated_at (uses existing update_updated_at_column function)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'update_updated_at_column') THEN
    CREATE TRIGGER update_fire_zones_updated_at BEFORE UPDATE ON fire_zones
      FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    CREATE TRIGGER update_fire_dampers_updated_at BEFORE UPDATE ON fire_dampers
      FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    CREATE TRIGGER update_fire_pressurization_updated_at BEFORE UPDATE ON fire_pressurization
      FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
  END IF;
END
$$;

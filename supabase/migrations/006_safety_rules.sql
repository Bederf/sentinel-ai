-- =====================================================
-- Migration 006: Safety Rules Table
-- Stores safety validation rules for device control
-- =====================================================

-- Safety rules table
CREATE TABLE safety_rules (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  code TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  rule_type TEXT NOT NULL CHECK (rule_type IN (
    'temperature_range',
    'pressure_limit',
    'interlock',
    'runtime_limit',
    'brightness_limit',
    'custom'
  )),
  severity TEXT NOT NULL CHECK (severity IN ('block', 'warning', 'alarm')),
  description TEXT,
  device_type TEXT,  -- hvac, lighting, security, fire_safety, etc.
  device_id TEXT,    -- specific device ID or null for all matching type
  point_name TEXT,   -- specific point or null for all points
  enabled BOOLEAN DEFAULT true,
  parameters JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_safety_rules_type ON safety_rules(rule_type);
CREATE INDEX idx_safety_rules_device_type ON safety_rules(device_type);
CREATE INDEX idx_safety_rules_device_id ON safety_rules(device_id);
CREATE INDEX idx_safety_rules_enabled ON safety_rules(enabled);

-- Update timestamp trigger
CREATE OR REPLACE FUNCTION update_safety_rules_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER safety_rules_updated
  BEFORE UPDATE ON safety_rules
  FOR EACH ROW
  EXECUTE FUNCTION update_safety_rules_timestamp();

-- Seed default safety rules
INSERT INTO safety_rules (code, name, rule_type, severity, description, device_type, device_id, point_name, enabled, parameters) VALUES
  -- Zone temperature range (for zone controllers)
  ('temp_zone_safe_range', 'Zone Temperature Safe Range', 'temperature_range', 'block',
   'Zone temperature setpoints must be within 16-28°C for occupant comfort',
   'hvac', NULL, 'cooling_setpoint', true,
   '{"min_temp": 16.0, "max_temp": 28.0, "unit": "°C"}'::jsonb),

  -- CHW supply temperature range
  ('temp_chw_supply_range', 'CHW Supply Temperature Range', 'temperature_range', 'block',
   'Chilled water supply temperature must be within 5-12°C',
   'hvac', NULL, 'supply_temp_setpoint', true,
   '{"min_temp": 5.0, "max_temp": 12.0, "unit": "°C"}'::jsonb),

  -- Chiller minimum temperature (prevent freeze)
  ('temp_chiller_min', 'Chiller Minimum Temperature', 'temperature_range', 'block',
   'Chiller supply temperature must be above 5°C to prevent freeze damage',
   'hvac', NULL, 'setpoint', true,
   '{"min_temp": 5.0, "max_temp": 15.0, "unit": "°C"}'::jsonb),

  -- Chiller runtime limit
  ('chiller_runtime_limit', 'Chiller Minimum Runtime', 'runtime_limit', 'block',
   'Chiller must run for at least 5 minutes before restart to protect compressor',
   'hvac', NULL, 'chiller_status', true,
   '{"min_runtime_minutes": 5, "max_starts_per_hour": 4}'::jsonb),

  -- Chiller pressure limit
  ('chiller_pressure_max', 'Chiller Maximum Pressure', 'pressure_limit', 'block',
   'Chiller compressor pressure must not exceed 20 bar for safety',
   'hvac', NULL, 'compressor_pressure', true,
   '{"min_pressure": 0.0, "max_pressure": 20.0, "unit": "bar"}'::jsonb),

  -- Lighting brightness limit
  ('lighting_brightness_max', 'Maximum Brightness Limit', 'brightness_limit', 'warning',
   'Lighting brightness should not exceed 90% to save energy',
   'lighting', NULL, NULL, true,
   '{"min_brightness": 0, "max_brightness": 90}'::jsonb),

  -- Fire alarm HVAC interlock
  ('fire_alarm_hvac_interlock', 'Fire Alarm HVAC Interlock', 'interlock', 'block',
   'When fire alarm is active, disable HVAC to prevent smoke spread',
   'hvac', NULL, NULL, true,
   '{"trigger_device_type": "fire_safety", "trigger_point": "pump_status", "trigger_value": 1, "action": "disable"}'::jsonb),

  -- Humidity range
  ('humidity_safe_range', 'Humidity Safe Range', 'custom', 'warning',
   'Humidity setpoint should be within 30-65% for comfort',
   'hvac', NULL, 'humidity_setpoint', true,
   '{"min_value": 30.0, "max_value": 65.0, "unit": "%", "validation_logic": "value >= 30.0 AND value <= 65.0"}'::jsonb);

-- Comment on table
COMMENT ON TABLE safety_rules IS 'Safety validation rules for device control operations';

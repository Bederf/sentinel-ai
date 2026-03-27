-- Phase 174: P0 runtime-authority migration
-- Canonical runtime stores for settings, health config, alert muting/routing,
-- and site processing state.

-- Ensure the renamed sites table carries the runtime processing toggle.
ALTER TABLE sites
  ADD COLUMN IF NOT EXISTS sentinel_processing_enabled BOOLEAN DEFAULT true;

COMMENT ON COLUMN sites.sentinel_processing_enabled IS
  'When false, shipped SENTINEL runtime skips ML feeding, health monitoring, alerts, and recommendations for this site.';

-- Canonical per-equipment health calculation configuration.
CREATE TABLE IF NOT EXISTS equipment_health_configs (
  equipment_type TEXT PRIMARY KEY,
  expected_life_years INTEGER NOT NULL,
  service_interval_days INTEGER NOT NULL,
  weights JSONB NOT NULL,
  thresholds JSONB NOT NULL,
  fault_weights JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_by TEXT
);

CREATE TRIGGER update_equipment_health_configs_updated_at
  BEFORE UPDATE ON equipment_health_configs
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Canonical alert mute state.
CREATE TABLE IF NOT EXISTS alert_mutes (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  equipment_code TEXT NOT NULL,
  reason TEXT NOT NULL,
  duration_hours INTEGER NOT NULL,
  muted_at TIMESTAMPTZ NOT NULL,
  muted_until TIMESTAMPTZ NOT NULL,
  muted_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alert_mutes_equipment_code ON alert_mutes(equipment_code);
CREATE INDEX IF NOT EXISTS idx_alert_mutes_muted_until ON alert_mutes(muted_until);

-- Canonical alert routing rules.
CREATE TABLE IF NOT EXISTS alert_routing_rules (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  severity JSONB NOT NULL DEFAULT '[]'::jsonb,
  equipment_types JSONB NOT NULL DEFAULT '[]'::jsonb,
  site_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  channels JSONB NOT NULL DEFAULT '[]'::jsonb,
  recipient_roles JSONB NOT NULL DEFAULT '[]'::jsonb,
  recipient_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  escalation_minutes INTEGER,
  escalation_to_roles JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by TEXT,
  updated_by TEXT
);

CREATE TRIGGER update_alert_routing_rules_updated_at
  BEFORE UPDATE ON alert_routing_rules
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Seed canonical system settings used by shipped runtime if absent.
INSERT INTO system_settings (key, value, category, description, data_type, is_public, is_editable)
VALUES
  (
    'risk_thresholds',
    '{"medium": 31, "high": 61, "critical": 81}'::jsonb,
    'risk',
    'Risk score thresholds for cockpit severity interpretation (0-100 scale)',
    'object',
    TRUE,
    TRUE
  ),
  (
    'notifications',
    '{
      "alertCommands": {
        "reset": {"enabled": true, "label": "Remote reset"},
        "info": {"enabled": true, "label": "More info"},
        "note": {"enabled": true, "label": "Add note"},
        "wo": {"enabled": true, "label": "Create work order"}
      },
      "alertCooldownMinutes": 5,
      "resetBlockedTypes": ["FIRE", "GEN"]
    }'::jsonb,
    'notifications',
    'Runtime notification settings and alert command configuration',
    'object',
    FALSE,
    TRUE
  ),
  (
    'display',
    '{}'::jsonb,
    'display',
    'Display configuration for runtime UI surfaces',
    'object',
    TRUE,
    TRUE
  ),
  (
    'control_limits',
    '{
      "temperature_setpoint": {
        "min": 18,
        "max": 26,
        "default": 22,
        "unit": "°C",
        "description": "Allowed temperature setpoint range"
      },
      "chiller_setpoint": {
        "min": 5,
        "max": 12,
        "default": 7,
        "unit": "°C",
        "description": "Chilled water setpoint range"
      },
      "fan_speed": {
        "modes": ["Off", "Low", "Medium", "High", "Auto"],
        "default": "Auto",
        "description": "Available fan speed modes"
      },
      "humidity_setpoint": {
        "min": 40,
        "max": 60,
        "default": 50,
        "unit": "%RH",
        "description": "Humidity setpoint range"
      }
    }'::jsonb,
    'controls',
    'Runtime control limits used by shipped HVAC and chat control surfaces',
    'object',
    FALSE,
    TRUE
  )
ON CONFLICT (key) DO NOTHING;

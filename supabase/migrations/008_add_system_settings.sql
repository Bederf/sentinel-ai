-- =====================================================
-- Migration 008: System Settings Table
-- Health thresholds, notification settings, etc.
-- =====================================================

-- System settings table (key-value store for global settings)
CREATE TABLE IF NOT EXISTS system_settings (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

  -- Setting key (unique identifier)
  key TEXT NOT NULL UNIQUE,

  -- Setting value (flexible JSON type for different data types)
  value JSONB NOT NULL,

  -- Metadata
  category TEXT NOT NULL, -- 'health_thresholds', 'notifications', 'display', etc.
  description TEXT,
  data_type TEXT NOT NULL CHECK (data_type IN ('string', 'number', 'boolean', 'object', 'array')),

  -- Access control
  is_public BOOLEAN DEFAULT FALSE, -- Can be read by non-admin users
  is_editable BOOLEAN DEFAULT TRUE, -- Can be modified by users

  -- Audit
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by TEXT,
  updated_by TEXT
);

-- Index for quick lookups by key
CREATE INDEX idx_system_settings_key ON system_settings(key);
CREATE INDEX idx_system_settings_category ON system_settings(category);

-- Insert default health thresholds
INSERT INTO system_settings (key, value, category, description, data_type, is_public)
VALUES
  (
    'health_thresholds',
    '{"healthy": 90, "warning": 70, "critical": 50}'::jsonb,
    'health',
    'Health score thresholds for equipment classification (0-100 scale)',
    'object',
    TRUE
  ),
  (
    'alert_intervals',
    '{"critical": 30, "warning": 60, "info": 1440}'::jsonb,
    'alerts',
    'Alert throttling intervals in minutes (how often to repeat alerts)',
    'object',
    FALSE
  ),
  (
    'monitoring_enabled',
    'true'::jsonb,
    'monitoring',
    'Enable/disable automated health monitoring',
    'boolean',
    FALSE
  ),
  (
    'daily_summary_time',
    '"08:00"'::jsonb,
    'monitoring',
    'Time to send daily health summary (24h format)',
    'string',
    FALSE
  )
ON CONFLICT (key) DO NOTHING;

-- Function to get setting by key
CREATE OR REPLACE FUNCTION get_setting(setting_key TEXT)
RETURNS JSONB AS $$
DECLARE
  setting_value JSONB;
BEGIN
  SELECT value INTO setting_value
  FROM system_settings
  WHERE key = get_setting.key;

  IF NOT FOUND THEN
    RETURN NULL::jsonb;
  END IF;

  RETURN setting_value;
END;
$$ LANGUAGE plpgsql;

-- Function to set/update setting
CREATE OR REPLACE FUNCTION set_setting(
  setting_key TEXT,
  setting_value JSONB,
  setting_category TEXT DEFAULT 'general',
  setting_description TEXT DEFAULT NULL,
  user_name TEXT DEFAULT NULL
)
RETURNS JSONB AS $$
BEGIN
  INSERT INTO system_settings (key, value, category, description, updated_by)
  VALUES (set_setting.setting_key, set_setting.setting_value, setting_category, setting_description, user_name)
  ON CONFLICT (key) DO UPDATE
  SET
    value = EXCLUDED.value,
    updated_at = NOW(),
    updated_by = set_setting.user_name
  WHERE system_settings.key = set_setting.setting_key;

  RETURN get_setting(set_setting.setting_key);
END;
$$ LANGUAGE plpgsql;

-- View for public settings (accessible to all users)
CREATE OR REPLACE VIEW public_settings AS
SELECT
  key,
  value,
  category,
  description,
  data_type
FROM system_settings
WHERE is_public = TRUE;

-- Grant permissions (adjust as needed for your setup)
-- GRANT SELECT ON public_settings TO authenticated;
-- GRANT SELECT, UPDATE ON system_settings TO admin;

-- Trigger for updated_at
CREATE TRIGGER update_system_settings_updated_at BEFORE UPDATE ON system_settings
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Add comment
COMMENT ON TABLE system_settings IS 'Global system configuration stored in database (better than JSON files for production)';

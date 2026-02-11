-- Phase 12: Add theme and notification preference columns
-- Extends dashboard_preferences table with Phase 12 user preference columns

-- Theme mode: 'auto' (follows system), 'light', 'dark'
ALTER TABLE IF EXISTS dashboard_preferences
ADD COLUMN IF NOT EXISTS theme_mode TEXT DEFAULT 'auto';

-- Glass theme blur intensity (0-30)
ALTER TABLE IF EXISTS dashboard_preferences
ADD COLUMN IF NOT EXISTS glass_blur_intensity INTEGER DEFAULT 12;

-- Glass theme panel opacity (0-100)
ALTER TABLE IF EXISTS dashboard_preferences
ADD COLUMN IF NOT EXISTS glass_panel_opacity INTEGER DEFAULT 65;

-- Glass theme border strength (0-100)
ALTER TABLE IF EXISTS dashboard_preferences
ADD COLUMN IF NOT EXISTS glass_border_strength INTEGER DEFAULT 12;

-- Flag to use custom glass theme
ALTER TABLE IF EXISTS dashboard_preferences
ADD COLUMN IF NOT EXISTS use_custom_glass_theme BOOLEAN DEFAULT FALSE;

-- Sidebar collapsed state
ALTER TABLE IF EXISTS dashboard_preferences
ADD COLUMN IF NOT EXISTS sidebar_collapsed BOOLEAN DEFAULT FALSE;

-- Default view: 'dashboard', 'sites', 'analytics'
ALTER TABLE IF EXISTS dashboard_preferences
ADD COLUMN IF NOT EXISTS default_view TEXT DEFAULT 'dashboard';

-- Notification frequency: 'realtime', 'digest', 'weekly'
ALTER TABLE IF EXISTS dashboard_preferences
ADD COLUMN IF NOT EXISTS notification_frequency TEXT DEFAULT 'realtime';

-- Notification methods as JSONB
-- Example: {"email": false, "sms": false, "telegram": true}
ALTER TABLE IF EXISTS dashboard_preferences
ADD COLUMN IF NOT EXISTS notification_methods JSONB DEFAULT '{"email": false, "sms": false, "telegram": true}';

-- Add comment explaining Phase 12 additions
COMMENT ON COLUMN dashboard_preferences.theme_mode IS 'User theme preference: auto, light, dark';
COMMENT ON COLUMN dashboard_preferences.glass_blur_intensity IS 'Glass theme blur intensity (0-30)';
COMMENT ON COLUMN dashboard_preferences.glass_panel_opacity IS 'Glass theme panel opacity (0-100)';
COMMENT ON COLUMN dashboard_preferences.glass_border_strength IS 'Glass theme border strength (0-100)';
COMMENT ON COLUMN dashboard_preferences.use_custom_glass_theme IS 'Enable custom glass theme overrides';
COMMENT ON COLUMN dashboard_preferences.sidebar_collapsed IS 'Sidebar UI state (collapsed/expanded)';
COMMENT ON COLUMN dashboard_preferences.default_view IS 'Default dashboard view on login';
COMMENT ON COLUMN dashboard_preferences.notification_frequency IS 'How often to send notifications';
COMMENT ON COLUMN dashboard_preferences.notification_methods IS 'Enabled notification channels (email, sms, telegram)';

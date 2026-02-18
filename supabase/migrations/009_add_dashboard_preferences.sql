-- Dashboard Preferences Migration
-- Stores user dashboard customization preferences

-- Create dashboard_preferences table
CREATE TABLE IF NOT EXISTS dashboard_preferences (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE,  -- Can be anonymous session ID or auth user ID

    -- Card visibility (which cards are shown)
    visible_kpi_cards JSONB NOT NULL DEFAULT '["kpi-protected-sites", "kpi-monitored-assets", "kpi-active-risks", "kpi-potential-savings", "kpi-risk-predictions"]',
    visible_sections JSONB NOT NULL DEFAULT '["kpi-row", "site-protection", "energy-analytics", "risk-predictions"]',

    -- Card ordering
    kpi_card_order JSONB NOT NULL DEFAULT '["kpi-protected-sites", "kpi-monitored-assets", "kpi-active-risks", "kpi-potential-savings", "kpi-risk-predictions"]',
    section_order JSONB NOT NULL DEFAULT '["kpi-row", "site-protection", "energy-analytics", "risk-predictions"]',

    -- Additional preferences
    default_energy_period INTEGER DEFAULT 30,
    default_energy_site_id TEXT DEFAULT NULL,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index on user_id for fast lookups
CREATE INDEX IF NOT EXISTS idx_dashboard_preferences_user_id ON dashboard_preferences(user_id);

-- Create updated_at trigger
CREATE OR REPLACE FUNCTION update_dashboard_preferences_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_dashboard_preferences_updated_at ON dashboard_preferences;
CREATE TRIGGER trigger_dashboard_preferences_updated_at
    BEFORE UPDATE ON dashboard_preferences
    FOR EACH ROW
    EXECUTE FUNCTION update_dashboard_preferences_updated_at();

-- Enable RLS
ALTER TABLE dashboard_preferences ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only access their own preferences
CREATE POLICY "Users can view own preferences" ON dashboard_preferences
    FOR SELECT USING (true);  -- For now, allow all reads (no auth yet)

CREATE POLICY "Users can insert own preferences" ON dashboard_preferences
    FOR INSERT WITH CHECK (true);  -- For now, allow all inserts

CREATE POLICY "Users can update own preferences" ON dashboard_preferences
    FOR UPDATE USING (true);  -- For now, allow all updates

COMMENT ON TABLE dashboard_preferences IS 'Stores user dashboard customization preferences including visible cards and ordering';
COMMENT ON COLUMN dashboard_preferences.user_id IS 'User identifier - session ID for anonymous users, auth ID for logged in users';
COMMENT ON COLUMN dashboard_preferences.visible_kpi_cards IS 'Array of KPI card IDs that are visible on dashboard';
COMMENT ON COLUMN dashboard_preferences.visible_sections IS 'Array of section IDs that are visible on dashboard';
COMMENT ON COLUMN dashboard_preferences.kpi_card_order IS 'Array of KPI card IDs in display order';
COMMENT ON COLUMN dashboard_preferences.section_order IS 'Array of section IDs in display order';

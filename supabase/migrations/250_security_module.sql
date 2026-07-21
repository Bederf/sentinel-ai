-- =============================================================================
-- Migration: Security Module Dashboard Schema
-- =============================================================================
-- Phase 69-01: Extends security tables from migration 033 with:
--   - access_rules (configurable access restrictions)
--   - zone_occupancy enhancement with max_capacity
--   - Sample data for demo mode
-- =============================================================================

-- =====================================================
-- 1. Access Rules Table (configurable access restrictions)
-- =====================================================
CREATE TABLE IF NOT EXISTS access_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zone_id TEXT NOT NULL,
    rule_type TEXT NOT NULL DEFAULT 'time_based'
        CHECK (rule_type IN ('time_based', 'occupancy_based', 'emergency')),
    rule_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    description TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for access_rules
CREATE INDEX IF NOT EXISTS idx_access_rules_zone_id
    ON access_rules(zone_id);
CREATE INDEX IF NOT EXISTS idx_access_rules_active
    ON access_rules(active, rule_type);

-- =====================================================
-- 2. Zone Occupancy Extension (max_capacity for fire code)
-- =====================================================
-- Add max_capacity column to existing security_occupancy table if it exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'security_occupancy') THEN
        -- Add max_capacity if not present
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'security_occupancy' AND column_name = 'max_capacity'
        ) THEN
            ALTER TABLE security_occupancy ADD COLUMN max_capacity INTEGER DEFAULT 50;
        END IF;

        -- Add percent_full if not present
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'security_occupancy' AND column_name = 'percent_full'
        ) THEN
            ALTER TABLE security_occupancy ADD COLUMN percent_full DECIMAL(5,2) DEFAULT 0.0;
        END IF;
    END IF;
END $$;

-- =====================================================
-- 3. Add stream_url and camera_model to security_cameras
-- =====================================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'security_cameras') THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'security_cameras' AND column_name = 'stream_url'
        ) THEN
            ALTER TABLE security_cameras ADD COLUMN stream_url TEXT DEFAULT '';
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'security_cameras' AND column_name = 'camera_model'
        ) THEN
            ALTER TABLE security_cameras ADD COLUMN camera_model TEXT DEFAULT '';
        END IF;
    END IF;
END $$;

-- =====================================================
-- 4. Sample Data — Zone Occupancy with Capacity
-- =====================================================
-- Ground floor zones
INSERT INTO security_occupancy (zone_id, zone_name, occupancy_count, badge_entries, badge_exits, max_capacity, percent_full, source)
VALUES
    ('zone_000', 'Ground Floor Lobby', 12, 45, 33, 50, 24.0, 'badge'),
    ('zone_001', 'Level 1 Open Plan', 22, 38, 16, 40, 55.0, 'badge'),
    ('zone_002', 'Level 2 Executive', 8, 15, 7, 35, 22.9, 'badge'),
    ('zone_plant', 'Plant Room B1', 0, 2, 2, 10, 0.0, 'badge')
ON CONFLICT DO NOTHING;

-- Sample access rules
INSERT INTO access_rules (zone_id, rule_type, rule_config, active, description) VALUES
    ('zone_000', 'time_based', '{"start_hour": 6, "end_hour": 22, "days": ["mon","tue","wed","thu","fri"]}', true, 'Business hours access for ground floor'),
    ('zone_001', 'time_based', '{"start_hour": 7, "end_hour": 20, "days": ["mon","tue","wed","thu","fri"]}', true, 'Standard office hours for Level 1'),
    ('zone_plant', 'occupancy_based', '{"max_occupancy": 5, "alert_threshold": 4}', true, 'Plant room occupancy limit'),
    ('zone_000', 'emergency', '{"unlock_all_doors": true, "notify_security": true, "evacuation_route": "north_stairwell"}', false, 'Emergency evacuation protocol')
ON CONFLICT DO NOTHING;

-- =====================================================
-- 5. Trigger for updated_at on access_rules
-- =====================================================
CREATE OR REPLACE FUNCTION update_access_rules_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_access_rules_updated_at ON access_rules;
CREATE TRIGGER trigger_access_rules_updated_at
    BEFORE UPDATE ON access_rules
    FOR EACH ROW
    EXECUTE FUNCTION update_access_rules_updated_at();

-- Comments
COMMENT ON TABLE access_rules IS 'Configurable access restrictions per zone: time-based, occupancy-based, emergency protocols';
COMMENT ON COLUMN access_rules.rule_config IS 'JSONB config: time windows, occupancy thresholds, emergency actions';

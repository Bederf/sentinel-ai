-- =====================================================
-- Migration 035: User Site Access Control
-- Role-based building access so users only see buildings
-- they're authorized to access
-- =====================================================

-- User site access mapping table
CREATE TABLE IF NOT EXISTS user_site_access (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_email TEXT NOT NULL,
    building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
    granted_by TEXT,
    granted_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_email, building_id)
);

-- Indexes for efficient lookups
CREATE INDEX idx_user_site_access_email ON user_site_access(user_email);
CREATE INDEX idx_user_site_access_building ON user_site_access(building_id);

-- =====================================================
-- Helper function: Get accessible buildings for a user
-- ADMIN role bypasses filtering and sees all buildings
-- =====================================================
CREATE OR REPLACE FUNCTION get_user_accessible_buildings(
    p_user_email TEXT,
    p_user_role TEXT DEFAULT 'auditor'
) RETURNS TABLE (building_id UUID, building_code TEXT) AS $$
BEGIN
    -- ADMIN sees all buildings
    IF p_user_role = 'admin' THEN
        RETURN QUERY SELECT b.id, b.code FROM buildings b;
    ELSE
        -- Other roles see only assigned buildings
        RETURN QUERY
        SELECT b.id, b.code FROM buildings b
        JOIN user_site_access usa ON usa.building_id = b.id
        WHERE usa.user_email = LOWER(p_user_email);
    END IF;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- Seed data
-- =====================================================

-- Admin user (bederf@gmail.com) gets access to all buildings
INSERT INTO user_site_access (user_email, building_id, granted_by)
SELECT 'bederf@gmail.com', b.id, 'system'
FROM buildings b
ON CONFLICT (user_email, building_id) DO NOTHING;

-- Admin user (admin@sentinel.bms) gets access to all buildings
INSERT INTO user_site_access (user_email, building_id, granted_by)
SELECT 'admin@sentinel.bms', b.id, 'system'
FROM buildings b
ON CONFLICT (user_email, building_id) DO NOTHING;

-- Demo operator gets site-002 (Sandton City) only
INSERT INTO user_site_access (user_email, building_id, granted_by)
SELECT 'operator@sentinel.bms', b.id, 'system'
FROM buildings b
WHERE b.code = 'site-002'
ON CONFLICT (user_email, building_id) DO NOTHING;

-- Developer gets site-002 (Sandton City) only
INSERT INTO user_site_access (user_email, building_id, granted_by)
SELECT 'dev@sentinel.bms', b.id, 'system'
FROM buildings b
WHERE b.code = 'site-002'
ON CONFLICT (user_email, building_id) DO NOTHING;

-- Auditor gets site-002 (Sandton City) only
INSERT INTO user_site_access (user_email, building_id, granted_by)
SELECT 'auditor@sentinel.bms', b.id, 'system'
FROM buildings b
WHERE b.code = 'site-002'
ON CONFLICT (user_email, building_id) DO NOTHING;

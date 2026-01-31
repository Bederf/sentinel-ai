-- ================================================
-- SENTINEL BMS - Complaints Schema
-- Migration: 012_complaints_schema.sql
--
-- Stores comfort complaints for pattern analysis
-- and historical tracking.
-- ================================================

-- Complaints table
CREATE TABLE IF NOT EXISTS complaints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    complaint_id VARCHAR(100) UNIQUE NOT NULL,

    -- Location
    building_id VARCHAR(50) NOT NULL,
    desk_id VARCHAR(50) NOT NULL,
    zone_id VARCHAR(50),
    floor VARCHAR(50),

    -- Complaint details
    complaint_type VARCHAR(50) NOT NULL, -- too_hot, too_cold, stuffy, drafty, other
    description TEXT,
    user_name VARCHAR(100),

    -- Diagnosis
    diagnosis TEXT,
    root_cause TEXT,
    confidence VARCHAR(20), -- high, medium, low
    suggestions JSONB DEFAULT '[]'::jsonb,

    -- Resolution
    status VARCHAR(20) DEFAULT 'open', -- open, diagnosed, in_progress, resolved, closed
    auto_action_taken TEXT,
    resolution_notes TEXT,
    resolved_by VARCHAR(100),
    resolved_at TIMESTAMPTZ,

    -- Context snapshot (at time of complaint)
    zone_temp DECIMAL(5,2),
    zone_setpoint DECIMAL(5,2),
    fcu_status VARCHAR(50),
    occupancy_percent INTEGER,
    daylight_lux INTEGER,

    -- Metadata
    source VARCHAR(50) DEFAULT 'web', -- web, telegram, api, mobile
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_complaints_building ON complaints(building_id);
CREATE INDEX IF NOT EXISTS idx_complaints_desk ON complaints(desk_id);
CREATE INDEX IF NOT EXISTS idx_complaints_zone ON complaints(zone_id);
CREATE INDEX IF NOT EXISTS idx_complaints_type ON complaints(complaint_type);
CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status);
CREATE INDEX IF NOT EXISTS idx_complaints_created ON complaints(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_complaints_building_created ON complaints(building_id, created_at DESC);

-- Trigger to update updated_at
CREATE OR REPLACE FUNCTION update_complaints_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS complaints_updated_at ON complaints;
CREATE TRIGGER complaints_updated_at
    BEFORE UPDATE ON complaints
    FOR EACH ROW
    EXECUTE FUNCTION update_complaints_updated_at();

-- View for complaint analytics
CREATE OR REPLACE VIEW complaint_analytics AS
SELECT
    building_id,
    zone_id,
    complaint_type,
    DATE_TRUNC('day', created_at) as complaint_date,
    COUNT(*) as complaint_count,
    AVG(CASE WHEN confidence = 'high' THEN 1 WHEN confidence = 'medium' THEN 0.5 ELSE 0.25 END) as avg_confidence,
    COUNT(CASE WHEN status = 'resolved' THEN 1 END) as resolved_count,
    AVG(EXTRACT(EPOCH FROM (resolved_at - created_at))/3600) as avg_resolution_hours
FROM complaints
GROUP BY building_id, zone_id, complaint_type, DATE_TRUNC('day', created_at);

-- Sample data for testing (Sandton building)
INSERT INTO complaints (complaint_id, building_id, desk_id, zone_id, floor, complaint_type, diagnosis, root_cause, confidence, suggestions, status, zone_temp, zone_setpoint, source)
VALUES
    ('demo-001', 'sandton', '201', 'Zone-L12-N', 'Level 12', 'too_hot', 'Solar heat gain detected', 'Desk near west-facing window during afternoon', 'high', '["Close blinds", "Boost cooling temporarily"]'::jsonb, 'resolved', 24.5, 22.0, 'demo'),
    ('demo-002', 'sandton', '203', 'Zone-L12-S', 'Level 12', 'too_cold', 'Direct airflow from diffuser', 'Desk directly under supply air outlet DIFF-203', 'high', '["Adjust diffuser direction", "Install deflector"]'::jsonb, 'open', 21.0, 22.0, 'demo'),
    ('demo-003', 'sandton', '204', 'Zone-L11-S', 'Level 11', 'too_hot', 'Local heat source detected', 'Printer equipment nearby generating heat', 'medium', '["Relocate desk", "Check printer duty cycle"]'::jsonb, 'diagnosed', 25.0, 22.0, 'demo')
ON CONFLICT (complaint_id) DO NOTHING;

COMMENT ON TABLE complaints IS 'Comfort complaints with diagnosis and resolution tracking';

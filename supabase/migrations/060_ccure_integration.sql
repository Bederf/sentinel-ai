-- Migration: C•CURE 9000 Integration (Phase 58.2)
-- Adds tables for security anomalies and C•CURE controller tracking

-- Extend security_badge_events for C•CURE-specific fields
ALTER TABLE IF EXISTS security_badge_events
ADD COLUMN IF NOT EXISTS event_type TEXT DEFAULT 'access_granted'
  CHECK (event_type IN ('access_granted', 'access_denied', 'forced_door',
                        'door_held_open', 'anti_passback', 'tamper',
                        'controller_offline', 'duress'));

ALTER TABLE IF EXISTS security_badge_events
ADD COLUMN IF NOT EXISTS clearance_level TEXT;

ALTER TABLE IF EXISTS security_badge_events
ADD COLUMN IF NOT EXISTS department TEXT;

ALTER TABLE IF EXISTS security_badge_events
ADD COLUMN IF NOT EXISTS after_hours BOOLEAN DEFAULT FALSE;

-- Security anomalies tracking table
CREATE TABLE IF NOT EXISTS security_anomalies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    anomaly_type TEXT NOT NULL CHECK (anomaly_type IN
        ('after_hours_access', 'forced_door', 'door_held_open',
         'anti_passback', 'controller_offline', 'energy_waste')),
    severity TEXT NOT NULL CHECK (severity IN ('warning', 'critical', 'info')),
    badge_event_id TEXT REFERENCES security_badge_events(event_id),
    zone_id TEXT,
    description TEXT NOT NULL,
    hvac_correlation JSONB,  -- Store correlated HVAC events
    lighting_correlation JSONB,  -- Store correlated lighting events
    energy_impact TEXT,  -- e.g., "Estimated 2-5 kWh excess consumption"
    resolved BOOLEAN DEFAULT FALSE,
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- C•CURE controllers tracking (iSTAR hardware)
CREATE TABLE IF NOT EXISTS ccure_controllers (
    controller_id TEXT PRIMARY KEY,
    site_id TEXT NOT NULL,
    name TEXT NOT NULL,
    model TEXT NOT NULL,
    firmware TEXT,
    encryption_mode TEXT,
    tamper_status TEXT DEFAULT 'normal' CHECK (tamper_status IN ('normal', 'enclosure_open', 'back_tamper')),
    last_seen TIMESTAMPTZ,
    ip_address TEXT,
    reader_count INT DEFAULT 0,
    status TEXT DEFAULT 'online' CHECK (status IN ('online', 'offline', 'degraded')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_security_anomalies_severity
    ON security_anomalies(severity, detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_security_anomalies_type
    ON security_anomalies(anomaly_type, detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_security_anomalies_unresolved
    ON security_anomalies(resolved, detected_at DESC)
    WHERE resolved = FALSE;

CREATE INDEX IF NOT EXISTS idx_security_anomalies_zone
    ON security_anomalies(zone_id, detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_ccure_controllers_status
    ON ccure_controllers(status, last_seen DESC);

CREATE INDEX IF NOT EXISTS idx_ccure_controllers_site
    ON ccure_controllers(site_id, status);

-- Cleanup indexes for old data retention
CREATE INDEX IF NOT EXISTS idx_security_badge_events_after_hours
    ON security_badge_events(after_hours, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_security_badge_events_department
    ON security_badge_events(department, timestamp DESC);

-- Enable RLS for security tables
ALTER TABLE security_anomalies ENABLE ROW LEVEL SECURITY;
ALTER TABLE ccure_controllers ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Allow authenticated users to read security anomalies
CREATE POLICY "Allow authenticated read access to security_anomalies"
    ON security_anomalies
    FOR SELECT
    USING (auth.role() = 'authenticated');

-- RLS Policy: Allow service role to manage security anomalies
CREATE POLICY "Allow service role to manage security_anomalies"
    ON security_anomalies
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- RLS Policy: Allow authenticated users to read C•CURE controllers
CREATE POLICY "Allow authenticated read access to ccure_controllers"
    ON ccure_controllers
    FOR SELECT
    USING (auth.role() = 'authenticated');

-- RLS Policy: Allow service role to manage C•CURE controllers
CREATE POLICY "Allow service role to manage ccure_controllers"
    ON ccure_controllers
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- Function to get recent security anomalies (for API)
CREATE OR REPLACE FUNCTION get_recent_security_anomalies(
    p_hours INTEGER DEFAULT 24,
    p_severity TEXT DEFAULT NULL
)
RETURNS TABLE(
    id UUID,
    anomaly_type TEXT,
    severity TEXT,
    description TEXT,
    energy_impact TEXT,
    detected_at TIMESTAMPTZ,
    resolved BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        security_anomalies.id,
        security_anomalies.anomaly_type,
        security_anomalies.severity,
        security_anomalies.description,
        security_anomalies.energy_impact,
        security_anomalies.detected_at,
        security_anomalies.resolved
    FROM security_anomalies
    WHERE (NOW() - security_anomalies.detected_at) < (p_hours || ' hours')::INTERVAL
        AND (p_severity IS NULL OR security_anomalies.severity = p_severity)
    ORDER BY security_anomalies.detected_at DESC;
END;
$$ LANGUAGE plpgsql;

-- Comment tables for documentation
COMMENT ON TABLE security_anomalies IS
    'C•CURE 9000 security anomalies: after-hours access, equipment health, cross-system correlations';

COMMENT ON TABLE ccure_controllers IS
    'C•CURE iSTAR controller status and health tracking';

COMMENT ON COLUMN security_anomalies.hvac_correlation IS
    'JSON object containing correlated HVAC events (zone, setpoint change, activation time)';

COMMENT ON COLUMN security_anomalies.lighting_correlation IS
    'JSON object containing correlated lighting events (zone, brightness change, activation time)';

COMMENT ON COLUMN security_anomalies.energy_impact IS
    'Human-readable estimate of energy impact (e.g., "Estimated 2-5 kWh excess per hour")';

COMMENT ON COLUMN ccure_controllers.encryption_mode IS
    'Encryption standard (e.g., "FIPS 197 AES-256", "FIPS 140-2")';

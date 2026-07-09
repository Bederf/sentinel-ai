-- Security module restore migration
--
-- Restores the canonical security tables used by the badge/access-control
-- occupancy path and the security API. This is schema only; it does not seed
-- fabricated telemetry.

CREATE TABLE IF NOT EXISTS security_access_zones (
    zone_id TEXT PRIMARY KEY,
    building_id TEXT NOT NULL DEFAULT 'site-002',
    name TEXT NOT NULL,
    floor TEXT NOT NULL,
    access_level TEXT NOT NULL DEFAULT 'restricted'
        CHECK (access_level IN ('public', 'restricted', 'secure', 'critical')),
    doors TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS security_doors (
    door_id TEXT PRIMARY KEY,
    zone_id TEXT NOT NULL REFERENCES security_access_zones(zone_id),
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'locked'
        CHECK (status IN ('open', 'closed', 'locked', 'fault')),
    reader_type TEXT NOT NULL DEFAULT 'card'
        CHECK (reader_type IN ('card', 'biometric', 'pin')),
    last_event_time TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS security_badge_events (
    event_id TEXT PRIMARY KEY,
    door_id TEXT NOT NULL,
    zone_id TEXT NOT NULL,
    badge_id TEXT NOT NULL,
    person_name TEXT NOT NULL DEFAULT '',
    direction TEXT NOT NULL DEFAULT 'entry'
        CHECK (direction IN ('entry', 'exit')),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    granted BOOLEAN NOT NULL DEFAULT TRUE,
    reason TEXT DEFAULT '',
    event_type TEXT DEFAULT 'access_granted'
        CHECK (event_type IN (
            'access_granted',
            'access_denied',
            'forced_door',
            'door_held_open',
            'anti_passback',
            'tamper',
            'controller_offline',
            'duress'
        )),
    clearance_level TEXT,
    department TEXT,
    after_hours BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_badge_events_timestamp
    ON security_badge_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_badge_events_zone_id
    ON security_badge_events(zone_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_badge_events_badge_id
    ON security_badge_events(badge_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_badge_events_granted
    ON security_badge_events(granted, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_badge_events_direction
    ON security_badge_events(direction, zone_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_security_badge_events_after_hours
    ON security_badge_events(after_hours, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_security_badge_events_department
    ON security_badge_events(department, timestamp DESC);

CREATE TABLE IF NOT EXISTS security_cameras (
    camera_id TEXT PRIMARY KEY,
    zone_id TEXT NOT NULL,
    name TEXT NOT NULL,
    floor TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'online'
        CHECK (status IN ('online', 'offline', 'fault')),
    camera_type TEXT NOT NULL DEFAULT 'fixed'
        CHECK (camera_type IN ('fixed', 'ptz', 'dome')),
    resolution TEXT DEFAULT '1080p',
    has_analytics BOOLEAN DEFAULT FALSE,
    motion_detected BOOLEAN DEFAULT FALSE,
    stream_url TEXT DEFAULT '',
    camera_model TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS security_alarm_zones (
    zone_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'disarmed'
        CHECK (status IN ('armed', 'disarmed', 'triggered', 'fault')),
    arm_type TEXT NOT NULL DEFAULT 'full'
        CHECK (arm_type IN ('full', 'perimeter', 'night')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS security_occupancy (
    id SERIAL PRIMARY KEY,
    zone_id TEXT NOT NULL,
    zone_name TEXT NOT NULL DEFAULT '',
    occupancy_count INTEGER NOT NULL DEFAULT 0,
    badge_entries INTEGER NOT NULL DEFAULT 0,
    badge_exits INTEGER NOT NULL DEFAULT 0,
    max_capacity INTEGER DEFAULT 50,
    percent_full DECIMAL(5,2) DEFAULT 0.0,
    source TEXT NOT NULL DEFAULT 'badge'
        CHECK (source IN ('badge', 'camera', 'combined')),
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_occupancy_zone
    ON security_occupancy(zone_id, last_updated DESC);
CREATE INDEX IF NOT EXISTS idx_occupancy_updated
    ON security_occupancy(last_updated DESC);

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

CREATE INDEX IF NOT EXISTS idx_access_rules_zone_id
    ON access_rules(zone_id);
CREATE INDEX IF NOT EXISTS idx_access_rules_active
    ON access_rules(active, rule_type);

CREATE TABLE IF NOT EXISTS security_anomalies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    anomaly_type TEXT NOT NULL CHECK (anomaly_type IN
        ('after_hours_access', 'forced_door', 'door_held_open',
         'anti_passback', 'controller_offline', 'energy_waste')),
    severity TEXT NOT NULL CHECK (severity IN ('warning', 'critical', 'info')),
    badge_event_id TEXT REFERENCES security_badge_events(event_id),
    zone_id TEXT,
    description TEXT NOT NULL,
    hvac_correlation JSONB,
    lighting_correlation JSONB,
    energy_impact TEXT,
    resolved BOOLEAN DEFAULT FALSE,
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

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

CREATE TABLE IF NOT EXISTS visitors (
    visitor_id TEXT PRIMARY KEY,
    site TEXT NOT NULL,
    name TEXT NOT NULL,
    company TEXT NOT NULL,
    visit_date TIMESTAMPTZ NOT NULL,
    host_contact TEXT NOT NULL,
    access_points TEXT[] DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'checked_in', 'checked_out', 'revoked')),
    checkin_time TIMESTAMPTZ,
    checkout_time TIMESTAMPTZ,
    purpose TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_visitors_site_status
    ON visitors(site, status, visit_date DESC);

CREATE TABLE IF NOT EXISTS security_alerts (
    alert_id TEXT PRIMARY KEY,
    alert_type TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    location TEXT NOT NULL,
    site_id TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('critical', 'warning', 'info')),
    status TEXT NOT NULL CHECK (status IN ('open', 'acknowledged', 'resolved')),
    description TEXT NOT NULL,
    related_events TEXT[] DEFAULT '{}',
    acknowledged_by TEXT,
    acknowledged_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_security_alerts_site_status
    ON security_alerts(site_id, status, timestamp DESC);

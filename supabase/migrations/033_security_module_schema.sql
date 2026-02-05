-- =============================================================================
-- Migration 030: Security Module Schema
-- =============================================================================
-- Phase 58-01: Access control, CCTV monitoring, occupancy tracking
-- Creates tables for security zones, doors, badge events, cameras,
-- alarm zones, and occupancy snapshots.
-- =============================================================================

-- Security access zones
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

-- Security doors
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

-- Security badge events (access log)
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
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for badge events (common query patterns)
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

-- Security cameras
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
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Security alarm zones
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

-- Security occupancy snapshots (per-zone occupancy from badge events)
CREATE TABLE IF NOT EXISTS security_occupancy (
    id SERIAL PRIMARY KEY,
    zone_id TEXT NOT NULL,
    zone_name TEXT NOT NULL DEFAULT '',
    occupancy_count INTEGER NOT NULL DEFAULT 0,
    badge_entries INTEGER NOT NULL DEFAULT 0,
    badge_exits INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'badge'
        CHECK (source IN ('badge', 'camera', 'combined')),
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for occupancy queries
CREATE INDEX IF NOT EXISTS idx_occupancy_zone
    ON security_occupancy(zone_id, last_updated DESC);
CREATE INDEX IF NOT EXISTS idx_occupancy_updated
    ON security_occupancy(last_updated DESC);

-- Performance indexes for security doors
CREATE INDEX IF NOT EXISTS idx_doors_zone_id
    ON security_doors(zone_id);
CREATE INDEX IF NOT EXISTS idx_doors_status
    ON security_doors(status);

-- Performance indexes for cameras
CREATE INDEX IF NOT EXISTS idx_cameras_zone_id
    ON security_cameras(zone_id);
CREATE INDEX IF NOT EXISTS idx_cameras_status
    ON security_cameras(status);

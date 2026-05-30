-- ============================================================================
-- Residential Devices — SENTINEL Phase 210: SIMBIOT Residential Energy Integration
-- Migration: residential_devices.sql
-- Created: 2026-05-30
-- Depends on: residential_sites.sql (must be run first)
-- ============================================================================

-- UP
CREATE TABLE IF NOT EXISTS residential_devices (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    residential_site_id  UUID        NOT NULL REFERENCES residential_sites(id) ON DELETE CASCADE,
    device_id            VARCHAR     NOT NULL,
    device_name          VARCHAR,
    device_type          VARCHAR     CHECK (device_type IN ('inverter', 'battery', 'logger', 'meter', 'other')),
    capabilities         JSONB       NOT NULL DEFAULT '[]',
    last_seen            TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(residential_site_id, device_id)
);

CREATE INDEX IF NOT EXISTS idx_residential_devices_site      ON residential_devices(residential_site_id);
CREATE INDEX IF NOT EXISTS idx_residential_devices_last_seen ON residential_devices(last_seen);

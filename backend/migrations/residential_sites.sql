-- ============================================================================
-- Residential Sites — SENTINEL Phase 210: SIMBIOT Residential Energy Integration
-- Migration: residential_sites.sql
-- Created: 2026-05-30
-- Run BEFORE: residential_devices.sql
-- ============================================================================

-- UP
CREATE TABLE IF NOT EXISTS residential_sites (
    id                       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id                  VARCHAR     NOT NULL REFERENCES sites(code),
    platform                 VARCHAR     NOT NULL CHECK (platform IN ('solarman', 'victron', 'growatt', 'fronius', 'other')),
    deployment_tier          VARCHAR     NOT NULL CHECK (deployment_tier IN ('full_simbiot', 'cloud_only')),
    site_config              JSONB       NOT NULL DEFAULT '{}',
    eskom_area_code          VARCHAR,
    tariff_type              VARCHAR     CHECK (tariff_type IN ('prepaid', 'time_of_use', 'standard')),
    polling_interval_seconds INTEGER     NOT NULL DEFAULT 300,
    is_active                BOOLEAN     NOT NULL DEFAULT true,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_residential_sites_site_id  ON residential_sites(site_id);
CREATE INDEX IF NOT EXISTS idx_residential_sites_platform ON residential_sites(platform);
CREATE INDEX IF NOT EXISTS idx_residential_sites_is_active ON residential_sites(is_active);

-- Trigger to keep updated_at current on every row update
CREATE OR REPLACE FUNCTION update_residential_sites_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER residential_sites_updated_at
    BEFORE UPDATE ON residential_sites
    FOR EACH ROW EXECUTE FUNCTION update_residential_sites_updated_at();

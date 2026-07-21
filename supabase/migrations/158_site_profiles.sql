-- Phase 191: Site Profile Foundation — Schema
-- Migration: M191_site_profiles
-- Purpose: Building profile for new site onboarding gating.
-- S002 (pilot) is unaffected — no changes to existing phase state.

CREATE TABLE IF NOT EXISTS site_profiles (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id         UUID        NOT NULL REFERENCES sites(id) ON DELETE CASCADE UNIQUE,
    building_type   TEXT        NOT NULL CHECK (building_type IN (
        'commercial_office', 'hospital', 'retail', 'mixed_use', 'industrial', 'residential'
    )),
    primary_objective  TEXT     NOT NULL CHECK (primary_objective IN (
        'cost', 'comfort', 'compliance', 'balanced'
    )),
    objective_weights  JSONB    NOT NULL DEFAULT '{"cost": 0.5, "comfort": 0.5}',
    operating_schedule  JSONB    NOT NULL DEFAULT '{}',
    tariff_structure   TEXT    NOT NULL DEFAULT 'flat' CHECK (tariff_structure IN (
        'flat', 'tou_megaflex', 'tou_miniflex', 'wheeling', 'municipal'
    )),
    on_site_generation  JSONB    NOT NULL DEFAULT '{"solar_kwp": 0, "bess_kwh": 0, "generator": false}',
    temp_band_min_c    NUMERIC(4,1) NOT NULL DEFAULT 19.0,
    temp_band_max_c    NUMERIC(4,1) NOT NULL DEFAULT 26.0,
    clinical_zones_present BOOLEAN NOT NULL DEFAULT false,
    regulatory_frameworks TEXT[] NOT NULL DEFAULT ARRAY['SANS_10400_XA'],
    confirmed_at       TIMESTAMPTZ,
    confirmed_by       TEXT,
    profile_version    INTEGER   NOT NULL DEFAULT 1,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_site_profiles_site_id ON site_profiles(site_id);

-- Automatic update of updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER site_profiles_updated_at
    BEFORE UPDATE ON site_profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

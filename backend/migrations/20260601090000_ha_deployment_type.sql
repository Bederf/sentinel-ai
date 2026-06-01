-- Migration: 20260601090000_ha_deployment_type.sql
-- Purpose: Add ha_deployment_type to residential_sites and indexes

ALTER TABLE residential_sites
  ADD COLUMN IF NOT EXISTS ha_deployment_type VARCHAR DEFAULT 'local';

-- Backfill existing HA sites to 'local' where null
UPDATE residential_sites
  SET ha_deployment_type = 'local'
  WHERE platform = 'home_assistant'
    AND (ha_deployment_type IS NULL OR ha_deployment_type = '');

-- Partial index for HA platform filtering on deployment type
CREATE INDEX IF NOT EXISTS idx_residential_sites_ha_deployment
  ON residential_sites(ha_deployment_type)
  WHERE platform = 'home_assistant';

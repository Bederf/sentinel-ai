-- Rollback: 20260601090000_ha_deployment_type_rollback.sql

-- Drop partial index if exists
DROP INDEX IF EXISTS idx_residential_sites_ha_deployment;

-- Remove column (safe only if nothing depends on it)
ALTER TABLE residential_sites
  DROP COLUMN IF EXISTS ha_deployment_type;

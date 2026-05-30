-- ============================================================================
-- Residential Sites — ROLLBACK
-- Migration: residential_sites_rollback.sql
-- Created: 2026-05-30
-- WARNING: CASCADE will also drop residential_devices if not rolled back first.
--          Run residential_devices_rollback.sql before this file to be explicit.
-- ============================================================================

-- ROLLBACK
DROP TRIGGER IF EXISTS residential_sites_updated_at ON residential_sites;
DROP FUNCTION IF EXISTS update_residential_sites_updated_at();
DROP TABLE IF EXISTS residential_sites CASCADE;

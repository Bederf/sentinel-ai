-- ============================================================================
-- Residential Devices — ROLLBACK
-- Migration: residential_devices_rollback.sql
-- Created: 2026-05-30
-- Run BEFORE: residential_sites_rollback.sql
-- ============================================================================

-- ROLLBACK
DROP TABLE IF EXISTS residential_devices CASCADE;

-- ============================================================================
-- Residential Sites — SENTINEL Phase 213: chat-id-migration
-- Rollback: 20260530203000_residential_sites_chat_id_rollback.sql
-- Created: 2026-05-30
-- ============================================================================

ALTER TABLE residential_sites
  DROP COLUMN IF EXISTS chat_id,
  DROP COLUMN IF EXISTS notification_channel,
  DROP COLUMN IF EXISTS onboarding_method;

DROP INDEX IF EXISTS idx_residential_sites_site_id_active;

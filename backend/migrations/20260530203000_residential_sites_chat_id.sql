-- ============================================================================
-- Residential Sites — SENTINEL Phase 213: chat-id-migration
-- Migration: 20260530203000_residential_sites_chat_id.sql
-- Created: 2026-05-30
-- ============================================================================

ALTER TABLE residential_sites
  ADD COLUMN chat_id BIGINT,
  ADD COLUMN notification_channel VARCHAR DEFAULT 'telegram',
  ADD COLUMN onboarding_method VARCHAR DEFAULT 'wizard';

CREATE INDEX idx_residential_sites_chat_id
  ON residential_sites(chat_id)
  WHERE chat_id IS NOT NULL;

-- Unique partial index: only one active record per site_id at DB level.
-- Prevents duplicate active sites when /connect is called twice.
CREATE UNIQUE INDEX idx_residential_sites_site_id_active
  ON residential_sites(site_id)
  WHERE is_active = true;

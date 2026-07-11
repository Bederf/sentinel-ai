-- Per-site ML training toggle. When a site passes wizard acceptance gates,
-- this is auto-flipped alongside sentinel_processing_enabled. The background
-- training jobs check this flag before running for a given site.
ALTER TABLE sites ADD COLUMN IF NOT EXISTS ml_training_enabled boolean NOT NULL DEFAULT false;

-- Backfill for site-002 (already has ML hours, should train)
UPDATE sites SET ml_training_enabled = true WHERE code IN ('site-002');

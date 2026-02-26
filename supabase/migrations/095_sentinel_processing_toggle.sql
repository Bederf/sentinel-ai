-- Phase 125: Per-building SENTINEL processing toggle
-- Adds a boolean column to buildings table to enable/disable SENTINEL intelligence
-- processing per building. When OFF, data still flows but SENTINEL ignores it
-- (no ML feeding, health monitoring, alerts, or recommendations).

ALTER TABLE buildings
  ADD COLUMN IF NOT EXISTS sentinel_processing_enabled BOOLEAN DEFAULT true;

COMMENT ON COLUMN buildings.sentinel_processing_enabled IS
  'When false, SENTINEL skips ML feeding, health monitoring, alerts, and recommendations for this building. Data persistence continues.';

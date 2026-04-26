-- Migration: 20260428_002_recommendation_shadow_mode
-- Add shadow_mode column to recommendations table
-- Shadow mode recommendations are generated and stored for ML training
-- but invisible to the frontend UI

ALTER TABLE recommendations
ADD COLUMN IF NOT EXISTS shadow_mode boolean DEFAULT false;

-- Index for efficient filtering of non-shadow recommendations
CREATE INDEX IF NOT EXISTS idx_recommendations_shadow_mode
ON recommendations(shadow_mode)
WHERE shadow_mode = false;

-- Backfill: existing recommendations are visible (shadow_mode = false)
-- No need to update anything since default is false

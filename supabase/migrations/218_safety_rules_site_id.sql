-- =====================================================
-- Migration: Add site_id column to safety_rules
-- Enables per-site safety rule scoping
-- All existing global rules (site_id=NULL) remain as fallbacks
-- =====================================================

-- Add site_id column (NULL = global fallback rule, applies to all sites)
ALTER TABLE safety_rules
ADD COLUMN site_id TEXT;

-- Index for efficient site-scoped lookups
CREATE INDEX idx_safety_rules_site_id ON safety_rules(site_id);

-- Re-enable trigger if it was dropped during schema alignment
DROP TRIGGER IF EXISTS safety_rules_updated ON safety_rules;
CREATE OR REPLACE FUNCTION update_safety_rules_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER safety_rules_updated
  BEFORE UPDATE ON safety_rules
  FOR EACH ROW
  EXECUTE FUNCTION update_safety_rules_timestamp();

-- Backfill: existing rules become global fallbacks for site-002 (primary active site)
-- site-001 is future/inactive — site-002 is the only active site
UPDATE safety_rules SET site_id = 'site-002' WHERE site_id IS NULL;

-- Add comment
COMMENT ON COLUMN safety_rules.site_id IS 'Site scope for rule. NULL means global fallback (applies to all sites). site_id column allows per-site safety thresholds.';

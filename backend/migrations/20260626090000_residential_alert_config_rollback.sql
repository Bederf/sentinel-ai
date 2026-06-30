-- Phase 222 rollback — Residential configurable alert toggles

ALTER TABLE residential_sites
  DROP CONSTRAINT IF EXISTS residential_sites_platform_check;

ALTER TABLE residential_sites
  ADD CONSTRAINT residential_sites_platform_check
  CHECK (platform IN ('solarman', 'victron', 'growatt', 'fronius', 'home_assistant', 'ha_addon', 'other'));

ALTER TABLE residential_sites
  DROP COLUMN IF EXISTS alert_config;

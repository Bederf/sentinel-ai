-- Migration: add licensed column to site_modules
-- Building system modules require explicit licensing per site.
-- Platform modules (mandatory) are always licensed — this column is
-- only meaningful for building system and add-on modules.

ALTER TABLE site_modules
  ADD COLUMN IF NOT EXISTS licensed boolean NOT NULL DEFAULT false;

ALTER TABLE site_modules
  ADD COLUMN IF NOT EXISTS connected boolean NOT NULL DEFAULT false;

-- Backfill: mark currently active building system modules as licensed
-- This preserves existing site-002 active module state
UPDATE site_modules
SET licensed = true
WHERE status = 'active'
  AND module_type IN (
    'hvac', 'energy', 'lighting', 'solar',
    'water', 'fire', 'security', 'digital_twin',
    'hvac_control', 'energy_control', 'lighting_control',
    'solar_control', 'water_control', 'security_control',
    'digital_twin_control', 'maintenance', 'financial',
    'compliance', 'sustainability', 'contracts', 'access',
    'fleet_ml', 'space_optimization', 'fuel_monitoring',
    'fuel_alerts'
  );

-- Platform modules are always effectively licensed — set to true
UPDATE site_modules
SET licensed = true
WHERE module_type IN (
    'kpi', 'ml', 'notifications', 'integrations',
    'simbiot', 'logging', 'assets'
);

-- Verify
SELECT module_type, status, licensed
FROM site_modules
WHERE site_id IN (SELECT id FROM sites WHERE code = 'site-002')
ORDER BY module_type;

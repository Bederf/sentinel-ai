-- Migration: add licensed column to site_modules
-- Building system modules require explicit licensing per site.
-- Platform modules (mandatory) are always licensed — this column is
-- only meaningful for building system and add-on modules.

ALTER TABLE site_modules
  ADD COLUMN IF NOT EXISTS licensed boolean NOT NULL DEFAULT false;

-- Backfill: mark currently active building system and add-on modules as licensed
-- This preserves existing site state — all active modules were implicitly licensed before.
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
    'fuel_alerts', 'block_booking', 'control'
  );

-- Platform modules are always effectively licensed
UPDATE site_modules
SET licensed = true
WHERE module_type IN (
    'kpi', 'ml', 'notifications', 'integrations',
    'simbiot', 'logging', 'assets'
);

-- Migration: Add control_enabled and control_note to buildings table
-- Purpose: Track which buildings have remote control capabilities enabled

ALTER TABLE buildings
ADD COLUMN IF NOT EXISTS control_enabled BOOLEAN DEFAULT FALSE;

ALTER TABLE buildings
ADD COLUMN IF NOT EXISTS control_note TEXT;

-- Update Sandton City (the demo site) to have control enabled
UPDATE buildings
SET control_enabled = TRUE,
    control_note = 'Remote control enabled 2026-01-28 - AHU, Chiller, FCU, Zone Controller'
WHERE code = 'site-001';

-- Add comment for documentation
COMMENT ON COLUMN buildings.control_enabled IS 'Whether remote control is enabled for this building';
COMMENT ON COLUMN buildings.control_note IS 'Notes about control capabilities/configuration';

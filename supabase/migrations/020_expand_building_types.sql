-- Migration: 020_expand_building_types.sql
-- Description: Expand building type constraint to support more building types
-- Types: regional_office, branch, retail, hospital, data_centre
-- Note: Uses data_centre (British spelling) for consistency with South African codebase

-- Drop the existing constraint
ALTER TABLE buildings DROP CONSTRAINT IF EXISTS buildings_type_check;

-- Add expanded constraint with all building types
ALTER TABLE buildings ADD CONSTRAINT buildings_type_check 
  CHECK (type IN ('regional_office', 'branch', 'retail', 'hospital', 'data_centre'));

-- Update any legacy 'data_center' values to 'data_centre' (if they exist)
UPDATE buildings SET type = 'data_centre' WHERE type = 'data_center';

-- Comment for documentation
COMMENT ON COLUMN buildings.type IS 'Building type: regional_office, branch, retail, hospital, data_centre';

-- Update buildings with correct types from legacy sites.json data
-- Match by name since that's the reliable identifier

-- Retail buildings
UPDATE buildings SET type = 'retail' WHERE name ILIKE '%Centurion Mall%';
UPDATE buildings SET type = 'retail' WHERE name ILIKE '%V&A Waterfront%';
UPDATE buildings SET type = 'retail' WHERE name ILIKE '%Gateway Theatre%';

-- Hospital buildings
UPDATE buildings SET type = 'hospital' WHERE name ILIKE '%Mediclinic%';

-- Branch offices
UPDATE buildings SET type = 'branch' WHERE name ILIKE '%Standard Bank Rosebank%';

-- Regional offices (default for office buildings without specific type)
UPDATE buildings SET type = 'regional_office' WHERE name ILIKE '%Rosebank Towers%';
UPDATE buildings SET type = 'regional_office' WHERE name ILIKE '%Sandton City Office%';
UPDATE buildings SET type = 'regional_office' WHERE name ILIKE '%Standard Bank Centre%';
UPDATE buildings SET type = 'regional_office' WHERE name ILIKE '%Standard Bank Durban%';

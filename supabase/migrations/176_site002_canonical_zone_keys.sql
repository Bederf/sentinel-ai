-- Site-002 zone inventory is owned by Supabase zones/hvac_zones.
-- Normalize active equipment.zone_key values to those canonical IDs and clear
-- ambiguous panel/floor-level values that are not real zones.

WITH site AS (
  SELECT id FROM public.sites WHERE code = 'site-002'
)
UPDATE public.equipment
SET zone_key = CASE
  WHEN zone_key = 'B1' THEN 'Zone-B'
  WHEN zone_key = 'Roof' THEN 'Zone-R'
  WHEN zone_key ~ '^Zone-L[0-2]-[1-5]$' THEN
    'Zone-' ||
    replace(split_part(zone_key, '-', 2), 'L', '') ||
    lpad(split_part(zone_key, '-', 3), 2, '0')
  WHEN code = 'S002-LUM-101' THEN 'Zone-101'
  WHEN code = 'S002-DALI-1001' THEN NULL
  WHEN code IN ('S002-LTG-021', 'S002-LTG-041', 'S002-LTG-061', 'S002-LTG-081') THEN NULL
  ELSE zone_key
END,
updated_at = NOW()
WHERE site_id = (SELECT id FROM site)
  AND (
    zone_key IN ('B1', 'Roof')
    OR zone_key ~ '^Zone-L[0-2]-[1-5]$'
    OR code IN ('S002-LUM-101', 'S002-DALI-1001', 'S002-LTG-021', 'S002-LTG-041', 'S002-LTG-061', 'S002-LTG-081')
  );

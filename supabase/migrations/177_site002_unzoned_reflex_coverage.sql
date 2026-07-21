-- Close one unambiguous S002 reflex coverage gap and leave multi-zone/floor
-- lighting controllers visible through reflex_zone_resolution_gaps.

WITH site AS (
  SELECT id FROM public.sites WHERE code = 'site-002'
)
UPDATE public.equipment
SET zone_key = 'Zone-201',
    updated_at = NOW()
WHERE site_id = (SELECT id FROM site)
  AND code = 'S002-AHU-L2-001'
  AND (zone_key IS NULL OR zone_key = '');

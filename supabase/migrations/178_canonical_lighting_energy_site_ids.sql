-- Canonicalise DALI lighting site identifiers.
--
-- Equipment codes still use the building prefix (for example S002-DALI-L1-CTR),
-- but database site_id values must use the canonical site code format
-- (site-002, site-005, ...). The live S002 DALI energy rows were using S002,
-- which made them invisible to services querying by site-002.

UPDATE public.lighting_energy
SET site_id = 'site-002'
WHERE site_id = 'S002';

ALTER TABLE public.lighting_energy
DROP CONSTRAINT IF EXISTS lighting_energy_site_id_canonical_format;

ALTER TABLE public.lighting_energy
ADD CONSTRAINT lighting_energy_site_id_canonical_format
CHECK (site_id ~ '^site-[0-9]{3}$');

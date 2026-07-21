-- Canonicalise remaining active-site text site_id values.
--
-- The canonical database site identifier is site-###. Equipment identifiers may
-- still use prefixes such as S002-..., but site_id columns must not use S002/S005.

UPDATE public.commissioning_scorecards
SET site_id = 'site-002'
WHERE site_id = 'S002';

UPDATE public.cross_module_links
SET site_id = 'site-002'
WHERE site_id = 'S002';

UPDATE public.equipment_fault_events
SET site_id = 'site-002'
WHERE site_id = 'S002';

UPDATE public.equipment_fault_events
SET site_id = 'site-005'
WHERE site_id = 'S005';

UPDATE public.parasite_decisions
SET site_id = 'site-002'
WHERE site_id = 'S002';

DELETE FROM public.site_module_configs
WHERE site_id = 'S002'
  AND EXISTS (
    SELECT 1
    FROM public.site_module_configs canonical
    WHERE canonical.site_id = 'site-002'
  );

UPDATE public.site_module_configs
SET site_id = 'site-002'
WHERE site_id = 'S002';

UPDATE public.site_module_configs
SET site_name = 'Sandton City Office Tower Updated'
WHERE site_id = 'site-002';

ALTER TABLE public.cross_module_links
DROP CONSTRAINT IF EXISTS cross_module_links_site_id_canonical_format;

ALTER TABLE public.cross_module_links
ADD CONSTRAINT cross_module_links_site_id_canonical_format
CHECK (site_id ~ '^site-[0-9]{3}$');

ALTER TABLE public.equipment_fault_events
DROP CONSTRAINT IF EXISTS equipment_fault_events_site_id_canonical_format;

ALTER TABLE public.equipment_fault_events
ADD CONSTRAINT equipment_fault_events_site_id_canonical_format
CHECK (site_id ~ '^site-[0-9]{3}$');

ALTER TABLE public.parasite_decisions
DROP CONSTRAINT IF EXISTS parasite_decisions_site_id_canonical_format;

ALTER TABLE public.parasite_decisions
ADD CONSTRAINT parasite_decisions_site_id_canonical_format
CHECK (site_id ~ '^site-[0-9]{3}$');

ALTER TABLE public.site_module_configs
DROP CONSTRAINT IF EXISTS site_module_configs_site_id_canonical_format;

ALTER TABLE public.site_module_configs
ADD CONSTRAINT site_module_configs_site_id_canonical_format
CHECK (site_id ~ '^site-[0-9]{3}$');

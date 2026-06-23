-- Add denormalized zone-equipment columns used by runtime gate and bridge paths.
--
-- The onboarding pipeline writes canonical equipment relationships into
-- equipment_zone_relationships, but several live read paths still expect the
-- zone tables to expose direct pointers for FCU / VAV / AHU / lighting.

ALTER TABLE public.zones
    ADD COLUMN IF NOT EXISTS fcu_id TEXT,
    ADD COLUMN IF NOT EXISTS vav_id TEXT,
    ADD COLUMN IF NOT EXISTS ahu_id TEXT,
    ADD COLUMN IF NOT EXISTS lighting_id TEXT;

ALTER TABLE public.hvac_zones
    ADD COLUMN IF NOT EXISTS fcu_id TEXT,
    ADD COLUMN IF NOT EXISTS vav_id TEXT,
    ADD COLUMN IF NOT EXISTS ahu_id TEXT,
    ADD COLUMN IF NOT EXISTS lighting_id TEXT;

WITH zone_equipment AS (
    SELECT
        site_id,
        zone_id,
        max(CASE WHEN eq_type = 'fcu' THEN eq_code END) AS fcu_id,
        max(CASE WHEN eq_type = 'vav' THEN eq_code END) AS vav_id,
        max(CASE WHEN eq_type = 'ahu' THEN eq_code END) AS ahu_id,
        max(CASE WHEN eq_type IN ('dali', 'lum', 'lighting', 'lighting_panel', 'zone') THEN eq_code END) AS lighting_id
    FROM (
        SELECT
            ez.site_id,
            ez.zone_id,
            lower(COALESCE(e.type, '')) AS eq_type,
            COALESCE(NULLIF(e.canonical_code, ''), NULLIF(e.code, ''), NULLIF(e.raw_code, '')) AS eq_code
        FROM public.equipment_zone_relationships ez
        JOIN public.equipment e ON e.id = ez.equipment_id
        WHERE ez.review_status IS DISTINCT FROM 'rejected'
        UNION ALL
        SELECT
            e.site_id,
            COALESCE(NULLIF(e.zone_key, ''), NULLIF(e.canonical_zone_id, '')) AS zone_id,
            lower(COALESCE(e.type, '')) AS eq_type,
            COALESCE(NULLIF(e.canonical_code, ''), NULLIF(e.code, ''), NULLIF(e.raw_code, '')) AS eq_code
        FROM public.equipment e
        WHERE COALESCE(NULLIF(e.zone_key, ''), NULLIF(e.canonical_zone_id, '')) IS NOT NULL
    ) AS mapped
    WHERE zone_id IS NOT NULL
    GROUP BY site_id, zone_id
)
UPDATE public.zones z
SET
    fcu_id = COALESCE(NULLIF(z.fcu_id, ''), ze.fcu_id),
    vav_id = COALESCE(NULLIF(z.vav_id, ''), ze.vav_id),
    ahu_id = COALESCE(NULLIF(z.ahu_id, ''), ze.ahu_id),
    lighting_id = COALESCE(NULLIF(z.lighting_id, ''), ze.lighting_id)
FROM zone_equipment ze
WHERE z.site_id = ze.site_id
  AND z.zone_id = ze.zone_id;

WITH zone_equipment AS (
    SELECT
        site_id,
        zone_id,
        max(CASE WHEN eq_type = 'fcu' THEN eq_code END) AS fcu_id,
        max(CASE WHEN eq_type = 'vav' THEN eq_code END) AS vav_id,
        max(CASE WHEN eq_type = 'ahu' THEN eq_code END) AS ahu_id,
        max(CASE WHEN eq_type IN ('dali', 'lum', 'lighting', 'lighting_panel', 'zone') THEN eq_code END) AS lighting_id
    FROM (
        SELECT
            ez.site_id,
            ez.zone_id,
            lower(COALESCE(e.type, '')) AS eq_type,
            COALESCE(NULLIF(e.canonical_code, ''), NULLIF(e.code, ''), NULLIF(e.raw_code, '')) AS eq_code
        FROM public.equipment_zone_relationships ez
        JOIN public.equipment e ON e.id = ez.equipment_id
        WHERE ez.review_status IS DISTINCT FROM 'rejected'
        UNION ALL
        SELECT
            e.site_id,
            COALESCE(NULLIF(e.zone_key, ''), NULLIF(e.canonical_zone_id, '')) AS zone_id,
            lower(COALESCE(e.type, '')) AS eq_type,
            COALESCE(NULLIF(e.canonical_code, ''), NULLIF(e.code, ''), NULLIF(e.raw_code, '')) AS eq_code
        FROM public.equipment e
        WHERE COALESCE(NULLIF(e.zone_key, ''), NULLIF(e.canonical_zone_id, '')) IS NOT NULL
    ) AS mapped
    WHERE zone_id IS NOT NULL
    GROUP BY site_id, zone_id
)
UPDATE public.hvac_zones z
SET
    fcu_id = COALESCE(NULLIF(z.fcu_id, ''), ze.fcu_id),
    vav_id = COALESCE(NULLIF(z.vav_id, ''), ze.vav_id),
    ahu_id = COALESCE(NULLIF(z.ahu_id, ''), ze.ahu_id),
    lighting_id = COALESCE(NULLIF(z.lighting_id, ''), ze.lighting_id)
FROM zone_equipment ze
WHERE z.site_id = ze.site_id
  AND z.zone_id = ze.zone_id;

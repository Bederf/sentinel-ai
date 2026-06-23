-- Equipment canonicalization support.
-- This preserves current equipment.code while storing the intended SENTINEL
-- canonical code, raw/source code, canonical zone, aliases, and zone
-- relationships for reviewed backfills.

ALTER TABLE public.equipment
    ADD COLUMN IF NOT EXISTS raw_code TEXT,
    ADD COLUMN IF NOT EXISTS canonical_code TEXT,
    ADD COLUMN IF NOT EXISTS canonical_zone_id TEXT,
    ADD COLUMN IF NOT EXISTS canonicalization_status TEXT NOT NULL DEFAULT 'unreviewed'
        CHECK (canonicalization_status IN (
            'unreviewed',
            'canonical',
            'source_alias',
            'point_level_source',
            'plant_alias',
            'needs_review'
        )),
    ADD COLUMN IF NOT EXISTS canonicalization_source TEXT,
    ADD COLUMN IF NOT EXISTS canonicalization_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_equipment_canonical_code
    ON public.equipment (canonical_code);

CREATE INDEX IF NOT EXISTS idx_equipment_canonical_zone
    ON public.equipment (site_id, canonical_zone_id);

CREATE INDEX IF NOT EXISTS idx_equipment_canonicalization_status
    ON public.equipment (site_id, canonicalization_status);

CREATE TABLE IF NOT EXISTS public.equipment_aliases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES public.sites(id) ON DELETE CASCADE,
    equipment_id UUID NOT NULL REFERENCES public.equipment(id) ON DELETE CASCADE,
    alias_code TEXT NOT NULL,
    canonical_code TEXT NOT NULL,
    alias_type TEXT NOT NULL DEFAULT 'source'
        CHECK (alias_type IN ('source', 'legacy', 'display', 'point_source')),
    source TEXT NOT NULL DEFAULT 'onboarding',
    confidence NUMERIC(4, 3) NOT NULL DEFAULT 1.0
        CHECK (confidence >= 0 AND confidence <= 1),
    review_status TEXT NOT NULL DEFAULT 'approved'
        CHECK (review_status IN ('suggested', 'approved', 'rejected')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (site_id, alias_code)
);

CREATE INDEX IF NOT EXISTS idx_equipment_aliases_site_canonical
    ON public.equipment_aliases (site_id, canonical_code);

CREATE INDEX IF NOT EXISTS idx_equipment_aliases_equipment
    ON public.equipment_aliases (equipment_id);

CREATE TABLE IF NOT EXISTS public.equipment_zone_relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES public.sites(id) ON DELETE CASCADE,
    equipment_id UUID NOT NULL REFERENCES public.equipment(id) ON DELETE CASCADE,
    zone_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL
        CHECK (relationship_type IN ('serves', 'located_in', 'controls', 'monitors', 'plant')),
    source TEXT NOT NULL DEFAULT 'onboarding',
    confidence NUMERIC(4, 3) NOT NULL DEFAULT 1.0
        CHECK (confidence >= 0 AND confidence <= 1),
    review_status TEXT NOT NULL DEFAULT 'approved'
        CHECK (review_status IN ('suggested', 'approved', 'rejected')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (equipment_id, zone_id, relationship_type)
);

CREATE INDEX IF NOT EXISTS idx_equipment_zone_relationships_site_zone
    ON public.equipment_zone_relationships (site_id, zone_id);

CREATE INDEX IF NOT EXISTS idx_equipment_zone_relationships_equipment
    ON public.equipment_zone_relationships (equipment_id);

CREATE TABLE IF NOT EXISTS public.equipment_relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES public.sites(id) ON DELETE CASCADE,
    parent_canonical_code TEXT NOT NULL,
    child_canonical_code TEXT NOT NULL,
    relationship_type TEXT NOT NULL
        CHECK (relationship_type IN ('controls', 'manages', 'feeds', 'contains', 'monitors', 'parent_of', 'serves', 'located_in')),
    source TEXT NOT NULL DEFAULT 'onboarding',
    confidence NUMERIC(4, 3) NOT NULL DEFAULT 1.0
        CHECK (confidence >= 0 AND confidence <= 1),
    review_status TEXT NOT NULL DEFAULT 'approved'
        CHECK (review_status IN ('suggested', 'approved', 'rejected')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (parent_canonical_code <> child_canonical_code),
    UNIQUE (site_id, parent_canonical_code, child_canonical_code, relationship_type)
);

CREATE INDEX IF NOT EXISTS idx_equipment_relationships_site_parent
    ON public.equipment_relationships (site_id, parent_canonical_code);

CREATE INDEX IF NOT EXISTS idx_equipment_relationships_site_child
    ON public.equipment_relationships (site_id, child_canonical_code);

ALTER TABLE public.equipment_relationships
    DROP CONSTRAINT IF EXISTS equipment_relationships_relationship_type_check;

ALTER TABLE public.equipment_relationships
    ADD CONSTRAINT equipment_relationships_relationship_type_check
    CHECK (relationship_type IN ('controls', 'manages', 'feeds', 'contains', 'monitors', 'parent_of', 'serves', 'located_in'));

DO $$
DECLARE
    v_site_id UUID;
BEGIN
    SELECT id INTO v_site_id
    FROM public.sites
    WHERE code = 'site-005'
    LIMIT 1;

    IF v_site_id IS NULL THEN
        RAISE NOTICE 'site-005 not found; skipping equipment canonicalization seed';
        RETURN;
    END IF;

    UPDATE public.equipment
    SET raw_code = COALESCE(raw_code, code)
    WHERE site_id = v_site_id;

    -- Existing occupied-zone codes that point at known canonical S005 zones.
    WITH mapped AS (
        SELECT
            e.id,
            e.site_id,
            e.code,
            substring(e.code from '^S005-[A-Z]+-([0-9]{3})$') AS zone_num,
            substring(e.code from '^S005-([A-Z]+)-[0-9]{3}$') AS equipment_type
        FROM public.equipment e
        JOIN public.zones z
          ON z.site_id = e.site_id
         AND z.zone_id = 'Zone-' || substring(e.code from '^S005-[A-Z]+-([0-9]{3})$')
        WHERE e.site_id = v_site_id
          AND e.code ~ '^S005-[A-Z]+-[0-9]{3}$'
    )
    UPDATE public.equipment e
    SET canonical_code = mapped.code,
        canonical_zone_id = 'Zone-' || mapped.zone_num,
        zone_key = COALESCE(NULLIF(e.zone_key, ''), 'Zone-' || mapped.zone_num),
        canonicalization_status = 'canonical',
        canonicalization_source = 'site005_equipment_canonical_seed',
        canonicalization_metadata = jsonb_build_object(
            'reason', 'existing_code_matches_known_canonical_zone',
            'equipment_type', mapped.equipment_type
        ),
        updated_at = NOW()
    FROM mapped
    WHERE e.id = mapped.id;

    INSERT INTO public.equipment_zone_relationships
        (site_id, equipment_id, zone_id, relationship_type, source, confidence, review_status, metadata)
    SELECT
        e.site_id,
        e.id,
        e.canonical_zone_id,
        CASE
            WHEN lower(e.type) IN ('ahu', 'fcu', 'vav', 'split', 'dali', 'lum') THEN 'serves'
            ELSE 'located_in'
        END,
        'site005_equipment_canonical_seed',
        1.0,
        'approved',
        jsonb_build_object('reason', 'existing_canonical_equipment_zone')
    FROM public.equipment e
    WHERE e.site_id = v_site_id
      AND e.canonicalization_status = 'canonical'
      AND e.canonical_zone_id IS NOT NULL
    ON CONFLICT (equipment_id, zone_id, relationship_type) DO UPDATE
    SET source = EXCLUDED.source,
        confidence = EXCLUDED.confidence,
        review_status = EXCLUDED.review_status,
        metadata = EXCLUDED.metadata,
        updated_at = NOW();

    -- Compact plant legacy codes such as S005-CT-R01 -> S005-CT-R-001.
    WITH plant AS (
        SELECT
            e.id,
            e.site_id,
            e.code,
            COALESCE(b.parts[1], r.parts[1]) AS equipment_type,
            CASE WHEN b.parts IS NOT NULL THEN 'B1' ELSE 'R' END AS plant_floor,
            COALESCE(b.parts[2], r.parts[2]) AS plant_seq
        FROM public.equipment e
        LEFT JOIN LATERAL regexp_match(e.code, '^S005-([A-Z]+)-B0*([0-9]+)$') AS b(parts) ON TRUE
        LEFT JOIN LATERAL regexp_match(e.code, '^S005-([A-Z]+)-R0*([0-9]+)$') AS r(parts) ON TRUE
        WHERE e.site_id = v_site_id
          AND e.code ~ '^S005-[A-Z]+-(B[0-9]|R)[0-9]+$'
          AND (b.parts IS NOT NULL OR r.parts IS NOT NULL)
    ),
    plant_codes AS (
        SELECT
            *,
            'S005-' || equipment_type || '-' || plant_floor || '-' || lpad(plant_seq, 3, '0') AS desired_code,
            'Zone-' || plant_floor || '-' || lpad(plant_seq, 3, '0') AS plant_zone
        FROM plant
    )
    UPDATE public.equipment e
    SET canonical_code = plant_codes.desired_code,
        canonical_zone_id = plant_codes.plant_zone,
        zone_key = COALESCE(NULLIF(e.zone_key, ''), plant_codes.plant_zone),
        canonicalization_status = 'plant_alias',
        canonicalization_source = 'site005_equipment_canonical_seed',
        canonicalization_metadata = jsonb_build_object(
            'reason', 'compact_plant_code_alias',
            'legacy_code', plant_codes.code
        ),
        updated_at = NOW()
    FROM plant_codes
    WHERE e.id = plant_codes.id;

    WITH plant_codes AS (
        SELECT
            e.*,
            e.canonical_code AS desired_code
        FROM public.equipment e
        WHERE e.site_id = v_site_id
          AND e.canonicalization_status = 'plant_alias'
          AND e.canonical_code IS NOT NULL
    )
    INSERT INTO public.equipment_aliases
        (site_id, equipment_id, alias_code, canonical_code, alias_type, source, confidence, review_status, metadata)
    SELECT
        site_id,
        id,
        code,
        desired_code,
        'legacy',
        'site005_equipment_canonical_seed',
        1.0,
        'approved',
        jsonb_build_object('reason', 'compact_plant_code_alias')
    FROM plant_codes
    ON CONFLICT (site_id, alias_code) DO UPDATE
    SET equipment_id = EXCLUDED.equipment_id,
        canonical_code = EXCLUDED.canonical_code,
        alias_type = EXCLUDED.alias_type,
        source = EXCLUDED.source,
        confidence = EXCLUDED.confidence,
        review_status = EXCLUDED.review_status,
        metadata = EXCLUDED.metadata,
        updated_at = NOW();

    DELETE FROM public.equipment_zone_relationships ez
    USING public.equipment e
    WHERE ez.equipment_id = e.id
      AND e.site_id = v_site_id
      AND ez.source = 'site005_equipment_canonical_seed'
      AND ez.relationship_type = 'plant'
      AND ez.zone_id LIKE 'Zone-B0-%';

    INSERT INTO public.equipment_zone_relationships
        (site_id, equipment_id, zone_id, relationship_type, source, confidence, review_status, metadata)
    SELECT
        site_id,
        id,
        canonical_zone_id,
        'plant',
        'site005_equipment_canonical_seed',
        1.0,
        'approved',
        jsonb_build_object('reason', 'compact_plant_code_alias')
    FROM public.equipment
    WHERE site_id = v_site_id
      AND canonicalization_status = 'plant_alias'
      AND canonical_zone_id IS NOT NULL
    ON CONFLICT (equipment_id, zone_id, relationship_type) DO UPDATE
    SET source = EXCLUDED.source,
        confidence = EXCLUDED.confidence,
        review_status = EXCLUDED.review_status,
        metadata = EXCLUDED.metadata,
        updated_at = NOW();

    -- Raw source rows with a resolvable source zone alias. These rows often
    -- represent point-level source objects, so store the intended canonical
    -- equipment code without changing equipment.code.
    WITH raw_parse AS (
        SELECT
            e.id,
            e.site_id,
            e.code,
            upper((regexp_match(e.code, '^site-005-UMH-([A-Z]+)-(B[0-9]|R|L[0-9]+)-([A-Z0-9]+)(?:[.-].*)?$'))[1]) AS equipment_type,
            upper((regexp_match(e.code, '^site-005-UMH-([A-Z]+)-(B[0-9]|R|L[0-9]+)-([A-Z0-9]+)(?:[.-].*)?$'))[2]) AS floor_code,
            upper((regexp_match(e.code, '^site-005-UMH-([A-Z]+)-(B[0-9]|R|L[0-9]+)-([A-Z0-9]+)(?:[.-].*)?$'))[3]) AS source_zone,
            position('.' in e.code) > 0 AS has_point_suffix
        FROM public.equipment e
        WHERE e.site_id = v_site_id
          AND e.code ~ '^site-005-UMH-[A-Z]+-(B[0-9]|R|L[0-9]+)-[A-Z0-9]+'
    ),
    raw_alias AS (
        SELECT
            rp.*,
            CASE
                WHEN rp.floor_code IN ('R') THEN 'Zone-' || rp.floor_code || '-' || lpad(rp.source_zone, 3, '0')
                WHEN rp.floor_code LIKE 'B%' THEN 'Zone-' || rp.floor_code || '-' || lpad(rp.source_zone, 3, '0')
                WHEN rp.source_zone ~ '^[0-9]+$' THEN 'Zone-' || rp.floor_code || '-' || lpad(rp.source_zone, 3, '0')
                ELSE 'Zone-' || rp.floor_code || '-' || rp.source_zone
            END AS alias_key
        FROM raw_parse rp
    ),
    resolved AS (
        SELECT
            ra.*,
            za.canonical_zone_id
        FROM raw_alias ra
        JOIN public.zone_aliases za
          ON za.site_id = ra.site_id
         AND za.alias_key = ra.alias_key
         AND za.review_status = 'approved'
    ),
    desired AS (
        SELECT
            *,
            'S005-' || equipment_type || '-' || substring(canonical_zone_id from '^Zone-([0-9]{3})$') AS desired_code
        FROM resolved
        WHERE canonical_zone_id ~ '^Zone-[0-9]{3}$'
    )
    UPDATE public.equipment e
    SET canonical_code = desired.desired_code,
        canonical_zone_id = desired.canonical_zone_id,
        canonicalization_status = CASE WHEN desired.has_point_suffix THEN 'point_level_source' ELSE 'source_alias' END,
        canonicalization_source = 'site005_equipment_canonical_seed',
        canonicalization_metadata = jsonb_build_object(
            'reason', 'raw_source_zone_alias_resolved',
            'source_zone_alias', desired.alias_key,
            'has_point_suffix', desired.has_point_suffix
        ),
        updated_at = NOW()
    FROM desired
    WHERE e.id = desired.id;

    -- Raw source plant rows that use basement/roof identifiers instead of an
    -- occupied-zone alias. Examples:
    --   S005-site-005-UMH-AHU-B01       -> S005-AHU-B1-001
    --   site-005-UMH-CT-R-001.fan      -> S005-CT-R-001
    WITH plant_source_parse AS (
        SELECT
            e.id,
            e.site_id,
            e.code,
            upper(COALESCE(b.parts[2], r.parts[2])) AS equipment_type,
            CASE WHEN b.parts IS NOT NULL THEN 'B' || b.parts[3] ELSE 'R' END AS plant_floor,
            CASE WHEN b.parts IS NOT NULL THEN '001' ELSE lpad(r.parts[3], 3, '0') END AS plant_seq,
            position('.' in e.code) > 0 AS has_point_suffix
        FROM public.equipment e
        LEFT JOIN LATERAL regexp_match(e.code, '^(S005-)?site-005-UMH-([A-Z]+)-B0*([0-9]+)([.].*)?$') AS b(parts) ON TRUE
        LEFT JOIN LATERAL regexp_match(e.code, '^(S005-)?site-005-UMH-([A-Z]+)-R-?0*([0-9]+)([.].*)?$') AS r(parts) ON TRUE
        WHERE e.site_id = v_site_id
          AND (b.parts IS NOT NULL OR r.parts IS NOT NULL)
    ),
    plant_source_desired AS (
        SELECT
            *,
            'S005-' || equipment_type || '-' || plant_floor || '-' || plant_seq AS desired_code,
            'Zone-' || plant_floor || '-' || plant_seq AS plant_zone
        FROM plant_source_parse
    )
    UPDATE public.equipment e
    SET canonical_code = psd.desired_code,
        canonical_zone_id = psd.plant_zone,
        zone_key = COALESCE(NULLIF(e.zone_key, ''), psd.plant_zone),
        canonicalization_status = CASE WHEN psd.has_point_suffix THEN 'point_level_source' ELSE 'source_alias' END,
        canonicalization_source = 'site005_equipment_canonical_seed',
        canonicalization_metadata = jsonb_build_object(
            'reason', 'raw_source_plant_alias_resolved',
            'plant_floor', psd.plant_floor,
            'plant_sequence', psd.plant_seq,
            'has_point_suffix', psd.has_point_suffix
        ),
        updated_at = NOW()
    FROM plant_source_desired psd
    WHERE e.id = psd.id;

    WITH resolved AS (
        SELECT *
        FROM public.equipment
        WHERE site_id = v_site_id
          AND canonicalization_status IN ('source_alias', 'point_level_source')
          AND canonical_code IS NOT NULL
    )
    INSERT INTO public.equipment_aliases
        (site_id, equipment_id, alias_code, canonical_code, alias_type, source, confidence, review_status, metadata)
    SELECT
        site_id,
        id,
        code,
        canonical_code,
        CASE WHEN canonicalization_status = 'point_level_source' THEN 'point_source' ELSE 'source' END,
        'site005_equipment_canonical_seed',
        0.95,
        'approved',
        canonicalization_metadata
    FROM resolved
    ON CONFLICT (site_id, alias_code) DO UPDATE
    SET equipment_id = EXCLUDED.equipment_id,
        canonical_code = EXCLUDED.canonical_code,
        alias_type = EXCLUDED.alias_type,
        source = EXCLUDED.source,
        confidence = EXCLUDED.confidence,
        review_status = EXCLUDED.review_status,
        metadata = EXCLUDED.metadata,
        updated_at = NOW();

    DELETE FROM public.equipment_zone_relationships ez
    USING public.equipment e
    WHERE ez.equipment_id = e.id
      AND e.site_id = v_site_id
      AND ez.source = 'site005_equipment_canonical_seed'
      AND ez.relationship_type = 'serves'
      AND e.canonical_zone_id ~ '^Zone-(B[0-9]+|R)-[0-9]{3}$';

    INSERT INTO public.equipment_zone_relationships
        (site_id, equipment_id, zone_id, relationship_type, source, confidence, review_status, metadata)
    SELECT
        site_id,
        id,
        canonical_zone_id,
        CASE
            WHEN canonicalization_status = 'point_level_source' THEN 'monitors'
            WHEN canonical_zone_id ~ '^Zone-(B[0-9]+|R)-[0-9]{3}$' THEN 'plant'
            ELSE 'serves'
        END,
        'site005_equipment_canonical_seed',
        0.95,
        'approved',
        canonicalization_metadata
    FROM public.equipment
    WHERE site_id = v_site_id
      AND canonicalization_status IN ('source_alias', 'point_level_source')
      AND canonical_zone_id IS NOT NULL
    ON CONFLICT (equipment_id, zone_id, relationship_type) DO UPDATE
    SET source = EXCLUDED.source,
        confidence = EXCLUDED.confidence,
        review_status = EXCLUDED.review_status,
        metadata = EXCLUDED.metadata,
        updated_at = NOW();

    UPDATE public.equipment
    SET canonicalization_status = 'needs_review',
        canonicalization_source = COALESCE(canonicalization_source, 'site005_equipment_canonical_seed'),
        canonicalization_metadata = CASE
            WHEN canonicalization_metadata = '{}'::jsonb
                THEN jsonb_build_object('reason', 'no_safe_canonical_equipment_mapping')
            ELSE canonicalization_metadata
        END,
        updated_at = NOW()
    WHERE site_id = v_site_id
      AND canonicalization_status = 'unreviewed';
END $$;

-- Canonicalize site-005 seed zones without creating unused floor ranges.
-- Existing source labels are preserved in zone_aliases.

DO $$
DECLARE
    v_site_id UUID;
    rec RECORD;
BEGIN
    SELECT id INTO v_site_id
    FROM public.sites
    WHERE code = 'site-005'
    LIMIT 1;

    IF v_site_id IS NULL THEN
        RAISE NOTICE 'site-005 not found; skipping canonical zone seed';
        RETURN;
    END IF;

    CREATE TEMP TABLE tmp_site005_zone_map (
        old_zone_id TEXT PRIMARY KEY,
        new_zone_id TEXT NOT NULL,
        zone_name TEXT NOT NULL,
        floor TEXT NOT NULL,
        zone_letter TEXT NOT NULL,
        zone_type TEXT NOT NULL,
        typical_occupancy INTEGER
    ) ON COMMIT DROP;

    INSERT INTO tmp_site005_zone_map
        (old_zone_id, new_zone_id, zone_name, floor, zone_letter, zone_type, typical_occupancy)
    VALUES
        ('Zone-G-001',  'Zone-001', 'Ground Zone 001',       'G',  '001', 'hospital_zone', NULL),
        ('Zone-L1-001', 'Zone-100', 'Level 1 Zone 001',      'L1', '001', 'hospital_zone', NULL),
        ('Zone-L1-002', 'Zone-101', 'Level 1 Zone 002',      'L1', '002', 'hospital_zone', NULL),
        ('Zone-L2-001', 'Zone-200', 'Level 2 Zone 001',      'L2', '001', 'hospital_zone', NULL),
        ('Zone-L2-002', 'Zone-201', 'Level 2 Zone 002',      'L2', '002', 'hospital_zone', NULL),
        ('Zone-L3-ICU', 'Zone-300', 'Level 3 ICU',           'L3', 'ICU', 'icu',           NULL),
        ('Zone-L3-TH1', 'Zone-301', 'Level 3 Theatre 1',     'L3', 'TH1', 'theatre',       NULL),
        ('Zone-L3-TH2', 'Zone-302', 'Level 3 Theatre 2',     'L3', 'TH2', 'theatre',       NULL),
        ('Zone-L3-TH3', 'Zone-303', 'Level 3 Theatre 3',     'L3', 'TH3', 'theatre',       NULL),
        ('Zone-L4-001', 'Zone-400', 'Level 4 Zone 001',      'L4', '001', 'hospital_zone', NULL),
        ('Zone-L4-002', 'Zone-401', 'Level 4 Zone 002',      'L4', '002', 'hospital_zone', NULL),
        ('Zone-L5-001', 'Zone-500', 'Level 5 Zone 001',      'L5', '001', 'hospital_zone', NULL),
        ('Zone-L5-002', 'Zone-501', 'Level 5 Zone 002',      'L5', '002', 'hospital_zone', NULL),
        ('Zone-L6-001', 'Zone-600', 'Level 6 Zone 001',      'L6', '001', 'hospital_zone', NULL),
        ('Zone-L6-002', 'Zone-601', 'Level 6 Zone 002',      'L6', '002', 'hospital_zone', NULL),
        ('Zone-L7-001', 'Zone-700', 'Level 7 Zone 001',      'L7', '001', 'hospital_zone', NULL),
        ('Zone-L8-001', 'Zone-800', 'Level 8 Zone 001',      'L8', '001', 'hospital_zone', NULL),
        ('Zone-L9-001', 'Zone-900', 'Level 9 Zone 001',      'L9', '001', 'hospital_zone', NULL);

    FOR rec IN SELECT * FROM tmp_site005_zone_map LOOP
        IF EXISTS (
            SELECT 1 FROM public.zones
            WHERE site_id = v_site_id AND zone_id = rec.old_zone_id
        ) THEN
            UPDATE public.zones
            SET zone_id = rec.new_zone_id,
                zone_name = rec.zone_name,
                floor = rec.floor,
                zone_letter = rec.zone_letter,
                zone_type = rec.zone_type,
                typical_occupancy = COALESCE(public.zones.typical_occupancy, rec.typical_occupancy),
                updated_at = NOW()
            WHERE site_id = v_site_id
              AND zone_id = rec.old_zone_id;
        ELSE
            INSERT INTO public.zones
                (site_id, zone_id, zone_name, floor, zone_letter, zone_type, typical_occupancy)
            VALUES
                (v_site_id, rec.new_zone_id, rec.zone_name, rec.floor, rec.zone_letter, rec.zone_type, rec.typical_occupancy)
            ON CONFLICT (site_id, zone_id) DO UPDATE
            SET zone_name = EXCLUDED.zone_name,
                floor = EXCLUDED.floor,
                zone_letter = EXCLUDED.zone_letter,
                zone_type = EXCLUDED.zone_type,
                typical_occupancy = COALESCE(public.zones.typical_occupancy, EXCLUDED.typical_occupancy),
                updated_at = NOW();
        END IF;

        INSERT INTO public.zone_aliases
            (site_id, alias_key, canonical_zone_id, alias_type, source, confidence, review_status, metadata)
        VALUES
            (
                v_site_id,
                rec.old_zone_id,
                rec.new_zone_id,
                'legacy',
                'site005_canonical_zone_seed',
                1.0,
                'approved',
                jsonb_build_object('reason', 'canonicalized_site005_seed_zone')
            )
        ON CONFLICT (site_id, alias_key) DO UPDATE
        SET canonical_zone_id = EXCLUDED.canonical_zone_id,
            alias_type = EXCLUDED.alias_type,
            source = EXCLUDED.source,
            confidence = EXCLUDED.confidence,
            review_status = EXCLUDED.review_status,
            metadata = EXCLUDED.metadata,
            updated_at = NOW();
    END LOOP;
END $$;

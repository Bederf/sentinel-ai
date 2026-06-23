-- Add site-005 canonical zones inferred from source FCU/zone-controller
-- equipment labels. These are actual observed source identifiers, not full
-- floor-range preallocation.

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
        RAISE NOTICE 'site-005 not found; skipping inferred zone seed';
        RETURN;
    END IF;

    CREATE TEMP TABLE tmp_site005_inferred_zone_map (
        alias_key TEXT PRIMARY KEY,
        canonical_zone_id TEXT NOT NULL,
        zone_name TEXT NOT NULL,
        floor TEXT NOT NULL,
        zone_letter TEXT NOT NULL,
        zone_type TEXT NOT NULL
    ) ON COMMIT DROP;

    INSERT INTO tmp_site005_inferred_zone_map
        (alias_key, canonical_zone_id, zone_name, floor, zone_letter, zone_type)
    VALUES
        ('Zone-L4-003', 'Zone-402', 'Level 4 Zone 003', 'L4', '003', 'hospital_zone'),
        ('Zone-L4-004', 'Zone-403', 'Level 4 Zone 004', 'L4', '004', 'hospital_zone'),
        ('Zone-L4-005', 'Zone-404', 'Level 4 Zone 005', 'L4', '005', 'hospital_zone'),
        ('Zone-L5-003', 'Zone-502', 'Level 5 Zone 003', 'L5', '003', 'hospital_zone'),
        ('Zone-L5-004', 'Zone-503', 'Level 5 Zone 004', 'L5', '004', 'hospital_zone'),
        ('Zone-L5-005', 'Zone-504', 'Level 5 Zone 005', 'L5', '005', 'hospital_zone'),
        ('Zone-L6-003', 'Zone-602', 'Level 6 Zone 003', 'L6', '003', 'hospital_zone'),
        ('Zone-L6-004', 'Zone-603', 'Level 6 Zone 004', 'L6', '004', 'hospital_zone'),
        ('Zone-L6-005', 'Zone-604', 'Level 6 Zone 005', 'L6', '005', 'hospital_zone'),
        ('Zone-L7-002', 'Zone-701', 'Level 7 Zone 002', 'L7', '002', 'hospital_zone'),
        ('Zone-L7-003', 'Zone-702', 'Level 7 Zone 003', 'L7', '003', 'hospital_zone'),
        ('Zone-L7-004', 'Zone-703', 'Level 7 Zone 004', 'L7', '004', 'hospital_zone'),
        ('Zone-L7-005', 'Zone-704', 'Level 7 Zone 005', 'L7', '005', 'hospital_zone'),
        ('Zone-L8-002', 'Zone-801', 'Level 8 Zone 002', 'L8', '002', 'hospital_zone'),
        ('Zone-L8-003', 'Zone-802', 'Level 8 Zone 003', 'L8', '003', 'hospital_zone'),
        ('Zone-L8-004', 'Zone-803', 'Level 8 Zone 004', 'L8', '004', 'hospital_zone'),
        ('Zone-L8-005', 'Zone-804', 'Level 8 Zone 005', 'L8', '005', 'hospital_zone'),
        ('Zone-L9-002', 'Zone-901', 'Level 9 Zone 002', 'L9', '002', 'hospital_zone'),
        ('Zone-L9-003', 'Zone-902', 'Level 9 Zone 003', 'L9', '003', 'hospital_zone'),
        ('Zone-L9-004', 'Zone-903', 'Level 9 Zone 004', 'L9', '004', 'hospital_zone'),
        ('Zone-L9-005', 'Zone-904', 'Level 9 Zone 005', 'L9', '005', 'hospital_zone');

    FOR rec IN SELECT * FROM tmp_site005_inferred_zone_map LOOP
        INSERT INTO public.zones
            (site_id, zone_id, zone_name, floor, zone_letter, zone_type)
        VALUES
            (v_site_id, rec.canonical_zone_id, rec.zone_name, rec.floor, rec.zone_letter, rec.zone_type)
        ON CONFLICT (site_id, zone_id) DO UPDATE
        SET zone_name = EXCLUDED.zone_name,
            floor = EXCLUDED.floor,
            zone_letter = EXCLUDED.zone_letter,
            zone_type = EXCLUDED.zone_type,
            updated_at = NOW();

        INSERT INTO public.zone_aliases
            (site_id, alias_key, canonical_zone_id, alias_type, source, confidence, review_status, metadata)
        VALUES
            (
                v_site_id,
                rec.alias_key,
                rec.canonical_zone_id,
                'source',
                'site005_inferred_equipment_zone_seed',
                0.95,
                'approved',
                jsonb_build_object('reason', 'inferred_from_source_fcu_or_zone_controller')
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

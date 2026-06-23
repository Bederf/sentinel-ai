-- Fix S002/S005 equipment mapping gaps found during hierarchy onboarding.
--
-- This is intentionally conservative: it derives type/location/zone from
-- explicit equipment-code evidence and leaves provenance in canonicalization
-- metadata. It does not delete duplicate legacy rows.

DO $$
DECLARE
    v_s002 UUID;
    v_s005 UUID;
BEGIN
    SELECT id INTO v_s002 FROM public.sites WHERE code = 'site-002' LIMIT 1;
    SELECT id INTO v_s005 FROM public.sites WHERE code = 'site-005' LIMIT 1;

    IF v_s002 IS NOT NULL THEN
        -- S002 legacy lighting rows were imported as unknown:
        -- S002-LTG-G-301 is a source spelling for S002-LTG-301.
        UPDATE public.equipment
        SET
            raw_code = COALESCE(raw_code, code),
            type = 'lighting_panel',
            canonical_code = regexp_replace(code, '^S002-LTG-G-', 'S002-LTG-'),
            canonical_zone_id = 'Zone-' || substring(code from '([0-9]{3})$'),
            zone_key = 'Zone-' || substring(code from '([0-9]{3})$'),
            canonicalization_status = 'source_alias',
            canonicalization_source = 's002_s005_mapping_backfill',
            canonicalization_metadata = canonicalization_metadata || jsonb_build_object(
                'reason', 'legacy_ground_lighting_code_resolved',
                'source', 'operator_backfill_20260622'
            )
        WHERE site_id = v_s002
          AND code ~ '^S002-LTG-G-[0-9]{3}$';

        -- Four-digit LTG rows such as S002-LTG-0101 are legacy zero-padded
        -- spellings for occupied-zone lighting panels.
        UPDATE public.equipment
        SET
            raw_code = COALESCE(raw_code, code),
            canonical_code = 'S002-LTG-' || substring(code from '^S002-LTG-0([0-9]{3})$'),
            canonical_zone_id = 'Zone-' || substring(code from '^S002-LTG-0([0-9]{3})$'),
            zone_key = 'Zone-' || substring(code from '^S002-LTG-0([0-9]{3})$'),
            canonicalization_status = 'source_alias',
            canonicalization_source = 's002_s005_mapping_backfill',
            canonicalization_metadata = canonicalization_metadata || jsonb_build_object(
                'reason', 'legacy_zero_padded_lighting_code_resolved',
                'source', 'operator_backfill_20260622'
            )
        WHERE site_id = v_s002
          AND code ~ '^S002-LTG-0[0-9]{3}$';

        -- Fill S002 missing zone keys where the code encodes enough location.
        UPDATE public.equipment
        SET zone_key = CASE
                WHEN code ~ '^S002-[A-Z0-9_]+-[0-9]{3}$'
                    THEN 'Zone-' || substring(code from '([0-9]{3})$')
                WHEN code ~ '^S002-[A-Z0-9_]+-0[0-9]{3}$'
                    THEN 'Zone-' || substring(code from '^S002-[A-Z0-9_]+-0([0-9]{3})$')
                WHEN code ~ '^S002-.*-B0?1$' OR code ~ '^S002-.*-B1-' OR code ~ '^S002-.*-B1$'
                    THEN 'Zone-B1-001'
                WHEN code ~ '^S002-.*-R0?1$' OR code ~ '^S002-.*-R-' OR code ~ '^S002-.*-R$'
                    THEN 'Zone-R-001'
                WHEN code ~ '^S002-.*-L1'
                    THEN 'Zone-L1'
                WHEN code ~ '^S002-.*-L2'
                    THEN 'Zone-L2'
                WHEN code = 'S002-DALI-1001'
                    THEN 'Zone-L1'
                WHEN code LIKE 'S002-LCA-DRIVER-%'
                    THEN 'Zone-B1-001'
                WHEN code = 'S002-SCENE-EVO-CTRL'
                    THEN 'Zone-B1-001'
                WHEN code = 'S002-WATER-MTR-001'
                    THEN 'Zone-B1-001'
                WHEN code = 'S002-ZONE_SENSOR-2001'
                    THEN 'Zone-201'
                WHEN code IN ('S002-CCURE-SVR', 'S002-DOOR-MAIN-ENT', 'S002-DOOR-SIDE-A', 'S002-DOOR-SIDE-B', 'S002-GATE-VEHICLE')
                    THEN 'Zone-001'
                WHEN code ~ '^S002-PV-' OR code ~ '^S002-INV-R'
                    THEN 'Zone-R-001'
                ELSE COALESCE(zone_key, canonical_zone_id)
            END
        WHERE site_id = v_s002
          AND NULLIF(TRIM(COALESCE(zone_key, canonical_zone_id, '')), '') IS NULL;

        -- Fill S002 locations from explicit plant/floor/zone code evidence.
        UPDATE public.equipment
        SET location = CASE
                WHEN code = 'S002-CCURE-SVR' THEN 'L0 Security Control Room'
                WHEN code LIKE 'S002-DOOR-%' OR code = 'S002-GATE-VEHICLE' THEN 'L0 Security / Entrance'
                WHEN code LIKE 'S002-LCA-DRIVER-%' THEN 'B1 DALI Panel Room'
                WHEN code = 'S002-SCENE-EVO-CTRL' THEN 'B1 BMS Panel Room'
                WHEN code LIKE 'S002-PV-%' OR code LIKE 'S002-INV-R%' OR code LIKE 'S002-MTR-R%' THEN 'Rooftop Plant Room'
                WHEN code LIKE 'S002-CT-R%' THEN 'Rooftop Cooling Tower Pad'
                WHEN code LIKE 'S002-GEN-B%' THEN 'B1 Generator Room'
                WHEN code LIKE 'S002-UPS-B%' THEN 'B1 UPS / Server Room'
                WHEN code LIKE 'S002-MTR-W%' THEN 'B1 Utility Room - Water Incoming'
                WHEN code LIKE 'S002-MTR-B%' THEN 'B1 Main Electrical Room'
                WHEN code LIKE 'S002-DALI%B%' THEN 'B1 DALI Panel Room'
                WHEN code = 'S002-DALI-1001' THEN 'L1 Electrical Riser / DALI Panel'
                WHEN code LIKE 'S002-DALI%L1%' THEN 'L1 Electrical Riser / DALI Panel'
                WHEN code LIKE 'S002-DALI%L2%' THEN 'L2 Electrical Riser / DALI Panel'
                WHEN code = 'S002-AHU-L2-001' THEN 'L2 AHU Riser Room'
                WHEN code LIKE 'S002-%-B%' THEN 'B1 Plant Room'
                WHEN code LIKE 'S002-%-R%' THEN 'Rooftop Plant Room'
                WHEN code ~ '^S002-(FCU|VAV|LTG|LUM|ZONE)-[0-9]{3}$'
                    THEN format(
                        'L%s - Zone %s',
                        floor((substring(code from '([0-9]{3})$')::int) / 100)::int,
                        lpad(((substring(code from '([0-9]{3})$')::int % 100))::text, 2, '0')
                    )
                WHEN code ~ '^S002-LTG-G-[0-9]{3}$'
                    THEN format(
                        'L%s - Lighting Zone %s',
                        floor((substring(code from '([0-9]{3})$')::int) / 100)::int,
                        lpad(((substring(code from '([0-9]{3})$')::int % 100))::text, 2, '0')
                    )
                WHEN code ~ '^S002-LTG-0[0-9]{3}$'
                    THEN format(
                        'L%s - Lighting Zone %s',
                        floor((substring(code from '^S002-LTG-0([0-9]{3})$')::int) / 100)::int,
                        lpad(((substring(code from '^S002-LTG-0([0-9]{3})$')::int % 100))::text, 2, '0')
                    )
                WHEN code LIKE 'S002-SENSOR-L2%' THEN 'L2 - Zone Sensors'
                WHEN code LIKE 'S002-ZONE_SENSOR%' THEN 'L2 - Zone Sensors'
                WHEN code LIKE 'S002-WATER-MTR%' THEN 'B1 Utility Room - Water Incoming'
                ELSE 'Site - Sandton City Office Tower'
            END
        WHERE site_id = v_s002
          AND NULLIF(TRIM(COALESCE(location, '')), '') IS NULL;

        -- Mark S002 rows as mapped once the deterministic fields are present.
        UPDATE public.equipment
        SET
            canonical_code = CASE
                WHEN canonical_code IS NOT NULL THEN canonical_code
                WHEN code ~ '^S002-([A-Z0-9_]+)-B0?1$'
                    THEN regexp_replace(code, '^S002-([A-Z0-9_]+)-B0?1$', 'S002-\1-B1-001')
                WHEN code ~ '^S002-([A-Z0-9_]+)-R0?1$'
                    THEN regexp_replace(code, '^S002-([A-Z0-9_]+)-R0?1$', 'S002-\1-R-001')
                ELSE code
            END,
            canonical_zone_id = COALESCE(canonical_zone_id, zone_key),
            canonicalization_status = CASE
                WHEN code ~ '^S002-[A-Z0-9_]+-[0-9]{3}$' THEN 'canonical'
                WHEN code ~ '^S002-[A-Z0-9_]+-(B0?1|R0?1)$' THEN 'plant_alias'
                ELSE 'source_alias'
            END,
            canonicalization_source = COALESCE(canonicalization_source, 's002_s005_mapping_backfill'),
            canonicalization_metadata = canonicalization_metadata || jsonb_build_object(
                'source', 'operator_backfill_20260622',
                'reason', COALESCE(canonicalization_metadata->>'reason', 'deterministic_code_mapping_completed')
            )
        WHERE site_id = v_s002
          AND canonicalization_status IN ('unreviewed', 'needs_review');
    END IF;

    IF v_s005 IS NOT NULL THEN
        -- Correct type for rows that were canonicalized but left as unknown.
        UPDATE public.equipment
        SET
            type = CASE upper(substring(canonical_code from '^S005-([A-Z0-9_]+)-'))
                WHEN 'CT' THEN 'cooling_tower'
                WHEN 'GEN' THEN 'generator'
                WHEN 'KEF' THEN 'exhaust_fan'
                WHEN 'MEDGAS' THEN 'medical_gas'
                WHEN 'MSB' THEN 'switchboard'
                WHEN 'COLD' THEN 'cold_room'
                ELSE lower(substring(canonical_code from '^S005-([A-Z0-9_]+)-'))
            END,
            canonicalization_source = COALESCE(canonicalization_source, 's002_s005_mapping_backfill'),
            canonicalization_metadata = canonicalization_metadata || jsonb_build_object(
                'reason', COALESCE(canonicalization_metadata->>'reason', 'type_resolved_from_canonical_code'),
                'source', 'operator_backfill_20260622'
            )
        WHERE site_id = v_s005
          AND lower(COALESCE(type, '')) = 'unknown'
          AND canonical_code ~ '^S005-[A-Z0-9_]+-.+';

        -- Fill S005 locations from hospital source IDs and canonical plant codes.
        UPDATE public.equipment
        SET location = CASE
                WHEN code LIKE '%AHU-L3-ICU%' THEN 'ICU Level 3'
                WHEN code LIKE '%AHU-L3-TH1%' THEN 'Theatre 1 Level 3'
                WHEN code LIKE '%AHU-L3-TH2%' THEN 'Theatre 2 Level 3'
                WHEN code LIKE '%AHU-L3-TH3%' THEN 'Theatre 3 Level 3'
                WHEN code LIKE '%AHU-L%-001%' THEN regexp_replace(code, '^.*AHU-(L[0-9]+)-.*$', '\1 AHU Plant / Ward HVAC')
                WHEN code LIKE '%FCU-L%-__' THEN regexp_replace(code, '^.*FCU-(L[0-9]+)-([0-9]+)$', '\1 Ward Zone \2')
                WHEN code LIKE '%ZONE-L%-__' THEN regexp_replace(code, '^.*ZONE-(L[0-9]+)-([0-9]+)$', '\1 Ward Zone \2')
                WHEN code LIKE '%CT-R-%' THEN 'Rooftop Cooling Tower Plant'
                WHEN code LIKE '%COLD-L1-%' THEN 'L1 Cold Room'
                WHEN code LIKE '%SPLIT-L1-%' THEN 'L1 Split AC Zone'
                WHEN code LIKE '%MEDGAS-B%' THEN 'Medical Gas Plant Room - Basement B1'
                WHEN code LIKE '%MSB-B%' THEN 'B1 Main Electrical Room'
                WHEN code LIKE '%GEN-B%' THEN 'B1 Generator Room'
                WHEN code LIKE '%PUMP-B%' OR code LIKE '%BOILER-B%' OR code LIKE '%COLD-B%' OR code LIKE '%KEF-B%' OR code LIKE '%AHU-B%' THEN 'B1 Plant Room'
                WHEN code LIKE 'S005-AHU-%' AND canonical_zone_id ~ '^Zone-[0-9]{3}$'
                    THEN format('L%s - Clinical/Ward Zone %s', floor((substring(canonical_zone_id from '([0-9]{3})$')::int) / 100)::int, substring(canonical_zone_id from '([0-9]{3})$'))
                WHEN code LIKE 'S005-BESS-%' OR code LIKE 'S005-CHILLER-%' THEN 'B1 Plant Room'
                WHEN code LIKE 'S005-CT-R%' THEN 'Rooftop Cooling Tower Plant'
                ELSE 'Site - Busamed Gateway Private Hospital'
            END
        WHERE site_id = v_s005
          AND NULLIF(TRIM(COALESCE(location, '')), '') IS NULL;

        UPDATE public.equipment
        SET zone_key = CASE
                WHEN code = 'S005-SITE-AGG' THEN 'Site'
                WHEN code = 'S005-WATER-MTR-001' THEN 'Zone-B1-001'
                ELSE COALESCE(zone_key, canonical_zone_id)
            END
        WHERE site_id = v_s005
          AND NULLIF(TRIM(COALESCE(zone_key, canonical_zone_id, '')), '') IS NULL;

        -- Add reviewable equipment rows for Niagara hierarchy nodes that were
        -- present in the BMS tree but absent from the flat equipment catalog.
        INSERT INTO public.equipment (
            site_id, code, raw_code, canonical_code, canonical_zone_id, zone_key,
            name, type, status, location,
            canonicalization_status, canonicalization_source, canonicalization_metadata
        )
        SELECT v_s005, code, raw_code, code, zone_key, zone_key, name, type, 'unknown', location,
               'source_alias', 's002_s005_mapping_backfill',
               jsonb_build_object('source', 'niagara_station_tree', 'review_status', 'suggested', 'reason', 'missing_hierarchy_node_stub')
        FROM (VALUES
            ('S005-BOILER-B1-001', 'site-005-UMH-BOILER-B1-001', 'Zone-B1-001', 'Boiler B1 001', 'boiler', 'B1 Plant Room'),
            ('S005-BOILER-B1-002', 'site-005-UMH-BOILER-B1-002', 'Zone-B1-002', 'Boiler B1 002', 'boiler', 'B1 Plant Room'),
            ('S005-PUMP-B1-CHW1', 'site-005-UMH-PUMP-B1-CHW1', 'Zone-B1', 'Chilled Water Pump B1 CHW1', 'pump', 'B1 Plant Room'),
            ('S005-PUMP-B1-CW1', 'site-005-UMH-PUMP-B1-CW1', 'Zone-B1', 'Condenser Water Pump B1 CW1', 'pump', 'B1 Plant Room'),
            ('S005-GEN-B1-001', 'site-005-UMH-GEN-B1-001', 'Zone-B1-001', 'Generator B1 001', 'generator', 'B1 Generator Room'),
            ('S005-GEN-B1-002', 'site-005-UMH-GEN-B1-002', 'Zone-B1-002', 'Generator B1 002', 'generator', 'B1 Generator Room'),
            ('S005-GEN-B1-003', 'site-005-UMH-GEN-B1-003', 'Zone-B1-003', 'Generator B1 003', 'generator', 'B1 Generator Room'),
            ('S005-MSB-B1-001', 'site-005-UMH-MSB-B1-001', 'Zone-B1-001', 'Main Switchboard B1 001', 'switchboard', 'B1 Main Electrical Room'),
            ('S005-MEDGAS-B1-001', 'site-005-UMH-MEDGAS-B1-001', 'Zone-B1-001', 'Medical Gas Panel B1 001', 'medical_gas', 'Medical Gas Plant Room - Basement B1'),
            ('S005-COLD-B1-001', 'site-005-UMH-COLD-B1-001', 'Zone-B1-001', 'Cold Room B1 001', 'cold_room', 'B1 Plant Room'),
            ('S005-KEF-B1-001', 'site-005-UMH-KEF-B1-001', 'Zone-B1-001', 'Kitchen Exhaust Fan B1 001', 'exhaust_fan', 'B1 Plant Room'),
            ('S005-AHU-B1-LAUN', 'site-005-UMH-AHU-B1-LAUN', 'Zone-B1', 'Laundry AHU B1', 'ahu', 'B1 Laundry / Plant Room')
        ) AS stub(code, raw_code, zone_key, name, type, location)
        ON CONFLICT (code) DO UPDATE
        SET
            raw_code = EXCLUDED.raw_code,
            canonical_code = EXCLUDED.canonical_code,
            canonical_zone_id = EXCLUDED.canonical_zone_id,
            zone_key = EXCLUDED.zone_key,
            name = EXCLUDED.name,
            type = EXCLUDED.type,
            location = EXCLUDED.location,
            canonicalization_status = EXCLUDED.canonicalization_status,
            canonicalization_source = EXCLUDED.canonicalization_source,
            canonicalization_metadata = public.equipment.canonicalization_metadata || EXCLUDED.canonicalization_metadata;

        INSERT INTO public.equipment_aliases (
            site_id, equipment_id, alias_code, canonical_code, alias_type, source, confidence, review_status, metadata
        )
        SELECT v_s005, e.id, e.raw_code, e.canonical_code, 'source', 'niagara_station_tree', 0.90, 'approved',
               jsonb_build_object('reason', 'raw_niagara_hierarchy_code_alias')
        FROM public.equipment e
        WHERE e.site_id = v_s005
          AND e.raw_code LIKE 'site-005-UMH-%'
          AND e.canonical_code IS NOT NULL
        ON CONFLICT (site_id, alias_code) DO UPDATE
        SET
            equipment_id = EXCLUDED.equipment_id,
            canonical_code = EXCLUDED.canonical_code,
            source = EXCLUDED.source,
            confidence = EXCLUDED.confidence,
            review_status = EXCLUDED.review_status,
            metadata = public.equipment_aliases.metadata || EXCLUDED.metadata;
    END IF;
END $$;

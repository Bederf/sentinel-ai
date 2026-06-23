-- Resolve stale S002 integration-health unmatched point mappings after the
-- equipment onboarding backfill created/normalized the referenced assets.

DO $$
DECLARE
    v_s002 UUID;
    v_equipment_id UUID;
BEGIN
    SELECT id INTO v_s002 FROM public.sites WHERE code = 'site-002' LIMIT 1;

    IF v_s002 IS NULL THEN
        RETURN;
    END IF;

    -- Bridge points reference B1 luminaires as S002-LUM-B01. Create the
    -- corresponding reviewable active equipment row because no existing
    -- luminaire row represented the basement lighting load.
    INSERT INTO public.equipment (
        site_id, code, raw_code, canonical_code, canonical_zone_id, zone_key,
        name, type, status, location,
        canonicalization_status, canonicalization_source, canonicalization_metadata
    )
    VALUES (
        v_s002,
        'S002-LUM-B1-001',
        'S002-LUM-B01',
        'S002-LUM-B1-001',
        'Zone-B1-001',
        'Zone-B1-001',
        'Basement Luminaire B1 001',
        'luminaire',
        'unknown',
        'B1 - Basement Lighting Zone',
        'source_alias',
        'integration_health_backfill',
        jsonb_build_object('reason', 'bridge_point_asset_alias_resolved', 'source', 'operator_backfill_20260622')
    )
    ON CONFLICT (code) DO UPDATE
    SET
        raw_code = EXCLUDED.raw_code,
        canonical_code = EXCLUDED.canonical_code,
        canonical_zone_id = EXCLUDED.canonical_zone_id,
        zone_key = EXCLUDED.zone_key,
        location = EXCLUDED.location,
        canonicalization_status = EXCLUDED.canonicalization_status,
        canonicalization_source = EXCLUDED.canonicalization_source,
        canonicalization_metadata = public.equipment.canonicalization_metadata || EXCLUDED.canonicalization_metadata;

    -- Alias spellings used by old point mappings to the normalized equipment.
    FOR v_equipment_id IN
        SELECT id FROM public.equipment WHERE site_id = v_s002 AND code = 'S002-DALI-B1-CTRL'
    LOOP
        INSERT INTO public.equipment_aliases (
            site_id, equipment_id, alias_code, canonical_code, alias_type, source, confidence, review_status, metadata
        )
        VALUES (
            v_s002, v_equipment_id, 'S002-DALI-B1-CTR', 'S002-DALI-B1-CTRL',
            'legacy', 'integration_health_backfill', 1.0, 'approved',
            jsonb_build_object('reason', 'legacy_dali_controller_alias')
        )
        ON CONFLICT (site_id, alias_code) DO UPDATE
        SET equipment_id = EXCLUDED.equipment_id,
            canonical_code = EXCLUDED.canonical_code,
            source = EXCLUDED.source,
            confidence = EXCLUDED.confidence,
            review_status = EXCLUDED.review_status,
            metadata = public.equipment_aliases.metadata || EXCLUDED.metadata;
    END LOOP;

    FOR v_equipment_id IN
        SELECT id FROM public.equipment WHERE site_id = v_s002 AND code = 'S002-INV-R-002'
    LOOP
        INSERT INTO public.equipment_aliases (site_id, equipment_id, alias_code, canonical_code, alias_type, source, confidence, review_status, metadata)
        VALUES (v_s002, v_equipment_id, 'S002-INV-R02', 'S002-INV-R-002', 'legacy', 'integration_health_backfill', 1.0, 'approved', jsonb_build_object('reason', 'compact_roof_inverter_alias'))
        ON CONFLICT (site_id, alias_code) DO UPDATE SET equipment_id = EXCLUDED.equipment_id, canonical_code = EXCLUDED.canonical_code, source = EXCLUDED.source, confidence = EXCLUDED.confidence, review_status = EXCLUDED.review_status, metadata = public.equipment_aliases.metadata || EXCLUDED.metadata;
    END LOOP;

    FOR v_equipment_id IN
        SELECT id FROM public.equipment WHERE site_id = v_s002 AND code = 'S002-INV-R-003'
    LOOP
        INSERT INTO public.equipment_aliases (site_id, equipment_id, alias_code, canonical_code, alias_type, source, confidence, review_status, metadata)
        VALUES (v_s002, v_equipment_id, 'S002-INV-R03', 'S002-INV-R-003', 'legacy', 'integration_health_backfill', 1.0, 'approved', jsonb_build_object('reason', 'compact_roof_inverter_alias'))
        ON CONFLICT (site_id, alias_code) DO UPDATE SET equipment_id = EXCLUDED.equipment_id, canonical_code = EXCLUDED.canonical_code, source = EXCLUDED.source, confidence = EXCLUDED.confidence, review_status = EXCLUDED.review_status, metadata = public.equipment_aliases.metadata || EXCLUDED.metadata;
    END LOOP;

    FOR v_equipment_id IN
        SELECT id FROM public.equipment WHERE site_id = v_s002 AND code = 'S002-INV-R-004'
    LOOP
        INSERT INTO public.equipment_aliases (site_id, equipment_id, alias_code, canonical_code, alias_type, source, confidence, review_status, metadata)
        VALUES (v_s002, v_equipment_id, 'S002-INV-R04', 'S002-INV-R-004', 'legacy', 'integration_health_backfill', 1.0, 'approved', jsonb_build_object('reason', 'compact_roof_inverter_alias'))
        ON CONFLICT (site_id, alias_code) DO UPDATE SET equipment_id = EXCLUDED.equipment_id, canonical_code = EXCLUDED.canonical_code, source = EXCLUDED.source, confidence = EXCLUDED.confidence, review_status = EXCLUDED.review_status, metadata = public.equipment_aliases.metadata || EXCLUDED.metadata;
    END LOOP;

    FOR v_equipment_id IN
        SELECT id FROM public.equipment WHERE site_id = v_s002 AND code = 'S002-LUM-B1-001'
    LOOP
        INSERT INTO public.equipment_aliases (site_id, equipment_id, alias_code, canonical_code, alias_type, source, confidence, review_status, metadata)
        VALUES (v_s002, v_equipment_id, 'S002-LUM-B01', 'S002-LUM-B1-001', 'legacy', 'integration_health_backfill', 1.0, 'approved', jsonb_build_object('reason', 'compact_basement_luminaire_alias'))
        ON CONFLICT (site_id, alias_code) DO UPDATE SET equipment_id = EXCLUDED.equipment_id, canonical_code = EXCLUDED.canonical_code, source = EXCLUDED.source, confidence = EXCLUDED.confidence, review_status = EXCLUDED.review_status, metadata = public.equipment_aliases.metadata || EXCLUDED.metadata;
    END LOOP;

    -- Points whose extracted_asset_id is now an exact equipment code.
    UPDATE public.point_asset_mappings pam
    SET
        match_confidence = 'exact',
        is_verified = true,
        mapping_source = 'integration_health_backfill',
        updated_at = NOW()
    WHERE pam.site_id = v_s002
      AND pam.match_confidence = 'unmatched'
      AND EXISTS (
          SELECT 1
          FROM public.equipment e
          WHERE e.site_id = v_s002
            AND upper(e.code) = upper(pam.extracted_asset_id)
      );

    -- Points resolved through approved aliases.
    UPDATE public.point_asset_mappings pam
    SET
        match_confidence = 'manual',
        is_verified = true,
        mapping_source = 'integration_health_backfill',
        updated_at = NOW()
    WHERE pam.site_id = v_s002
      AND pam.match_confidence = 'unmatched'
      AND EXISTS (
          SELECT 1
          FROM public.equipment_aliases ea
          WHERE ea.site_id = v_s002
            AND upper(ea.alias_code) = upper(pam.extracted_asset_id)
            AND ea.review_status = 'approved'
      );
END $$;

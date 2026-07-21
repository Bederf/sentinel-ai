-- ============================================================
-- Migration 232: Atomic commit_bridge_review RPC
--
-- Replaces the 6-step Python commit in api/onboarding.py with a single
-- Postgres transaction. All-or-nothing. If any step fails, everything rolls
-- back and the exception propagates to the Python caller.
--
-- Parameters:
--   p_site_id      TEXT    — site code (e.g. 'site-005')
--   p_discovery_id UUID    — from site_discovery_sessions
--   p_approved_by  TEXT    — user identifier
--   p_modules      TEXT[]  — inferred module types (from Python inference)
--   p_equipment    JSONB   — array of equipment objects
--   p_points       JSONB   — array of point objects
--
-- Returns JSONB summary:
--   {
--     "success": true,
--     "site_id": "site-005",
--     "site_uuid": "...",
--     "equipment_created": 179,
--     "points_mapped": 1078,
--     "modules_registered": ["assets", "hvac", ...],
--     "staged_rows_onboarded": 149
--   }
-- ============================================================

BEGIN;

-- Helper: map frontend confidence string to DB confidence value
CREATE OR REPLACE FUNCTION public._map_point_confidence(p_confidence TEXT)
RETURNS TEXT AS $$
BEGIN
    RETURN CASE lower(coalesce(p_confidence, ''))
        WHEN 'high'    THEN 'exact'
        WHEN 'medium'  THEN 'fuzzy'
        WHEN 'low'     THEN 'manual'
        WHEN 'manual'  THEN 'manual'
        WHEN 'unknown' THEN 'unmatched'
        ELSE 'fuzzy'
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ── commit_bridge_review ─────────────────────────────────────
CREATE OR REPLACE FUNCTION public.commit_bridge_review(
    p_site_id         TEXT,
    p_discovery_id    UUID,
    p_approved_by     TEXT,
    p_modules         TEXT[],
    p_equipment       JSONB,
    p_points          JSONB
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
    v_site_uuid        UUID;
    v_site_name        TEXT;
    v_now              TIMESTAMPTZ := now();
    v_equip_item       JSONB;
    v_point_item       JSONB;
    v_equipment_code   TEXT;
    v_raw_equipment_id TEXT;
    v_equipment_type   TEXT;
    v_point_id         TEXT;
    v_confidence       TEXT;
    v_match_conf       TEXT;
    v_equip_count      INT := 0;
    v_point_count      INT := 0;
    v_staged_count     INT := 0;
    v_module_type      TEXT;
    v_discovery_rec    RECORD;
BEGIN
    -- ── 1. Resolve site ─────────────────────────────────────
    SELECT id, name INTO v_site_uuid, v_site_name
    FROM sites WHERE code = p_site_id;

    IF v_site_uuid IS NULL THEN
        RAISE EXCEPTION 'Site % not found', p_site_id USING ERRCODE = 'P0002';
    END IF;

    -- ── 2. Validate discovery session ───────────────────────
    SELECT site_id, adapter_type, discovered_at, status
    INTO v_discovery_rec
    FROM site_discovery_sessions
    WHERE discovery_id = p_discovery_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Discovery session % not found', p_discovery_id USING ERRCODE = 'P0002';
    END IF;

    IF v_discovery_rec.site_id != p_site_id THEN
        RAISE EXCEPTION 'Discovery session % belongs to site %, not %',
            p_discovery_id, v_discovery_rec.site_id, p_site_id
            USING ERRCODE = 'P0001';
    END IF;

    IF v_discovery_rec.status != 'active' THEN
        RAISE EXCEPTION 'Discovery session % is not active (status=%)',
            p_discovery_id, v_discovery_rec.status
            USING ERRCODE = 'P0001';
    END IF;

    IF v_now - v_discovery_rec.discovered_at > interval '10 minutes' THEN
        RAISE EXCEPTION 'Discovery session % expired (> 10 min). Rescan and retry.',
            p_discovery_id
            USING ERRCODE = 'P0001';
    END IF;

    -- ── 3. Upsert equipment ─────────────────────────────────
    FOR v_equip_item IN SELECT * FROM jsonb_array_elements(p_equipment)
    LOOP
        v_raw_equipment_id := coalesce(nullif(trim(v_equip_item->>'equipment_id'), ''), trim(v_equip_item->>'equipment_name'));
        IF v_raw_equipment_id IS NULL OR v_raw_equipment_id = '' THEN
            CONTINUE;
        END IF;

        v_equipment_code := coalesce(nullif(trim(v_equip_item->>'equipment_id'), ''), v_raw_equipment_id);
        v_equipment_type := coalesce(nullif(trim(v_equip_item->>'equipment_type'), ''), 'unknown');

        INSERT INTO equipment (
            site_id, code, raw_code, canonical_code, name, type,
            status, health_score,
            canonicalization_status, canonicalization_source, canonicalization_metadata,
            operating_data, last_discovery, updated_at
        ) VALUES (
            v_site_uuid,
            v_equipment_code,
            v_raw_equipment_id,
            v_equipment_code,
            coalesce(nullif(trim(v_equip_item->>'equipment_name'), ''), v_raw_equipment_id),
            v_equipment_type,
            'normal',
            100,
            'canonical',
            'simbiot_bridge_review',
            jsonb_build_object(
                'source', 'simbiot_bridge_review',
                'approved_by', p_approved_by,
                'confidence', v_equip_item->>'confidence',
                'point_count', jsonb_array_length(coalesce(v_equip_item->'points', '[]'::jsonb))
            ),
            jsonb_build_object(
                'onboarding', jsonb_build_object(
                    'onboarded', true,
                    'source', 'simbiot_bridge_review',
                    'approved_by', p_approved_by,
                    'approved_at', v_now
                ),
                'simbiot', jsonb_build_object(
                    'raw_equipment_id', v_raw_equipment_id,
                    'point_count', jsonb_array_length(coalesce(v_equip_item->'points', '[]'::jsonb))
                )
            ),
            v_now,
            v_now
        )
        ON CONFLICT (code) DO UPDATE SET
            site_id                  = EXCLUDED.site_id,
            raw_code                 = EXCLUDED.raw_code,
            canonical_code           = EXCLUDED.canonical_code,
            name                     = EXCLUDED.name,
            type                     = EXCLUDED.type,
            status                   = EXCLUDED.status,
            health_score             = EXCLUDED.health_score,
            canonicalization_status  = EXCLUDED.canonicalization_status,
            canonicalization_source  = EXCLUDED.canonicalization_source,
            canonicalization_metadata= EXCLUDED.canonicalization_metadata,
            operating_data           = EXCLUDED.operating_data,
            last_discovery           = EXCLUDED.last_discovery,
            updated_at               = EXCLUDED.updated_at;

        v_equip_count := v_equip_count + 1;
    END LOOP;

    -- ── 4. Upsert point_asset_mappings ──────────────────────
    FOR v_point_item IN SELECT * FROM jsonb_array_elements(p_points)
    LOOP
        v_point_id   := coalesce(nullif(trim(v_point_item->>'name'), ''), trim(v_point_item->>'original_name'));
        IF v_point_id IS NULL OR v_point_id = '' THEN
            CONTINUE;
        END IF;

        v_equipment_code := trim(v_point_item->>'equipment_code');
        v_confidence     := coalesce(v_point_item->>'confidence', v_point_item->>'equipment_confidence', 'medium');
        v_match_conf     := public._map_point_confidence(v_confidence);

        INSERT INTO point_asset_mappings (
            site_id, bms_point_id, extracted_asset_id,
            parameter_name, parameter_type, match_confidence,
            is_verified, mapping_source, updated_at
        ) VALUES (
            v_site_uuid,
            v_point_id,
            v_equipment_code,
            coalesce(nullif(trim(v_point_item->>'original_name'), ''), v_point_id),
            coalesce(nullif(trim(v_point_item->>'point_type'), ''), 'sensor'),
            v_match_conf,
            v_match_conf IN ('exact', 'manual'),
            'simbiot_bridge_review',
            v_now
        )
        ON CONFLICT (site_id, bms_point_id) DO UPDATE SET
            extracted_asset_id = EXCLUDED.extracted_asset_id,
            parameter_name     = EXCLUDED.parameter_name,
            parameter_type     = EXCLUDED.parameter_type,
            match_confidence   = EXCLUDED.match_confidence,
            is_verified        = EXCLUDED.is_verified,
            mapping_source     = EXCLUDED.mapping_source,
            updated_at         = EXCLUDED.updated_at;

        v_point_count := v_point_count + 1;
    END LOOP;

    -- ── 5. Update sites.equipment_count ─────────────────────
    UPDATE sites
    SET equipment_count = (SELECT count(*) FROM equipment WHERE site_id = v_site_uuid),
        updated_at = v_now
    WHERE id = v_site_uuid;

    -- ── 6. Upsert site_module_configs ───────────────────────
    INSERT INTO site_module_configs (site_id, site_name, ai_enabled, auto_integration, updated_at)
    VALUES (p_site_id, coalesce(v_site_name, p_site_id), true, false, v_now)
    ON CONFLICT (site_id) DO UPDATE SET
        site_name        = EXCLUDED.site_name,
        ai_enabled       = EXCLUDED.ai_enabled,
        auto_integration = EXCLUDED.auto_integration,
        updated_at       = EXCLUDED.updated_at;

    -- ── 7. Upsert site_modules ──────────────────────────────
    FOREACH v_module_type IN ARRAY p_modules
    LOOP
        INSERT INTO site_modules (
            instance_id, site_id, module_type, status, activated_at,
            config, health_score, last_telemetry, error_message,
            licensed, connected, phase_override, updated_at
        ) VALUES (
            p_site_id || '-' || v_module_type,
            p_site_id,
            v_module_type,
            'active',
            v_now,
            jsonb_build_object(
                'source', 'simbiot_bridge_review',
                'mode', 'shadow_read_only',
                'control_enabled', false
            ),
            100,
            CASE WHEN v_module_type = 'simbiot' THEN v_now ELSE NULL END,
            NULL,
            true,
            v_module_type = 'simbiot',
            'shadow',
            v_now
        )
        ON CONFLICT (instance_id) DO UPDATE SET
            status         = EXCLUDED.status,
            config         = EXCLUDED.config,
            health_score   = EXCLUDED.health_score,
            last_telemetry = EXCLUDED.last_telemetry,
            error_message  = EXCLUDED.error_message,
            licensed       = EXCLUDED.licensed,
            connected      = EXCLUDED.connected,
            phase_override = EXCLUDED.phase_override,
            updated_at     = EXCLUDED.updated_at;
    END LOOP;

    -- ── 8. Mark bridge_discovered_equipment onboarded ───────
    UPDATE bridge_discovered_equipment
    SET status      = 'onboarded',
        reason      = 'approved_in_simbiot_wizard',
        onboarded_at= v_now,
        onboarded_by= p_approved_by,
        updated_at  = v_now
    WHERE site_id = p_site_id
      AND status  = 'pending';

    GET DIAGNOSTICS v_staged_count = ROW_COUNT;

    -- ── 9. Mark discovery session committed ─────────────────
    UPDATE site_discovery_sessions
    SET status       = 'committed',
        committed_at = v_now
    WHERE discovery_id = p_discovery_id;

    -- ── 10. Transition onboarding state ─────────────────────
    INSERT INTO site_onboarding_state (site_id, state, last_transition_at, discovery_id, error_message)
    VALUES (p_site_id, 'canonical', v_now, p_discovery_id, NULL)
    ON CONFLICT (site_id) DO UPDATE SET
        state              = EXCLUDED.state,
        last_transition_at = EXCLUDED.last_transition_at,
        discovery_id       = EXCLUDED.discovery_id,
        error_message      = EXCLUDED.error_message;

    -- ── 11. Return summary ──────────────────────────────────
    RETURN jsonb_build_object(
        'success', true,
        'site_id', p_site_id,
        'site_uuid', v_site_uuid,
        'equipment_created', v_equip_count,
        'points_mapped', v_point_count,
        'modules_registered', p_modules,
        'staged_rows_onboarded', v_staged_count
    );
END;
$function$;

-- Grant execute to backend service role
GRANT EXECUTE ON FUNCTION public.commit_bridge_review(TEXT, UUID, TEXT, TEXT[], JSONB, JSONB) TO service_role;
GRANT EXECUTE ON FUNCTION public._map_point_confidence(TEXT) TO service_role;

COMMIT;

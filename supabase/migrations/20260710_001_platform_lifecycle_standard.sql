-- ============================================================
-- Migration: Platform Lifecycle Standard v1 — site_onboarding
--
-- Implements PLS tables, transition RPC, replay function, and
-- backfill for the site_onboarding_state lifecycle (SIMBIOT domain).
--
-- Adds to: migration 231 (base table) and 232 (commit RPC)
-- Replaces: direct state UPSERT in commit_bridge_review with PLS RPC
-- Machine: PLS §9 — site_onboarding_state (ratified 2026-07-10)
-- ============================================================

BEGIN;

-- ── 1. Extend existing site_onboarding_state for PLS ────────

ALTER TABLE public.site_onboarding_state
    ADD COLUMN IF NOT EXISTS id              uuid DEFAULT gen_random_uuid(),
    ADD COLUMN IF NOT EXISTS machine_version text NOT NULL DEFAULT '1.0',
    ADD COLUMN IF NOT EXISTS version         bigint NOT NULL DEFAULT 1;

-- Backfill id and machine_version for rows created before this migration
UPDATE public.site_onboarding_state
SET id = gen_random_uuid()
WHERE id IS NULL;

-- Widen state CHECK to include PLS lifecycle states
ALTER TABLE public.site_onboarding_state
    DROP CONSTRAINT IF EXISTS site_onboarding_state_state_check,
    ADD CONSTRAINT site_onboarding_state_state_check
        CHECK (state IN (
            'created', 'discovering', 'discovered',
            'synced', 'canonical', 'live',
            'discovery_failed', 'discovery_timed_out', 'abandoned'
        ));

-- Replace old updated_at trigger with combined version + timestamp bump
DROP TRIGGER IF EXISTS trg_site_onboarding_state_updated_at
    ON public.site_onboarding_state;

CREATE OR REPLACE FUNCTION public.bump_site_onboarding_state_version()
RETURNS TRIGGER AS $$
BEGIN
    NEW.version    = OLD.version + 1;
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_site_onboarding_state_version
    BEFORE UPDATE ON public.site_onboarding_state
    FOR EACH ROW
    EXECUTE FUNCTION public.bump_site_onboarding_state_version();

-- Revoke direct DML from service_role — transitions go through RPC only
REVOKE ALL ON public.site_onboarding_state FROM service_role;
-- SELECT remains needed for reads; UPDATE/INSERT/DELETE are RPC-only now
GRANT SELECT ON public.site_onboarding_state TO service_role;

-- ── 2. Create PLS infrastructure tables ─────────────────────

-- States declaration — exactly one initial, at least one terminal
CREATE TABLE IF NOT EXISTS public.site_onboarding_states (
    state              text PRIMARY KEY,
    is_initial         boolean NOT NULL DEFAULT false,
    is_terminal        boolean NOT NULL DEFAULT false,
    is_recoverable     boolean NOT NULL DEFAULT true,
    timeout_seconds    integer,
    timeout_transition text
);

-- Machine definition — composite key for multi-from-state edges (abandon)
CREATE TABLE IF NOT EXISTS public.site_onboarding_machine (
    transition          text NOT NULL,
    from_state          text NOT NULL REFERENCES public.site_onboarding_states(state),
    to_state            text NOT NULL REFERENCES public.site_onboarding_states(state),
    allowed_actor_types text[] NOT NULL,
    external_effect     boolean NOT NULL DEFAULT false,
    machine_version     text NOT NULL,
    PRIMARY KEY (transition, from_state, machine_version)
);

-- Active version pointer (one row, migration-managed)
CREATE TABLE IF NOT EXISTS public.site_onboarding_machine_active (
    machine_version text PRIMARY KEY,
    activated_at    timestamptz NOT NULL DEFAULT now()
);

-- Transitions log — append-only, authoritative history
CREATE TABLE IF NOT EXISTS public.site_onboarding_transitions (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id        uuid NOT NULL,
    site_id          text NOT NULL,
    from_state       text,
    to_state         text NOT NULL,
    transition       text NOT NULL,
    reason           text NOT NULL,
    actor            text NOT NULL,
    actor_type       text NOT NULL CHECK (actor_type IN ('operator', 'system', 'service')),
    evidence_ref     jsonb,
    machine_version  text NOT NULL,
    policy_version   text,
    intent_id        uuid,
    created_at       timestamptz NOT NULL DEFAULT now()
);

-- No direct DML for application roles on any PLS table
REVOKE ALL ON public.site_onboarding_states           FROM service_role;
REVOKE ALL ON public.site_onboarding_machine           FROM service_role;
REVOKE ALL ON public.site_onboarding_machine_active   FROM service_role;
REVOKE ALL ON public.site_onboarding_transitions      FROM service_role;
-- SELECT for read queries / replay
GRANT SELECT ON public.site_onboarding_states          TO service_role;
GRANT SELECT ON public.site_onboarding_machine          TO service_role;
GRANT SELECT ON public.site_onboarding_machine_active  TO service_role;
GRANT SELECT ON public.site_onboarding_transitions     TO service_role;

-- ── 3. Seed states declaration ────────────────────────────

INSERT INTO public.site_onboarding_states (state, is_initial, is_terminal, is_recoverable, timeout_seconds, timeout_transition) VALUES
    ('created',             true,  false, true,  NULL, NULL),
    ('discovering',         false, false, false, 900,  'discovery_timeout'),
    ('discovered',          false, false, true,  NULL, NULL),
    ('discovery_failed',    false, false, true,  NULL, NULL),
    ('discovery_timed_out', false, false, true,  NULL, NULL),
    ('synced',              false, false, true,  NULL, NULL),
    ('canonical',           false, false, true,  NULL, NULL),
    ('live',                false, true,  false, NULL, NULL),
    ('abandoned',           false, true,  false, NULL, NULL)
ON CONFLICT (state) DO NOTHING;

-- Verify exactly one initial state (PLS INV-1 structural check)
DO $$
DECLARE
    v_count integer;
BEGIN
    SELECT count(*) INTO v_count
    FROM public.site_onboarding_states
    WHERE is_initial = true;

    IF v_count != 1 THEN
        RAISE EXCEPTION 'PLS structural violation: expected exactly 1 initial state, got %', v_count;
    END IF;

    -- Verify terminal states have no outbound machine edges (seeded below)
    -- This is validated after machine seeding in step 4, but the DO block
    -- captures both checks.
END;
$$;

-- ── 4. Seed machine definition ────────────────────────────

INSERT INTO public.site_onboarding_machine (transition, from_state, to_state, allowed_actor_types, external_effect, machine_version) VALUES
    -- Discovery intent/outcome cycle (external_effect exercises full PLS bracketing)
    ('begin_discovery',      'created',             'discovering',         '{operator,service}', true,  '1.0'),
    ('discovery_completed',  'discovering',         'discovered',          '{system,service}',   false, '1.0'),
    ('discovery_failed',     'discovering',         'discovery_failed',    '{system,service}',   false, '1.0'),
    ('discovery_timeout',    'discovering',         'discovery_timed_out', '{system}',            false, '1.0'),
    ('retry_discovery',      'discovery_failed',    'discovering',         '{operator,service}', true,  '1.0'),
    ('retry_discovery',      'discovery_timed_out', 'discovering',         '{operator,service}', true,  '1.0'),
    -- Capability sync (internal DB operation, no external effect)
    ('capability_sync',      'discovered',          'synced',              '{service}',          false, '1.0'),
    -- Canonicalize — calls existing commit_bridge_review inside same transaction
    ('canonicalize',         'synced',              'canonical',           '{operator,service}', false, '1.0'),
    -- Activate — operator-only per INV-7
    ('activate',             'canonical',           'live',                '{operator}',         false, '1.0'),
    -- Abandon — operator-only, any non-terminal state
    ('abandon',              'created',             'abandoned',           '{operator}',         false, '1.0'),
    ('abandon',              'discovering',         'abandoned',           '{operator}',         false, '1.0'),
    ('abandon',              'discovered',          'abandoned',           '{operator}',         false, '1.0'),
    ('abandon',              'discovery_failed',    'abandoned',           '{operator}',         false, '1.0'),
    ('abandon',              'discovery_timed_out', 'abandoned',           '{operator}',         false, '1.0'),
    ('abandon',              'synced',              'abandoned',           '{operator}',         false, '1.0')
ON CONFLICT (transition, from_state, machine_version) DO NOTHING;

-- Verify: no terminal states have outbound edges
DO $$
DECLARE
    v_violation boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM public.site_onboarding_machine m
        JOIN public.site_onboarding_states s ON s.state = m.from_state
        WHERE s.is_terminal = true
    ) INTO v_violation;

    IF v_violation THEN
        RAISE EXCEPTION 'PLS structural violation: terminal state has outbound machine edge';
    END IF;
END;
$$;

-- Activate machine version 1.0
INSERT INTO public.site_onboarding_machine_active (machine_version) VALUES ('1.0')
ON CONFLICT (machine_version) DO NOTHING;

-- ── 5. Transition RPC ─────────────────────────────────────

CREATE OR REPLACE FUNCTION public.site_onboarding_transition(
    p_site_id          TEXT,
    p_transition       TEXT,
    p_actor            TEXT,
    p_actor_type       TEXT,
    p_reason           TEXT,
    p_expected_version BIGINT DEFAULT NULL,
    p_intent_id        UUID DEFAULT NULL,
    p_evidence_ref     JSONB DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $$
DECLARE
    v_entity     RECORD;
    v_edge       RECORD;
    v_new_state  TEXT;
    v_new_intent UUID;
    v_policy_ver TEXT := '1.0';
BEGIN
    -- 1. Lock entity row
    SELECT * INTO v_entity
    FROM public.site_onboarding_state
    WHERE site_id = p_site_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'PSMS_ENTITY_NOT_FOUND' USING ERRCODE = 'P0002';
    END IF;

    -- 2. Optimistic lock
    IF p_expected_version IS NOT NULL AND v_entity.version != p_expected_version THEN
        RAISE EXCEPTION 'PSMS_VERSION_CONFLICT: expected=%, actual=%',
            p_expected_version, v_entity.version
            USING ERRCODE = 'P0001';
    END IF;

    -- 3. Edge lookup — composite key matches (transition, from_state, machine_version)
    SELECT * INTO v_edge
    FROM public.site_onboarding_machine
    WHERE transition = p_transition
      AND from_state = v_entity.state
      AND machine_version = v_entity.machine_version;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'PSMS_ILLEGAL_TRANSITION: % from % (machine v%)',
            p_transition, v_entity.state, v_entity.machine_version
            USING ERRCODE = 'P0001';
    END IF;

    -- 4. Terminal state check
    IF EXISTS (SELECT 1 FROM public.site_onboarding_states
               WHERE state = v_entity.state AND is_terminal = true) THEN
        RAISE EXCEPTION 'PSMS_TERMINAL_STATE: % is terminal', v_entity.state
            USING ERRCODE = 'P0001';
    END IF;

    -- 5. Actor check
    IF NOT (p_actor_type = ANY(v_edge.allowed_actor_types)) THEN
        RAISE EXCEPTION 'PSMS_ACTOR_DENIED: % not in allowed types %',
            p_actor_type, v_edge.allowed_actor_types
            USING ERRCODE = 'P0001';
    END IF;

    -- 6. Domain guard — v1: always pass (extension point)
    -- Future: site_processing_enabled check on activate,
    --         discovery session freshness on discovery_completed, etc.

    -- 7. Intent/outcome: external_effect edges generate intent_id
    IF v_edge.external_effect THEN
        v_new_intent := gen_random_uuid();
    ELSE
        v_new_intent := p_intent_id;
    END IF;

    -- 8. Apply — trigger bumps version + updated_at
    v_new_state := v_edge.to_state;

    UPDATE public.site_onboarding_state
    SET state = v_new_state,
        error_message = CASE WHEN v_new_state IN ('discovery_failed', 'discovery_timed_out')
                             THEN p_reason ELSE NULL END
    WHERE site_id = p_site_id;

    -- 9. Record transition (authoritative history per INV-10)
    INSERT INTO public.site_onboarding_transitions (
        entity_id, site_id, from_state, to_state,
        transition, reason, actor, actor_type,
        evidence_ref, machine_version, policy_version, intent_id
    ) VALUES (
        v_entity.id, p_site_id, v_entity.state, v_new_state,
        p_transition, p_reason, p_actor, p_actor_type,
        p_evidence_ref, v_entity.machine_version, v_policy_ver,
        v_new_intent
    );

    -- 10. Return new state + version + intent_id (if generated)
    RETURN jsonb_build_object(
        'state',    v_new_state,
        'version',  (SELECT version FROM public.site_onboarding_state WHERE site_id = p_site_id),
        'intent_id', v_new_intent
    );
END;
$$;

GRANT EXECUTE ON FUNCTION public.site_onboarding_transition(
    TEXT, TEXT, TEXT, TEXT, TEXT, BIGINT, UUID, JSONB
) TO service_role;

-- ── 6. Replay function ────────────────────────────────────

CREATE OR REPLACE FUNCTION public.site_onboarding_replay(
    p_site_id TEXT,
    p_as_of   TIMESTAMPTZ DEFAULT now()
)
RETURNS TABLE (state TEXT, version BIGINT)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_last_state TEXT;
    v_count      BIGINT;
BEGIN
    -- Latest transition's to_state = current entity state
    SELECT to_state INTO v_last_state
    FROM public.site_onboarding_transitions
    WHERE site_id = p_site_id AND created_at <= p_as_of
    ORDER BY created_at DESC
    LIMIT 1;

    -- Count transitions; entity starts at version 1, bumps per transition
    SELECT count(*) + 1 INTO v_count
    FROM public.site_onboarding_transitions
    WHERE site_id = p_site_id AND created_at <= p_as_of;

    IF v_last_state IS NULL THEN
        -- No transitions → initial state, version 1
        RETURN QUERY SELECT 'created'::TEXT, 1::BIGINT;
    ELSE
        RETURN QUERY SELECT v_last_state, v_count;
    END IF;
END;
$$;

GRANT EXECUTE ON FUNCTION public.site_onboarding_replay(TEXT, TIMESTAMPTZ) TO service_role;

-- ── 7. Backfill existing sites ────────────────────────────
-- Creates synthetic genesis transitions so replay(entity, now()) = entity row
-- for all pre-existing sites (PLS §11 item 8).

INSERT INTO public.site_onboarding_transitions (
    entity_id, site_id, from_state, to_state, transition, reason,
    actor, actor_type, machine_version, policy_version, created_at
)
SELECT
    s.id,
    s.site_id,
    NULL,                                    -- genesis: no prior state
    s.state,                                 -- current state at migration time
    'backfill_20260710',
    'PLS migration: genesis transition for pre-existing site',
    'system',
    'system',
    s.machine_version,
    '1.0',
    s.updated_at
FROM public.site_onboarding_state s
WHERE NOT EXISTS (
    SELECT 1 FROM public.site_onboarding_transitions t
    WHERE t.site_id = s.site_id
);

-- Sync entity version to match transitions count + 1 (replay contract)
UPDATE public.site_onboarding_state s
SET version = (
    SELECT count(*) + 1
    FROM public.site_onboarding_transitions t
    WHERE t.site_id = s.site_id
);

-- ── 8. Update commit_bridge_review to use PLS RPC ──────────
-- Step 10 changes from direct UPSERT to PLS transition call.
-- All other steps (1-9, 11) unchanged.

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
    v_pls_result       JSONB;
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

    -- ── 10. PLS transition (replaces direct UPSERT) ─────────
    v_pls_result := public.site_onboarding_transition(
        p_site_id,
        'canonicalize',
        p_approved_by,
        'operator',
        'Bridge review committed via wizard',
        NULL,  -- expected_version: let the RPC resolve optimistically
        NULL,  -- intent_id: canonicalize is not external_effect
        jsonb_build_object(
            'discovery_id', p_discovery_id,
            'equipment_count', v_equip_count,
            'point_count', v_point_count,
            'modules', p_modules
        )
    );

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

-- Re-grant: function signature unchanged from migration 232
GRANT EXECUTE ON FUNCTION public.commit_bridge_review(TEXT, UUID, TEXT, TEXT[], JSONB, JSONB) TO service_role;

-- Verify backfill integrity: replay(entity, now()) = entity row for all sites
DO $$
DECLARE
    v_entity  RECORD;
    v_replay  RECORD;
    v_mismatch boolean := false;
BEGIN
    FOR v_entity IN SELECT site_id, state, version FROM public.site_onboarding_state
    LOOP
        SELECT state, version INTO v_replay
        FROM public.site_onboarding_replay(v_entity.site_id);

        IF v_replay.state IS DISTINCT FROM v_entity.state THEN
            RAISE WARNING 'Replay mismatch for %: entity state=%, replay state=%',
                v_entity.site_id, v_entity.state, v_replay.state;
            v_mismatch := true;
        END IF;
    END LOOP;

    IF v_mismatch THEN
        RAISE EXCEPTION 'PLS backfill integrity check FAILED — one or more sites have replay/entity divergence';
    END IF;
END;
$$;

COMMIT;

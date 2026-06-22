-- ============================================================
-- Migration 20260622_001: RSI Tuner Rebuild (Phase 230-R)
--
-- NON-NEGOTIABLE CONSTRAINT (human-in-the-loop):
--   No code path, present or future, may promote a threshold proposal
--   or transition a phase without an authenticated operator action.
--   The sentinel_tuner DB role enforces this at the grant level: it can
--   INSERT proposals but cannot write site_thresholds. Promotion only
--   happens through the operator PATCH endpoint (require_role(4)).
--   Any feature request that would automate this step is out of scope
--   and must be rejected.
--
-- Replaces ad-hoc migration-230 objects with corrected:
--   - Key-presence CHECK constraints (fixes NULL-propagation bug
--     where missing jsonb keys passed ordering checks via 3-valued logic)
--   - RLS on all tuner tables (service_role-only writes, site-scoped SELECT)
--   - SECURITY DEFINER functions with key-presence pre-checks
--   - tuner_active_set_hash with ROW_ABSENT sentinel (no COALESCE)
--   - Real tuner password (replaces CHANGE_ME_IMMEDIATELY placeholder)
--
-- Preserves: site_thresholds table data + existing RLS policies
--
-- Run with:
--   psql -h 127.0.0.1 -p 55322 -U postgres -d postgres \
--     -v tuner_password="$TUNER_DB_PASSWORD" \
--     -f supabase/migrations/20260622_001_rsi_tuner_rebuild.sql
-- ============================================================

BEGIN;

-- ============================================================
-- 1. DROP existing tuner objects
--    Order: functions first (they reference tables), then tables,
--    then role last (REASSIGN/DROP OWNED before DROP ROLE).
-- ============================================================

DROP FUNCTION IF EXISTS public.tuner_active_set_hash(text);
DROP FUNCTION IF EXISTS public.tuner_get_active_thresholds(text);
DROP FUNCTION IF EXISTS public.tuner_submit_proposal(text, jsonb, jsonb, text, text, jsonb);

DROP TABLE IF EXISTS public.site_threshold_proposals CASCADE;
DROP TABLE IF EXISTS public.threshold_change_log CASCADE;
DROP TABLE IF EXISTS public.tuner_allowed_sites CASCADE;

-- ============================================================
-- 2. Replace CHECK constraints on site_thresholds
--    Data is preserved (2 rows: __global__ + site-002, both valid).
--    Old constraints used (health->>'key')::int which returns NULL
--    for missing keys; NULL > NULL is NULL (not FALSE), so CHECK passed.
--    New constraints require key existence FIRST via jsonb ? operator,
--    short-circuiting the casts before they can produce NULL.
-- ============================================================

ALTER TABLE public.site_thresholds DROP CONSTRAINT IF EXISTS valid_health;
ALTER TABLE public.site_thresholds DROP CONSTRAINT IF EXISTS valid_risk;

ALTER TABLE public.site_thresholds ADD CONSTRAINT valid_health CHECK (
    health ? 'critical' AND health ? 'warning' AND health ? 'healthy'
    AND (health->>'critical')::int >= 0
    AND (health->>'critical')::int < (health->>'warning')::int
    AND (health->>'warning')::int < (health->>'healthy')::int
    AND (health->>'healthy')::int <= 100
);

ALTER TABLE public.site_thresholds ADD CONSTRAINT valid_risk CHECK (
    risk ? 'critical' AND risk ? 'high' AND risk ? 'medium'
    AND (risk->>'medium')::int >= 0
    AND (risk->>'medium')::int < (risk->>'high')::int
    AND (risk->>'high')::int < (risk->>'critical')::int
    AND (risk->>'critical')::int <= 100
);

-- ============================================================
-- 3. Create tuner_allowed_sites
--    Controls which sites the RSI tuner is permitted to adjust.
--    RLS: service_role only (not exposed to app users).
--    SECURITY DEFINER functions bypass RLS (owned by postgres/superuser),
--    so sentinel_tuner can read this table through the functions
--    despite having no direct table grants.
-- ============================================================

CREATE TABLE public.tuner_allowed_sites (
    site_id    text PRIMARY KEY,
    enabled    boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text
);

ALTER TABLE public.tuner_allowed_sites ENABLE ROW LEVEL SECURITY;

CREATE POLICY tuner_allowed_sites_service_role
    ON public.tuner_allowed_sites FOR ALL
    TO public
    USING (auth.role() = 'service_role'::text)
    WITH CHECK (auth.role() = 'service_role'::text);

-- ============================================================
-- 4. Create site_threshold_proposals
--    Versioning table for threshold adjustment proposals.
--    RLS: site-scoped SELECT (app users see proposals for their site),
--         service_role-only writes.
--    CHECK constraints mirror site_thresholds (key-presence + ordering).
-- ============================================================

CREATE TABLE public.site_threshold_proposals (
    proposal_id    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id        text NOT NULL,
    health         jsonb NOT NULL,
    risk           jsonb NOT NULL,
    rationale      text,
    trigger_metric text,
    trigger_value  jsonb,
    status         text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected', 'superseded')),
    proposed_at    timestamptz NOT NULL DEFAULT now(),
    reviewed_at    timestamptz,
    reviewed_by    text,
    change_log_id  bigint,
    CONSTRAINT proposal_health_keys CHECK (
        health ? 'critical' AND health ? 'warning' AND health ? 'healthy'
        AND (health->>'critical')::int >= 0
        AND (health->>'critical')::int < (health->>'warning')::int
        AND (health->>'warning')::int < (health->>'healthy')::int
        AND (health->>'healthy')::int <= 100
    ),
    CONSTRAINT proposal_risk_keys CHECK (
        risk ? 'critical' AND risk ? 'high' AND risk ? 'medium'
        AND (risk->>'medium')::int >= 0
        AND (risk->>'medium')::int < (risk->>'high')::int
        AND (risk->>'high')::int < (risk->>'critical')::int
        AND (risk->>'critical')::int <= 100
    )
);

ALTER TABLE public.site_threshold_proposals ENABLE ROW LEVEL SECURITY;

CREATE POLICY proposals_select
    ON public.site_threshold_proposals FOR SELECT
    TO public
    USING (
        (auth.jwt() ->> 'site_id') = site_id
        OR auth.role() = 'service_role'::text
    );

CREATE POLICY proposals_service_role_write
    ON public.site_threshold_proposals FOR ALL
    TO public
    USING (auth.role() = 'service_role'::text)
    WITH CHECK (auth.role() = 'service_role'::text);

-- ============================================================
-- 5. Create threshold_change_log
--    Audit trail for all threshold changes (promote/rollback/operator).
--    RLS: site-scoped SELECT (__global__ visible to all + own site),
--         service_role-only writes.
-- ============================================================

CREATE TABLE public.threshold_change_log (
    log_id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id         text NOT NULL,
    old_health      jsonb,
    old_risk        jsonb,
    new_health      jsonb NOT NULL,
    new_risk        jsonb NOT NULL,
    triggered_by    text NOT NULL
        CHECK (triggered_by IN ('operator', 'tuner_proposal', 'rollback')),
    proposal_id     bigint,
    approved_by     text,
    previous_log_id bigint,
    changed_at      timestamptz NOT NULL DEFAULT now(),
    active_hash     text NOT NULL
);

ALTER TABLE public.threshold_change_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY change_log_select
    ON public.threshold_change_log FOR SELECT
    TO public
    USING (
        site_id = '__global__'
        OR (auth.jwt() ->> 'site_id') = site_id
        OR auth.role() = 'service_role'::text
    );

CREATE POLICY change_log_service_role_write
    ON public.threshold_change_log FOR ALL
    TO public
    USING (auth.role() = 'service_role'::text)
    WITH CHECK (auth.role() = 'service_role'::text);

-- ============================================================
-- 6. Create tuner functions (SECURITY DEFINER, owned by postgres)
--
--    All functions are owned by postgres (superuser), so they bypass
--    RLS. sentinel_tuner has EXECUTE grants only — no table grants.
--    The functions implement access control via the tuner_allowed_sites
--    allowlist and key-presence validation.
-- ============================================================

-- tuner_active_set_hash:
--   Existing row  -> MD5(site_id|health::text|risk::text)
--   No row        -> MD5(site_id|ROW_ABSENT)
--
--   Sentinel 'ROW_ABSENT' is versioned: it means "no row exists, full stop."
--   Do not reuse this sentinel string for any other absence state.
--   Drift monitoring can distinguish "row deleted" (sentinel hash)
--   from "row changed" (different hash) from "no change" (same hash).
--
--   The old COALESCE(health::text, '{}') was dead code — health/risk
--   are NOT NULL, so COALESCE never fired. And when no row matched,
--   the scalar subquery returned NULL, not '{}'. This version is explicit.
CREATE OR REPLACE FUNCTION public.tuner_active_set_hash(p_site_id text)
RETURNS text
LANGUAGE sql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
    SELECT md5(
        p_site_id || '|' ||
        health::text || '|' ||
        risk::text
    )
    FROM site_thresholds
    WHERE site_id = p_site_id
    UNION ALL
    SELECT md5(p_site_id || '|ROW_ABSENT')
    WHERE NOT EXISTS (
        SELECT 1 FROM site_thresholds WHERE site_id = p_site_id
    )
$function$;

-- tuner_get_active_thresholds:
--   Reads site_thresholds for an allowlisted site.
--   SECURITY DEFINER allows reading tuner_allowed_sites (service_role-only
--   RLS) and site_thresholds (site-scoped RLS) without direct grants.
CREATE OR REPLACE FUNCTION public.tuner_get_active_thresholds(p_site_id text)
RETURNS TABLE(site_id text, health jsonb, risk jsonb, updated_at timestamptz)
LANGUAGE sql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
    SELECT st.site_id, st.health, st.risk, st.updated_at
    FROM site_thresholds st
    WHERE st.site_id = p_site_id
      AND p_site_id IN (
          SELECT site_id FROM tuner_allowed_sites WHERE enabled = true
      )
$function$;

-- tuner_submit_proposal:
--   Inserts a proposal after key-presence pre-check.
--   Ordering/boundary validation is enforced by table CHECK constraints
--   (the enforcement backstop). The function's pre-check gives the
--   operator a readable error message for the common case (missing keys).
--   If the pre-check passes but ordering is wrong, the INSERT fails on
--   the table CHECK — the function is never the only gate.
CREATE OR REPLACE FUNCTION public.tuner_submit_proposal(
    p_site_id text,
    p_health jsonb,
    p_risk jsonb,
    p_rationale text DEFAULT NULL,
    p_trigger_metric text DEFAULT NULL,
    p_trigger_value jsonb DEFAULT NULL
)
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
    v_proposal_id bigint;
BEGIN
    -- Validate site is allowlisted
    IF p_site_id NOT IN (
        SELECT site_id FROM tuner_allowed_sites WHERE enabled = true
    ) THEN
        RAISE EXCEPTION 'Site % is not enabled for tuning', p_site_id
            USING ERRCODE = 'check_violation';
    END IF;

    -- Pre-check: key presence only (table CHECK enforces ordering/boundaries)
    IF NOT (p_health ? 'healthy' AND p_health ? 'warning' AND p_health ? 'critical') THEN
        RAISE EXCEPTION 'Health thresholds must include healthy, warning, and critical keys'
            USING ERRCODE = 'check_violation';
    END IF;
    IF NOT (p_risk ? 'medium' AND p_risk ? 'high' AND p_risk ? 'critical') THEN
        RAISE EXCEPTION 'Risk thresholds must include medium, high, and critical keys'
            USING ERRCODE = 'check_violation';
    END IF;

    -- Insert (table CHECK constraints enforce ordering/boundaries)
    INSERT INTO site_threshold_proposals (
        site_id, health, risk, rationale, trigger_metric, trigger_value, status
    ) VALUES (
        p_site_id, p_health, p_risk, p_rationale, p_trigger_metric, p_trigger_value, 'pending'
    ) RETURNING proposal_id INTO v_proposal_id;

    RETURN v_proposal_id;
END;
$function$;

-- ============================================================
-- 7. Seed tuner_allowed_sites
-- ============================================================

INSERT INTO public.tuner_allowed_sites (site_id, enabled, created_by)
VALUES ('site-002', true, 'migration-230-r-rebuild');

-- ============================================================
-- 8. Seed threshold_change_log with deliberate bootstrap rows
--    Replaces migration-230 bootstrap rows (from the session that
--    shipped the NULL-propagation bug). These are deliberate 'operator'
--    entries establishing the current known-good state as the baseline.
-- ============================================================

INSERT INTO public.threshold_change_log
    (site_id, old_health, old_risk, new_health, new_risk, triggered_by, approved_by, active_hash)
SELECT
    st.site_id,
    NULL,
    NULL,
    st.health,
    st.risk,
    'operator',
    'migration-230-r-rebuild',
    tuner_active_set_hash(st.site_id)
FROM public.site_thresholds st
ORDER BY st.site_id;

-- ============================================================
-- 9. Recreate sentinel_tuner role with real password
--    Password provided via psql variable: -v tuner_password='...'
--    The migration file itself never contains the password.
-- ============================================================

-- Drop old role. REASSIGN/DROP OWNED not needed: the role owns 0 objects
-- and function grants were auto-revoked when functions were dropped in step 1.
-- Explicit REVOKE handles residual grants (schema USAGE, table, sequence).
REVOKE ALL ON SCHEMA public FROM sentinel_tuner;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM sentinel_tuner;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM sentinel_tuner;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM sentinel_tuner;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sentinel_tuner') THEN
        DROP ROLE sentinel_tuner;
    END IF;
END
$$;

CREATE ROLE sentinel_tuner WITH LOGIN PASSWORD :'tuner_password';

GRANT USAGE ON SCHEMA public TO sentinel_tuner;
GRANT EXECUTE ON FUNCTION public.tuner_active_set_hash(text) TO sentinel_tuner;
GRANT EXECUTE ON FUNCTION public.tuner_get_active_thresholds(text) TO sentinel_tuner;
GRANT EXECUTE ON FUNCTION public.tuner_submit_proposal(text, jsonb, jsonb, text, text, jsonb) TO sentinel_tuner;

COMMIT;

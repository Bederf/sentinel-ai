-- =====================================================
-- Migration 230: Operational Tuner Containment
-- RSI Layer 4 — operational threshold self-tuning
--
-- Three concerns, three mechanisms:
--   1. App-user site isolation  → RLS policy hardening (defense-in-depth for frontend path)
--   2. Tuner containment        → dedicated DB role + SECURITY DEFINER functions
--   3. Change-control trail     → append-only log + staging proposals
--
-- Key design decisions:
--   - NO FORCE RLS: service_role has rolbypassrls=t, so FORCE RLS is dead weight.
--     Containment is enforced via GRANT/REVOKE on a dedicated sentinel_tuner role,
--     not via RLS. RLS is only for multi-tenant app-user isolation.
--   - NO session variables: pgbouncer runs in transaction pool_mode, so SET app.site_id
--     would reset/leak between transactions. SECURITY DEFINER functions are stateless
--     per-call — correct primitive under transaction pooling.
--   - Tuner reads active thresholds via a SECURITY DEFINER function, not a table GRANT.
--     The function validates site_id against tuner_allowed_sites (operator-controlled allowlist).
--   - Tuner writes proposals via a SECURITY DEFINER function, not a bare INSERT grant.
--     Same allowlist validation — prevents silent writes for unonboarded sites.
--   - The tuner role has ZERO direct grants on site_thresholds (the active table).
--     It cannot promote its own proposal. Promotion is operator-only via existing PATCH endpoint.
--
-- ROLLBACK:
--   DROP FUNCTION IF EXISTS tuner_get_active_thresholds(text);
--   DROP FUNCTION IF EXISTS tuner_submit_proposal(text, jsonb, jsonb, text);
--   DROP TABLE IF EXISTS threshold_change_log;
--   DROP TABLE IF EXISTS site_threshold_proposals;
--   DROP TABLE IF EXISTS tuner_allowed_sites;
--   DROP ROLE IF EXISTS sentinel_tuner;
--   -- Restore original RLS policies (see comments below)
-- =====================================================

-- ── 1. RLS Policy Hardening (app-user site isolation) ───────────────
-- The original policies (from 221_site_thresholds.sql) authenticate the caller
-- but do NOT scope by site_id:
--   SELECT: USING (true)  — any authenticated user reads ALL rows
--   INSERT/UPDATE: auth.role() = 'authenticated' — any site_id
--
-- These are defense-in-depth for the frontend/API path. The service_role bypasses
-- RLS entirely (rolbypassrls=t), so these do not constrain the backend — that's
-- the tuner role's job (see section 2).
--
-- We need a site_id mapping for RLS. Reuse the existing user_site_access table
-- if it exists; otherwise fall back to role >= 4 (admin) sees all.
-- The select policy scopes reads to the user's accessible sites (or __global__).

-- Drop old policies
DROP POLICY IF EXISTS site_thresholds_select ON site_thresholds;
DROP POLICY IF EXISTS site_thresholds_insert ON site_thresholds;
DROP POLICY IF EXISTS site_thresholds_update ON site_thresholds;

-- Uses the established pattern from recommendations_select_site_scoped:
-- auth.jwt() ->> 'site_id' contains the caller's site claim.
-- service_role bypasses RLS entirely (rolbypassrls=t), so these policies
-- only constrain anon/authenticated users on the HTTP path.

-- New SELECT policy: users can read their own site + __global__ fallback
CREATE POLICY site_thresholds_select ON site_thresholds
    FOR SELECT
    USING (
        site_id = '__global__'
        OR (auth.jwt() ->> 'site_id') = site_id
        OR auth.role() = 'service_role'
    );

-- New INSERT/UPDATE policy: service_role only (API layer enforces require_role(4))
-- App users should not write thresholds directly — all writes go through the backend API
CREATE POLICY site_thresholds_insert ON site_thresholds
    FOR INSERT
    WITH CHECK (auth.role() = 'service_role');

CREATE POLICY site_thresholds_update ON site_thresholds
    FOR UPDATE
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- ── 2. Tuner Allowed Sites (operator-controlled allowlist) ──────────
-- This is the second enforcement point: even if the tuner process is compromised
-- or buggy and passes the wrong site_id, it cannot read or propose for a site
-- that hasn't been explicitly onboarded to the loop.
-- This also serves as the rollout gate — add site-002 here to enable the loop
-- for that site, without touching any function definition.

CREATE TABLE IF NOT EXISTS tuner_allowed_sites (
    site_id TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by TEXT,
    CONSTRAINT tuner_allowed_sites_pkey PRIMARY KEY (site_id),
    CONSTRAINT tuner_allowed_sites_site_id_fk
        FOREIGN KEY (site_id) REFERENCES site_thresholds(site_id)
        ON DELETE CASCADE
);

COMMENT ON TABLE tuner_allowed_sites IS
    'Operator-controlled allowlist of sites eligible for automated threshold tuning. '
    'The tuner can only read/propose for sites listed here with enabled=true. '
    'This is the rollout gate — add a site here to enable the loop for it.';

-- Seed: site-002 is the only active production site (site-001 is future/inactive)
INSERT INTO tuner_allowed_sites (site_id, enabled, created_by)
VALUES ('site-002', true, 'migration-230')
ON CONFLICT (site_id) DO NOTHING;

-- ── 3. Staging: site_threshold_proposals ─────────────────────────────
-- The tuner writes here. It never writes to site_thresholds (the active table).
-- Operator reviews and promotes via PATCH endpoint (extended in step 4).

CREATE TABLE IF NOT EXISTS site_threshold_proposals (
    proposal_id BIGSERIAL PRIMARY KEY,
    site_id TEXT NOT NULL,
    health JSONB NOT NULL,
    risk JSONB NOT NULL,
    rationale TEXT,
    -- Evaluation signal that triggered the proposal
    trigger_metric TEXT,
    trigger_value JSONB,
    -- Lifecycle
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected', 'superseded')),
    proposed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ,
    reviewed_by TEXT,
    -- Link to change log entry created on promotion (null until approved)
    change_log_id BIGINT,
    CONSTRAINT proposal_health_order CHECK (
        (health->>'healthy')::int > (health->>'warning')::int
        AND (health->>'warning')::int > (health->>'critical')::int
        AND (health->>'critical')::int >= 0
        AND (health->>'healthy')::int <= 100
    ),
    CONSTRAINT proposal_risk_order CHECK (
        (risk->>'medium')::int >= 0
        AND (risk->>'high')::int > (risk->>'medium')::int
        AND (risk->>'critical')::int > (risk->>'high')::int
        AND (risk->>'critical')::int <= 100
    )
);

CREATE INDEX IF NOT EXISTS idx_proposals_site_status
    ON site_threshold_proposals(site_id, status)
    WHERE status = 'pending';

COMMENT ON TABLE site_threshold_proposals IS
    'Staging table for automated threshold tuning proposals. '
    'Tuner writes here via SECURITY DEFINER function. '
    'Operator promotes via PATCH endpoint — never auto-promoted.';

-- ── 4. Change-Control Trail: threshold_change_log ────────────────────
-- Append-only. Every promotion (manual or from-proposal) writes a row here.
-- This is the POPIA change-control trail — lighter than model-card governance
-- but documented, append-only, queryable. Git commits after the fact don't satisfy it.

CREATE TABLE IF NOT EXISTS threshold_change_log (
    log_id BIGSERIAL PRIMARY KEY,
    site_id TEXT NOT NULL,
    -- What changed
    old_health JSONB,
    old_risk JSONB,
    new_health JSONB NOT NULL,
    new_risk JSONB NOT NULL,
    -- Who/what triggered it
    triggered_by TEXT NOT NULL CHECK (triggered_by IN ('operator', 'tuner_proposal', 'rollback')),
    proposal_id BIGINT,  -- FK to site_threshold_proposals if promoted from a proposal
    approved_by TEXT,    -- operator user_id (required for operator/tuner_proposal triggers)
    -- Rollback support
    previous_log_id BIGINT,  -- points to the log entry this one reverted (if rollback)
    -- Timestamp
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Content hash for runtime drift monitoring
    active_hash TEXT NOT NULL  -- hash of (site_id, new_health, new_risk) — monitoring compares against live
);

CREATE INDEX IF NOT EXISTS idx_change_log_site_time
    ON threshold_change_log(site_id, changed_at DESC);
CREATE INDEX IF NOT EXISTS idx_change_log_rollback
    ON threshold_change_log(previous_log_id)
    WHERE previous_log_id IS NOT NULL;

COMMENT ON TABLE threshold_change_log IS
    'Append-only change-control trail for threshold modifications. '
    'Every promotion (manual, from-proposal, or rollback) writes a row. '
    'This is the POPIA change-control record — queryable, not just git commits. '
    'active_hash enables runtime drift detection: monitoring compares the hash '
    'of the live site_thresholds row against the most recent log entry.';

-- ── 5. sentinel_tuner Role (created early — functions grant to it) ───
-- This is the openshell-equivalent: the tuner connects with credentials that
-- physically cannot UPDATE/DELETE site_thresholds, cannot read unallowlisted
-- sites, cannot touch any other table in the schema.
-- The role exists only to run the two SECURITY DEFINER functions below.

-- Create role (password must be set via env: TUNER_DATABASE_URL)
-- Use DO block to avoid error if role already exists from a partial run
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sentinel_tuner') THEN
        -- Password is a placeholder; must be changed immediately after migration
        CREATE ROLE sentinel_tuner WITH LOGIN PASSWORD 'CHANGE_ME_IMMEDIATELY';
    END IF;
END $$;

-- ── 6. SECURITY DEFINER Functions (tuner interface) ──────────────────
-- These are the ONLY entry points for the sentinel_tuner role.
-- They are stateless per-call — no session variables, no GUC leakage risk
-- under pgbouncer transaction pooling.
-- Each function validates site_id against tuner_allowed_sites.

-- 5a. Read active thresholds for a site
CREATE OR REPLACE FUNCTION tuner_get_active_thresholds(p_site_id text)
RETURNS TABLE(site_id text, health jsonb, risk jsonb, updated_at timestamptz)
SECURITY DEFINER
SET search_path = public
LANGUAGE sql AS $$
    SELECT st.site_id, st.health, st.risk, st.updated_at
    FROM site_thresholds st
    WHERE st.site_id = p_site_id
      AND p_site_id IN (
          SELECT site_id FROM tuner_allowed_sites WHERE enabled = true
      )
$$;

REVOKE ALL ON FUNCTION tuner_get_active_thresholds(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tuner_get_active_thresholds(text) TO sentinel_tuner;

COMMENT ON FUNCTION tuner_get_active_thresholds(text) IS
    'Tuner read interface. Returns active thresholds for a site ONLY if the site '
    'is in tuner_allowed_sites with enabled=true. SECURITY DEFINER — runs as table '
    'owner, not as caller. Stateless: no session variables, pgbouncer-safe.';

-- 5b. Submit a threshold proposal
CREATE OR REPLACE FUNCTION tuner_submit_proposal(
    p_site_id text,
    p_health jsonb,
    p_risk jsonb,
    p_rationale text DEFAULT NULL,
    p_trigger_metric text DEFAULT NULL,
    p_trigger_value jsonb DEFAULT NULL
)
RETURNS bigint  -- returns the proposal_id
SECURITY DEFINER
SET search_path = public
LANGUAGE plpgsql AS $$
DECLARE
    v_proposal_id bigint;
    v_healthy int;
    v_warning int;
    v_critical int;
    v_medium int;
    v_high int;
    v_critical_risk int;
BEGIN
    -- Validate site is allowlisted
    IF p_site_id NOT IN (
        SELECT site_id FROM tuner_allowed_sites WHERE enabled = true
    ) THEN
        RAISE EXCEPTION 'Site % is not enabled for tuning', p_site_id
            USING ERRCODE = 'check_violation';
    END IF;

    -- Extract values for validation
    v_healthy := (p_health->>'healthy')::int;
    v_warning := (p_health->>'warning')::int;
    v_critical := (p_health->>'critical')::int;
    v_medium := (p_risk->>'medium')::int;
    v_high := (p_risk->>'high')::int;
    v_critical_risk := (p_risk->>'critical')::int;

    -- Validate ordering (same constraints as site_thresholds)
    IF NOT (v_healthy > v_warning AND v_warning > v_critical AND v_critical >= 0 AND v_healthy <= 100) THEN
        RAISE EXCEPTION 'Health thresholds must satisfy: 0 <= critical < warning < healthy <= 100'
            USING ERRCODE = 'check_violation';
    END IF;
    IF NOT (v_medium >= 0 AND v_high > v_medium AND v_critical_risk > v_high AND v_critical_risk <= 100) THEN
        RAISE EXCEPTION 'Risk thresholds must satisfy: 0 <= medium < high < critical <= 100'
            USING ERRCODE = 'check_violation';
    END IF;

    -- Insert the proposal
    INSERT INTO site_threshold_proposals (
        site_id, health, risk, rationale, trigger_metric, trigger_value, status
    ) VALUES (
        p_site_id, p_health, p_risk, p_rationale, p_trigger_metric, p_trigger_value, 'pending'
    ) RETURNING proposal_id INTO v_proposal_id;

    RETURN v_proposal_id;
END;
$$;

REVOKE ALL ON FUNCTION tuner_submit_proposal(text, jsonb, jsonb, text, text, jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tuner_submit_proposal(text, jsonb, jsonb, text, text, jsonb) TO sentinel_tuner;

COMMENT ON FUNCTION tuner_submit_proposal(text, jsonb, jsonb, text, text, jsonb) IS
    'Tuner write interface. Submits a threshold proposal for operator review. '
    'Validates site_id against tuner_allowed_sites. '
    'SECURITY DEFINER — the tuner role has NO direct INSERT on site_threshold_proposals. '
    'This is the only path for the tuner to create a proposal. Never auto-promotes.';

-- ── 7. Role Grants (the capability boundary) ─────────────────────────
-- Revoke all privileges on all tables by default.
-- The tuner should have NO direct table access — only function EXECUTE.

REVOKE ALL ON site_thresholds FROM sentinel_tuner;
REVOKE ALL ON site_threshold_proposals FROM sentinel_tuner;
REVOKE ALL ON threshold_change_log FROM sentinel_tuner;
REVOKE ALL ON tuner_allowed_sites FROM sentinel_tuner;

-- Grant USAGE on the public schema (required to call functions)
GRANT USAGE ON SCHEMA public TO sentinel_tuner;

-- Explicitly do NOT grant:
--   - SELECT/INSERT/UPDATE/DELETE on site_thresholds (the active table)
--   - SELECT/INSERT/UPDATE/DELETE on site_threshold_proposals (staging)
--   - SELECT/INSERT/UPDATE/DELETE on threshold_change_log (audit trail)
--   - SELECT/INSERT/UPDATE/DELETE on tuner_allowed_sites (allowlist)
--   - Any access to any other table in the schema
--
-- The tuner's entire surface area is two function calls. That's the containment.

COMMENT ON ROLE sentinel_tuner IS
    'Dedicated DB role for the operational threshold tuner (RSI Layer 4). '
    'Has EXECUTE on two SECURITY DEFINER functions only — no direct table access. '
    'Cannot promote its own proposals (that requires UPDATE on site_thresholds, '
    'which it does not have). Password must be set via TUNER_DATABASE_URL env var.';

-- ── 7. Active-Set Hash Function (for runtime drift monitoring) ───────
-- Monitoring compares the hash of the live site_thresholds row against the
-- most recent threshold_change_log entry. Drift = alert (something wrote to
-- site_thresholds outside the promote path).

CREATE OR REPLACE FUNCTION tuner_active_set_hash(p_site_id text)
RETURNS text
SECURITY DEFINER
SET search_path = public
LANGUAGE sql AS $$
    SELECT md5(
        p_site_id || '|' ||
        COALESCE(health::text, '{}') || '|' ||
        COALESCE(risk::text, '{}')
    )
    FROM site_thresholds
    WHERE site_id = p_site_id
$$;

REVOKE ALL ON FUNCTION tuner_active_set_hash(text) FROM PUBLIC;
-- Grant to service_role (backend runs monitoring) and sentinel_tuner (for self-verification)
GRANT EXECUTE ON FUNCTION tuner_active_set_hash(text) TO service_role;
GRANT EXECUTE ON FUNCTION tuner_active_set_hash(text) TO sentinel_tuner;

COMMENT ON FUNCTION tuner_active_set_hash(text) IS
    'Computes a content hash of the active threshold set for a site. '
    'Monitoring compares this against threshold_change_log.active_hash. '
    'Drift indicates a write to site_thresholds outside the promote path.';

-- ── 8. Seed change_log with current state ────────────────────────────
-- Record the current active thresholds as the baseline log entry for each site.
-- This gives monitoring a starting reference point.

INSERT INTO threshold_change_log (
    site_id, old_health, old_risk, new_health, new_risk,
    triggered_by, approved_by, active_hash
)
SELECT
    st.site_id,
    NULL,  -- no prior state — this is the baseline
    NULL,
    st.health,
    st.risk,
    'operator',
    'migration-230',
    tuner_active_set_hash(st.site_id)
FROM site_thresholds st
WHERE NOT EXISTS (
    SELECT 1 FROM threshold_change_log tcl WHERE tcl.site_id = st.site_id
);

-- ── Verification queries (run manually after applying) ───────────────
-- Confirm the containment is correct:
--
-- 1. sentinel_tuner has no direct table grants:
--    SELECT grantee, privilege_type, table_name
--    FROM information_schema.table_privileges
--    WHERE grantee = 'sentinel_tuner';
--    -- Expected: 0 rows
--
-- 2. sentinel_tuner has function EXECUTE only:
--    SELECT routine_name, privilege_type
--    FROM information_schema.routine_privileges
--    WHERE grantee = 'sentinel_tuner';
--    -- Expected: tuner_get_active_thresholds, tuner_submit_proposal, tuner_active_set_hash
--
-- 3. Role attributes:
--    SELECT rolname, rolbypassrls, rolsuper, rolcanlogin
--    FROM pg_roles WHERE rolname = 'sentinel_tuner';
--    -- Expected: rolbypassrls=f, rolsuper=f, rolcanlogin=t
--
-- 4. Test: connect as sentinel_tuner, try to SELECT from site_thresholds:
--    -- Expected: permission denied
--
-- 5. Test: connect as sentinel_tuner, call tuner_get_active_thresholds('site-002'):
--    -- Expected: returns the row
--
-- 6. Test: connect as sentinel_tuner, call tuner_get_active_thresholds('__global__'):
--    -- Expected: returns 0 rows (not in allowlist)
--
-- 7. Test: connect as sentinel_tuner, try to UPDATE site_thresholds:
--    -- Expected: permission denied

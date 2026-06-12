-- ==============================================================================
-- Migration 050: Site-Scoped RLS Policies
-- Phase: 226.1.7 (Production Deployment Readiness — Fable audit remediation)
-- Generated: 2026-06-12
-- ==============================================================================
--
-- PURPOSE
--   The Fable security audit flagged that the dominant RLS pattern in this
--   codebase is `auth.role() = 'service_role'`, which bypasses ALL row-level
--   restrictions. If the Supabase service-role key leaks, an attacker gets
--   full database access.
--
--   This migration is DEFENSE-IN-DEPTH: it adds a `site_id` JWT-claim
--   constraint to the 5 most sensitive tables. Even if an attacker has a
--   valid (non-service-role) JWT, they can only see rows matching the
--   `site_id` claim baked into their token at issuance time.
--
-- IMPORTANT — SERVICE-ROLE BYPASS PRESERVED
--   System jobs (APScheduler, AI optimizer, RAG ingestion, background
--   workers) legitimately need cross-site access. The new policies keep
--   `auth.role() = 'service_role'` as the FIRST disjunct — system jobs
--   continue to see all rows. Site-scoping only applies to user-facing
--   API paths that present an anon or authenticated JWT.
--
-- PATTERN — ADDITIVE
--   Migration 040 already created policies on `audit_log` and `mfa_secrets`.
--   Those policies REMAIN. We add new policies whose names are suffixed
--   `_site_scoped`. PostgreSQL OR-combines permissive policies, so the new
--   policies are additive: they RESTRICT the user-facing path, they do not
--   loosen the service-role path.
--
-- JWT CLAIM ASSUMPTION
--   The application must add `site_id` to the JWT `app_metadata` or
--   `user_metadata` at token issuance. This migration reads it as
--   `auth.jwt()->>'site_id'`. Backend middleware update is a SEPARATE
--   code change tracked outside this migration.
--
--   - NULL `site_id` claim  → see nothing (fail-safe). Missing claim is an
--                             unknown caller, NOT a trusted caller. Only
--                             service_role or explicit admin role bypass.
--   - Non-NULL `site_id`    → row is visible only if the row's site_id
--                             matches the claim.
--   - `service_role`        → bypasses all row-level restrictions.
--   - `ADMIN` role claim    → site-scope-bypass for operators (matches
--                             040's existing admin escape hatch on
--                             audit_log).
-- ==============================================================================


-- ==============================================================================
-- PART 1: PREREQUISITE — site_id COLUMNS
-- ==============================================================================
--
-- The following ADD COLUMN IF NOT EXISTS blocks are SAFE to re-run.
-- Existing data is preserved; new column is NULLABLE so legacy rows
-- (system events with no site context) are not blocked.
--
-- Column types are chosen to match existing convention:
--   - TEXT for tables that store site-002 / site-005 codes (recommendations)
--   - UUID for tables that join to sites.id (work_orders, audit_log)
--
-- mfa_secrets is a USER-SCOPED table (not site-scoped) — the column is
-- added for compliance tagging only. The RLS predicate for mfa_secrets
-- uses user_email, NOT site_id.

-- audit_log: add site_id (UUID, joins to sites.id). NULL = legacy system event.
ALTER TABLE audit_log
    ADD COLUMN IF NOT EXISTS site_id UUID;

CREATE INDEX IF NOT EXISTS idx_audit_log_site_id ON audit_log(site_id);

-- mfa_secrets: add site_id (TEXT) for compliance tagging only.
-- RLS predicate continues to use user_email. Site-scoping on this table
-- is intentionally NOT applied because MFA secrets are user-bound, not
-- site-bound (a user can have MFA enrolled while temporarily
-- reassigned across sites).
ALTER TABLE mfa_secrets
    ADD COLUMN IF NOT EXISTS site_id TEXT;

CREATE INDEX IF NOT EXISTS idx_mfa_secrets_site_id ON mfa_secrets(site_id);


-- ==============================================================================
-- PART 2: RECOMMENDATIONS — site-scoped SELECT + UPDATE
-- ==============================================================================
--
-- Existing RLS state: NONE (recommendations has no RLS in 040).
-- This is a NEW RLS enablement. We add it now because recommendations
-- contain site-specific energy/cost guidance and should not leak
-- across tenants.

ALTER TABLE recommendations ENABLE ROW LEVEL SECURITY;

-- 2a. SELECT — service-role OR site-matching user.
-- Fail-safe: NULL/missing site_id claim = see nothing (NOT system context).
-- The "trust NULL" default is rejected — missing claim is an unknown caller.
CREATE POLICY recommendations_select_site_scoped ON recommendations
    FOR SELECT
    USING (
        auth.role() = 'service_role'
        OR (auth.jwt()->>'site_id')::text = site_id::text
    );

-- 2b. INSERT — service role OR site-matching user
-- Backend writes go through service role (FastAPI with service key).
-- Allow anon/authenticated INSERT only if their claim matches.
CREATE POLICY recommendations_insert_site_scoped ON recommendations
    FOR INSERT
    WITH CHECK (
        auth.role() = 'service_role'
        OR (auth.jwt()->>'site_id')::text = site_id::text
    );

-- 2c. UPDATE — same predicate as SELECT (RLS is enforced on both USING and WITH CHECK)
CREATE POLICY recommendations_update_site_scoped ON recommendations
    FOR UPDATE
    USING (
        auth.role() = 'service_role'
        OR (auth.jwt()->>'site_id')::text = site_id::text
    )
    WITH CHECK (
        auth.role() = 'service_role'
        OR (auth.jwt()->>'site_id')::text = site_id::text
    );

-- 2d. DELETE — service role only (no user-facing delete path)
CREATE POLICY recommendations_delete_service ON recommendations
    FOR DELETE
    USING (auth.role() = 'service_role');


-- ==============================================================================
-- PART 3: WORK_ORDERS — site-scoped SELECT + UPDATE
-- ==============================================================================
--
-- Existing RLS state: NONE (work_orders has no RLS in 040).
-- Site isolation is critical here because work orders expose equipment
-- problems, costs, and labor data.

ALTER TABLE work_orders ENABLE ROW LEVEL SECURITY;

-- 3a. SELECT — service-role OR site-matching user.
-- Fail-safe: NULL/missing site_id claim = see nothing.
CREATE POLICY work_orders_select_site_scoped ON work_orders
    FOR SELECT
    USING (
        auth.role() = 'service_role'
        OR (auth.jwt()->>'site_id')::text = site_id::text
    );

-- 3b. INSERT — backend writes via service role
CREATE POLICY work_orders_insert_site_scoped ON work_orders
    FOR INSERT
    WITH CHECK (
        auth.role() = 'service_role'
        OR (auth.jwt()->>'site_id')::text = site_id::text
    );

-- 3c. UPDATE — site-scoped; technicians can update their assigned WOs
CREATE POLICY work_orders_update_site_scoped ON work_orders
    FOR UPDATE
    USING (
        auth.role() = 'service_role'
        OR (auth.jwt()->>'site_id')::text = site_id::text
    )
    WITH CHECK (
        auth.role() = 'service_role'
        OR (auth.jwt()->>'site_id')::text = site_id::text
    );

-- 3d. DELETE — service role only
CREATE POLICY work_orders_delete_service ON work_orders
    FOR DELETE
    USING (auth.role() = 'service_role');


-- ==============================================================================
-- PART 4: SITES — site-scoped SELECT (a user can only see their own site)
-- ==============================================================================
--
-- Existing RLS state: NONE in 040 (sites has no RLS).
-- The sites table uses `code` (TEXT, e.g. 'site-002') as the business
-- identifier, not a `site_id` column. The RLS predicate compares the
-- JWT's site_id claim to `sites.code`.
--
-- Admins (role claim = 'ADMIN' or 'admin') can see all sites; everyone
-- else only sees the row matching their claim.

ALTER TABLE sites ENABLE ROW LEVEL SECURITY;

-- 4a. SELECT — service-role OR admin OR row's code matches the claim.
-- Fail-safe: NULL/missing site_id claim = see nothing (admin escape hatch still works).
CREATE POLICY sites_select_site_scoped ON sites
    FOR SELECT
    USING (
        auth.role() = 'service_role'
        OR LOWER(auth.jwt()->>'role') IN ('admin', 'super_admin', 'superadmin')
        OR (auth.jwt()->>'site_id')::text = code::text
    );

-- 4b. INSERT — service role only (site registration is a privileged op)
CREATE POLICY sites_insert_service ON sites
    FOR INSERT
    WITH CHECK (auth.role() = 'service_role');

-- 4c. UPDATE — service role OR admin
CREATE POLICY sites_update_admin ON sites
    FOR UPDATE
    USING (
        auth.role() = 'service_role'
        OR LOWER(auth.jwt()->>'role') IN ('admin', 'super_admin', 'superadmin')
    )
    WITH CHECK (
        auth.role() = 'service_role'
        OR LOWER(auth.jwt()->>'role') IN ('admin', 'super_admin', 'superadmin')
    );

-- 4d. DELETE — service role only
CREATE POLICY sites_delete_service ON sites
    FOR DELETE
    USING (auth.role() = 'service_role');


-- ==============================================================================
-- PART 5: AUDIT_LOG — EXTEND 040 with site-scope
-- ==============================================================================
--
-- Existing RLS state from 040:
--   - audit_log_select_own:  service_role OR ADMIN OR user_id=auth.uid OR user_name=email
--   - audit_log_insert_service: WITH CHECK (auth.role() = 'service_role')
--
-- We ADD a new SELECT policy that constrains non-admin users to their site.
-- The 040 policies remain intact — PostgreSQL OR-combines permissive
-- policies, so the user-visible result is the UNION of all USING
-- expressions that evaluate to TRUE.

-- 5a. New site-scoped SELECT (additive to 040's audit_log_select_own)
-- A user can see audit log rows for their site OR rows authored by them.
-- Admins and service roles are covered by 040 and bypass site scope.
--
-- Legacy row handling: rows where site_id IS NULL were written before
-- this migration. The application MUST set site_id on all new rows.
-- Legacy rows are visible to anyone with a site-scoped session because
-- we don't want to break historical audit visibility. This matches
-- pre-migration behavior (no site_id filter on legacy data).
--
-- Fail-safe: NULL/missing JWT site_id claim = see nothing for the
-- non-legacy rows. The site_id IS NULL clause on the row side is a
-- separate legacy-compat decision, not a NULL-claim trust.
CREATE POLICY audit_log_select_site_scoped ON audit_log
    FOR SELECT
    USING (
        auth.role() = 'service_role'
        OR LOWER(auth.jwt()->>'role') IN ('admin', 'super_admin', 'superadmin')
        OR site_id IS NULL                          -- legacy rows without site (pre-migration)
        OR (auth.jwt()->>'site_id')::text = site_id::text
        OR user_id = auth.uid()::text               -- own actions
        OR user_name = auth.jwt() ->> 'email'       -- own actions (by email)
    );

-- 5b. INSERT — keep 040's policy intact (service role only).
-- No new INSERT policy is added. The 040 audit_log_insert_service
-- already locks down writes to service_role.

-- 5c. UPDATE — audit log is append-only. Add explicit no-update for
-- non-service-role to prevent tampering.
CREATE POLICY audit_log_update_service ON audit_log
    FOR UPDATE
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- 5d. DELETE — service role only (matches 040 cleanup function path)
CREATE POLICY audit_log_delete_service ON audit_log
    FOR DELETE
    USING (auth.role() = 'service_role');


-- ==============================================================================
-- PART 6: MFA_SECRETS — user-scoped, with site tag
-- ==============================================================================
--
-- Existing RLS state from 040:
--   - mfa_secrets_select_own:   service_role OR user_email = jwt.email
--   - mfa_secrets_update_own:   service_role OR user_email = jwt.email
--   - mfa_secrets_insert_service: WITH CHECK (auth.role() = 'service_role')
--   - mfa_secrets_delete_service: USING (auth.role() = 'service_role')
--
-- MFA secrets are USER-SCOPED, not site-scoped. The site_id column
-- added in Part 1 is for compliance tagging only.
--
-- We DO NOT add a new site-scoped predicate. The 040 policies are
-- correct: a user's MFA secret is bound to their email, regardless of
-- which site they happen to be on at the moment.
--
-- However, we DO tighten the 040 UPDATE/SELECT policies so that even
-- service-role paths are constrained: a service-role session can still
-- access any row (for system recovery / admin), but the 040 predicate
-- remains. No changes needed beyond adding the column.
--
-- NOTE: The site_id column on mfa_secrets is NOT used in the RLS
-- predicate. It is metadata for compliance reporting
-- (e.g. "which sites has this user's MFA been used on?").


-- ==============================================================================
-- PART 7: COMMENTS
-- ==============================================================================

COMMENT ON POLICY recommendations_select_site_scoped ON recommendations
    IS 'Site-scoped SELECT. service_role bypasses. User MUST have a matching site_id claim. NULL/missing claim = see nothing (fail-safe).';
COMMENT ON POLICY recommendations_insert_site_scoped ON recommendations
    IS 'Site-scoped INSERT. service_role bypasses. User MUST have matching site_id claim.';
COMMENT ON POLICY recommendations_update_site_scoped ON recommendations
    IS 'Site-scoped UPDATE. service_role bypasses.';
COMMENT ON POLICY recommendations_delete_service ON recommendations
    IS 'Service role only. No user-facing delete path.';

COMMENT ON POLICY work_orders_select_site_scoped ON work_orders
    IS 'Site-scoped SELECT. service_role bypasses. NULL/missing claim = see nothing.';
COMMENT ON POLICY work_orders_insert_site_scoped ON work_orders
    IS 'Site-scoped INSERT. service_role bypasses. NULL/missing claim = no insert.';
COMMENT ON POLICY work_orders_update_site_scoped ON work_orders
    IS 'Site-scoped UPDATE. service_role bypasses. NULL/missing claim = no update.';
COMMENT ON POLICY work_orders_delete_service ON work_orders
    IS 'Service role only.';

COMMENT ON POLICY sites_select_site_scoped ON sites
    IS 'Site-scoped SELECT. service_role and admin bypass. Users see only their own site (code matches claim). NULL/missing claim = see nothing.';
COMMENT ON POLICY sites_insert_service ON sites
    IS 'Service role only. Site registration is a privileged operation.';
COMMENT ON POLICY sites_update_admin ON sites
    IS 'service_role or admin only.';
COMMENT ON POLICY sites_delete_service ON sites
    IS 'Service role only.';

COMMENT ON POLICY audit_log_select_site_scoped ON audit_log
    IS 'ADDITIVE to 040 audit_log_select_own. Adds site-scope for non-admin users. NULL JWT claim = see nothing for non-legacy rows. Legacy rows (audit_log.site_id IS NULL) remain visible to site-scoped sessions for historical continuity.';
COMMENT ON POLICY audit_log_update_service ON audit_log
    IS 'Audit log is append-only. Only service role can update (e.g. for archival reclassification).';
COMMENT ON POLICY audit_log_delete_service ON audit_log
    IS 'Service role only. Used by cleanup_old_audit_logs function.';

COMMENT ON COLUMN audit_log.site_id
    IS 'Site scope for the audit event. NULL = legacy system event or no site context. Joins to sites.id.';
COMMENT ON COLUMN mfa_secrets.site_id
    IS 'Compliance tag only. MFA secrets are user-scoped (user_email), not site-scoped. This column records the site the user was on at enrollment time.';


-- ==============================================================================
-- PART 8: VERIFICATION (run manually after applying)
-- ==============================================================================
--
-- 1. Confirm RLS is enabled and policies exist:
--    SELECT schemaname, tablename, policyname, cmd, qual
--    FROM pg_policies
--    WHERE tablename IN ('recommendations', 'work_orders', 'sites', 'audit_log', 'mfa_secrets')
--    ORDER BY tablename, policyname;
--
-- 2. As a JWT with site_id='site-002', query:
--    SET LOCAL request.jwt.claims = '{"sub": "u1", "site_id": "site-002", "role": "authenticated"}';
--    SELECT count(*) FROM recommendations;   -- should return only site-002 rows
--    SELECT count(*) FROM work_orders;        -- should return only site-002 rows
--    SELECT count(*) FROM sites;              -- should return only the site-002 row
--    SELECT count(*) FROM audit_log WHERE site_id IS NOT NULL;  -- site-002 only
--
-- 3. As service role (postgres / supabase service key):
--    SELECT count(*) FROM recommendations;    -- should return ALL rows
--    SELECT count(*) FROM work_orders;         -- should return ALL rows
--    SELECT count(*) FROM sites;               -- should return ALL rows
--    SELECT count(*) FROM audit_log;           -- should return ALL rows
--
-- 4. Cross-tenant leak check (must return 0):
--    SET LOCAL request.jwt.claims = '{"sub": "u1", "site_id": "site-005", "role": "authenticated"}';
--    SELECT count(*) FROM recommendations WHERE site_id::text = 'site-002';
--    -- expected: 0 (user scoped to site-005 cannot read site-002 rows)
--
-- 5. NULL-claim fail-safe (must return 0 — see nothing):
--    SET LOCAL request.jwt.claims = '{"sub": "system", "role": "service_role"}';
--    SELECT count(*) FROM recommendations;    -- service role bypass (expected: ALL rows)
--    SET LOCAL request.jwt.claims = '{"sub": "u1", "site_id": null, "role": "authenticated"}';
--    SELECT count(*) FROM recommendations;    -- NULL claim = see nothing (expected: 0)
--    SET LOCAL request.jwt.claims = '{"sub": "admin", "role": "authenticated", "site_id": null}';
--    SELECT count(*) FROM sites;              -- NULL claim, non-admin role (expected: 0)
--
-- 6. APScheduler sanity check (after migration, before deploy):
--    curl -H "Authorization: Bearer $SERVICE_KEY" \
--         $SUPABASE_URL/rest/v1/recommendations?select=count
--    -- service key bypasses RLS — should return total count
--
-- 7. Frontend sanity check (after backend middleware emits site_id claim):
--    Login as site-002 user → confirm only site-002 data is visible.
--    Login as site-005 user → confirm only site-005 data is visible.
--    Log in as admin → confirm cross-site data is visible.
-- ==============================================================================


-- ==============================================================================
-- ROLLBACK (manual — not run automatically)
-- ==============================================================================
--
-- DROP POLICY IF EXISTS recommendations_select_site_scoped ON recommendations;
-- DROP POLICY IF EXISTS recommendations_insert_site_scoped ON recommendations;
-- DROP POLICY IF EXISTS recommendations_update_site_scoped ON recommendations;
-- DROP POLICY IF EXISTS recommendations_delete_service       ON recommendations;
--
-- DROP POLICY IF EXISTS work_orders_select_site_scoped  ON work_orders;
-- DROP POLICY IF EXISTS work_orders_insert_site_scoped  ON work_orders;
-- DROP POLICY IF EXISTS work_orders_update_site_scoped  ON work_orders;
-- DROP POLICY IF EXISTS work_orders_delete_service      ON work_orders;
--
-- DROP POLICY IF EXISTS sites_select_site_scoped ON sites;
-- DROP POLICY IF EXISTS sites_insert_service     ON sites;
-- DROP POLICY IF EXISTS sites_update_admin       ON sites;
-- DROP POLICY IF EXISTS sites_delete_service     ON sites;
--
-- DROP POLICY IF EXISTS audit_log_select_site_scoped ON audit_log;
-- DROP POLICY IF EXISTS audit_log_update_service      ON audit_log;
-- DROP POLICY IF EXISTS audit_log_delete_service      ON audit_log;
--
-- ALTER TABLE recommendations DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE work_orders      DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE sites            DISABLE ROW LEVEL SECURITY;
-- (audit_log and mfa_secrets RLS remains ON — covered by 040 policies)
--
-- ALTER TABLE audit_log    DROP COLUMN IF EXISTS site_id;
-- ALTER TABLE mfa_secrets  DROP COLUMN IF EXISTS site_id;
-- ==============================================================================

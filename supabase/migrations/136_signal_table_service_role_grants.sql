-- Migration: 20260417_001_signal_table_service_role_grants.sql
-- Grant service_role table privileges on signal table.
-- service_role bypasses RLS but still needs basic table privileges.
-- This was missing from the initial migration, causing "permission denied for table signal" errors.

BEGIN;

-- Grant SELECT and UPDATE to service_role (RLS is disabled on this table)
GRANT SELECT, UPDATE ON public.signal TO service_role;

COMMIT;

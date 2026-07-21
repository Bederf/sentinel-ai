-- Allow backend telemetry ingestion to write current DALI/Encom lighting rows.
-- The table has no RLS, but service_role only had SELECT, so Supabase writes
-- from ShadowModePollingService failed with "permission denied".

GRANT SELECT, INSERT, UPDATE, DELETE ON public.lighting_energy TO service_role;

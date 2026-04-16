-- Migration: Grant system_settings permissions to service role
-- Fixes: permission denied for table system_settings (code 42501)

GRANT INSERT, UPDATE, SELECT ON system_settings TO service_role;
GRANT SELECT ON system_settings TO authenticated;
GRANT SELECT ON public_settings TO authenticated;

-- Add optional per-module phase override to site_modules
ALTER TABLE site_modules
  ADD COLUMN IF NOT EXISTS phase_override TEXT
  CHECK (phase_override IN ('shadow','advisory','supervised','auto'));

COMMENT ON COLUMN site_modules.phase_override IS
  'When set, overrides the site-level onboarding_phase for this module only.
   NULL means inherit from site.';

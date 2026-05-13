-- ML feedback state storage (Supabase source of truth, JSON local backup).
-- Stores serialized ML feedback service state in a single row keyed by state_key.

CREATE TABLE IF NOT EXISTS public.ml_feedback_state (
  state_key TEXT PRIMARY KEY,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS update_ml_feedback_state_updated_at ON public.ml_feedback_state;
CREATE TRIGGER update_ml_feedback_state_updated_at
  BEFORE UPDATE ON public.ml_feedback_state
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE INDEX IF NOT EXISTS idx_ml_feedback_state_updated_at
  ON public.ml_feedback_state(updated_at DESC);

-- Allow service role (anon + authenticated bypass RLS for backend service account)
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ml_feedback_state TO service_role;

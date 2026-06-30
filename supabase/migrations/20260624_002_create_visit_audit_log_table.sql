CREATE TABLE IF NOT EXISTS public.visit_audit_log (
  id bigserial PRIMARY KEY,
  event_type text NOT NULL CHECK (event_type IN ('SCAN', 'REGISTER', 'APPROVE', 'DENY', 'ACCESS_ISSUED', 'ACCESS_REVOKED', 'EXPIRED')),
  visit_id uuid,
  details jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_visit_audit_log_event_type
  ON public.visit_audit_log(event_type);

CREATE INDEX IF NOT EXISTS idx_visit_audit_log_visit_id
  ON public.visit_audit_log(visit_id);

CREATE INDEX IF NOT EXISTS idx_visit_audit_log_created_at
  ON public.visit_audit_log(created_at DESC);

COMMENT ON TABLE public.visit_audit_log IS
  'Append-only audit log for visit lifecycle events (scan, register, approve, deny, access, expire).';

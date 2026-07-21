CREATE TABLE IF NOT EXISTS public.privacy_requests (
  request_id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  data_subject_hash text NOT NULL,
  request_type text NOT NULL CHECK (request_type IN ('access', 'deletion', 'rectification', 'objection', 'portability')),
  channel text NOT NULL DEFAULT 'api',
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'fulfilled', 'rejected')),
  details text NOT NULL DEFAULT '',
  requested_by text NOT NULL DEFAULT '',
  assigned_to text,
  due_at timestamptz NOT NULL,
  closed_at timestamptz,
  outcome_summary text,
  evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_privacy_requests_status ON public.privacy_requests(status);
CREATE INDEX IF NOT EXISTS idx_privacy_requests_hash ON public.privacy_requests(data_subject_hash);

COMMENT ON TABLE public.privacy_requests IS 'POPIA data subject requests (access, deletion, rectification, objection, portability).';

--

CREATE TABLE IF NOT EXISTS public.popia_retention_runs (
  id bigserial PRIMARY KEY,
  executed_at timestamptz NOT NULL,
  dry_run boolean NOT NULL DEFAULT true,
  categories jsonb NOT NULL DEFAULT '[]'::jsonb,
  total_reviewed int NOT NULL DEFAULT 0,
  total_deleted int NOT NULL DEFAULT 0,
  errors jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_popia_retention_runs_executed ON public.popia_retention_runs(executed_at DESC);

COMMENT ON TABLE public.popia_retention_runs IS 'POPIA retention policy enforcement run logs.';

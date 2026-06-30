CREATE TABLE IF NOT EXISTS public.autonomous_decisions (
  id bigserial PRIMARY KEY,
  decision_id text NOT NULL UNIQUE,
  site_id text,
  device_id text,
  device_name text NOT NULL DEFAULT '',
  point_name text NOT NULL DEFAULT '',
  current_value double precision,
  target_value double precision,
  decision_rationale text NOT NULL DEFAULT '',
  rule_triggered text NOT NULL DEFAULT '',
  safety_validation jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT '',
  result text NOT NULL DEFAULT '',
  execution_time_ms double precision NOT NULL DEFAULT 0,
  escalation_level int NOT NULL DEFAULT 0,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  decided_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_autonomous_decisions_device ON public.autonomous_decisions(device_id);
CREATE INDEX IF NOT EXISTS idx_autonomous_decisions_ts ON public.autonomous_decisions(decided_at DESC);

COMMENT ON TABLE public.autonomous_decisions IS 'Autonomous decision engine action records for audit trail.';

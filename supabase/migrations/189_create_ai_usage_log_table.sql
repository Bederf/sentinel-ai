CREATE TABLE IF NOT EXISTS public.ai_usage_log (
  id bigserial PRIMARY KEY,
  log_date date NOT NULL,
  provider text NOT NULL,
  model text NOT NULL,
  calls int NOT NULL DEFAULT 0,
  input_tokens bigint NOT NULL DEFAULT 0,
  output_tokens bigint NOT NULL DEFAULT 0,
  cache_read_tokens bigint NOT NULL DEFAULT 0,
  cache_creation_tokens bigint NOT NULL DEFAULT 0,
  cost_usd double precision NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (log_date, provider, model)
);

CREATE INDEX IF NOT EXISTS idx_ai_usage_log_date ON public.ai_usage_log(log_date DESC);

COMMENT ON TABLE public.ai_usage_log IS 'Daily aggregated AI usage per provider/model for cost tracking.';

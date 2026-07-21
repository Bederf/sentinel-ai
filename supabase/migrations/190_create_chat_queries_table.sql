CREATE TABLE IF NOT EXISTS public.chat_queries (
  id bigserial PRIMARY KEY,
  query text NOT NULL,
  queried_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_queries_queried_at ON public.chat_queries(queried_at DESC);

COMMENT ON TABLE public.chat_queries IS 'Feature request / chat query log.';

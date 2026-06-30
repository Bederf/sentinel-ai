CREATE TABLE IF NOT EXISTS public.call_log_escalations (
  id bigserial PRIMARY KEY,
  reporter_name text NOT NULL DEFAULT '',
  reporter_telegram_id text NOT NULL DEFAULT '',
  original_message text NOT NULL DEFAULT '',
  reason text NOT NULL DEFAULT '',
  site_id text,
  status text NOT NULL DEFAULT 'pending_review',
  escalated_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_call_log_escalations_status ON public.call_log_escalations(status);
CREATE INDEX IF NOT EXISTS idx_call_log_escalations_site ON public.call_log_escalations(site_id);

COMMENT ON TABLE public.call_log_escalations IS 'Call log escalations from Telegram bot for manual review.';

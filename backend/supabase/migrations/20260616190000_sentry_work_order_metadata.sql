-- Sentry technician work-order metadata for detail view and closeout routing

ALTER TABLE public.work_orders ADD COLUMN IF NOT EXISTS category text;
ALTER TABLE public.work_orders ADD COLUMN IF NOT EXISTS service_type text;
ALTER TABLE public.work_orders ADD COLUMN IF NOT EXISTS action_point text;
ALTER TABLE public.work_orders ADD COLUMN IF NOT EXISTS action_value text;
ALTER TABLE public.work_orders ADD COLUMN IF NOT EXISTS recommendation_id text;
ALTER TABLE public.work_orders ADD COLUMN IF NOT EXISTS notified_technician_telegram_id bigint;

CREATE INDEX IF NOT EXISTS idx_work_orders_technician_open
    ON public.work_orders(notified_technician_telegram_id, status, milestone_status);

COMMENT ON COLUMN public.work_orders.category IS 'Work-order discipline/category used by Sentry closeout routing';
COMMENT ON COLUMN public.work_orders.service_type IS 'Work-order type such as callout, breakdown, inspection, advisory';
COMMENT ON COLUMN public.work_orders.notified_technician_telegram_id IS 'Telegram ID of the technician notified by Sentry Tech bot';

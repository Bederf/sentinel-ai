-- Preserve the latest health-check failure reason in the current adapter snapshot.
-- The restored retention schema omitted this column even though adapter_health
-- history has always stored it.

ALTER TABLE public.adapter_health_current
    ADD COLUMN IF NOT EXISTS error_message text;

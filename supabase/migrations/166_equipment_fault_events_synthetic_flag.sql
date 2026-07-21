ALTER TABLE public.equipment_fault_events
ADD COLUMN IF NOT EXISTS is_synthetic boolean NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_fault_events_synthetic
ON public.equipment_fault_events (site_id, is_synthetic, recorded_at);

-- Restore columns that the code expects but were dropped in cleanup migrations

-- === predictions table ===

ALTER TABLE public.predictions ADD COLUMN IF NOT EXISTS code TEXT UNIQUE;
ALTER TABLE public.predictions ADD COLUMN IF NOT EXISTS timeframe_days INTEGER;
ALTER TABLE public.predictions ADD COLUMN IF NOT EXISTS similar_failures JSONB DEFAULT '[]';
ALTER TABLE public.predictions ADD COLUMN IF NOT EXISTS repair_cost_zar DECIMAL(12, 2);
ALTER TABLE public.predictions ADD COLUMN IF NOT EXISTS replacement_cost_zar DECIMAL(12, 2);
ALTER TABLE public.predictions ADD COLUMN IF NOT EXISTS downtime_cost_per_hour_zar DECIMAL(12, 2);
ALTER TABLE public.predictions ADD COLUMN IF NOT EXISTS potential_loss_zar DECIMAL(12, 2);
ALTER TABLE public.predictions ADD COLUMN IF NOT EXISTS urgency TEXT;
ALTER TABLE public.predictions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE public.predictions ADD COLUMN IF NOT EXISTS predicted_failure_date TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_predictions_code ON public.predictions (code);
CREATE INDEX IF NOT EXISTS idx_predictions_equipment_id ON public.predictions (equipment_id);

-- === ml_models table ===

ALTER TABLE public.ml_models ADD COLUMN IF NOT EXISTS validation_samples INTEGER;
ALTER TABLE public.ml_models ADD COLUMN IF NOT EXISTS notes TEXT;

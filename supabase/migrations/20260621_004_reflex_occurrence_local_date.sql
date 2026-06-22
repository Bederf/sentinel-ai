-- Prevent recurrence promotion from counting repeated scheduler ticks in the
-- same local time bucket as separate recurrence evidence.

ALTER TABLE public.reflex_reconciliation_occurrences
    ADD COLUMN IF NOT EXISTS local_date DATE;

UPDATE public.reflex_reconciliation_occurrences
SET local_date = (occurred_at AT TIME ZONE 'Africa/Johannesburg')::date
WHERE local_date IS NULL;

ALTER TABLE public.reflex_reconciliation_occurrences
    ALTER COLUMN local_date SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_reflex_occurrence_bucket_date
    ON public.reflex_reconciliation_occurrences (
        site_id,
        canonical_zone_id,
        system_type,
        rule_key,
        local_date,
        local_time_bucket
    );

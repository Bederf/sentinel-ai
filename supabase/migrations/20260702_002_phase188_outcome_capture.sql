-- Phase 188: structured outcome capture for post-cutover recommendation evidence.
-- Adds report-only fields; does not alter routing, approvals, or work-order creation.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'recommendations'
          AND column_name = 'phase188_outcome_status'
    ) THEN
        ALTER TABLE public.recommendations
            ADD COLUMN phase188_outcome_status text,
            ADD COLUMN phase188_linked_work_order_id uuid,
            ADD COLUMN phase188_outcome_recorded_at timestamptz,
            ADD COLUMN phase188_outcome_recorded_by text,
            ADD COLUMN phase188_outcome_source text,
            ADD COLUMN phase188_outcome_notes text;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'recommendations_phase188_outcome_status_check'
    ) THEN
        ALTER TABLE public.recommendations
            ADD CONSTRAINT recommendations_phase188_outcome_status_check
            CHECK (
                phase188_outcome_status IS NULL
                OR phase188_outcome_status IN (
                    'real_fault_confirmed',
                    'sensor_fault_confirmed',
                    'alarm_cleared',
                    'false_positive',
                    'inconclusive'
                )
            );
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'recommendations_phase188_linked_work_order_id_fkey'
    ) THEN
        ALTER TABLE public.recommendations
            ADD CONSTRAINT recommendations_phase188_linked_work_order_id_fkey
            FOREIGN KEY (phase188_linked_work_order_id)
            REFERENCES public.work_orders(id)
            ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_recommendations_phase188_work_order
    ON public.recommendations(phase188_linked_work_order_id)
    WHERE phase188_linked_work_order_id IS NOT NULL;

COMMENT ON COLUMN public.recommendations.phase188_outcome_status IS
    'Structured Phase 188 human/measured outcome: real_fault_confirmed, sensor_fault_confirmed, alarm_cleared, false_positive, or inconclusive.';

COMMENT ON COLUMN public.recommendations.phase188_linked_work_order_id IS
    'Optional work order used to collect the human outcome for this recommendation evidence row.';

COMMENT ON COLUMN public.recommendations.phase188_outcome_recorded_by IS
    'Actor who recorded the Phase 188 outcome. Required by process when phase188_outcome_status is set.';

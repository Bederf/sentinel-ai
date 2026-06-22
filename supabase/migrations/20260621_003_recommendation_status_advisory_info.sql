-- Align live recommendations.status constraint with RecommendationStatus enum.
-- The application already uses advisory_info for manual/advisory-only rows.

ALTER TABLE public.recommendations
    DROP CONSTRAINT IF EXISTS recommendations_status_check;

ALTER TABLE public.recommendations
    ADD CONSTRAINT recommendations_status_check
    CHECK (
        status = ANY (
            ARRAY[
                'pending',
                'approved',
                'rejected',
                'auto_executed',
                'advisory_info',
                'expired',
                'executed',
                'rolled_back',
                'failed'
            ]::text[]
        )
    );

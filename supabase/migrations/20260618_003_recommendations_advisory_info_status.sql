-- Add advisory_info status for operational advisories that require manual action.
-- These rows are intentionally visible to operators and must not be treated as
-- ordinary stale pending approvals.

ALTER TABLE public.recommendations
    DROP CONSTRAINT IF EXISTS recommendations_status_check;

ALTER TABLE public.recommendations
    ADD CONSTRAINT recommendations_status_check
    CHECK (
        status = ANY (
            ARRAY[
                'pending'::text,
                'approved'::text,
                'rejected'::text,
                'auto_executed'::text,
                'advisory_info'::text,
                'expired'::text,
                'executed'::text,
                'rolled_back'::text,
                'failed'::text
            ]
        )
    );

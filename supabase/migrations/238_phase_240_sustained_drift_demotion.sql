-- Phase 240 M2.3: Sustained Drift Demotion
-- Extends phase_transition_log to track drift-related demotions

BEGIN;

-- Add drift-related audit columns to phase_transition_log
ALTER TABLE phase_transition_log
ADD COLUMN IF NOT EXISTS drift_verdict TEXT,
ADD COLUMN IF NOT EXISTS drift_equipment_count INT,
ADD COLUMN IF NOT EXISTS trust_delta NUMERIC(4, 2);

-- Add comment for new columns
COMMENT ON COLUMN phase_transition_log.drift_verdict IS 'Drift verdict that triggered demotion (e.g., DRIFT_DETECTED)';
COMMENT ON COLUMN phase_transition_log.drift_equipment_count IS 'Number of equipment showing drift at time of demotion';
COMMENT ON COLUMN phase_transition_log.trust_delta IS 'Trust confidence penalty applied (e.g., -0.2)';

-- Create index for finding drift-related demotions
CREATE INDEX IF NOT EXISTS idx_phase_transition_log_drift_reason ON phase_transition_log(site_id, reason)
WHERE reason LIKE '%drift%';

COMMIT;

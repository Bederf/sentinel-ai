-- Phase 240 M2.3: Drift→Trust Causality Integration
-- Adds equipment_id column to drift_detection_log for per-equipment verdict tracking

BEGIN;

-- Add equipment_id column to drift_detection_log
ALTER TABLE drift_detection_log
ADD COLUMN equipment_id TEXT;

-- Create index for efficient verdict lookup per equipment
CREATE INDEX idx_drift_detection_log_site_equipment_latest ON drift_detection_log(
  site_id, equipment_type, equipment_id, recorded_at DESC
) WHERE verdict IS NOT NULL;

-- Add comment documenting the column
COMMENT ON COLUMN drift_detection_log.equipment_id IS 'Equipment identifier for equipment-specific drift verdicts (e.g., S002-CHILLER-B1-001)';

COMMIT;

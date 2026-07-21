-- Phase 241 M2.4 Plan 2: drift_detection_log.equipment_id
--
-- Pre-existing gap found during Plan 2: Phase 240's
-- extract_equipment_verdicts_from_db() selects equipment_id from
-- drift_detection_log, but the column was never added — every readiness
-- drift lookup errored (42703 via PostgREST) and fail-closed to UNEVALUABLE.
-- Nullable: model-level verdict rows written by the drift verdict
-- evaluation job have no single equipment instance.

ALTER TABLE drift_detection_log ADD COLUMN IF NOT EXISTS equipment_id text;

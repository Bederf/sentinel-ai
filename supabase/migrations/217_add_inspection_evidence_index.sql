-- Inspection Telemetry Bridge: Fast lookup for latest inspection score per equipment.
-- Used by InspectionTelemetryService.get_latest_inspection_score().
-- Partial index avoids scanning non-inspection asset_evidence rows.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_asset_evidence_inspection
ON asset_evidence (equipment_id, event_timestamp DESC)
WHERE source_type = 'inspection'
  AND evidence_class = 'condition_assessment';

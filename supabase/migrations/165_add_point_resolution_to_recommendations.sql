-- Phase 228: Point Resolution Audit Trail — JSONB provenance for point-name resolution
-- Migration: 20260615_001
-- Purpose: Audit trail showing how each AI-generated point name was resolved.
--          Schema: {raw, resolved, method, confidence, unit_raw, unit_resolved, note, resolved_at}
--          method ∈ {alias_table, fuzzy, exact, dropped, none}
--          confidence ∈ {exact, alias, fuzzy, dropped, none}

ALTER TABLE recommendations
ADD COLUMN IF NOT EXISTS point_resolution JSONB;

COMMENT ON COLUMN recommendations.point_resolution IS
  'Audit trail for point-name resolution during optimizer pass. '
  'Schema: {raw, resolved, method, confidence, unit_raw, unit_resolved, note, resolved_at}. '
  'method ∈ {alias_table, fuzzy, exact, dropped, none}. '
  'confidence ∈ {exact, alias, fuzzy, dropped, none}.';

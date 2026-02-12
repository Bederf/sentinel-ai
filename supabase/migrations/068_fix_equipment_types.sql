-- Phase 68-03: Fix Equipment Types from Code Patterns
--
-- Issue: Phase 078 standardized equipment codes but didn't backfill equipment.type column
-- Result: 41/47 equipment for S002 have type='unknown', but type is embedded in code
--
-- Solution: Extract equipment type from code pattern:
--   S002-CHILLER-B1-001 → CHILLER
--   site-002-S002-AHU-B1-001 → AHU
--   S002-VAV-101 → VAV
--
-- This migration safely extracts types for ALL buildings

-- ============================================================================
-- FUNCTION: Extract equipment type from code
-- ============================================================================

CREATE OR REPLACE FUNCTION extract_equipment_type(code TEXT) RETURNS TEXT AS $$
BEGIN
  -- Handle both code formats:
  -- Format 1: S002-CHILLER-B1-001 (3 parts) → part 2
  -- Format 2: site-002-S002-AHU-B1-001 (4+ parts) → part 3

  DECLARE
    parts TEXT[];
  BEGIN
    parts := string_to_array(code, '-');

    -- If 3 parts: S002-CHILLER-B1-001
    IF array_length(parts, 1) = 3 THEN
      RETURN UPPER(parts[2]);
    END IF;

    -- If 4+ parts: site-002-S002-AHU-B1-001
    IF array_length(parts, 1) >= 4 THEN
      RETURN UPPER(parts[3]);
    END IF;

    -- Fallback: return as-is if can't parse
    RETURN UPPER(code);
  EXCEPTION WHEN OTHERS THEN
    RETURN code;
  END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ============================================================================
-- MIGRATION: Fix equipment.type for all equipment with unknown/null type
-- ============================================================================

UPDATE equipment
SET type = extract_equipment_type(code)
WHERE type IS NULL
   OR type = ''
   OR type = 'unknown'
   OR LOWER(type) IN ('unknown', 'n/a', 'na', 'none');

-- Log the changes
INSERT INTO audit_log (table_name, operation, record_id, changes_summary)
SELECT
  'equipment',
  'UPDATE',
  id,
  jsonb_build_object('type', extract_equipment_type(code))
FROM equipment
WHERE type IS NULL
   OR type = ''
   OR type = 'unknown'
   OR LOWER(type) IN ('unknown', 'n/a', 'na', 'none');

-- ============================================================================
-- VERIFICATION QUERIES (for manual checking)
-- ============================================================================

-- See updated equipment types
-- SELECT code, type, extract_equipment_type(code) as extracted_type
-- FROM equipment
-- ORDER BY code;

-- See count by type before/after
-- SELECT type, COUNT(*) FROM equipment GROUP BY type ORDER BY COUNT(*) DESC;

-- See equipment at S002 site
-- SELECT code, type FROM equipment WHERE code ILIKE '%S002%' ORDER BY code;

-- ============================================================================
-- MIGRATION INFO
-- ============================================================================
-- Phase: 68-03 (ML Integration & Multi-System Grouping)
-- Purpose: Fix equipment.type field from code patterns
-- Impact: Fixes ~41 equipment items with type='unknown'
--
-- This migration is required BEFORE applying ML model registry
-- because equipment.type is used to link to ML models
--
-- Depends on: Nothing (self-contained)
-- Required by: 067_ml_model_registry.sql

-- =====================================================================
-- Migration 079: Site-005 Equipment Type Extraction
-- Fix broken equipment types (all showing '005' instead of AHU, GEN, etc.)
-- =====================================================================
--
-- Problem: All 90 equipment items at site-005 have type='005' instead of
-- proper equipment types (AHU, GEN, LIFT, JACE, CT, etc.)
--
-- Impact: Breaks technician assignment, ML model lookup, dashboard filtering
--
-- Solution: Extract types from equipment code pattern
-- Pattern: site-005-UMH-{TYPE}-{FLOOR}-{ID}.{POINT}
-- Example: site-005-UMH-AHU-L3-ICU.fan → type='AHU'

-- PHASE 1: BACKUP
-- Create backup table for safety and auditability
CREATE TABLE equipment_backup_079 AS
SELECT * FROM equipment
WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-005');

COMMENT ON TABLE equipment_backup_079 IS 'Backup of site-005 equipment before Phase 079 type extraction (Migration 079)';

-- PHASE 2: EXTRACT TYPES FROM CODES
-- Extract equipment type from code pattern: site-005-UMH-{TYPE}-...
-- Uses regex to capture the third segment after first two hyphens
UPDATE equipment
SET type = SUBSTRING(code FROM 'site-005-UMH-([A-Z]+)-')
WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-005')
  AND type = '005';

-- PHASE 3: VALIDATION QUERIES
-- These queries verify the extraction was successful

-- Query 1: Verify type distribution (should show 15 unique types, 90 total)
-- SELECT type, COUNT(*) as count
-- FROM equipment
-- WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-005')
-- GROUP BY type ORDER BY count DESC;

-- Query 2: Check for any remaining broken '005' types (should return 0 rows)
-- SELECT COUNT(*) as broken_types
-- FROM equipment
-- WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-005')
--   AND type = '005';

-- Query 3: Sample of extracted types (verify extraction pattern worked)
-- SELECT code, type FROM equipment
-- WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-005')
-- LIMIT 10;

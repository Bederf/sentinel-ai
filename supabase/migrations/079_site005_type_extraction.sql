-- =====================================================================
-- Migration 079: Site-005 Equipment Type Extraction
-- Problem: All 90 equipment items have type='005' instead of proper types
-- Solution: Extract type from code pattern: site-005-UMH-{TYPE}-{FLOOR}-{ID}.{POINT}
-- Example: site-005-UMH-AHU-L3-ICU.fan → type='AHU'
-- =====================================================================

-- PHASE 1: BACKUP
-- Create backup table for rollback safety
CREATE TABLE equipment_backup_079 AS
SELECT * FROM equipment
WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-005');

COMMENT ON TABLE equipment_backup_079 IS 'Backup before site-005 type extraction (Migration 079)';

-- PHASE 2: EXTRACT TYPES FROM CODES
-- Pattern: site-005-UMH-{TYPE}-{FLOOR}-{ID}.{POINT}
-- Examples:
--   site-005-UMH-AHU-L3-ICU.fan → AHU
--   site-005-UMH-GEN-B1-001.fuel → GEN
--   site-005-UMH-LIFT-L4-001 → LIFT
--   site-005-UMH-JACE-L3-001 → JACE

UPDATE equipment
SET type = SUBSTRING(code FROM 'site-005-UMH-([A-Z]+)-')
WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-005')
  AND type = '005';

-- PHASE 3: VALIDATION QUERIES (commented out - run manually to verify)
-- -- Verify all types extracted (should return 0 rows with type='005')
-- SELECT code, type FROM equipment
-- WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-005')
--   AND type = '005';

-- -- Show type distribution (should show AHU, GEN, LIFT, JACE, CT, FIRE, PUMP, COLD, MSB, UPS, BOILER, DB, KEF, SPLIT, MEDGAS)
-- SELECT type, COUNT(*) as count FROM equipment
-- WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-005')
-- GROUP BY type ORDER BY count DESC;

-- -- Show sample equipment after type extraction
-- SELECT code, type FROM equipment
-- WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-005')
-- LIMIT 20;

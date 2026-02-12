-- =====================================================================
-- Migration 078: Two-Tier Equipment Naming System
-- Complete standardization: Zone equipment (001-204) + Plant equipment (B1/R/G)
-- =====================================================================

-- PHASE 1: BACKUP
CREATE TABLE equipment_backup_078 AS SELECT * FROM equipment;
COMMENT ON TABLE equipment_backup_078 IS 'Backup of equipment before Phase 078 two-tier naming standardization';

-- PHASE 2: DELETE DUPLICATES (32 items total)
-- Category A: Duplicate prefix (site-002-S002-XXX) - 19 items
DELETE FROM equipment WHERE code IN (
    'site-002-S002-UNKNOWN-L1-001',
    'site-002-S002-GEN-G-001',
    'site-002-S002-UNKNOWN-201',
    'site-002-S002-CHILLER-B1-002',
    'site-002-S002-FCU-201',
    'site-002-S002-MTR-R-M',
    'site-002-S002-UNKNOWN-M-001',
    'site-002-S002-CT-B1-001',
    'site-002-S002-UPS-B1-001',
    'site-002-S002-UNKNOWN-L2-002',
    'site-002-S002-VAV-101',
    'site-002-S002-UNKNOWN-100',
    'site-002-S002-VAV-200',
    'site-002-S002-FCU-100',
    'site-002-S002-VAV-100',
    'site-002-S002-DALI-R-001',
    'site-002-S002-AHU-B1-001',
    'site-002-S002-CHILLER-B1-001',
    'site-002-S002-AHU-B1-002'
);

-- Category B: Wrong prefix duplicates - 13 items
DELETE FROM equipment WHERE code IN (
    'site-002-CH-1',
    'site-002-CH-2',
    'site-002-GEN-1',
    'site-002-VAV-100',
    'site-002-VAV-101',
    'site-002-VAV-200',
    'site-002-FCU-100',
    'site-002-DALI-100',
    'site-002-DALI-201',
    'site-002-UPS-1',
    'site-002-CT-1',
    'site-002-AHU-1',
    'site-002-AHU-2'
);

-- PHASE 3: UPDATE WRONG PREFIXES (6 unique items)
UPDATE equipment SET code = 'S002-ZONE-100' WHERE code = 'site-002-ZONE-L1';
UPDATE equipment SET code = 'S002-ZONE-200' WHERE code = 'site-002-ZONE-L2';
UPDATE equipment SET code = 'S002-DALI-B1-CTRL' WHERE code = 'site-002-DALI-CTRL-L1';
UPDATE equipment SET code = 'S002-PUMP-B1-CHW1' WHERE code = 'site-002-PUMP-CHW-1';
UPDATE equipment SET code = 'S002-PUMP-B1-CW1' WHERE code = 'site-002-PUMP-CW-1';
UPDATE equipment SET code = 'S002-MTR-B1-MAIN' WHERE code = 'site-002-MTR-MAIN';

-- PHASE 4: CONVERT WRONG FLOOR FORMATS (4 items)
UPDATE equipment SET code = 'S002-ZONE-101' WHERE code = 'S002-ZONE-L1-001';
UPDATE equipment SET code = 'S002-ZONE-201' WHERE code = 'S002-ZONE-L2-001';
UPDATE equipment SET code = 'S002-DALI-220' WHERE code = 'S002-DALI-L2-20';
UPDATE equipment SET code = 'S002-AHU-201' WHERE code = 'S002-AHU-L2-001';

-- PHASE 5: SPECIAL CASES (2 items)
UPDATE equipment SET code = 'S002-DALI-B1-CTRL' WHERE code = 'S002-DALI-L1-CTRL';
UPDATE equipment SET code = 'S002-MTR-B1-WATER' WHERE code = 'S002-MTR-W-MAIN';

-- PHASE 6: EXTRACT EQUIPMENT TYPES
-- Populate equipment.type from code pattern (S002-CHILLER-B1-001 → CHILLER)
UPDATE equipment
SET type = SPLIT_PART(code, '-', 2)
WHERE code LIKE 'S002-%'
  AND (type IS NULL OR type = 'unknown' OR type = 'UNKNOWN');

-- PHASE 7: VALIDATION QUERIES
-- The following validation queries should return 0 rows (placed as comments for reference)
-- Check for remaining non-standard codes:
-- SELECT code, type, name FROM equipment
-- WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-002')
--   AND (code LIKE 'site-002-%' OR code NOT LIKE 'S002-%');
--
-- Check for duplicates:
-- SELECT code, COUNT(*) as count FROM equipment
-- WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-002')
-- GROUP BY code HAVING COUNT(*) > 1;
--
-- Verify type extraction (should show all types populated):
-- SELECT type, COUNT(*) as count FROM equipment
-- WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-002')
-- GROUP BY type ORDER BY count DESC;

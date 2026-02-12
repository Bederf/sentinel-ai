-- =====================================================================
-- Migration 067: Equipment Zone ID Standardization
-- Replace floor-letter notation (L0-A, L1-B, L2-E) with numeric zone IDs
-- Equipment codes now directly reference zone numbers: 001, 101, 204, etc.
-- =====================================================================

-- Step 1: Update equipment codes with zone letter notation (L0-A through L2-E)
-- Pattern: S002-{TYPE}-{FLOOR}-{ZONE_LETTER} → S002-{TYPE}-{ZONE_ID}

UPDATE equipment e
SET code = (
    CASE
        -- L0 zones
        WHEN code LIKE '%L0-A' THEN SUBSTRING(code FROM 1 FOR LENGTH(code) - 5) || '001'
        WHEN code LIKE '%L0-B' THEN SUBSTRING(code FROM 1 FOR LENGTH(code) - 5) || '002'
        WHEN code LIKE '%L0-C' THEN SUBSTRING(code FROM 1 FOR LENGTH(code) - 5) || '003'
        WHEN code LIKE '%L0-D' THEN SUBSTRING(code FROM 1 FOR LENGTH(code) - 5) || '004'
        WHEN code LIKE '%L0-E' THEN SUBSTRING(code FROM 1 FOR LENGTH(code) - 5) || '005'
        -- L1 zones
        WHEN code LIKE '%L1-A' THEN SUBSTRING(code FROM 1 FOR LENGTH(code) - 5) || '100'
        WHEN code LIKE '%L1-B' THEN SUBSTRING(code FROM 1 FOR LENGTH(code) - 5) || '101'
        WHEN code LIKE '%L1-C' THEN SUBSTRING(code FROM 1 FOR LENGTH(code) - 5) || '102'
        WHEN code LIKE '%L1-D' THEN SUBSTRING(code FROM 1 FOR LENGTH(code) - 5) || '103'
        WHEN code LIKE '%L1-E' THEN SUBSTRING(code FROM 1 FOR LENGTH(code) - 5) || '104'
        -- L2 zones
        WHEN code LIKE '%L2-A' THEN SUBSTRING(code FROM 1 FOR LENGTH(code) - 5) || '200'
        WHEN code LIKE '%L2-B' THEN SUBSTRING(code FROM 1 FOR LENGTH(code) - 5) || '201'
        WHEN code LIKE '%L2-C' THEN SUBSTRING(code FROM 1 FOR LENGTH(code) - 5) || '202'
        WHEN code LIKE '%L2-D' THEN SUBSTRING(code FROM 1 FOR LENGTH(code) - 5) || '203'
        WHEN code LIKE '%L2-E' THEN SUBSTRING(code FROM 1 FOR LENGTH(code) - 5) || '204'
        ELSE code
    END
),
updated_at = NOW()
WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-002')
  AND (
    code LIKE '%L0-A' OR code LIKE '%L0-B' OR code LIKE '%L0-C' OR code LIKE '%L0-D' OR code LIKE '%L0-E' OR
    code LIKE '%L1-A' OR code LIKE '%L1-B' OR code LIKE '%L1-C' OR code LIKE '%L1-D' OR code LIKE '%L1-E' OR
    code LIKE '%L2-A' OR code LIKE '%L2-B' OR code LIKE '%L2-C' OR code LIKE '%L2-D' OR code LIKE '%L2-E'
  );

-- Step 2: Display results
SELECT 'EQUIPMENT CODE CONVERSION RESULTS' as section;

-- Show updated equipment codes
SELECT
    COUNT(*) as total_equipment,
    COUNT(CASE WHEN code ~ '[0-9]{3}$' THEN 1 END) as now_using_numeric_zones,
    COUNT(CASE WHEN code LIKE '%L%-%' THEN 1 END) as still_with_floor_notation,
    COUNT(CASE WHEN code LIKE '%-B1-%' OR code LIKE '%-R-' OR code LIKE '%-G-' THEN 1 END) as plant_room_equipment
FROM equipment
WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-002');

-- Show sample of converted equipment
SELECT 'Sample of converted equipment codes:' as info;
SELECT code, name FROM equipment
WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-002')
  AND code ~ '[0-9]{3}$'  -- Ends with 3 digits (numeric zone ID)
ORDER BY code
LIMIT 15;

-- =====================================================================
-- DOCUMENTATION
-- =====================================================================
--
-- Equipment Code Conversion:
--
-- Before (Floor-Letter Notation):
-- ──────────────────────────────
-- S002-DALI-L0-A      ← Floor L0, Zone A
-- S002-VAV-L1-B       ← Floor L1, Zone B
-- S002-DALI-L2-E      ← Floor L2, Zone E
-- S002-FCU-L0-C       ← Floor L0, Zone C
--
-- After (Numeric Zone IDs):
-- ────────────────────────
-- S002-DALI-001       ← Zone-001 (L0, Zone A)
-- S002-VAV-101        ← Zone-101 (L1, Zone B)
-- S002-DALI-204       ← Zone-204 (L2, Zone E)
-- S002-FCU-003        ← Zone-003 (L0, Zone C)
--
-- Mapping Reference:
-- ──────────────────
-- Zone 001-005 = L0 (Ground), Zones A-E
-- Zone 100-104 = L1 (Level 1), Zones A-E
-- Zone 200-204 = L2 (Level 2), Zones A-E
--
-- Benefits:
--   ✓ Equipment code directly encodes zone number
--   ✓ S002-DALI-101 immediately identifies Zone-101 equipment
--   ✓ Aligns with desk numbering (Desk-122 in Zone-101)
--   ✓ Aligns with zone numbering (001-005, 100-104, 200-204)
--   ✓ No ambiguity between floor notation and zone reference
--   ✓ Simplifies queries: WHERE code LIKE '%-101' = all Zone-101 equipment
--   ✓ One unified numbering system across zones, desks, and equipment
--
-- Plant Room Equipment:
--   Equipment with codes like S002-CHILLER-B1-001 (basement) or S002-INV-R-001 (roof)
--   remain unchanged as they serve facility infrastructure, not zone-specific areas
--
-- Verification Queries:
--   -- Count equipment per zone
--   SELECT SUBSTRING(code FROM LENGTH(code) - 2) as zone_id, COUNT(*)
--   FROM equipment WHERE code ~ '[0-9]{3}$'
--   GROUP BY SUBSTRING(code FROM LENGTH(code) - 2) ORDER BY zone_id;
--
--   -- Find all Zone-101 equipment
--   SELECT code, name FROM equipment WHERE code LIKE '%-101';
--

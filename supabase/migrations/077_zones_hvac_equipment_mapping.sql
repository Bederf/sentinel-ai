-- =====================================================================
-- Migration 082: Add HVAC Equipment Mapping to Zones Table
-- Link zones directly to their HVAC equipment (FCU, VAV, AHU)
-- Enables desk complaint handler to find zone HVAC status efficiently
-- =====================================================================

-- Step 1: Add HVAC equipment reference columns to zones table
ALTER TABLE zones
ADD COLUMN IF NOT EXISTS fcu_id TEXT,      -- Fan Coil Unit equipment code
ADD COLUMN IF NOT EXISTS vav_id TEXT,      -- Variable Air Volume equipment code
ADD COLUMN IF NOT EXISTS ahu_id TEXT,      -- Air Handling Unit equipment code
ADD COLUMN IF NOT EXISTS temp_sensor TEXT, -- Temperature sensor ID
ADD COLUMN IF NOT EXISTS co2_sensor TEXT,  -- CO2 sensor ID
ADD COLUMN IF NOT EXISTS humidity_sensor TEXT; -- Humidity sensor ID

-- Step 2: Populate HVAC equipment references from equipment table
-- Pattern: Equipment with code ending in zone_id should be linked to that zone
-- e.g., S002-FCU-101 → Zone-101, S002-VAV-101 → Zone-101

-- For each zone, find equipment that matches the zone pattern
UPDATE zones z
SET
    fcu_id = (
        SELECT code FROM equipment
        WHERE type = 'FCU'
          AND building_id = z.building_id
          AND code LIKE '%' || RIGHT(z.zone_id, 3)
        LIMIT 1
    ),
    vav_id = (
        SELECT code FROM equipment
        WHERE type = 'VAV'
          AND building_id = z.building_id
          AND code LIKE '%' || RIGHT(z.zone_id, 3)
        LIMIT 1
    ),
    ahu_id = (
        SELECT code FROM equipment
        WHERE type = 'AHU'
          AND building_id = z.building_id
          AND code LIKE '%' || RIGHT(z.zone_id, 3)
        LIMIT 1
    )
WHERE z.zone_id LIKE 'Zone-%';  -- Only for desk zones (Zone-001, Zone-101, etc.)

-- Step 3: Log population results for verification
DO $$
DECLARE
    zones_with_fcu INT;
    zones_with_vav INT;
    zones_with_ahu INT;
    total_zones INT;
BEGIN
    SELECT COUNT(*) INTO total_zones FROM zones WHERE zone_id LIKE 'Zone-%';
    SELECT COUNT(*) INTO zones_with_fcu FROM zones WHERE fcu_id IS NOT NULL;
    SELECT COUNT(*) INTO zones_with_vav FROM zones WHERE vav_id IS NOT NULL;
    SELECT COUNT(*) INTO zones_with_ahu FROM zones WHERE ahu_id IS NOT NULL;

    RAISE NOTICE 'Zone HVAC Equipment Mapping Results:';
    RAISE NOTICE '  Total desk zones: %', total_zones;
    RAISE NOTICE '  Zones with FCU mapped: %', zones_with_fcu;
    RAISE NOTICE '  Zones with VAV mapped: %', zones_with_vav;
    RAISE NOTICE '  Zones with AHU mapped: %', zones_with_ahu;
END $$;

-- Step 4: Add comment for documentation
COMMENT ON COLUMN zones.fcu_id IS 'Fan Coil Unit equipment ID serving this zone (e.g., S002-FCU-101)';
COMMENT ON COLUMN zones.vav_id IS 'Variable Air Volume damper ID serving this zone';
COMMENT ON COLUMN zones.ahu_id IS 'Air Handling Unit ID serving this zone (usually building-wide, serves multiple zones)';

-- =====================================================================
-- VERIFICATION QUERIES
-- =====================================================================
--
-- Check how many zones have equipment mapped:
-- SELECT zone_id, fcu_id, vav_id, ahu_id FROM zones WHERE zone_id LIKE 'Zone-%' ORDER BY zone_id;
--
-- Find zones WITHOUT equipment (need data entry):
-- SELECT zone_id, floor FROM zones WHERE zone_id LIKE 'Zone-%' AND fcu_id IS NULL;
--
-- Check equipment codes match naming convention:
-- SELECT DISTINCT code FROM equipment WHERE type IN ('FCU', 'VAV', 'AHU')
-- ORDER BY code;
--
-- =====================================================================
-- TROUBLESHOOTING
-- =====================================================================
--
-- If zones don't have equipment mapped:
--
-- 1. Check if equipment exists for those zones:
--    SELECT code, type FROM equipment WHERE code LIKE '%-101' ORDER BY code;
--
-- 2. Manually link equipment if needed:
--    UPDATE zones SET fcu_id = 'S002-FCU-101'
--    WHERE zone_id = 'Zone-101';
--
-- 3. Check equipment naming convention:
--    Equipment should end with zone number: S002-FCU-101, S002-VAV-101, etc.
--
-- =====================================================================

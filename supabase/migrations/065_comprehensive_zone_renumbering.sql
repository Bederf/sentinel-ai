-- =====================================================================
-- Migration 065: Comprehensive Zone Renumbering System-Wide
-- Implement numeric zone naming: 001-099 (L0), 100-199 (L1), 200-299 (L2)
-- Zone number encodes floor: first digit(s) = floor identifier
-- =====================================================================

-- Step 1: Create temporary mapping table for old → new zone IDs
CREATE TEMP TABLE zone_id_mapping (
    old_zone_id TEXT,
    new_zone_id TEXT,
    floor TEXT,
    building_code TEXT,
    PRIMARY KEY (old_zone_id, building_code)
);

-- Step 2: Build mapping from current zones to new numeric format
-- For site-002 (Sandton City Office Tower)
INSERT INTO zone_id_mapping (old_zone_id, new_zone_id, floor, building_code)
SELECT
    z.zone_id AS old_zone_id,
    CASE
        -- L0 (Ground): 001-005
        WHEN z.floor = 'L0' AND z.zone_letter = 'A' THEN 'Zone-001'
        WHEN z.floor = 'L0' AND z.zone_letter = 'B' THEN 'Zone-002'
        WHEN z.floor = 'L0' AND z.zone_letter = 'C' THEN 'Zone-003'
        WHEN z.floor = 'L0' AND z.zone_letter = 'D' THEN 'Zone-004'
        WHEN z.floor = 'L0' AND z.zone_letter = 'E' THEN 'Zone-005'
        -- L1 (Level 1): 100-104
        WHEN z.floor = 'L1' AND z.zone_letter = 'A' THEN 'Zone-100'
        WHEN z.floor = 'L1' AND z.zone_letter = 'B' THEN 'Zone-101'
        WHEN z.floor = 'L1' AND z.zone_letter = 'C' THEN 'Zone-102'
        WHEN z.floor = 'L1' AND z.zone_letter = 'D' THEN 'Zone-103'
        WHEN z.floor = 'L1' AND z.zone_letter = 'E' THEN 'Zone-104'
        -- L2 (Level 2): 200-204
        WHEN z.floor = 'L2' AND z.zone_letter = 'A' THEN 'Zone-200'
        WHEN z.floor = 'L2' AND z.zone_letter = 'B' THEN 'Zone-201'
        WHEN z.floor = 'L2' AND z.zone_letter = 'C' THEN 'Zone-202'
        WHEN z.floor = 'L2' AND z.zone_letter = 'D' THEN 'Zone-203'
        WHEN z.floor = 'L2' AND z.zone_letter = 'E' THEN 'Zone-204'
        -- B1 (Basement): 300-304 (for future use)
        WHEN z.floor = 'B1' AND z.zone_letter = 'A' THEN 'Zone-300'
        WHEN z.floor = 'B1' AND z.zone_letter = 'B' THEN 'Zone-301'
        WHEN z.floor = 'B1' AND z.zone_letter = 'C' THEN 'Zone-302'
        WHEN z.floor = 'B1' AND z.zone_letter = 'D' THEN 'Zone-303'
        WHEN z.floor = 'B1' AND z.zone_letter = 'E' THEN 'Zone-304'
        ELSE 'Zone-999'  -- Catch-all for unmapped zones
    END AS new_zone_id,
    z.floor,
    b.code
FROM zones z
JOIN buildings b ON z.building_id = b.id
WHERE b.code = 'site-002';

-- Step 3: Update zones table with new zone_id values
-- First, add new zone records with numeric IDs
INSERT INTO zones (building_id, zone_id, zone_name, floor, zone_letter, zone_type, typical_occupancy, area_sqm)
SELECT
    z.building_id,
    zim.new_zone_id,
    z.zone_name,
    z.floor,
    z.zone_letter,
    z.zone_type,
    z.typical_occupancy,
    z.area_sqm
FROM zones z
JOIN zone_id_mapping zim ON z.zone_id = zim.old_zone_id
WHERE z.zone_id != zim.new_zone_id
ON CONFLICT (building_id, zone_id) DO NOTHING;

-- Step 4: Update desks to reference new zone_ids
UPDATE desks d
SET zone_id = zim.new_zone_id,
    updated_at = NOW()
FROM zone_id_mapping zim
WHERE d.zone_id = zim.old_zone_id
  AND d.building_id = (SELECT id FROM buildings WHERE code = 'site-002')
  AND d.zone_id != zim.new_zone_id;

-- Step 5: Update DALI zone mapping table to use new format
-- First, update the desk_zone_id in dali_zone_mapping
UPDATE dali_zone_mapping dzm
SET desk_zone_id = (
    CASE
        -- L0 mappings
        WHEN dzm.desk_zone_id = 'Zone-L0-A' THEN 'Zone-001'
        WHEN dzm.desk_zone_id = 'Zone-L0-B' THEN 'Zone-002'
        WHEN dzm.desk_zone_id = 'Zone-L0-C' THEN 'Zone-003'
        WHEN dzm.desk_zone_id = 'Zone-L0-D' THEN 'Zone-004'
        WHEN dzm.desk_zone_id = 'Zone-L0-E' THEN 'Zone-005'
        -- L1 mappings
        WHEN dzm.desk_zone_id = 'Zone-L1-A' THEN 'Zone-100'
        WHEN dzm.desk_zone_id = 'Zone-L1-B' THEN 'Zone-101'
        WHEN dzm.desk_zone_id = 'Zone-L1-C' THEN 'Zone-102'
        WHEN dzm.desk_zone_id = 'Zone-L1-D' THEN 'Zone-103'
        WHEN dzm.desk_zone_id = 'Zone-L1-E' THEN 'Zone-104'
        -- L2 mappings
        WHEN dzm.desk_zone_id = 'Zone-L2-A' THEN 'Zone-200'
        WHEN dzm.desk_zone_id = 'Zone-L2-B' THEN 'Zone-201'
        WHEN dzm.desk_zone_id = 'Zone-L2-C' THEN 'Zone-202'
        WHEN dzm.desk_zone_id = 'Zone-L2-D' THEN 'Zone-203'
        WHEN dzm.desk_zone_id = 'Zone-L2-E' THEN 'Zone-204'
        ELSE dzm.desk_zone_id
    END
),
updated_at = NOW()
WHERE dzm.building_id = (SELECT id FROM buildings WHERE code = 'site-002');

-- Step 6: Update DALI sensors to use new zone format
UPDATE dali_sensors ds
SET zone_id = (
    CASE
        WHEN ds.zone_id = 'Zone-L0-A' THEN 'Zone-001'
        WHEN ds.zone_id = 'Zone-L0-B' THEN 'Zone-002'
        WHEN ds.zone_id = 'Zone-L0-C' THEN 'Zone-003'
        WHEN ds.zone_id = 'Zone-L0-D' THEN 'Zone-004'
        WHEN ds.zone_id = 'Zone-L0-E' THEN 'Zone-005'
        WHEN ds.zone_id = 'Zone-L1-A' THEN 'Zone-100'
        WHEN ds.zone_id = 'Zone-L1-B' THEN 'Zone-101'
        WHEN ds.zone_id = 'Zone-L1-C' THEN 'Zone-102'
        WHEN ds.zone_id = 'Zone-L1-D' THEN 'Zone-103'
        WHEN ds.zone_id = 'Zone-L1-E' THEN 'Zone-104'
        WHEN ds.zone_id = 'Zone-L2-A' THEN 'Zone-200'
        WHEN ds.zone_id = 'Zone-L2-B' THEN 'Zone-201'
        WHEN ds.zone_id = 'Zone-L2-C' THEN 'Zone-202'
        WHEN ds.zone_id = 'Zone-L2-D' THEN 'Zone-203'
        WHEN ds.zone_id = 'Zone-L2-E' THEN 'Zone-204'
        ELSE ds.zone_id
    END
),
    last_updated = NOW()
WHERE ds.zone_id LIKE 'Zone-L%';

-- Step 7: Update DALI luminaires to use new zone format
UPDATE dali_luminaires dl
SET zone_id = (
    CASE
        WHEN dl.zone_id = 'Zone-L0-A' THEN 'Zone-001'
        WHEN dl.zone_id = 'Zone-L0-B' THEN 'Zone-002'
        WHEN dl.zone_id = 'Zone-L0-C' THEN 'Zone-003'
        WHEN dl.zone_id = 'Zone-L0-D' THEN 'Zone-004'
        WHEN dl.zone_id = 'Zone-L0-E' THEN 'Zone-005'
        WHEN dl.zone_id = 'Zone-L1-A' THEN 'Zone-100'
        WHEN dl.zone_id = 'Zone-L1-B' THEN 'Zone-101'
        WHEN dl.zone_id = 'Zone-L1-C' THEN 'Zone-102'
        WHEN dl.zone_id = 'Zone-L1-D' THEN 'Zone-103'
        WHEN dl.zone_id = 'Zone-L1-E' THEN 'Zone-104'
        WHEN dl.zone_id = 'Zone-L2-A' THEN 'Zone-200'
        WHEN dl.zone_id = 'Zone-L2-B' THEN 'Zone-201'
        WHEN dl.zone_id = 'Zone-L2-C' THEN 'Zone-202'
        WHEN dl.zone_id = 'Zone-L2-D' THEN 'Zone-203'
        WHEN dl.zone_id = 'Zone-L2-E' THEN 'Zone-204'
        ELSE dl.zone_id
    END
),
    last_updated = NOW()
WHERE dl.zone_id LIKE 'Zone-L%';

-- Step 8: Update occupancy_history table
UPDATE occupancy_history oh
SET zone_id = (
    CASE
        WHEN oh.zone_id = 'Zone-L0-A' THEN 'Zone-001'
        WHEN oh.zone_id = 'Zone-L0-B' THEN 'Zone-002'
        WHEN oh.zone_id = 'Zone-L0-C' THEN 'Zone-003'
        WHEN oh.zone_id = 'Zone-L0-D' THEN 'Zone-004'
        WHEN oh.zone_id = 'Zone-L0-E' THEN 'Zone-005'
        WHEN oh.zone_id = 'Zone-L1-A' THEN 'Zone-100'
        WHEN oh.zone_id = 'Zone-L1-B' THEN 'Zone-101'
        WHEN oh.zone_id = 'Zone-L1-C' THEN 'Zone-102'
        WHEN oh.zone_id = 'Zone-L1-D' THEN 'Zone-103'
        WHEN oh.zone_id = 'Zone-L1-E' THEN 'Zone-104'
        WHEN oh.zone_id = 'Zone-L2-A' THEN 'Zone-200'
        WHEN oh.zone_id = 'Zone-L2-B' THEN 'Zone-201'
        WHEN oh.zone_id = 'Zone-L2-C' THEN 'Zone-202'
        WHEN oh.zone_id = 'Zone-L2-D' THEN 'Zone-203'
        WHEN oh.zone_id = 'Zone-L2-E' THEN 'Zone-204'
        ELSE oh.zone_id
    END
)
WHERE oh.zone_id LIKE 'Zone-L%';

-- Step 9: Update lighting_energy table
UPDATE lighting_energy le
SET zone_id = (
    CASE
        WHEN le.zone_id = 'Zone-L0-A' THEN 'Zone-001'
        WHEN le.zone_id = 'Zone-L0-B' THEN 'Zone-002'
        WHEN le.zone_id = 'Zone-L0-C' THEN 'Zone-003'
        WHEN le.zone_id = 'Zone-L0-D' THEN 'Zone-004'
        WHEN le.zone_id = 'Zone-L0-E' THEN 'Zone-005'
        WHEN le.zone_id = 'Zone-L1-A' THEN 'Zone-100'
        WHEN le.zone_id = 'Zone-L1-B' THEN 'Zone-101'
        WHEN le.zone_id = 'Zone-L1-C' THEN 'Zone-102'
        WHEN le.zone_id = 'Zone-L1-D' THEN 'Zone-103'
        WHEN le.zone_id = 'Zone-L1-E' THEN 'Zone-104'
        WHEN le.zone_id = 'Zone-L2-A' THEN 'Zone-200'
        WHEN le.zone_id = 'Zone-L2-B' THEN 'Zone-201'
        WHEN le.zone_id = 'Zone-L2-C' THEN 'Zone-202'
        WHEN le.zone_id = 'Zone-L2-D' THEN 'Zone-203'
        WHEN le.zone_id = 'Zone-L2-E' THEN 'Zone-204'
        ELSE le.zone_id
    END
)
WHERE le.zone_id LIKE 'Zone-L%';

-- Step 10: Update dali_zones table (legacy DALI zones)
UPDATE dali_zones dz
SET zone_id = (
    CASE
        WHEN dz.zone_id = 'Zone-L10-A' OR dz.zone_id = 'Zone-L10-N' THEN 'Zone-001'
        WHEN dz.zone_id = 'Zone-L10-B' THEN 'Zone-002'
        WHEN dz.zone_id = 'Zone-L10-C' THEN 'Zone-003'
        WHEN dz.zone_id = 'Zone-L10-D' THEN 'Zone-004'
        WHEN dz.zone_id = 'Zone-L10-E' THEN 'Zone-005'
        WHEN dz.zone_id = 'Zone-L11-A' OR dz.zone_id = 'Zone-L11-N' THEN 'Zone-100'
        WHEN dz.zone_id = 'Zone-L11-B' THEN 'Zone-101'
        WHEN dz.zone_id = 'Zone-L11-C' THEN 'Zone-102'
        WHEN dz.zone_id = 'Zone-L11-D' THEN 'Zone-103'
        WHEN dz.zone_id = 'Zone-L11-E' THEN 'Zone-104'
        WHEN dz.zone_id = 'Zone-L12-A' OR dz.zone_id = 'Zone-L12-N' THEN 'Zone-200'
        WHEN dz.zone_id = 'Zone-L12-B' THEN 'Zone-201'
        WHEN dz.zone_id = 'Zone-L12-C' THEN 'Zone-202'
        WHEN dz.zone_id = 'Zone-L12-D' THEN 'Zone-203'
        WHEN dz.zone_id = 'Zone-L12-E' THEN 'Zone-204'
        ELSE dz.zone_id
    END
),
    updated_at = NOW()
WHERE dz.zone_id LIKE 'Zone-L%' OR dz.zone_id LIKE 'Zone-L%';

-- Step 11: Delete old zone records
DELETE FROM zones z
WHERE z.zone_id LIKE 'Zone-L%'
  AND z.building_id = (SELECT id FROM buildings WHERE code = 'site-002')
  AND EXISTS (
    SELECT 1 FROM zones z2
    WHERE z2.building_id = z.building_id
      AND z2.zone_id LIKE 'Zone-[0-9]%'
  );

-- Step 12: Recreate zone_centroids view with new naming convention
DROP VIEW IF EXISTS zone_centroids CASCADE;

CREATE VIEW zone_centroids AS
SELECT
    z.building_id,
    z.zone_id,
    z.floor,
    ROUND(CAST(AVG(d.x_coord) AS NUMERIC), 2) AS centroid_x,
    ROUND(CAST(AVG(d.z_coord) AS NUMERIC), 2) AS centroid_z,
    COUNT(d.id) AS desk_count,
    ROUND(CAST(AVG(d.y_coord) AS NUMERIC), 2) AS avg_y
FROM zones z
LEFT JOIN desks d ON d.zone_id = z.zone_id AND d.building_id = z.building_id
GROUP BY z.building_id, z.zone_id, z.floor;

-- Step 13: Recreate dali_zone_alignment_status view with new naming
DROP VIEW IF EXISTS dali_zone_alignment_status CASCADE;

CREATE VIEW dali_zone_alignment_status AS
SELECT
    b.code AS building_code,
    b.name AS building_name,

    -- New numeric zone ID
    dzm.desk_zone_id,

    -- Floor derived from zone number
    CASE
        WHEN dzm.desk_zone_id LIKE 'Zone-00%' OR dzm.desk_zone_id LIKE 'Zone-0[0-9][0-9]' THEN 'L0 (Ground)'
        WHEN dzm.desk_zone_id LIKE 'Zone-1%' THEN 'L1 (Level 1)'
        WHEN dzm.desk_zone_id LIKE 'Zone-2%' THEN 'L2 (Level 2)'
        WHEN dzm.desk_zone_id LIKE 'Zone-3%' THEN 'B1 (Basement)'
        ELSE 'Unknown'
    END AS floor_info,

    -- Zone configuration
    z.zone_name,
    z.zone_type,
    z.area_sqm,

    -- Mapping quality
    dzm.mapping_confidence,
    dzm.mapping_method,

    -- Equipment counts
    (SELECT COUNT(*) FROM dali_sensors WHERE zone_id = dzm.desk_zone_id) AS sensor_count,
    (SELECT COUNT(*) FROM dali_luminaires WHERE zone_id = dzm.desk_zone_id) AS luminaire_count,
    (SELECT COUNT(*) FROM desks WHERE zone_id = dzm.desk_zone_id AND building_id = b.id) AS desk_count,

    dzm.created_at,
    dzm.updated_at
FROM dali_zone_mapping dzm
LEFT JOIN buildings b ON dzm.building_id = b.id
LEFT JOIN zones z ON z.building_id = dzm.building_id AND z.zone_id = dzm.desk_zone_id
WHERE b.code = 'site-002'
ORDER BY dzm.desk_zone_id;

-- =====================================================================
-- DOCUMENTATION AND COMMENTS
-- =====================================================================

COMMENT ON COLUMN zones.zone_id IS 'Numeric zone identifier encoding floor: 001-099 (L0), 100-199 (L1), 200-299 (L2), 300-399 (B1). First digit(s) = floor.';

COMMENT ON COLUMN desks.zone_id IS 'Numeric zone reference (e.g., Zone-001 for Ground floor Zone A). Replaces letter-based naming (Zone-L0-A).';

COMMENT ON VIEW zone_centroids IS 'Calculates zone centroids from desk positions using numeric zone IDs for accurate equipment positioning in 3D visualization.';

COMMENT ON VIEW dali_zone_alignment_status IS 'Shows DALI zone mapping status with numeric zone IDs. Zone number self-documents floor: 001-099=L0, 100-199=L1, 200-299=L2, 300-399=B1.';

-- =====================================================================
-- MIGRATION NOTES
-- =====================================================================
--
-- Zone Numbering Standard (Complete):
--   L0 (Ground):  001-099 (zones 001-005 in use)
--   L1 (Level 1): 100-199 (zones 100-104 in use)
--   L2 (Level 2): 200-299 (zones 200-204 in use)
--   B1 (Basement): 300-399 (zones 300-304 reserved)
--
-- Benefits of Numeric Naming:
--   ✓ Zone ID self-documents floor (001-099 = L0, 100-199 = L1, etc.)
--   ✓ Eliminates ambiguous naming (no more Zone-L0-A vs Zone-L10-A confusion)
--   ✓ Supports unlimited zones per floor (001-099 = 99 possible zones)
--   ✓ Simplifies equipment positioning queries
--   ✓ Aligns with DALI zone mappings for lighting control
--
-- Tables Updated:
--   zones, desks, dali_sensors, dali_luminaires, dali_zones
--   occupancy_history, lighting_energy, dali_zone_mapping
--
-- Views Updated:
--   zone_centroids (for 3D digital twin positioning)
--   dali_zone_alignment_status (for zone alignment monitoring)
--
-- Verification Query:
--   SELECT zone_id, COUNT(*) as desk_count FROM desks
--   WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-002')
--   GROUP BY zone_id ORDER BY zone_id;
--
--   Expected Output:
--   Zone-001: 21 desks (L0-A)
--   Zone-002: 20 desks (L0-B)
--   Zone-003: 20 desks (L0-C)
--   Zone-004: 20 desks (L0-D)
--   Zone-005: 20 desks (L0-E)
--   Zone-100: 20 desks (L1-A)
--   ... etc for L1 and L2
--

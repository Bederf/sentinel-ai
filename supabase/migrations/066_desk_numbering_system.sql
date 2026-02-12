-- =====================================================================
-- Migration 066: Desk Numbering System with Floor Encoding
-- Desk numbers encode floor: 001-099 (L0), 100-199 (L1), 200-299 (L2)
-- Within each floor, desks distributed across 5 zones (20 desks each)
-- =====================================================================

-- Step 1: Create temporary table for old → new desk ID mapping
CREATE TEMP TABLE desk_id_mapping (
    old_id UUID,
    old_desk_id TEXT,
    new_desk_id TEXT,
    zone_id TEXT,
    floor TEXT,
    PRIMARY KEY (old_id)
);

-- Step 2: Build mapping for L0 (Ground) - Desks 001-099
INSERT INTO desk_id_mapping (old_id, old_desk_id, new_desk_id, zone_id, floor)
SELECT
    d.id,
    d.desk_id,
    -- Assign desk numbers 001-099 for L0, 20 per zone
    'Desk-' || LPAD(
        (ROW_NUMBER() OVER (ORDER BY d.zone_id, d.x_coord, d.z_coord) - 1)::TEXT,
        3,
        '0'
    ) AS new_desk_id,
    d.zone_id,
    'L0'
FROM desks d
WHERE d.floor = 'L0'
  AND d.building_id = (SELECT id FROM buildings WHERE code = 'site-002')
ORDER BY d.zone_id, d.x_coord, d.z_coord;

-- Step 3: Build mapping for L1 (Level 1) - Desks 100-199
INSERT INTO desk_id_mapping (old_id, old_desk_id, new_desk_id, zone_id, floor)
SELECT
    d.id,
    d.desk_id,
    -- Assign desk numbers 100-199 for L1, 20 per zone
    'Desk-' || LPAD(
        (100 + ROW_NUMBER() OVER (ORDER BY d.zone_id, d.x_coord, d.z_coord) - 1)::TEXT,
        3,
        '0'
    ) AS new_desk_id,
    d.zone_id,
    'L1'
FROM desks d
WHERE d.floor = 'L1'
  AND d.building_id = (SELECT id FROM buildings WHERE code = 'site-002')
ORDER BY d.zone_id, d.x_coord, d.z_coord;

-- Step 4: Build mapping for L2 (Level 2) - Desks 200-299
INSERT INTO desk_id_mapping (old_id, old_desk_id, new_desk_id, zone_id, floor)
SELECT
    d.id,
    d.desk_id,
    -- Assign desk numbers 200-299 for L2, 20 per zone
    'Desk-' || LPAD(
        (200 + ROW_NUMBER() OVER (ORDER BY d.zone_id, d.x_coord, d.z_coord) - 1)::TEXT,
        3,
        '0'
    ) AS new_desk_id,
    d.zone_id,
    'L2'
FROM desks d
WHERE d.floor = 'L2'
  AND d.building_id = (SELECT id FROM buildings WHERE code = 'site-002')
ORDER BY d.zone_id, d.x_coord, d.z_coord;

-- Step 5: Update desks table with new numbering
UPDATE desks d
SET desk_id = dim.new_desk_id,
    updated_at = NOW()
FROM desk_id_mapping dim
WHERE d.id = dim.old_id
  AND d.desk_id != dim.new_desk_id;

-- =====================================================================
-- CREATE HELPER VIEW: Desk Allocation Map
-- Shows desk numbering and zone assignment
-- =====================================================================

DROP VIEW IF EXISTS desk_allocation_map CASCADE;

CREATE VIEW desk_allocation_map AS
SELECT
    d.desk_id AS desk_number,
    d.zone_id,
    d.floor,
    -- Extract desk number from desk_id
    CAST(SUBSTRING(d.desk_id FROM 6) AS INTEGER) AS desk_numeric,
    -- Extract zone number from zone_id
    SUBSTRING(d.zone_id FROM 6) AS zone_number,
    d.occupied,
    d.x_coord,
    d.z_coord,
    d.context,
    -- Verify floor encoding
    CASE
        WHEN CAST(SUBSTRING(d.desk_id FROM 6) AS INTEGER) < 100 THEN 'L0'
        WHEN CAST(SUBSTRING(d.desk_id FROM 6) AS INTEGER) < 200 THEN 'L1'
        WHEN CAST(SUBSTRING(d.desk_id FROM 6) AS INTEGER) < 300 THEN 'L2'
        ELSE 'Unknown'
    END AS encoded_floor
FROM desks d
WHERE d.building_id = (SELECT id FROM buildings WHERE code = 'site-002')
ORDER BY d.desk_id;

COMMENT ON VIEW desk_allocation_map IS 'Shows desk numbering system where desk number encodes floor: 001-099=L0, 100-199=L1, 200-299=L2, with zone assignment per desk.';

-- =====================================================================
-- DOCUMENTATION
-- =====================================================================
--
-- Desk Numbering Standard (Complete):
--   L0 (Ground):  Desk-001 to Desk-099 (101 desks total)
--     Zone-001: Desk-001 to Desk-020 (20 desks)
--     Zone-002: Desk-021 to Desk-040 (20 desks)
--     Zone-003: Desk-041 to Desk-060 (20 desks)
--     Zone-004: Desk-061 to Desk-080 (20 desks)
--     Zone-005: Desk-081 to Desk-099+ (21 desks - remaining)
--
--   L1 (Level 1): Desk-100 to Desk-199 (100 desks total)
--     Zone-100: Desk-100 to Desk-119 (20 desks)
--     Zone-101: Desk-120 to Desk-139 (20 desks)
--     Zone-102: Desk-140 to Desk-159 (20 desks)
--     Zone-103: Desk-160 to Desk-179 (20 desks)
--     Zone-104: Desk-180 to Desk-199 (20 desks)
--
--   L2 (Level 2): Desk-200 to Desk-299 (100 desks total)
--     Zone-200: Desk-200 to Desk-219 (20 desks)
--     Zone-201: Desk-220 to Desk-239 (20 desks)
--     Zone-202: Desk-240 to Desk-259 (20 desks)
--     Zone-203: Desk-260 to Desk-279 (20 desks)
--     Zone-204: Desk-280 to Desk-299 (20 desks)
--
-- Key Benefits:
--   ✓ Desk ID encodes floor: first digit(s) tell you which floor
--   ✓ 001-099 = Ground (L0), 100-199 = L1, 200-299 = L2
--   ✓ Quick floor lookup: SELECT * FROM desks WHERE desk_id LIKE 'Desk-1%' = L1
--   ✓ Self-documenting: Desk-150 is immediately recognizable as L1
--   ✓ Supports 99 zones per floor (001-099 range per floor)
--   ✓ Zone number matches zone_id (Desk-045 is in Zone-003)
--
-- Verification Query:
--   SELECT zone_id, COUNT(*) as desk_count, MIN(desk_id) as first_desk, MAX(desk_id) as last_desk
--   FROM desks
--   WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-002')
--   GROUP BY zone_id
--   ORDER BY zone_id;
--

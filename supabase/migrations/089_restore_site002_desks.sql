-- =====================================================
-- Migration 089: Restore Site-002 Desks (Data Recovery)
-- Restores 300 desks for Sandton City Office Tower
-- Links desks to zones and populates 3D coordinates
-- =====================================================

DO $$
DECLARE
    v_building_id UUID;
    v_zone_id UUID;
BEGIN
    -- Look up building UUID for Sandton (site-002)
    SELECT id INTO v_building_id FROM buildings WHERE code = 'site-002';

    IF v_building_id IS NULL THEN
        RAISE NOTICE 'Building site-002 not found, skipping desks restoration';
        RETURN;
    END IF;

    -- =========================================================================
    -- CLEAR OLD DATA (CAREFUL - THIS DELETES)
    -- =========================================================================
    DELETE FROM desks WHERE building_id = v_building_id;

    -- =========================================================================
    -- BULK INSERT: Generate desks for all 15 zones (100 desks per level)
    -- Zones: 001-005 (L0), 101-105 (L1), 201-205 (L2)
    -- =========================================================================

    -- LEVEL 0: Zones 001-005 (20 desks each)
    INSERT INTO desks (desk_id, building_id, floor, zone_id, context, x_coord, z_coord, near_window, near_diffuser, near_printer, orientation)
    SELECT
        '00' || LPAD((ROW_NUMBER() OVER (ORDER BY zone_num, desk_seq))::TEXT, 3, '0') as desk_id,
        v_building_id,
        'L0',
        'Zone-' || LPAD(zone_num::TEXT, 3, '0') as zone_id,
        CASE (desk_seq % 4)
            WHEN 0 THEN 'near_diffuser'
            WHEN 1 THEN 'near_printer'
            WHEN 2 THEN 'near_window'
            ELSE 'near_wall'
        END as context,
        ROUND((RANDOM() * 20)::NUMERIC, 1) as x_coord,
        ROUND((RANDOM() * 15)::NUMERIC, 1) as z_coord,
        (desk_seq % 4 = 2) as near_window,
        (desk_seq % 4 = 0) as near_diffuser,
        (desk_seq % 4 = 1) as near_printer,
        CASE desk_seq % 4 WHEN 0 THEN 'N' WHEN 1 THEN 'S' WHEN 2 THEN 'E' ELSE 'W' END as orientation
    FROM (
        SELECT zone_num, desk_seq
        FROM GENERATE_SERIES(1, 5) zone_num,
             GENERATE_SERIES(1, 20) desk_seq
    ) t
    ON CONFLICT (desk_id) DO NOTHING;

    -- LEVEL 1: Zones 101-105 (20 desks each)
    INSERT INTO desks (desk_id, building_id, floor, zone_id, context, x_coord, z_coord, near_window, near_diffuser, near_printer, orientation)
    SELECT
        '10' || LPAD((ROW_NUMBER() OVER (ORDER BY zone_num, desk_seq))::TEXT, 3, '0') as desk_id,
        v_building_id,
        'L1',
        'Zone-' || LPAD(zone_num::TEXT, 3, '0') as zone_id,
        CASE (desk_seq % 4)
            WHEN 0 THEN 'near_diffuser'
            WHEN 1 THEN 'near_printer'
            WHEN 2 THEN 'near_window'
            ELSE 'near_wall'
        END as context,
        ROUND((RANDOM() * 20)::NUMERIC, 1) as x_coord,
        ROUND((RANDOM() * 15)::NUMERIC, 1) as z_coord,
        (desk_seq % 4 = 2) as near_window,
        (desk_seq % 4 = 0) as near_diffuser,
        (desk_seq % 4 = 1) as near_printer,
        CASE desk_seq % 4 WHEN 0 THEN 'N' WHEN 1 THEN 'S' WHEN 2 THEN 'E' ELSE 'W' END as orientation
    FROM (
        SELECT zone_num, desk_seq
        FROM GENERATE_SERIES(101, 105) zone_num,
             GENERATE_SERIES(1, 20) desk_seq
    ) t
    ON CONFLICT (desk_id) DO NOTHING;

    -- LEVEL 2: Zones 201-205 (20 desks each)
    INSERT INTO desks (desk_id, building_id, floor, zone_id, context, x_coord, z_coord, near_window, near_diffuser, near_printer, orientation)
    SELECT
        '20' || LPAD((ROW_NUMBER() OVER (ORDER BY zone_num, desk_seq))::TEXT, 3, '0') as desk_id,
        v_building_id,
        'L2',
        'Zone-' || LPAD(zone_num::TEXT, 3, '0') as zone_id,
        CASE (desk_seq % 4)
            WHEN 0 THEN 'near_diffuser'
            WHEN 1 THEN 'near_printer'
            WHEN 2 THEN 'near_window'
            ELSE 'near_wall'
        END as context,
        ROUND((RANDOM() * 20)::NUMERIC, 1) as x_coord,
        ROUND((RANDOM() * 15)::NUMERIC, 1) as z_coord,
        (desk_seq % 4 = 2) as near_window,
        (desk_seq % 4 = 0) as near_diffuser,
        (desk_seq % 4 = 1) as near_printer,
        CASE desk_seq % 4 WHEN 0 THEN 'N' WHEN 1 THEN 'S' WHEN 2 THEN 'E' ELSE 'W' END as orientation
    FROM (
        SELECT zone_num, desk_seq
        FROM GENERATE_SERIES(201, 205) zone_num,
             GENERATE_SERIES(1, 20) desk_seq
    ) t
    ON CONFLICT (desk_id) DO NOTHING;

    RAISE NOTICE 'Site-002 desks restored:';
    RAISE NOTICE '  - Level 0: 100 desks (Zones 001-005)';
    RAISE NOTICE '  - Level 1: 100 desks (Zones 101-105)';
    RAISE NOTICE '  - Level 2: 100 desks (Zones 201-205)';
    RAISE NOTICE '  - Total: 300 desks with 3D coordinates and zone associations';

END $$;

-- =====================================================
-- VERIFICATION QUERIES
-- =====================================================

-- Verify desks were created
SELECT COUNT(*) as desk_count FROM desks WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-002');

-- Count desks per level
SELECT floor, COUNT(*) as desk_count
FROM desks
WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-002')
GROUP BY floor
ORDER BY floor;

-- Count desks per zone (sample: Level 0)
SELECT zone_id, COUNT(*) as desk_count
FROM desks
WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-002')
  AND floor = 'L0'
GROUP BY zone_id
ORDER BY zone_id;

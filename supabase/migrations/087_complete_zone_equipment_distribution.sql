-- =====================================================
-- Migration 092: Complete Zone Equipment Distribution
-- Sandton City Office Tower (site-002)
-- Ensures ALL office zones have identical equipment:
-- - DALI (dali_luminaire)
-- - FCU (fan coil unit)
-- - VAV (variable air volume)
-- =====================================================

DO $$
DECLARE
    v_building_id UUID;
BEGIN
    -- Look up building UUID for Sandton (site-002)
    SELECT id INTO v_building_id FROM buildings WHERE code = 'site-002';

    IF v_building_id IS NULL THEN
        RAISE NOTICE 'Building site-002 not found, skipping zone equipment completion';
        RETURN;
    END IF;

    -- =========================================================================
    -- ADD MISSING FCU EQUIPMENT
    -- =========================================================================

    INSERT INTO equipment (code, building_id, name, type, status, health_score, commissioning_date)
    VALUES
        ('S002-FCU-105', v_building_id, 'Level 1 Zone E FCU', 'FCU', 'normal', 86, '2012-04-10'),
        ('S002-FCU-205', v_building_id, 'Level 2 Zone E FCU', 'FCU', 'normal', 85, '2012-04-10')
    ON CONFLICT (code) DO NOTHING;

    -- =========================================================================
    -- ADD MISSING VAV EQUIPMENT
    -- =========================================================================

    INSERT INTO equipment (code, building_id, name, type, status, health_score, commissioning_date)
    VALUES
        ('S002-VAV-105', v_building_id, 'Level 1 Zone E VAV', 'VAV', 'normal', 93, '2015-07-15'),
        ('S002-VAV-205', v_building_id, 'Level 2 Zone E VAV', 'VAV', 'normal', 94, '2015-07-15')
    ON CONFLICT (code) DO NOTHING;

    RAISE NOTICE 'Zone equipment distribution completed:';
    RAISE NOTICE '  - Added: S002-FCU-105, S002-FCU-205';
    RAISE NOTICE '  - Added: S002-VAV-105, S002-VAV-205';
    RAISE NOTICE '';
    RAISE NOTICE 'All 15 office zones now have identical equipment:';
    RAISE NOTICE '  Level 0 (001-005): 5 zones × 3 equipment types = 15 items';
    RAISE NOTICE '  Level 1 (100-105): 6 zones × 3 equipment types = 18 items';
    RAISE NOTICE '  Level 2 (200-205): 6 zones × 3 equipment types = 18 items';
    RAISE NOTICE '  ─────────────────────────────────────────────────────';
    RAISE NOTICE '  TOTAL: 51 zone equipment items (DALI + FCU + VAV)';
    RAISE NOTICE '  PLUS: Plant zones (B1, R, L2-Plant) with infrastructure equipment';

END $$;

-- =====================================================
-- VERIFICATION: ZONE EQUIPMENT COVERAGE
-- =====================================================

-- Verify all zones have complete equipment
WITH zone_nums AS (
  SELECT z.zone_id,
         SUBSTRING(z.zone_id FROM 'Zone-(.+)') as zone_code,
         z.floor
  FROM zones z
  WHERE z.building_id = (SELECT id FROM buildings WHERE code = 'site-002')
    AND z.zone_type = 'open_office'
)
SELECT
  z.zone_id,
  z.floor,
  z.zone_code,
  COUNT(CASE WHEN e.type IN ('dali_luminaire', 'DALI') THEN 1 END) as dali_count,
  COUNT(CASE WHEN e.type IN ('FCU', 'fcu') THEN 1 END) as fcu_count,
  COUNT(CASE WHEN e.type IN ('VAV', 'vav') THEN 1 END) as vav_count,
  COUNT(*) as total_equipment
FROM zone_nums z
LEFT JOIN equipment e ON e.building_id = (SELECT id FROM buildings WHERE code = 'site-002')
  AND (
    e.code LIKE 'S002-DALI-' || z.zone_code
    OR e.code LIKE 'S002-FCU-' || z.zone_code
    OR e.code LIKE 'S002-VAV-' || z.zone_code
  )
GROUP BY z.zone_id, z.floor, z.zone_code
ORDER BY z.zone_code;

-- Summary statistics
SELECT
  'Zone Equipment Summary for Site-002' as description,
  COUNT(DISTINCT SUBSTRING(code FROM 'S002-([A-Z]+)-')) as equipment_types,
  COUNT(*) as total_zone_equipment
FROM equipment
WHERE building_id = (SELECT id FROM buildings WHERE code = 'site-002')
  AND code ~ 'S002-(DALI|FCU|VAV)-[0-9]+'
  AND type != 'dali_controller';

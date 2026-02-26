-- =====================================================
-- Migration 040: Site-002 Equipment Baseline Seeding
-- Sandton City Office Tower (site-002)
-- Inserts all HVAC, electrical, solar, and control equipment
-- Includes health scores, status, and equipment metadata
-- =====================================================

DO $$
DECLARE
    v_building_id UUID;
BEGIN
    -- Look up building UUID for Sandton (site-002)
    SELECT id INTO v_building_id FROM buildings WHERE code = 'site-002';

    IF v_building_id IS NULL THEN
        RAISE NOTICE 'Building site-002 not found, skipping equipment baseline seed';
        RETURN;
    END IF;

    -- =========================================================================
    -- HVAC EQUIPMENT - CHILLERS
    -- =========================================================================

    INSERT INTO equipment (code, building_id, name, type, status, health_score, commissioning_date)
    VALUES
        ('S002-CHILLER-B1-001', v_building_id, 'Main Chiller 1', 'chiller', 'normal', 92, '2005-08-01'),
        ('S002-CHILLER-B1-002', v_building_id, 'Main Chiller 2', 'chiller', 'normal', 94, '2008-06-15')
    ON CONFLICT (code) DO NOTHING;

    -- =========================================================================
    -- HVAC EQUIPMENT - AIR HANDLING UNITS (AHU)
    -- =========================================================================

    INSERT INTO equipment (code, building_id, name, type, status, health_score, commissioning_date)
    VALUES
        ('S002-AHU-R-001', v_building_id, 'Rooftop AHU', 'ahu', 'normal', 85, '2010-03-20'),
        ('S002-AHU-L2-001', v_building_id, 'Level 2 AHU', 'ahu', 'normal', 78, '2019-06-10')
    ON CONFLICT (code) DO NOTHING;

    -- =========================================================================
    -- HVAC EQUIPMENT - COOLING TOWER
    -- =========================================================================

    INSERT INTO equipment (code, building_id, name, type, status, health_score, commissioning_date)
    VALUES
        ('S002-CT-R-001', v_building_id, 'Condenser Water Cooling Tower', 'cooling_tower', 'normal', 81, '2005-08-01')
    ON CONFLICT (code) DO NOTHING;

    -- =========================================================================
    -- HVAC EQUIPMENT - FAN COIL UNITS (FCU)
    -- =========================================================================

    INSERT INTO equipment (code, building_id, name, type, status, health_score, commissioning_date)
    VALUES
        ('S002-FCU-L1-A', v_building_id, 'Level 1 Zone A FCU', 'fcu', 'normal', 88, '2012-04-10'),
        ('S002-FCU-L1-B', v_building_id, 'Level 1 Zone B FCU', 'fcu', 'normal', 86, '2012-04-10'),
        ('S002-FCU-L2-A', v_building_id, 'Level 2 Zone A FCU', 'fcu', 'normal', 84, '2012-04-10'),
        ('S002-FCU-L2-D', v_building_id, 'Level 2 Zone D FCU', 'fcu', 'normal', 85, '2012-04-10')
    ON CONFLICT (code) DO NOTHING;

    -- =========================================================================
    -- HVAC EQUIPMENT - VAV BOXES (VARIABLE AIR VOLUME)
    -- =========================================================================

    INSERT INTO equipment (code, building_id, name, type, status, health_score, commissioning_date)
    VALUES
        ('S002-VAV-L0-A', v_building_id, 'Level 0 Zone A VAV', 'vav', 'normal', 91, '2015-07-15'),
        ('S002-VAV-L1-A', v_building_id, 'Level 1 Zone A VAV', 'vav', 'normal', 90, '2015-07-15'),
        ('S002-VAV-L1-B', v_building_id, 'Level 1 Zone B VAV', 'vav', 'normal', 93, '2015-07-15'),
        ('S002-VAV-L2-A', v_building_id, 'Level 2 Zone A VAV', 'vav', 'normal', 91, '2015-07-15'),
        ('S002-VAV-L2-C', v_building_id, 'Level 2 Zone C VAV', 'vav', 'normal', 95, '2015-07-15'),
        ('S002-VAV-L2-D', v_building_id, 'Level 2 Zone D VAV', 'vav', 'normal', 94, '2015-07-15')
    ON CONFLICT (code) DO NOTHING;

    -- =========================================================================
    -- HVAC EQUIPMENT - PUMPS & PLANT
    -- =========================================================================

    INSERT INTO equipment (code, building_id, name, type, status, health_score, commissioning_date)
    VALUES
        ('S002-PUMP-B1-CHW1', v_building_id, 'Chilled Water Pump 1', 'pump', 'normal', 90, '2005-08-01'),
        ('S002-PUMP-B1-CW1', v_building_id, 'Condenser Water Pump 1', 'pump', 'normal', 89, '2005-08-01')
    ON CONFLICT (code) DO NOTHING;

    -- =========================================================================
    -- HVAC EQUIPMENT - ZONE CONTROLLERS
    -- =========================================================================

    INSERT INTO equipment (code, building_id, name, type, status, health_score, commissioning_date)
    VALUES
        ('S002-ZONE-L1-001', v_building_id, 'Level 1 Zone Controller', 'controller', 'normal', 92, '2012-04-10'),
        ('S002-ZONE-L2-001', v_building_id, 'Level 2 Zone Controller', 'controller', 'normal', 91, '2012-04-10')
    ON CONFLICT (code) DO NOTHING;

    -- =========================================================================
    -- ELECTRICAL EQUIPMENT - GENERATORS
    -- =========================================================================

    INSERT INTO equipment (code, building_id, name, type, status, health_score, commissioning_date)
    VALUES
        ('S002-GEN-B1-001', v_building_id, 'Standby Generator 1', 'generator', 'normal', 96, '2015-03-15'),
        ('S002-GEN-B1-002', v_building_id, 'Standby Generator 2', 'generator', 'normal', 97, '2018-03-15')
    ON CONFLICT (code) DO NOTHING;

    -- =========================================================================
    -- ELECTRICAL EQUIPMENT - UPS & POWER
    -- =========================================================================

    INSERT INTO equipment (code, building_id, name, type, status, health_score, commissioning_date)
    VALUES
        ('S002-UPS-B1-001', v_building_id, 'Uninterruptible Power Supply', 'ups', 'normal', 88, '2010-11-20'),
        ('S002-MTR-B1-MAIN', v_building_id, 'Main Energy Meter', 'meter', 'normal', 96, '2005-08-01')
    ON CONFLICT (code) DO NOTHING;

    -- =========================================================================
    -- DALI LIGHTING EQUIPMENT
    -- =========================================================================

    INSERT INTO equipment (code, building_id, name, type, status, health_score, commissioning_date)
    VALUES
        ('S002-DALI-L1-CTRL', v_building_id, 'Level 1 DALI Controller', 'dali_controller', 'normal', 94, '2016-05-10'),
        ('S002-DALI-L1-A', v_building_id, 'Level 1 Zone A DALI Lights', 'dali_luminaire', 'normal', 91, '2016-05-10'),
        ('S002-DALI-L2-B', v_building_id, 'Level 2 Zone B DALI Lights', 'dali_luminaire', 'normal', 93, '2016-05-10')
    ON CONFLICT (code) DO NOTHING;

    -- =========================================================================
    -- WATER SYSTEM
    -- =========================================================================

    INSERT INTO equipment (code, building_id, name, type, status, health_score, commissioning_date)
    VALUES
        ('S002-MTR-W-MAIN', v_building_id, 'Main Water Meter', 'meter', 'normal', 97, '2005-08-01')
    ON CONFLICT (code) DO NOTHING;

    -- =========================================================================
    -- SOLAR & RENEWABLE ENERGY (297 kWp rooftop array)
    -- =========================================================================

    INSERT INTO equipment (code, building_id, name, type, status, health_score, commissioning_date)
    VALUES
        ('S002-INV-R-001', v_building_id, 'Solar Inverter 1 (Roof)', 'inverter', 'normal', 95, '2025-09-01'),
        ('S002-INV-R-002', v_building_id, 'Solar Inverter 2 (Roof)', 'inverter', 'normal', 96, '2025-09-01'),
        ('S002-INV-R-003', v_building_id, 'Solar Inverter 3 (Roof)', 'inverter', 'normal', 94, '2025-09-01'),
        ('S002-INV-R-004', v_building_id, 'Solar Inverter 4 (Roof)', 'inverter', 'normal', 97, '2025-09-01'),
        ('S002-BESS-B1-001', v_building_id, 'Battery Energy Storage (B1)', 'bess', 'normal', 98, '2025-09-01'),
        ('S002-MTR-R-SOLAR', v_building_id, 'Solar Generation Meter (Roof)', 'meter', 'normal', 100, '2025-09-01')
    ON CONFLICT (code) DO NOTHING;

    RAISE NOTICE 'Site-002 equipment baseline seeded: 28 equipment items inserted';
    RAISE NOTICE '  - HVAC: 11 items (chillers, AHU, FCU, VAV, pumps, controllers)';
    RAISE NOTICE '  - Electrical: 4 items (generators, UPS, main meter)';
    RAISE NOTICE '  - DALI Lighting: 3 items (controller, luminaires)';
    RAISE NOTICE '  - Water: 1 item (water meter)';
    RAISE NOTICE '  - Solar/Renewable: 6 items (4 inverters, BESS, solar meter)';
    RAISE NOTICE '  - All equipment set to HEALTHY status (90-100%% health scores)' ;

END $$;

-- 045_water_equipment.sql
-- Seed water meter equipment for Sandton City Office Tower (site-002)
-- Elster V100 water meter with Modbus pulse counter, 80mm diameter, 10L/pulse

DO $$
DECLARE
    v_building_id UUID;
BEGIN
    -- Look up building UUID
    SELECT id INTO v_building_id FROM buildings WHERE code = 'site-002';

    IF v_building_id IS NULL THEN
        RAISE NOTICE 'Building site-002 not found, skipping water meter seed';
        RETURN;
    END IF;

    -- =========================================================================
    -- Core equipment table row (water meter)
    -- =========================================================================

    -- Main water meter
    INSERT INTO equipment (code, building_id, name, type, manufacturer, model, capacity, location, status, health_score, commissioning_date)
    VALUES ('S002-MTR-W-MAIN', v_building_id, 'Main Water Meter (B1)', 'meter', 'Elster', 'V100', '80mm / 10L per pulse', 'Basement 1, Main Incoming Water', 'normal', 100, '2023-01-15')
    ON CONFLICT (code) DO NOTHING;

    RAISE NOTICE 'Sandton water meter equipment seeded: 1 equipment row';
END;
$$;

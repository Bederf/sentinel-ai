-- 044_sandton_solar_equipment.sql
-- Seed solar PV + BESS equipment for Sandton City Office Tower (site-002)
-- 297 kWp rooftop array: 4x Huawei SUN2000-100KTL-M2, 1x LUNA2000-200KWH-2H1 BESS, 1x Schneider PM5110

DO $$
DECLARE
    v_building_id UUID;
BEGIN
    -- Look up building UUID
    SELECT id INTO v_building_id FROM buildings WHERE code = 'site-002';

    IF v_building_id IS NULL THEN
        RAISE NOTICE 'Building site-002 not found, skipping solar seed';
        RETURN;
    END IF;

    -- =========================================================================
    -- Core equipment table rows (6 devices)
    -- =========================================================================

    -- Inverter 1
    INSERT INTO equipment (code, building_id, name, type, manufacturer, model, capacity, location, status, health_score, commissioning_date)
    VALUES ('S002-INV-R-001', v_building_id, 'Solar Inverter 1 (Roof)', 'inverter', 'Huawei', 'SUN2000-100KTL-M2', '100 kVA', 'Roof, Solar Plant', 'normal', 95, '2025-09-01')
    ON CONFLICT (code) DO NOTHING;

    -- Inverter 2
    INSERT INTO equipment (code, building_id, name, type, manufacturer, model, capacity, location, status, health_score, commissioning_date)
    VALUES ('S002-INV-R-002', v_building_id, 'Solar Inverter 2 (Roof)', 'inverter', 'Huawei', 'SUN2000-100KTL-M2', '100 kVA', 'Roof, Solar Plant', 'normal', 96, '2025-09-01')
    ON CONFLICT (code) DO NOTHING;

    -- Inverter 3
    INSERT INTO equipment (code, building_id, name, type, manufacturer, model, capacity, location, status, health_score, commissioning_date)
    VALUES ('S002-INV-R-003', v_building_id, 'Solar Inverter 3 (Roof)', 'inverter', 'Huawei', 'SUN2000-100KTL-M2', '100 kVA', 'Roof, Solar Plant', 'normal', 94, '2025-09-01')
    ON CONFLICT (code) DO NOTHING;

    -- Inverter 4
    INSERT INTO equipment (code, building_id, name, type, manufacturer, model, capacity, location, status, health_score, commissioning_date)
    VALUES ('S002-INV-R-004', v_building_id, 'Solar Inverter 4 (Roof)', 'inverter', 'Huawei', 'SUN2000-100KTL-M2', '100 kVA', 'Roof, Solar Plant', 'normal', 97, '2025-09-01')
    ON CONFLICT (code) DO NOTHING;

    -- BESS
    INSERT INTO equipment (code, building_id, name, type, manufacturer, model, capacity, location, status, health_score, commissioning_date)
    VALUES ('S002-BESS-B1-001', v_building_id, 'Battery Energy Storage (B1)', 'bess', 'Huawei', 'LUNA2000-200KWH-2H1', '200 kWh / 100 kW', 'B1, Electrical Room', 'normal', 98, '2025-09-01')
    ON CONFLICT (code) DO NOTHING;

    -- Solar meter
    INSERT INTO equipment (code, building_id, name, type, manufacturer, model, capacity, location, status, health_score, commissioning_date)
    VALUES ('S002-MTR-R-SOLAR', v_building_id, 'Solar Generation Meter (Roof)', 'meter', 'Schneider Electric', 'PM5110', NULL, 'Roof, Solar Plant', 'normal', 100, '2025-09-01')
    ON CONFLICT (code) DO NOTHING;

    -- =========================================================================
    -- Solar-specific tables
    -- =========================================================================

    -- Solar plant
    INSERT INTO solar_plants (
        plant_id, site_id, name, capacity_kwp, panel_count, inverter_count,
        panel_model, panel_rating_w, commissioning_date, latitude, longitude,
        orientation, tilt
    ) VALUES (
        'sandton-roof', v_building_id, 'Rooftop Array', 297, 540, 4,
        'JA Solar JAM72S30-550/MR', 550, '2025-09-01', -26.11, 28.06,
        0, 15
    ) ON CONFLICT (plant_id) DO NOTHING;

    -- Inverters
    INSERT INTO solar_inverters (
        inverter_id, plant_id, site_id, name, manufacturer, model,
        rated_power_kva, mppt_count, protocol, ip_address, port, unit_id
    ) VALUES
        ('S002-INV-R-001', 'sandton-roof', v_building_id, 'Huawei INV-1', 'Huawei', 'SUN2000-100KTL-M2', 100, 10, 'modbus_tcp', '10.2.1.101', 502, 1),
        ('S002-INV-R-002', 'sandton-roof', v_building_id, 'Huawei INV-2', 'Huawei', 'SUN2000-100KTL-M2', 100, 10, 'modbus_tcp', '10.2.1.102', 502, 1),
        ('S002-INV-R-003', 'sandton-roof', v_building_id, 'Huawei INV-3', 'Huawei', 'SUN2000-100KTL-M2', 100, 10, 'modbus_tcp', '10.2.1.103', 502, 1),
        ('S002-INV-R-004', 'sandton-roof', v_building_id, 'Huawei INV-4', 'Huawei', 'SUN2000-100KTL-M2', 100, 10, 'modbus_tcp', '10.2.1.104', 502, 1)
    ON CONFLICT (inverter_id) DO NOTHING;

    -- BESS container
    INSERT INTO bess_containers (
        container_id, site_id, name, manufacturer, model,
        capacity_kwh, rated_power_kw, rack_count, cell_chemistry, protocol
    ) VALUES (
        'S002-BESS-B1-001', v_building_id, 'LUNA2000 BESS', 'Huawei', 'LUNA2000-200KWH-2H1',
        200, 100, 2, 'LFP', 'modbus_tcp'
    ) ON CONFLICT (container_id) DO NOTHING;

    RAISE NOTICE 'Sandton solar equipment seeded: 6 equipment rows, 1 plant, 4 inverters, 1 BESS';
END;
$$;

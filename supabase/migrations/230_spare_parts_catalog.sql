-- Migration: 216_spare_parts_catalog
-- Spare parts catalog + inventory for equipment maintenance tracking

CREATE TABLE IF NOT EXISTS spare_parts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    equipment_id UUID REFERENCES equipment(id) ON DELETE CASCADE,
    equipment_type TEXT NOT NULL,
    manufacturer TEXT,
    model TEXT,
    part_name TEXT NOT NULL,
    part_number TEXT,
    alternate_part_numbers TEXT[] DEFAULT '{}',
    unit_cost_zar DECIMAL(10,2),
    typical_replacement_interval_days INTEGER,
    criticality TEXT CHECK (criticality IN ('critical','essential','consumable')) DEFAULT 'consumable',
    source TEXT CHECK (source IN ('curated','scraped','manual')) DEFAULT 'curated',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_spare_parts_equipment_id ON spare_parts(equipment_id);
CREATE INDEX IF NOT EXISTS idx_spare_parts_equipment_type ON spare_parts(equipment_type);
CREATE INDEX IF NOT EXISTS idx_spare_parts_manufacturer_model ON spare_parts(manufacturer, model);

CREATE TABLE IF NOT EXISTS spare_parts_inventory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    part_id UUID NOT NULL REFERENCES spare_parts(id) ON DELETE CASCADE,
    quantity_on_hand INTEGER NOT NULL DEFAULT 0,
    min_threshold INTEGER DEFAULT 2,
    max_threshold INTEGER DEFAULT 10,
    location TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_spare_parts_inventory_part_id ON spare_parts_inventory(part_id);

-- Seed curated spare parts by equipment type from maintenance knowledge
INSERT INTO spare_parts (equipment_type, part_name, part_number, unit_cost_zar, typical_replacement_interval_days, criticality, source) VALUES
    -- Chillers
    ('chiller', 'Compressor oil filter', 'OIL-FILTER-CH', 850.00, 365, 'critical', 'curated'),
    ('chiller', 'Refrigerant filter drier', 'FD-CH-001', 1200.00, 730, 'critical', 'curated'),
    ('chiller', 'Compressor oil (5L)', 'OIL-CH-SYNTH-5L', 2500.00, 365, 'essential', 'curated'),
    ('chiller', 'Condenser coil cleaner', 'COIL-CLN-CH', 450.00, 180, 'consumable', 'curated'),
    ('chiller', 'Coolant temperature sensor', 'TEMP-SNS-CH', 680.00, 1095, 'essential', 'curated'),
    ('chiller', 'Expansion valve kit', 'EXV-CH-KIT', 3200.00, 1460, 'essential', 'curated'),
    -- AHU
    ('ahu', 'V-belt set', 'BELT-AHU-B', 550.00, 365, 'essential', 'curated'),
    ('ahu', 'Air filter MERV-13 (set)', 'FLT-AHU-M13', 380.00, 90, 'critical', 'curated'),
    ('ahu', 'Fan bearing assembly', 'BRG-AHU-6205', 950.00, 730, 'essential', 'curated'),
    ('ahu', 'Motor capacitor', 'CAP-AHU-50UF', 180.00, 730, 'consumable', 'curated'),
    ('ahu', 'Condensate drain trap', 'DRAIN-AHU', 120.00, 1095, 'consumable', 'curated'),
    -- FCU
    ('fcu', 'Fan motor (EC)', 'MTR-FCU-EC', 1800.00, 1825, 'essential', 'curated'),
    ('fcu', 'Air filter (set)', 'FLT-FCU-STD', 120.00, 90, 'critical', 'curated'),
    ('fcu', 'Valve actuator 24V', 'ACT-FCU-24V', 650.00, 1095, 'essential', 'curated'),
    ('fcu', 'Thermostat sensor', 'TSTAT-FCU', 280.00, 1460, 'consumable', 'curated'),
    ('fcu', 'Drain pan tablet kit', 'DP-FCU-KIT', 85.00, 180, 'consumable', 'curated'),
    -- VAV
    ('vav', 'Damper actuator 24V', 'ACT-VAV-24V', 720.00, 1825, 'essential', 'curated'),
    ('vav', 'Flow sensor (thermal)', 'FLW-VAV-THERM', 1100.00, 2190, 'essential', 'curated'),
    ('vav', 'Reheat coil valve', 'VLV-VAV-RH', 580.00, 1460, 'consumable', 'curated'),
    ('vav', 'Controller board', 'CTRL-VAV', 2400.00, 2920, 'critical', 'curated'),
    -- Pump
    ('pump', 'Mechanical seal kit', 'SEAL-PUMP-STD', 450.00, 730, 'essential', 'curated'),
    ('pump', 'Bearing set', 'BRG-PUMP-6305', 680.00, 1095, 'essential', 'curated'),
    ('pump', 'Impeller', 'IMP-PUMP-CI', 2200.00, 1825, 'critical', 'curated'),
    ('pump', 'Gasket set', 'GSKT-PUMP', 150.00, 365, 'consumable', 'curated'),
    -- Cooling Tower
    ('cooling_tower', 'Fan belt set', 'BELT-CT-150', 850.00, 365, 'essential', 'curated'),
    ('cooling_tower', 'Motor bearing assembly', 'BRG-CT-6205', 1200.00, 730, 'essential', 'curated'),
    ('cooling_tower', 'Fill media (bundle)', 'FILL-CT-1200', 4500.00, 2190, 'critical', 'curated'),
    ('cooling_tower', 'Drift eliminator set', 'DRIFT-CT-A', 2100.00, 2190, 'essential', 'curated'),
    ('cooling_tower', 'Water level sensor', 'LVL-CT', 380.00, 730, 'consumable', 'curated'),
    -- Generator
    ('generator', 'Oil filter', 'FLT-GEN-OIL', 320.00, 365, 'critical', 'curated'),
    ('generator', 'Fuel filter', 'FLT-GEN-FUEL', 280.00, 365, 'critical', 'curated'),
    ('generator', 'Air filter', 'FLT-GEN-AIR', 240.00, 365, 'critical', 'curated'),
    ('generator', 'Battery set (12V)', 'BAT-GEN-12V', 1800.00, 1095, 'essential', 'curated'),
    ('generator', 'Coolant (5L)', 'COOL-GEN-50', 350.00, 730, 'consumable', 'curated'),
    -- BESS
    ('bess', 'Battery module (HV)', 'BAT-BESS-HV', 8500.00, 3650, 'critical', 'curated'),
    ('bess', 'BMS communication board', 'BMS-BESS-COM', 3200.00, 2190, 'critical', 'curated'),
    ('bess', 'Thermal sensor harness', 'TEMP-BESS-HARN', 450.00, 730, 'essential', 'curated'),
    ('bess', 'Contact relay 600V', 'RLY-BESS-600V', 1200.00, 1460, 'essential', 'curated'),
    -- UPS
    ('ups', 'Battery cartridge (set)', 'BAT-UPS-CART', 3500.00, 1095, 'critical', 'curated'),
    ('ups', 'Capacitor bank', 'CAP-UPS-BANK', 1800.00, 1825, 'essential', 'curated'),
    ('ups', 'Cooling fan', 'FAN-UPS-120MM', 280.00, 730, 'essential', 'curated'),
    ('ups', 'Surge suppression module', 'SPD-UPS', 950.00, 1825, 'essential', 'curated'),
    -- Meter
    ('meter', 'CT clamp (500A)', 'CT-MTR-500A', 450.00, 3650, 'essential', 'curated'),
    ('meter', 'Power supply module', 'PSU-MTR-24V', 380.00, 2190, 'essential', 'curated'),
    ('meter', 'Communication module (RS485)', 'COM-MTR-RS485', 650.00, 2190, 'essential', 'curated'),
    -- Lighting / DALI
    ('dali', 'DALI power supply', 'PSU-DALI-64', 850.00, 2190, 'essential', 'curated'),
    ('dali', 'DALI controller board', 'CTRL-DALI-MSTR', 2400.00, 3650, 'critical', 'curated'),
    ('dali', 'LED driver (Emergency)', 'DRV-DALI-EMR', 550.00, 1825, 'essential', 'curated'),
    ('dali', 'DALI bus coupler', 'CPL-DALI-BUS', 320.00, 2190, 'consumable', 'curated');

NOTIFY pgrst, 'reload schema';

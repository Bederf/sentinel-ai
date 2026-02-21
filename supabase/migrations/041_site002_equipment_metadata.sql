-- Migration 041: Populate location and manufacturer for site-002 equipment
-- These fields were empty after auto-discovery from Niagara, causing N/A in Sentry bot alerts
-- Data sourced from mock_devices.json equipment specs and building layout

-- ============================================================================
-- HVAC Equipment
-- ============================================================================

-- AHU - Roof level (main AHU)
UPDATE equipment SET
  manufacturer = 'Carrier',
  model = '39M-80',
  location = 'Roof Level, Mechanical Room'
WHERE code = 'S002-AHU-R-001';

-- AHU - Level 2
UPDATE equipment SET
  manufacturer = 'Carrier',
  model = '39M-40',
  location = 'Level 2, Plant Room'
WHERE code = 'S002-AHU-L2-001';

-- Chiller 1 - Basement
UPDATE equipment SET
  manufacturer = 'York',
  model = 'YLAA0220HE',
  location = 'Basement 1, Chiller Plant Room'
WHERE code = 'S002-CHILLER-B1-001';

-- Chiller 2 - Basement
UPDATE equipment SET
  manufacturer = 'York',
  model = 'YLAA0220HE',
  location = 'Basement 1, Chiller Plant Room'
WHERE code = 'S002-CHILLER-B1-002';

-- Cooling Tower - Roof
UPDATE equipment SET
  manufacturer = 'Baltimore Aircoil',
  model = 'FXV-412',
  location = 'Roof Level, Cooling Tower Bay'
WHERE code = 'S002-CT-R-001';

-- FCU - Level 1 Zone A
UPDATE equipment SET
  manufacturer = 'Trane',
  model = 'WCVF-08',
  location = 'Level 1, North Wing'
WHERE code = 'S002-FCU-L1-A';

-- VAV Boxes - Level 1
UPDATE equipment SET
  manufacturer = 'Trane',
  model = 'DERA-500',
  location = 'Level 1, Zone A'
WHERE code = 'S002-VAV-L1-A';

UPDATE equipment SET
  manufacturer = 'Trane',
  model = 'DERA-500',
  location = 'Level 1, Zone B'
WHERE code = 'S002-VAV-L1-B';

-- VAV Boxes - Level 2
UPDATE equipment SET
  manufacturer = 'Trane',
  model = 'DERA-500',
  location = 'Level 2, Zone A'
WHERE code = 'S002-VAV-L2-A';

-- CHW Pump
UPDATE equipment SET
  manufacturer = 'Grundfos',
  model = 'TPE 100-250',
  location = 'Basement 1, Chiller Plant Room'
WHERE code = 'S002-PUMP-B1-CHW1';

-- CW Pump
UPDATE equipment SET
  manufacturer = 'Grundfos',
  model = 'NB 80-200',
  location = 'Basement 1, Chiller Plant Room'
WHERE code = 'S002-PUMP-B1-CW1';

-- Zone Controllers
UPDATE equipment SET
  manufacturer = 'Johnson Controls',
  model = 'FX-PC',
  location = 'Level 1, BMS Panel'
WHERE code = 'S002-ZONE-L1-001';

UPDATE equipment SET
  manufacturer = 'Johnson Controls',
  model = 'FX-PC',
  location = 'Level 2, BMS Panel'
WHERE code = 'S002-ZONE-L2-001';

-- ============================================================================
-- Electrical / Power Equipment
-- ============================================================================

-- Generator
UPDATE equipment SET
  manufacturer = 'Cummins',
  model = 'C500D5',
  location = 'Basement 1, Generator Room'
WHERE code = 'S002-GEN-B1-001';

-- UPS
UPDATE equipment SET
  manufacturer = 'Eaton',
  model = '93PM-30',
  location = 'Basement 1, UPS Room'
WHERE code = 'S002-UPS-B1-001';

-- Main Meter
UPDATE equipment SET
  manufacturer = 'Schneider Electric',
  model = 'PM8000',
  location = 'Basement 1, Main Switchboard'
WHERE code = 'S002-MTR-B1-MAIN';

-- ============================================================================
-- DALI Lighting
-- ============================================================================

-- DALI Controller
UPDATE equipment SET
  manufacturer = 'Tridonic',
  model = 'DALI-2 Scenecom',
  location = 'Level 1, Electrical DB'
WHERE code = 'S002-DALI-L1-CTRL';

-- DALI Light - Level 1 Zone A
UPDATE equipment SET
  manufacturer = 'Tridonic',
  model = 'LCA 50W 1050mA',
  location = 'Level 1, Zone A Open Plan'
WHERE code = 'S002-DALI-L1-A';

-- DALI Light - Level 2 Zone B
UPDATE equipment SET
  manufacturer = 'Tridonic',
  model = 'LCA 50W 1050mA',
  location = 'Level 2, Zone B Open Plan'
WHERE code = 'S002-DALI-L2-B';

-- ============================================================================
-- Water Meter
-- ============================================================================

-- Main Water Meter
UPDATE equipment SET
  manufacturer = 'Elster',
  model = 'V100',
  location = 'Basement 1, Main Incoming Water'
WHERE code = 'S002-MTR-W-MAIN';

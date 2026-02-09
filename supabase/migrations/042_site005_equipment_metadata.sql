-- Migration 042: Populate location and manufacturer for site-005 (Busamed Gateway) equipment
-- Data sourced from site-004 (uMhlanga) JSON files which share the same equipment model data
-- site-005 Supabase codes are point-level: site-005-UMH-AHU-L3-ICU.fan, .room, .hepa etc.
-- We use LIKE to match all points belonging to the same base equipment

-- ============================================================================
-- site-005: Busamed Gateway Private Hospital (90 equipment point rows)
-- ============================================================================

-- UMH-AHU-B1-LAUN: AHI Carrier AHU-35
UPDATE equipment SET
  manufacturer = 'AHI Carrier',
  model = 'AHU-35',
  location = 'B1, Laundry'
WHERE code LIKE 'site-005-UMH-AHU-B1-LAUN%';

-- UMH-AHU-L2-001: AHI Carrier AHU-40
UPDATE equipment SET
  manufacturer = 'AHI Carrier',
  model = 'AHU-40',
  location = 'L2, Admin'
WHERE code LIKE 'site-005-UMH-AHU-L2-001%';

-- UMH-AHU-L3-ICU: Flakt Group DFHV-120
UPDATE equipment SET
  manufacturer = 'Flakt Group',
  model = 'DFHV-120',
  location = 'L3, ICU'
WHERE code LIKE 'site-005-UMH-AHU-L3-ICU%';

-- UMH-AHU-L3-TH1: Flakt Group DFHV-100
UPDATE equipment SET
  manufacturer = 'Flakt Group',
  model = 'DFHV-100',
  location = 'L3, Theatre Suite'
WHERE code LIKE 'site-005-UMH-AHU-L3-TH1%';

-- UMH-AHU-L3-TH2: Flakt Group DFHV-100
UPDATE equipment SET
  manufacturer = 'Flakt Group',
  model = 'DFHV-100',
  location = 'L3, Theatre Suite'
WHERE code LIKE 'site-005-UMH-AHU-L3-TH2%';

-- UMH-AHU-L3-TH3: Flakt Group DFHV-80
UPDATE equipment SET
  manufacturer = 'Flakt Group',
  model = 'DFHV-80',
  location = 'L3, Theatre Suite'
WHERE code LIKE 'site-005-UMH-AHU-L3-TH3%';

-- UMH-AHU-L4-001: AHI Carrier AHU-50
UPDATE equipment SET
  manufacturer = 'AHI Carrier',
  model = 'AHU-50',
  location = 'L4, General Ward'
WHERE code LIKE 'site-005-UMH-AHU-L4-001%';

-- UMH-AHU-L5-001: AHI Carrier AHU-50
UPDATE equipment SET
  manufacturer = 'AHI Carrier',
  model = 'AHU-50',
  location = 'L5, Maternity'
WHERE code LIKE 'site-005-UMH-AHU-L5-001%';

-- UMH-AHU-L6-001: AHI Carrier AHU-60
UPDATE equipment SET
  manufacturer = 'AHI Carrier',
  model = 'AHU-60',
  location = 'L6, Medical Ward'
WHERE code LIKE 'site-005-UMH-AHU-L6-001%';

-- UMH-AHU-L7-001: Daikin AHU-D50
UPDATE equipment SET
  manufacturer = 'Daikin',
  model = 'AHU-D50',
  location = 'L7, Surgical Ward'
WHERE code LIKE 'site-005-UMH-AHU-L7-001%';

-- UMH-AHU-L8-001: Daikin AHU-D40
UPDATE equipment SET
  manufacturer = 'Daikin',
  model = 'AHU-D40',
  location = 'L8, Private Suites'
WHERE code LIKE 'site-005-UMH-AHU-L8-001%';

-- UMH-AHU-L9-001: Daikin AHU-D60
UPDATE equipment SET
  manufacturer = 'Daikin',
  model = 'AHU-D60',
  location = 'L9, Cardiology'
WHERE code LIKE 'site-005-UMH-AHU-L9-001%';

-- UMH-BOILER-B1-001: Hoval UltraGas 400
UPDATE equipment SET
  manufacturer = 'Hoval',
  model = 'UltraGas 400',
  location = 'B1, Plant Room'
WHERE code LIKE 'site-005-UMH-BOILER-B1-001%';

-- UMH-BOILER-B1-002: Hoval UltraGas 400
UPDATE equipment SET
  manufacturer = 'Hoval',
  model = 'UltraGas 400',
  location = 'B1, Plant Room'
WHERE code LIKE 'site-005-UMH-BOILER-B1-002%';

-- UMH-CHILLER-B1-001: Carrier 30XA-1002
UPDATE equipment SET
  manufacturer = 'Carrier',
  model = '30XA-1002',
  location = 'B1, Plant Room'
WHERE code LIKE 'site-005-UMH-CHILLER-B1-001%';

-- UMH-CHILLER-B1-002: Carrier 30XA-1002
UPDATE equipment SET
  manufacturer = 'Carrier',
  model = '30XA-1002',
  location = 'B1, Plant Room'
WHERE code LIKE 'site-005-UMH-CHILLER-B1-002%';

-- UMH-CHILLER-B1-003: York YCIV-0450
UPDATE equipment SET
  manufacturer = 'York',
  model = 'YCIV-0450',
  location = 'B1, Plant Room'
WHERE code LIKE 'site-005-UMH-CHILLER-B1-003%';

-- UMH-COLD-B1-001: Bitzer 4FES-5Y
UPDATE equipment SET
  manufacturer = 'Bitzer',
  model = '4FES-5Y',
  location = 'B1, Kitchen'
WHERE code LIKE 'site-005-UMH-COLD-B1-001%';

-- UMH-COLD-L1-001: Bitzer 4FES-5Y
UPDATE equipment SET
  manufacturer = 'Bitzer',
  model = '4FES-5Y',
  location = 'L1, Pharmacy'
WHERE code LIKE 'site-005-UMH-COLD-L1-001%';

-- UMH-COLD-L1-002: Bitzer 4FES-3Y
UPDATE equipment SET
  manufacturer = 'Bitzer',
  model = '4FES-3Y',
  location = 'L1, Pharmacy'
WHERE code LIKE 'site-005-UMH-COLD-L1-002%';

-- UMH-CT-R-001: BAC VXT-850
UPDATE equipment SET
  manufacturer = 'BAC',
  model = 'VXT-850',
  location = 'R, Roof Plant'
WHERE code LIKE 'site-005-UMH-CT-R-001%';

-- UMH-CT-R-002: BAC VXT-850
UPDATE equipment SET
  manufacturer = 'BAC',
  model = 'VXT-850',
  location = 'R, Roof Plant'
WHERE code LIKE 'site-005-UMH-CT-R-002%';

-- UMH-DB-L3-001: Schneider Acti 9
UPDATE equipment SET
  manufacturer = 'Schneider',
  model = 'Acti 9',
  location = 'L3, Theatre Suite'
WHERE code LIKE 'site-005-UMH-DB-L3-001%';

-- UMH-DB-L3-002: Schneider Acti 9
UPDATE equipment SET
  manufacturer = 'Schneider',
  model = 'Acti 9',
  location = 'L3, ICU'
WHERE code LIKE 'site-005-UMH-DB-L3-002%';

-- UMH-FIRE-001: Kidde VS4
UPDATE equipment SET
  manufacturer = 'Kidde',
  model = 'VS4',
  location = 'L1, Security Office'
WHERE code LIKE 'site-005-UMH-FIRE-001%';

-- UMH-GEN-B1-001: Caterpillar C32
UPDATE equipment SET
  manufacturer = 'Caterpillar',
  model = 'C32',
  location = 'B1, Generator Room'
WHERE code LIKE 'site-005-UMH-GEN-B1-001%';

-- UMH-GEN-B1-002: Caterpillar C18
UPDATE equipment SET
  manufacturer = 'Caterpillar',
  model = 'C18',
  location = 'B1, Generator Room'
WHERE code LIKE 'site-005-UMH-GEN-B1-002%';

-- UMH-GEN-B1-003: Cummins QSK38-G5
UPDATE equipment SET
  manufacturer = 'Cummins',
  model = 'QSK38-G5',
  location = 'B1, Generator Room'
WHERE code LIKE 'site-005-UMH-GEN-B1-003%';

-- UMH-JACE-001: Tridium JACE 8000
UPDATE equipment SET
  manufacturer = 'Tridium',
  model = 'JACE 8000',
  location = 'B1, BMS Room'
WHERE code LIKE 'site-005-UMH-JACE-001%';

-- UMH-JACE-002: Tridium JACE 8000
UPDATE equipment SET
  manufacturer = 'Tridium',
  model = 'JACE 8000',
  location = 'B1, BMS Room'
WHERE code LIKE 'site-005-UMH-JACE-002%';

-- UMH-KEF-B1-001: Systemair KBT 280E4
UPDATE equipment SET
  manufacturer = 'Systemair',
  model = 'KBT 280E4',
  location = 'B1, Kitchen'
WHERE code LIKE 'site-005-UMH-KEF-B1-001%';

-- UMH-LIFT-001: KONE MonoSpace 700
UPDATE equipment SET
  manufacturer = 'KONE',
  model = 'MonoSpace 700',
  location = 'B1, Lift Lobby'
WHERE code LIKE 'site-005-UMH-LIFT-001%';

-- UMH-LIFT-002: KONE MonoSpace 700
UPDATE equipment SET
  manufacturer = 'KONE',
  model = 'MonoSpace 700',
  location = 'B1, Lift Lobby'
WHERE code LIKE 'site-005-UMH-LIFT-002%';

-- UMH-LIFT-003: Schindler 5500
UPDATE equipment SET
  manufacturer = 'Schindler',
  model = '5500',
  location = 'B1, Service Area'
WHERE code LIKE 'site-005-UMH-LIFT-003%';

-- UMH-LIFT-004: KONE MonoSpace 700 Bed
UPDATE equipment SET
  manufacturer = 'KONE',
  model = 'MonoSpace 700 Bed',
  location = 'B1, Theatre Service'
WHERE code LIKE 'site-005-UMH-LIFT-004%';

-- UMH-MCU2-L2-001: Rickard MCU2-32
UPDATE equipment SET
  manufacturer = 'Rickard',
  model = 'MCU2-32',
  location = 'L2, Admin'
WHERE code LIKE 'site-005-UMH-MCU2-L2-001%';

-- UMH-MCU2-L5-001: Rickard MCU2-32
UPDATE equipment SET
  manufacturer = 'Rickard',
  model = 'MCU2-32',
  location = 'L5, Maternity'
WHERE code LIKE 'site-005-UMH-MCU2-L5-001%';

-- UMH-MCU2-L8-001: Rickard MCU2-32
UPDATE equipment SET
  manufacturer = 'Rickard',
  model = 'MCU2-32',
  location = 'L8, Private Suites'
WHERE code LIKE 'site-005-UMH-MCU2-L8-001%';

-- UMH-MEDGAS-B1-001: BOC Healthcare Manifold System
UPDATE equipment SET
  manufacturer = 'BOC Healthcare',
  model = 'Manifold System',
  location = 'B1, Medical Gas Room'
WHERE code LIKE 'site-005-UMH-MEDGAS-B1-001%';

-- UMH-MSB-B1-001: Schneider Prisma iPM
UPDATE equipment SET
  manufacturer = 'Schneider',
  model = 'Prisma iPM',
  location = 'B1, Electrical Room'
WHERE code LIKE 'site-005-UMH-MSB-B1-001%';

-- UMH-PUMP-B1-CHW1: Grundfos NB 100-200
UPDATE equipment SET
  manufacturer = 'Grundfos',
  model = 'NB 100-200',
  location = 'B1, Plant Room'
WHERE code LIKE 'site-005-UMH-PUMP-B1-CHW1%';

-- UMH-PUMP-B1-CW1: Grundfos NB 100-200
UPDATE equipment SET
  manufacturer = 'Grundfos',
  model = 'NB 100-200',
  location = 'B1, Plant Room'
WHERE code LIKE 'site-005-UMH-PUMP-B1-CW1%';

-- UMH-SPLIT-L1-001: Daikin FXAQ-P
UPDATE equipment SET
  manufacturer = 'Daikin',
  model = 'FXAQ-P',
  location = 'L1, Emergency'
WHERE code LIKE 'site-005-UMH-SPLIT-L1-001%';

-- UMH-SPLIT-L1-002: Daikin FXAQ-P
UPDATE equipment SET
  manufacturer = 'Daikin',
  model = 'FXAQ-P',
  location = 'L1, Radiology'
WHERE code LIKE 'site-005-UMH-SPLIT-L1-002%';

-- UMH-SPLIT-L2-001: Daikin FXAQ-P
UPDATE equipment SET
  manufacturer = 'Daikin',
  model = 'FXAQ-P',
  location = 'L2, IT'
WHERE code LIKE 'site-005-UMH-SPLIT-L2-001%';

-- UMH-SPLIT-L3-001: Daikin FXAQ-P
UPDATE equipment SET
  manufacturer = 'Daikin',
  model = 'FXAQ-P',
  location = 'L3, Recovery'
WHERE code LIKE 'site-005-UMH-SPLIT-L3-001%';

-- UMH-SPLIT-L3-002: Daikin FXAQ-P
UPDATE equipment SET
  manufacturer = 'Daikin',
  model = 'FXAQ-P',
  location = 'L3, Recovery'
WHERE code LIKE 'site-005-UMH-SPLIT-L3-002%';

-- UMH-SPLIT-L9-001: Daikin FXAQ-P
UPDATE equipment SET
  manufacturer = 'Daikin',
  model = 'FXAQ-P',
  location = 'L9, Cardiology'
WHERE code LIKE 'site-005-UMH-SPLIT-L9-001%';

-- UMH-UPS-L3-001: APC Symmetra PX 80kW
UPDATE equipment SET
  manufacturer = 'APC',
  model = 'Symmetra PX 80kW',
  location = 'L3, ICU'
WHERE code LIKE 'site-005-UMH-UPS-L3-001%';

-- ============================================================================
-- S002: Missed entry from migration 041
-- ============================================================================

UPDATE equipment SET
  manufacturer = 'Tridonic',
  model = 'LCA 50W 1050mA',
  location = 'Level 2, Zone 20'
WHERE code = 'S002-DALI-L2-20';

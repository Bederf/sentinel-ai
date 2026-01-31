-- =====================================================
-- Migration 016: Energy Centre Schema
-- Complete electrical distribution infrastructure
-- MV incomers, transformers, switchboards, ATS, meters, UPS
-- =====================================================

-- Energy Centres (main container)
CREATE TABLE energy_centres (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  centre_id TEXT UNIQUE NOT NULL,                  -- e.g., 'SAN-EC-001'
  name TEXT NOT NULL,
  building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
  location TEXT,

  -- Current state summary
  mains_healthy BOOLEAN DEFAULT TRUE,
  on_generator BOOLEAN DEFAULT FALSE,
  total_load_kw DECIMAL(10,2),
  total_capacity_kw DECIMAL(10,2),
  power_factor DECIMAL(4,2),

  -- SCADA network config (stored as JSON for flexibility)
  scada_config JSONB,

  -- Timestamps
  last_poll TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_energy_centres_building ON energy_centres(building_id);

CREATE TRIGGER update_energy_centres_updated_at BEFORE UPDATE ON energy_centres
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- MV Incomers (Medium Voltage supply from utility)
CREATE TABLE mv_incomers (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  incomer_id TEXT UNIQUE NOT NULL,                 -- e.g., 'SAN-MV-001'
  name TEXT NOT NULL,
  energy_centre_id UUID NOT NULL REFERENCES energy_centres(id) ON DELETE CASCADE,
  location TEXT,

  -- Ratings
  nominal_voltage_kv DECIMAL(6,2),                 -- e.g., 11.0 kV
  rated_current_a INTEGER,
  fault_level_mva DECIMAL(8,2),

  -- Current measurements
  voltage_kv DECIMAL(6,3),
  current_a DECIMAL(8,2),
  power_kw DECIMAL(10,2),
  power_kva DECIMAL(10,2),
  power_factor DECIMAL(4,2),
  frequency_hz DECIMAL(5,2),

  -- Breaker
  breaker_state TEXT DEFAULT 'open' CHECK (breaker_state IN ('open', 'closed', 'tripped', 'fault')),
  healthy BOOLEAN DEFAULT TRUE,

  -- Protection relay
  protection_relay_model TEXT,                     -- e.g., 'Siemens SIPROTEC 7SJ82'
  overcurrent_pickup_a INTEGER,
  earth_fault_pickup_a INTEGER,
  last_trip_timestamp TIMESTAMPTZ,
  last_trip_code TEXT,

  -- Utility info
  supply_point_id TEXT,                            -- Eskom reference
  tariff_type TEXT,                                -- 'Megaflex', 'Miniflex', etc.

  -- SCADA
  modbus_ip INET,
  modbus_unit_id INTEGER,
  last_poll TIMESTAMPTZ,

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_mv_incomers_ec ON mv_incomers(energy_centre_id);

CREATE TRIGGER update_mv_incomers_updated_at BEFORE UPDATE ON mv_incomers
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Transformers (MV to LV)
CREATE TABLE transformers (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  transformer_id TEXT UNIQUE NOT NULL,             -- e.g., 'SAN-TX-001'
  name TEXT NOT NULL,
  energy_centre_id UUID NOT NULL REFERENCES energy_centres(id) ON DELETE CASCADE,
  location TEXT,

  -- Ratings
  rated_power_kva INTEGER NOT NULL,
  primary_voltage_kv DECIMAL(6,2),                 -- e.g., 11.0
  secondary_voltage_v INTEGER,                     -- e.g., 400
  vector_group TEXT,                               -- e.g., 'Dyn11'
  impedance_pct DECIMAL(4,2),

  -- Current state
  load_kva DECIMAL(10,2),
  load_percent DECIMAL(5,2),

  -- Temperature monitoring
  oil_temp_c DECIMAL(5,1),
  winding_temp_c DECIMAL(5,1),
  ambient_temp_c DECIMAL(5,1),
  oil_temp_alarm BOOLEAN DEFAULT FALSE,
  winding_temp_alarm BOOLEAN DEFAULT FALSE,

  -- Tap changer
  tap_position INTEGER DEFAULT 0,
  tap_range_pct DECIMAL(4,2),
  on_load_tap_changer BOOLEAN DEFAULT FALSE,

  -- Protection/monitoring
  healthy BOOLEAN DEFAULT TRUE,
  oil_level_ok BOOLEAN DEFAULT TRUE,
  buchholz_alarm BOOLEAN DEFAULT FALSE,
  pressure_relief_ok BOOLEAN DEFAULT TRUE,
  silica_gel_ok BOOLEAN DEFAULT TRUE,

  -- Cooling
  cooling_type TEXT,                               -- 'ONAN', 'ONAF', 'OFAF'
  fans_running INTEGER DEFAULT 0,
  fans_total INTEGER,

  -- SCADA
  modbus_ip INET,
  modbus_unit_id INTEGER,
  last_poll TIMESTAMPTZ,

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_transformers_ec ON transformers(energy_centre_id);
CREATE INDEX idx_transformers_load ON transformers(load_percent);

CREATE TRIGGER update_transformers_updated_at BEFORE UPDATE ON transformers
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- LV Switchboards (Main distribution boards)
CREATE TABLE lv_switchboards (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  switchboard_id TEXT UNIQUE NOT NULL,             -- e.g., 'SAN-MSB-001'
  name TEXT NOT NULL,
  energy_centre_id UUID NOT NULL REFERENCES energy_centres(id) ON DELETE CASCADE,
  location TEXT,

  -- Ratings
  rated_voltage INTEGER DEFAULT 400,
  rated_current_a INTEGER,
  fault_rating_ka DECIMAL(6,2),
  bus_sections INTEGER DEFAULT 1,

  -- Voltage measurements
  voltage_l1_n DECIMAL(6,2),
  voltage_l2_n DECIMAL(6,2),
  voltage_l3_n DECIMAL(6,2),
  voltage_l1_l2 DECIMAL(6,2),
  voltage_l2_l3 DECIMAL(6,2),
  voltage_l3_l1 DECIMAL(6,2),
  frequency_hz DECIMAL(5,2),

  -- Breaker states
  mains_incomer_closed BOOLEAN DEFAULT TRUE,
  gen_incomer_closed BOOLEAN DEFAULT FALSE,
  bus_coupler_closed BOOLEAN DEFAULT TRUE,

  -- Power measurements
  total_power_kw DECIMAL(10,2),
  total_power_kva DECIMAL(10,2),
  power_factor DECIMAL(4,2),
  total_kwh BIGINT DEFAULT 0,

  -- Status
  healthy BOOLEAN DEFAULT TRUE,
  temperature_c DECIMAL(5,1),

  -- SCADA
  modbus_ip INET,
  modbus_unit_id INTEGER,
  last_poll TIMESTAMPTZ,

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_lv_switchboards_ec ON lv_switchboards(energy_centre_id);

CREATE TRIGGER update_lv_switchboards_updated_at BEFORE UPDATE ON lv_switchboards
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ATS Units (Automatic Transfer Switches)
CREATE TABLE ats_units (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  ats_id TEXT UNIQUE NOT NULL,                     -- e.g., 'SAN-ATS-001'
  name TEXT NOT NULL,
  energy_centre_id UUID NOT NULL REFERENCES energy_centres(id) ON DELETE CASCADE,
  location TEXT,

  -- Ratings
  ats_type TEXT DEFAULT 'mechanical' CHECK (ats_type IN ('mechanical', 'static', 'hybrid')),
  rated_current_a INTEGER,
  rated_voltage INTEGER DEFAULT 400,
  poles INTEGER DEFAULT 4,

  -- Current state
  transfer_mode TEXT DEFAULT 'closed' CHECK (transfer_mode IN ('open', 'closed')),
  position TEXT DEFAULT 'mains' CHECK (position IN ('mains', 'gen', 'off', 'transitioning')),
  mains_available BOOLEAN DEFAULT TRUE,
  generator_available BOOLEAN DEFAULT FALSE,

  -- Breaker states
  mains_breaker TEXT DEFAULT 'closed' CHECK (mains_breaker IN ('open', 'closed', 'tripped')),
  gen_breaker TEXT DEFAULT 'open' CHECK (gen_breaker IN ('open', 'closed', 'tripped')),
  bus_coupler TEXT CHECK (bus_coupler IN ('open', 'closed', 'tripped')),

  -- Transfer metrics
  last_transfer_time_ms INTEGER,
  transfer_count INTEGER DEFAULT 0,
  last_transfer_timestamp TIMESTAMPTZ,
  last_transfer_reason TEXT,

  -- Interlocks
  mechanical_interlock_ok BOOLEAN DEFAULT TRUE,
  electrical_interlock_ok BOOLEAN DEFAULT TRUE,

  -- Controller
  controller_model TEXT,                           -- e.g., 'Socomec ATyS'
  controller_ip INET,
  protocol TEXT DEFAULT 'modbus' CHECK (protocol IN ('modbus', 'bacnet', 'snmp')),
  last_poll TIMESTAMPTZ,

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ats_units_ec ON ats_units(energy_centre_id);
CREATE INDEX idx_ats_units_position ON ats_units(position);

CREATE TRIGGER update_ats_units_updated_at BEFORE UPDATE ON ats_units
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Power Meters (billing, sub-metering)
CREATE TABLE power_meters (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  meter_id TEXT UNIQUE NOT NULL,                   -- e.g., 'SAN-MTR-MAIN'
  name TEXT NOT NULL,
  energy_centre_id UUID NOT NULL REFERENCES energy_centres(id) ON DELETE CASCADE,
  location TEXT,

  -- Meter info
  meter_type TEXT DEFAULT 'main' CHECK (meter_type IN ('main', 'generator', 'sub', 'tenant', 'pv')),
  manufacturer TEXT,
  model TEXT,
  serial_number TEXT,
  ct_ratio TEXT,                                   -- e.g., '4000/5'
  vt_ratio TEXT,

  -- Voltage measurements
  voltage_l1_n DECIMAL(6,2),
  voltage_l2_n DECIMAL(6,2),
  voltage_l3_n DECIMAL(6,2),

  -- Current measurements
  current_l1 DECIMAL(10,2),
  current_l2 DECIMAL(10,2),
  current_l3 DECIMAL(10,2),
  current_n DECIMAL(10,2),

  -- Power measurements
  active_power_kw DECIMAL(12,2),
  reactive_power_kvar DECIMAL(12,2),
  apparent_power_kva DECIMAL(12,2),
  power_factor DECIMAL(4,2),
  frequency_hz DECIMAL(5,2),

  -- Energy counters
  kwh_import BIGINT DEFAULT 0,
  kwh_export BIGINT DEFAULT 0,
  kvarh_import BIGINT DEFAULT 0,
  kvarh_export BIGINT DEFAULT 0,

  -- Demand
  max_demand_kw DECIMAL(12,2),
  max_demand_timestamp TIMESTAMPTZ,
  max_demand_kva DECIMAL(12,2),

  -- Power quality
  thd_voltage_pct DECIMAL(5,2),
  thd_current_pct DECIMAL(5,2),
  voltage_unbalance_pct DECIMAL(5,2),

  -- Tariff (for billing meters)
  tariff_type TEXT,
  tou_period TEXT,                                 -- 'peak', 'standard', 'off_peak'

  -- SCADA
  protocol TEXT DEFAULT 'modbus' CHECK (protocol IN ('modbus', 'bacnet', 'dlms')),
  ip_address INET,
  modbus_unit_id INTEGER,
  last_poll TIMESTAMPTZ,

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_power_meters_ec ON power_meters(energy_centre_id);
CREATE INDEX idx_power_meters_type ON power_meters(meter_type);

CREATE TRIGGER update_power_meters_updated_at BEFORE UPDATE ON power_meters
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- PFC Banks (Power Factor Correction)
CREATE TABLE pfc_banks (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  pfc_id TEXT UNIQUE NOT NULL,                     -- e.g., 'SAN-PFC-001'
  name TEXT NOT NULL,
  energy_centre_id UUID NOT NULL REFERENCES energy_centres(id) ON DELETE CASCADE,
  location TEXT,

  -- Capacity
  total_kvar INTEGER,
  steps INTEGER,
  step_size_kvar INTEGER,

  -- Current state
  active_steps INTEGER DEFAULT 0,
  active_kvar INTEGER DEFAULT 0,
  target_power_factor DECIMAL(4,2) DEFAULT 0.95,
  current_power_factor DECIMAL(4,2),

  -- Controller
  controller_model TEXT,                           -- e.g., 'Schneider Varlogic NR12'
  auto_mode BOOLEAN DEFAULT TRUE,

  -- Status
  healthy BOOLEAN DEFAULT TRUE,
  capacitor_temps_ok BOOLEAN DEFAULT TRUE,
  fuse_status_ok BOOLEAN DEFAULT TRUE,

  -- SCADA
  modbus_ip INET,
  modbus_unit_id INTEGER,
  last_poll TIMESTAMPTZ,

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_pfc_banks_ec ON pfc_banks(energy_centre_id);

CREATE TRIGGER update_pfc_banks_updated_at BEFORE UPDATE ON pfc_banks
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- UPS Systems
CREATE TABLE ups_systems (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  ups_id TEXT UNIQUE NOT NULL,                     -- e.g., 'SAN-UPS-001'
  name TEXT NOT NULL,
  energy_centre_id UUID NOT NULL REFERENCES energy_centres(id) ON DELETE CASCADE,
  location TEXT,

  -- Ratings
  rated_power_kva DECIMAL(10,2),
  rated_power_kw DECIMAL(10,2),
  topology TEXT DEFAULT 'online' CHECK (topology IN ('online', 'offline', 'line_interactive')),
  manufacturer TEXT,
  model TEXT,

  -- Input
  input_voltage DECIMAL(6,2),
  input_frequency DECIMAL(5,2),
  input_healthy BOOLEAN DEFAULT TRUE,

  -- Output
  output_voltage DECIMAL(6,2),
  output_frequency DECIMAL(5,2),
  load_kw DECIMAL(10,2),
  load_percent DECIMAL(5,2),

  -- Battery
  battery_voltage DECIMAL(6,2),
  battery_current DECIMAL(8,2),
  battery_charge_pct DECIMAL(5,2),
  battery_runtime_min INTEGER,
  battery_temp_c DECIMAL(5,1),
  battery_health_pct DECIMAL(5,2),
  battery_test_date DATE,
  battery_replace_date DATE,

  -- Mode and status
  mode TEXT DEFAULT 'online' CHECK (mode IN ('online', 'battery', 'bypass', 'eco', 'maintenance')),
  on_battery BOOLEAN DEFAULT FALSE,
  on_bypass BOOLEAN DEFAULT FALSE,
  overload BOOLEAN DEFAULT FALSE,
  alarms JSONB DEFAULT '[]',

  -- SCADA
  protocol TEXT DEFAULT 'snmp' CHECK (protocol IN ('snmp', 'modbus')),
  ip_address INET,
  modbus_unit_id INTEGER,
  last_poll TIMESTAMPTZ,

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ups_systems_ec ON ups_systems(energy_centre_id);
CREATE INDEX idx_ups_systems_battery ON ups_systems(on_battery) WHERE on_battery = TRUE;
CREATE INDEX idx_ups_systems_charge ON ups_systems(battery_charge_pct);

CREATE TRIGGER update_ups_systems_updated_at BEFORE UPDATE ON ups_systems
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Feeders (distribution feeders from main switchboard)
CREATE TABLE feeders (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  feeder_id TEXT UNIQUE NOT NULL,                  -- e.g., 'SAN-FDR-L12'
  name TEXT NOT NULL,
  energy_centre_id UUID NOT NULL REFERENCES energy_centres(id) ON DELETE CASCADE,
  switchboard_id UUID REFERENCES lv_switchboards(id) ON DELETE SET NULL,

  -- Ratings
  rated_current_a INTEGER,

  -- Current state
  breaker_state TEXT DEFAULT 'closed' CHECK (breaker_state IN ('open', 'closed', 'tripped')),
  current_a DECIMAL(10,2),
  power_kw DECIMAL(10,2),

  -- Load type classification
  load_type TEXT CHECK (load_type IN ('hvac', 'lighting', 'lifts', 'general', 'it', 'critical')),
  priority TEXT DEFAULT 'P3' CHECK (priority IN ('P1', 'P2', 'P3', 'P4', 'P5')),

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_feeders_ec ON feeders(energy_centre_id);
CREATE INDEX idx_feeders_switchboard ON feeders(switchboard_id);
CREATE INDEX idx_feeders_priority ON feeders(priority);

CREATE TRIGGER update_feeders_updated_at BEFORE UPDATE ON feeders
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Comments for documentation
COMMENT ON TABLE energy_centres IS 'Main energy centre container linking all electrical infrastructure';
COMMENT ON TABLE mv_incomers IS 'Medium voltage incomers from utility (Eskom)';
COMMENT ON TABLE transformers IS 'MV/LV transformers with temperature and protection monitoring';
COMMENT ON TABLE lv_switchboards IS 'Low voltage main distribution switchboards';
COMMENT ON TABLE ats_units IS 'Automatic Transfer Switches for mains/generator changeover';
COMMENT ON TABLE power_meters IS 'Energy meters for billing, sub-metering, and PV monitoring';
COMMENT ON TABLE pfc_banks IS 'Power Factor Correction capacitor banks';
COMMENT ON TABLE ups_systems IS 'Uninterruptible Power Supply systems with battery monitoring';
COMMENT ON TABLE feeders IS 'Distribution feeders from main switchboard to loads';
COMMENT ON COLUMN ats_units.transfer_mode IS 'closed = dead transition (no simultaneous sources)';
COMMENT ON COLUMN transformers.vector_group IS 'Transformer winding configuration (Dyn11, Yyn0, etc.)';

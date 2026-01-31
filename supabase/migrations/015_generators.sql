-- =====================================================
-- Migration 015: Generators Schema
-- Diesel generators with DSE controllers for backup power
-- Includes fuel tanks, generator groups (N+1 redundancy)
-- =====================================================

-- Diesel Tanks (must be created first, generators reference them)
CREATE TABLE diesel_tanks (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tank_id TEXT UNIQUE NOT NULL,                    -- e.g., 'SAN-TANK-001'
  name TEXT NOT NULL,
  building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
  location TEXT,

  -- Capacity
  capacity_liters INTEGER NOT NULL,
  current_level_liters INTEGER,
  current_level_pct DECIMAL(5,2),

  -- Alarm thresholds
  low_level_alarm_pct DECIMAL(5,2) DEFAULT 20.0,
  reorder_level_pct DECIMAL(5,2) DEFAULT 30.0,
  high_level_alarm_pct DECIMAL(5,2) DEFAULT 95.0,

  -- Consumption tracking
  daily_consumption_avg DECIMAL(8,2),              -- Liters per day average
  days_remaining INTEGER,                          -- Calculated from consumption

  -- Supply chain
  supplier TEXT,
  supplier_contact TEXT,
  last_fill_date DATE,
  last_fill_liters INTEGER,

  -- Status
  leak_detected BOOLEAN DEFAULT FALSE,
  level_sensor_fault BOOLEAN DEFAULT FALSE,

  -- SCADA
  modbus_ip INET,
  modbus_unit_id INTEGER,
  last_poll TIMESTAMPTZ,

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_diesel_tanks_building ON diesel_tanks(building_id);
CREATE INDEX idx_diesel_tanks_level ON diesel_tanks(current_level_pct);

CREATE TRIGGER update_diesel_tanks_updated_at BEFORE UPDATE ON diesel_tanks
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Generator Groups (N+1 redundancy configuration)
CREATE TABLE generator_groups (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  group_id TEXT UNIQUE NOT NULL,                   -- e.g., 'SAN-GRP-001'
  name TEXT NOT NULL,
  building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
  diesel_tank_id UUID REFERENCES diesel_tanks(id) ON DELETE SET NULL,

  -- Configuration
  total_generators INTEGER NOT NULL,
  required_running INTEGER NOT NULL,               -- N in N+1 redundancy
  transfer_mode TEXT DEFAULT 'closed' CHECK (transfer_mode IN ('open', 'closed')),
  sync_mode TEXT DEFAULT 'automatic' CHECK (sync_mode IN ('automatic', 'manual')),
  load_share_enabled BOOLEAN DEFAULT TRUE,

  -- Timing
  auto_start_delay_sec INTEGER DEFAULT 5,
  cooldown_period_sec INTEGER DEFAULT 300,
  rotation_interval_hours INTEGER DEFAULT 168,     -- Weekly rotation

  -- Current state
  generators_running INTEGER DEFAULT 0,
  total_load_kw DECIMAL(10,2) DEFAULT 0,
  total_capacity_kw DECIMAL(10,2),
  load_percent DECIMAL(5,2) DEFAULT 0,
  ats_position TEXT DEFAULT 'mains' CHECK (ats_position IN ('mains', 'gen', 'transitioning')),
  mains_healthy BOOLEAN DEFAULT TRUE,

  -- SCADA
  last_poll TIMESTAMPTZ,

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_generator_groups_building ON generator_groups(building_id);
CREATE INDEX idx_generator_groups_ats ON generator_groups(ats_position);

CREATE TRIGGER update_generator_groups_updated_at BEFORE UPDATE ON generator_groups
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Generators (individual units with DSE controllers)
CREATE TABLE generators (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  generator_id TEXT UNIQUE NOT NULL,               -- e.g., 'SAN-GEN-001'
  name TEXT NOT NULL,
  building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
  group_id UUID REFERENCES generator_groups(id) ON DELETE SET NULL,
  diesel_tank_id UUID REFERENCES diesel_tanks(id) ON DELETE SET NULL,
  location TEXT,

  -- Controller (DSE8610, etc.)
  controller_model TEXT,                           -- e.g., 'DSE8610'
  controller_ip INET,
  modbus_port INTEGER DEFAULT 502,
  modbus_unit_id INTEGER,

  -- Ratings
  rated_power_kw DECIMAL(10,2),
  rated_power_kva DECIMAL(10,2),
  rated_voltage INTEGER DEFAULT 400,
  rated_frequency INTEGER DEFAULT 50,
  rated_current_a DECIMAL(8,2),

  -- Current state
  status TEXT DEFAULT 'standby' CHECK (status IN ('standby', 'starting', 'running', 'cooling', 'fault', 'maintenance', 'offline')),
  mains_available BOOLEAN DEFAULT TRUE,
  engine_running BOOLEAN DEFAULT FALSE,
  on_load BOOLEAN DEFAULT FALSE,

  -- Engine
  rpm INTEGER DEFAULT 0,
  oil_pressure_kpa DECIMAL(8,2),
  coolant_temp_c DECIMAL(5,1),
  exhaust_temp_c DECIMAL(5,1),
  run_hours DECIMAL(10,1) DEFAULT 0,
  total_starts INTEGER DEFAULT 0,
  start_attempts INTEGER DEFAULT 0,
  fuel_rate_lph DECIMAL(8,2) DEFAULT 0,

  -- Electrical output (when running)
  output_voltage_l1 DECIMAL(6,1),
  output_voltage_l2 DECIMAL(6,1),
  output_voltage_l3 DECIMAL(6,1),
  output_current_l1 DECIMAL(8,2),
  output_current_l2 DECIMAL(8,2),
  output_current_l3 DECIMAL(8,2),
  output_power_kw DECIMAL(10,2),
  output_power_kva DECIMAL(10,2),
  output_frequency DECIMAL(5,2),
  power_factor DECIMAL(4,2),

  -- Battery
  battery_voltage DECIMAL(5,2),
  charger_current DECIMAL(5,2),
  battery_low BOOLEAN DEFAULT FALSE,
  charger_fault BOOLEAN DEFAULT FALSE,

  -- Fuel
  fuel_level_pct INTEGER,

  -- Alarms (JSON array of active alarm codes)
  alarms JSONB DEFAULT '[]',
  alarm_count INTEGER DEFAULT 0,

  -- Maintenance
  last_service_date DATE,
  next_service_hours DECIMAL(10,1),
  last_oil_change_hours DECIMAL(10,1),
  next_oil_change_hours DECIMAL(10,1),

  -- Group management
  priority INTEGER DEFAULT 1,                      -- Startup priority within group (1 = first)

  -- SCADA
  last_poll TIMESTAMPTZ,

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_generators_building ON generators(building_id);
CREATE INDEX idx_generators_group ON generators(group_id);
CREATE INDEX idx_generators_status ON generators(status);
CREATE INDEX idx_generators_tank ON generators(diesel_tank_id);
CREATE INDEX idx_generators_running ON generators(engine_running) WHERE engine_running = TRUE;

CREATE TRIGGER update_generators_updated_at BEFORE UPDATE ON generators
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Generator Run History (time-series for analytics)
CREATE TABLE generator_run_history (
  time TIMESTAMPTZ NOT NULL,
  generator_id TEXT NOT NULL,
  building_id UUID REFERENCES buildings(id) ON DELETE CASCADE,
  status TEXT,
  rpm INTEGER,
  oil_pressure_kpa DECIMAL(8,2),
  coolant_temp_c DECIMAL(5,1),
  output_power_kw DECIMAL(10,2),
  fuel_rate_lph DECIMAL(8,2),
  reason TEXT,                                     -- 'scheduled_test', 'mains_fail', 'rotation'
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_gen_history_gen_time ON generator_run_history(generator_id, time DESC);
CREATE INDEX idx_gen_history_building_time ON generator_run_history(building_id, time DESC);

-- Comments for documentation
COMMENT ON TABLE diesel_tanks IS 'Diesel fuel storage tanks with level monitoring and consumption tracking';
COMMENT ON TABLE generator_groups IS 'Generator groups for N+1 redundancy and load sharing';
COMMENT ON TABLE generators IS 'Individual diesel generators with DSE controller integration';
COMMENT ON TABLE generator_run_history IS 'Time-series generator run data (consider TimescaleDB in production)';
COMMENT ON COLUMN generators.priority IS 'Startup priority within group (1 = first to start)';
COMMENT ON COLUMN generators.controller_model IS 'DSE controller model (DSE8610, DSE7320, etc.)';
COMMENT ON COLUMN generator_groups.transfer_mode IS 'closed = dead transition (no simultaneous mains+gen)';

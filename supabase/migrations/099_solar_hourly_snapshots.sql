-- Solar Hourly Snapshots Table
-- Stores all 8,760 hourly data points from annual simulation
-- Allows real-time dashboard display of current hour's simulation data

CREATE TABLE IF NOT EXISTS solar_hourly_snapshots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Reference to simulation
  site_id TEXT NOT NULL,
  scenario TEXT NOT NULL,
  year INTEGER NOT NULL,
  simulation_id UUID REFERENCES solar_annual_simulations(id) ON DELETE CASCADE,

  -- Time information
  hour INTEGER NOT NULL,  -- 0-8759 (365 days × 24 hours)
  date DATE NOT NULL,
  month INTEGER NOT NULL,
  day_of_year INTEGER NOT NULL,
  hour_of_day INTEGER NOT NULL,

  -- Energy flows (kW)
  solar_gen_kw FLOAT NOT NULL DEFAULT 0,
  building_load_kw FLOAT NOT NULL DEFAULT 0,
  bess_soc_pct FLOAT NOT NULL DEFAULT 50,
  bess_charge_kw FLOAT NOT NULL DEFAULT 0,
  bess_discharge_kw FLOAT NOT NULL DEFAULT 0,
  grid_import_kw FLOAT NOT NULL DEFAULT 0,
  grid_export_kw FLOAT NOT NULL DEFAULT 0,

  -- Tariff information
  tariff_band TEXT NOT NULL DEFAULT 'standard',  -- peak|standard|off_peak
  tariff_rate_c_kwh FLOAT NOT NULL DEFAULT 0,

  -- Metadata
  created_at TIMESTAMPTZ DEFAULT NOW(),

  -- Constraints
  CONSTRAINT valid_hour CHECK (hour >= 0 AND hour < 8760),
  CONSTRAINT valid_month CHECK (month >= 1 AND month <= 12),
  CONSTRAINT valid_day CHECK (day_of_year >= 1 AND day_of_year <= 365),
  CONSTRAINT valid_hour_of_day CHECK (hour_of_day >= 0 AND hour_of_day <= 23),
  CONSTRAINT non_negative_energy CHECK (
    solar_gen_kw >= 0 AND building_load_kw >= 0 AND
    grid_import_kw >= 0 AND grid_export_kw >= 0
  )
);

-- Index for efficient queries by site/scenario/date
CREATE INDEX idx_solar_hourly_site_scenario ON solar_hourly_snapshots(site_id, scenario, year);
CREATE INDEX idx_solar_hourly_date ON solar_hourly_snapshots(date);
CREATE INDEX idx_solar_hourly_hour ON solar_hourly_snapshots(hour);
CREATE INDEX idx_solar_hourly_created ON solar_hourly_snapshots(created_at DESC);

-- Composite index for real-time dashboard queries
CREATE INDEX idx_solar_hourly_current ON solar_hourly_snapshots(site_id, scenario, date, hour_of_day);

COMMENT ON TABLE solar_hourly_snapshots IS 'All 8,760 hourly data points from 365-day solar simulation. Used for real-time dashboard display of current hour''s generation, load, and BESS status.';
COMMENT ON COLUMN solar_hourly_snapshots.solar_gen_kw IS 'Solar generation in kW for this hour';
COMMENT ON COLUMN solar_hourly_snapshots.bess_soc_pct IS 'Battery state of charge (0-100%) at end of hour';
COMMENT ON COLUMN solar_hourly_snapshots.tariff_band IS 'Current tariff period: peak (07:00-09:00, 18:00-19:00), standard (rest), or off_peak (21:00-06:00)';

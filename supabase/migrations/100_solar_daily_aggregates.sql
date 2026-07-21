-- Solar Daily Aggregates Table
-- Stores aggregated daily data from 365-day simulations
-- Simpler than hourly (365 rows instead of 8760)

CREATE TABLE IF NOT EXISTS solar_daily_aggregates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Reference to simulation
  site_id TEXT NOT NULL,
  scenario TEXT NOT NULL,
  year INTEGER NOT NULL,

  -- Date information
  date DATE NOT NULL,
  month INTEGER NOT NULL,
  day_of_year INTEGER NOT NULL,

  -- Daily energy totals (kWh)
  solar_gen_kwh FLOAT NOT NULL DEFAULT 0,
  building_load_kwh FLOAT NOT NULL DEFAULT 0,
  bess_charge_kwh FLOAT NOT NULL DEFAULT 0,
  bess_discharge_kwh FLOAT NOT NULL DEFAULT 0,
  grid_import_kwh FLOAT NOT NULL DEFAULT 0,
  grid_export_kwh FLOAT NOT NULL DEFAULT 0,

  -- Daily peaks & averages
  peak_generation_kw FLOAT NOT NULL DEFAULT 0,
  avg_bess_soc_pct FLOAT NOT NULL DEFAULT 50,

  -- Metadata
  created_at TIMESTAMPTZ DEFAULT NOW(),

  -- Constraints
  CONSTRAINT valid_month CHECK (month >= 1 AND month <= 12),
  CONSTRAINT valid_day CHECK (day_of_year >= 1 AND day_of_year <= 365),
  CONSTRAINT non_negative_energy CHECK (
    solar_gen_kwh >= 0 AND building_load_kwh >= 0 AND
    grid_import_kwh >= 0 AND grid_export_kwh >= 0
  )
);

-- Index for efficient queries by site/scenario/date
CREATE INDEX idx_solar_daily_site_scenario ON solar_daily_aggregates(site_id, scenario, year);
CREATE INDEX idx_solar_daily_date ON solar_daily_aggregates(date);
CREATE INDEX idx_solar_daily_month ON solar_daily_aggregates(month);
CREATE INDEX idx_solar_daily_created ON solar_daily_aggregates(created_at DESC);

-- Composite index for dashboard queries (day view)
CREATE INDEX idx_solar_daily_current ON solar_daily_aggregates(site_id, scenario, date);

COMMENT ON TABLE solar_daily_aggregates IS 'Daily aggregated data from 365-day solar simulation. Stores 365 records per simulation (vs 8760 hourly), more efficient for dashboard display and historical analysis.';
COMMENT ON COLUMN solar_daily_aggregates.solar_gen_kwh IS 'Total solar generation for the day (kWh)';
COMMENT ON COLUMN solar_daily_aggregates.peak_generation_kw IS 'Peak generation during the day (kW)';
COMMENT ON COLUMN solar_daily_aggregates.avg_bess_soc_pct IS 'Average battery state of charge (0-100%) for the day';

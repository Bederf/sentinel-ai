-- Phase A: Validation Pipeline Tables
-- A.3: Power meter validation results
-- A.4: Cost reconciliation records

-- Power meter validation: stores hourly/daily comparison of simulated vs real meter readings
CREATE TABLE IF NOT EXISTS power_meter_validations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id TEXT NOT NULL,
    meter_id TEXT NOT NULL,
    validation_date DATE NOT NULL,
    hour INTEGER,
    reading_kwh NUMERIC(10, 2),
    baseline_mean NUMERIC(10, 2),
    baseline_stdev NUMERIC(10, 2),
    variance_pct NUMERIC(6, 2),
    validation_status TEXT NOT NULL DEFAULT 'normal',
    severity TEXT NOT NULL DEFAULT 'normal',
    cop_current NUMERIC(4, 2),
    cop_design NUMERIC(4, 2) DEFAULT 3.5,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(site_id, meter_id, validation_date, hour)
);

CREATE INDEX IF NOT EXISTS idx_pmv_site_date ON power_meter_validations(site_id, validation_date);

-- Cost validation: stores monthly comparison of simulated vs real invoice costs
CREATE TABLE IF NOT EXISTS cost_validations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id TEXT NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    real_cost_r NUMERIC(12, 2),
    simulated_cost_r NUMERIC(12, 2),
    variance_pct NUMERIC(6, 2),
    validation_status TEXT NOT NULL DEFAULT 'normal',
    recommendation TEXT,
    confidence NUMERIC(4, 2),
    tariff_adjustment_factor NUMERIC(6, 4) DEFAULT 1.0,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(site_id, period_start, period_end)
);

CREATE INDEX IF NOT EXISTS idx_cv_site_period ON cost_validations(site_id, period_start);

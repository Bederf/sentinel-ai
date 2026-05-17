-- Migration: Create utility_tariffs table for electricity and water tariffs
-- This table stores municipal tariff schedules with automatic location-based lookup

CREATE TABLE IF NOT EXISTS utility_tariffs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id TEXT NOT NULL REFERENCES sites(code) ON DELETE CASCADE,
    utility_type TEXT NOT NULL CHECK (utility_type IN ('electricity', 'water', 'sewerage')),
    provider TEXT NOT NULL, -- e.g., 'Eskom', 'City Power', 'Rand Water', 'Johannesburg Water'
    municipality TEXT NOT NULL, -- e.g., 'Johannesburg', 'Tshwane', 'Ekurhuleni'
    region TEXT, -- e.g., 'Johannesburg CBD', 'Sandton'

    -- Tariff metadata
    tariff_name TEXT NOT NULL, -- e.g., 'LPU-TOU', 'Business TOU', 'Domestic'
    tariff_code TEXT, -- e.g., 'CP-LPU-TOU-2025'
    effective_date DATE NOT NULL,
    expiry_date DATE,

    -- Tariff structure (JSON for flexibility)
    tariff_structure JSONB NOT NULL DEFAULT '{}',
    -- Example electricity structure:
    -- {
    --   "tou_bands": [
    --     {"name": "peak", "hours": [7,8,17,18,19,20], "rate": 4.52, "unit": "ZAR/kWh"},
    --     {"name": "standard", "hours": [6,9,10,11,12,13,14,15,16,21,22], "rate": 2.28, "unit": "ZAR/kWh"},
    --     {"name": "off_peak", "hours": [0,1,2,3,4,5,23], "rate": 0.63, "unit": "ZAR/kWh"}
    --   ],
    --   "demand_charge_per_kva": 180.50,
    --   "fixed_monthly_charge": 1200.00,
    --   "network_charge_per_kwh": 0.45
    -- }
    -- Example water structure:
    -- {
    --   "tiered_rates": [
    --     {"tier": 1, "threshold_liters": 100000, "rate_r_per_kiloliter": 7.95},
    --     {"tier": 2, "threshold_liters": 500000, "rate_r_per_kiloliter": 12.50},
    --     {"tier": 3, "threshold_liters": null, "rate_r_per_kiloliter": 18.95}
    --   ],
    --   "sewerage_rate_r_per_kiloliter": 4.45,
    --   "fixed_monthly_charge": 250.00
    -- }

    -- Source tracking
    source_url TEXT, -- URL where tariff was fetched from
    source_type TEXT CHECK (source_type IN ('api', 'scrape', 'manual', 'pdf')),
    last_fetched_at TIMESTAMPTZ DEFAULT NOW(),
    fetch_status TEXT DEFAULT 'active' CHECK (fetch_status IN ('active', 'expired', 'error', 'manual')),
    fetch_error TEXT, -- Last error message if fetch failed

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT unique_tariff UNIQUE (site_id, utility_type, provider, tariff_name, effective_date)
);

-- Indexes for efficient lookups
CREATE INDEX idx_utility_tariffs_site_type ON utility_tariffs(site_id, utility_type);
CREATE INDEX idx_utility_tariffs_municipality ON utility_tariffs(municipality, utility_type);
CREATE INDEX idx_utility_tariffs_effective ON utility_tariffs(effective_date, expiry_date);
CREATE INDEX idx_utility_tariffs_provider ON utility_tariffs(provider, utility_type);
CREATE INDEX idx_utility_tariffs_fetch_status ON utility_tariffs(fetch_status) WHERE fetch_status != 'expired';

-- Trigger to update updated_at
CREATE OR REPLACE FUNCTION update_utility_tariffs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_utility_tariffs_updated_at ON utility_tariffs;
CREATE TRIGGER trigger_utility_tariffs_updated_at
    BEFORE UPDATE ON utility_tariffs
    FOR EACH ROW
    EXECUTE FUNCTION update_utility_tariffs_updated_at();

-- Comments
COMMENT ON TABLE utility_tariffs IS 'Stores electricity and water tariffs for each site with automatic monthly polling';
COMMENT ON COLUMN utility_tariffs.tariff_structure IS 'JSON containing rate structure - TOU bands for electricity, tiered rates for water';
COMMENT ON COLUMN utility_tariffs.source_url IS 'External URL where tariff data was obtained (e.g., Rand Water, Eskom, City Power)';

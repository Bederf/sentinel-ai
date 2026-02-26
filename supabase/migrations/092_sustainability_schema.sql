-- =====================================================
-- Migration 092: Sustainability & ESG Data Schema
-- Tracks carbon emissions (Scope 1/2/3), ESG metrics, and Green Star/LEED progress
-- =====================================================

-- Emission factors reference table (South Africa + IPCC standards)
-- Used by CarbonCalculator to convert consumption to CO2e
CREATE TABLE IF NOT EXISTS emission_factors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_type TEXT NOT NULL CHECK (
        source_type IN (
            'generator_diesel',
            'generator_lpg',
            'grid_electricity',
            'water_supply',
            'waste_landfill',
            'refrigerant_leak',
            'employee_commute',
            'business_travel'
        )
    ),
    unit TEXT NOT NULL,
    factor_value NUMERIC NOT NULL,
    scope INTEGER NOT NULL CHECK (scope IN (1, 2, 3)),
    region TEXT DEFAULT 'south_africa',
    reference_source TEXT,
    notes TEXT,
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_type, unit, region)
);

-- Monthly emissions data by source
-- Raw data from building energy systems (generators, grid, water meters, waste logs)
CREATE TABLE IF NOT EXISTS emissions_sources (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL CHECK (
        source_type IN (
            'generator_diesel',
            'generator_lpg',
            'grid_electricity',
            'water_supply',
            'waste_landfill',
            'refrigerant_leak',
            'employee_commute',
            'business_travel'
        )
    ),
    measurement_date DATE NOT NULL,
    monthly_value NUMERIC NOT NULL,
    unit TEXT NOT NULL,
    scope INTEGER NOT NULL CHECK (scope IN (1, 2, 3)),
    co2_factor NUMERIC,
    co2e_kg NUMERIC GENERATED ALWAYS AS (monthly_value * COALESCE(co2_factor, 0)) STORED,
    data_quality TEXT DEFAULT 'measured' CHECK (data_quality IN ('measured', 'estimated', 'historical_average')),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_emissions_sources_building_date
    ON emissions_sources (building_id, measurement_date DESC);
CREATE INDEX IF NOT EXISTS idx_emissions_sources_source_type
    ON emissions_sources (source_type);
CREATE INDEX IF NOT EXISTS idx_emissions_sources_scope
    ON emissions_sources (scope);

-- Annual emissions baseline per building
-- Aggregated from monthly emissions_sources data
-- Used for year-over-year benchmarking and Green Star/LEED tracking
CREATE TABLE IF NOT EXISTS emissions_baseline (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
    baseline_year INTEGER NOT NULL,
    scope1_kg_co2e NUMERIC NOT NULL DEFAULT 0,
    scope2_kg_co2e NUMERIC NOT NULL DEFAULT 0,
    scope3_kg_co2e NUMERIC NOT NULL DEFAULT 0,
    total_kg_co2e NUMERIC GENERATED ALWAYS AS (
        scope1_kg_co2e + scope2_kg_co2e + scope3_kg_co2e
    ) STORED,
    floor_area_m2 NUMERIC,
    intensity_kg_per_m2 NUMERIC GENERATED ALWAYS AS (
        CASE
            WHEN floor_area_m2 > 0 THEN (scope1_kg_co2e + scope2_kg_co2e + scope3_kg_co2e) / floor_area_m2
            ELSE NULL
        END
    ) STORED,
    reduction_target_pct NUMERIC,
    reduction_achieved_pct NUMERIC,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (building_id, baseline_year)
);

CREATE INDEX IF NOT EXISTS idx_emissions_baseline_building_year
    ON emissions_baseline (building_id, baseline_year DESC);

-- ESG metrics dashboard data
-- Calculated monthly from emissions_sources and building performance data
CREATE TABLE IF NOT EXISTS esg_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
    metric_month DATE NOT NULL,
    carbon_intensity_kg_per_m2 NUMERIC,
    carbon_intensity_score NUMERIC CHECK (carbon_intensity_score >= 0 AND carbon_intensity_score <= 100),
    energy_efficiency_score NUMERIC CHECK (energy_efficiency_score >= 0 AND energy_efficiency_score <= 100),
    waste_diversion_rate NUMERIC CHECK (waste_diversion_rate >= 0 AND waste_diversion_rate <= 100),
    waste_diversion_score NUMERIC CHECK (waste_diversion_score >= 0 AND waste_diversion_score <= 100),
    water_intensity_l_per_m2_day NUMERIC,
    water_efficiency_score NUMERIC CHECK (water_efficiency_score >= 0 AND water_efficiency_score <= 100),
    renewable_energy_pct NUMERIC CHECK (renewable_energy_pct >= 0 AND renewable_energy_pct <= 100),
    overall_esg_score NUMERIC GENERATED ALWAYS AS (
        ROUND((
            COALESCE(carbon_intensity_score, 50) * 0.40 +
            COALESCE(energy_efficiency_score, 50) * 0.30 +
            COALESCE(waste_diversion_score, 50) * 0.20 +
            COALESCE(water_efficiency_score, 50) * 0.10
        )::NUMERIC, 1)
    ) STORED,
    data_source TEXT DEFAULT 'calculated',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (building_id, metric_month)
);

CREATE INDEX IF NOT EXISTS idx_esg_metrics_building_month
    ON esg_metrics (building_id, metric_month DESC);

-- Green Star / LEED certification progress tracking
CREATE TABLE IF NOT EXISTS certification_progress (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
    cert_type TEXT NOT NULL CHECK (cert_type IN ('green_star', 'leed', 'carbon_trust', 'energystar')),
    rating_version TEXT,
    current_score NUMERIC DEFAULT 0,
    target_score NUMERIC,
    pct_progress NUMERIC GENERATED ALWAYS AS (
        CASE
            WHEN target_score > 0 THEN ROUND((current_score / target_score * 100)::NUMERIC, 1)
            ELSE 0
        END
    ) STORED,
    categories JSONB DEFAULT '[]'::JSONB,
    status TEXT DEFAULT 'in_progress' CHECK (status IN ('in_progress', 'submitted', 'certified', 'expired', 'discontinued')),
    submission_date DATE,
    certification_date DATE,
    renewal_date DATE,
    certifier_name TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (building_id, cert_type)
);

CREATE INDEX IF NOT EXISTS idx_certification_progress_building
    ON certification_progress (building_id);
CREATE INDEX IF NOT EXISTS idx_certification_progress_cert_type
    ON certification_progress (cert_type);

-- Carbon offset projects (tree planting, renewable energy credits, etc.)
CREATE TABLE IF NOT EXISTS carbon_offset_projects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
    project_name TEXT NOT NULL,
    project_type TEXT NOT NULL CHECK (
        project_type IN (
            'tree_planting',
            'renewable_energy_credits',
            'landfill_gas',
            'methane_capture',
            'energy_efficiency_retrofit',
            'carbon_sequestration',
            'other'
        )
    ),
    co2e_offset_kg NUMERIC NOT NULL,
    co2e_offset_tonnes NUMERIC GENERATED ALWAYS AS (co2e_offset_kg / 1000) STORED,
    certification TEXT,
    cost_usd NUMERIC,
    start_date DATE NOT NULL,
    end_date DATE,
    status TEXT DEFAULT 'active' CHECK (status IN ('planned', 'active', 'completed', 'retired')),
    verification_url TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_carbon_offset_building_date
    ON carbon_offset_projects (building_id, start_date DESC);
CREATE INDEX IF NOT EXISTS idx_carbon_offset_status
    ON carbon_offset_projects (status);

-- =====================================================
-- Insert default emission factors for South Africa
-- Reference: Eskom NRS 097-2-1, IPCC AR5, EPA GHG Inventory
-- =====================================================

INSERT INTO emission_factors (
    source_type,
    unit,
    factor_value,
    scope,
    region,
    reference_source,
    notes
) VALUES
-- Scope 1: Direct emissions
('generator_diesel', 'kg', 2.68, 1, 'south_africa', 'EPA GHG Inventory', 'Diesel combustion for backup power'),
('generator_lpg', 'kg', 1.63, 1, 'south_africa', 'EPA GHG Inventory', 'LPG combustion for backup power'),
('refrigerant_leak', 'kg', 1.0, 1, 'south_africa', 'IPCC AR5', 'Refrigerant with unit GWP already applied'),
('employee_commute', 'km', 0.21, 1, 'south_africa', 'EPA Mobile6.2', 'Average passenger car emissions'),

-- Scope 2: Purchased electricity (Eskom grid South Africa)
('grid_electricity', 'kWh', 0.95, 2, 'south_africa', 'Eskom National Grid Factor', 'South African grid average'),

-- Scope 3: Indirect/value chain
('water_supply', 'm3', 0.45, 3, 'south_africa', 'IPCC AR5 + local treatment', 'Water supply + distribution + treatment'),
('waste_landfill', 'kg', 0.5, 3, 'south_africa', 'EPA Waste Model', 'Organic waste to landfill with methane'),
('business_travel', 'km', 0.12, 3, 'south_africa', 'DEFRA Guidelines', 'Average flight + rail emissions')
ON CONFLICT (source_type, unit, region) DO NOTHING;

-- =====================================================
-- Seed test data for Sandton City (site-002)
-- Assume: 2000 m² GLA, 100 occupants, operational 12 months
-- =====================================================

-- Get Sandton building ID (site-002)
DO $$
DECLARE
    sandton_id UUID;
    i INT;
    base_diesel_l NUMERIC := 500;
    base_grid_kwh NUMERIC := 25000;
    base_water_m3 NUMERIC := 50;
    base_waste_kg NUMERIC := 200;
BEGIN
    SELECT id INTO sandton_id FROM buildings WHERE code = 'site-002' LIMIT 1;

    IF sandton_id IS NOT NULL THEN
        -- Insert 12 months of emissions data (2025)
        FOR i IN 0..11 LOOP
            -- Generators (Scope 1): Higher in winter, lower in summer
            INSERT INTO emissions_sources (
                building_id, source_type, measurement_date, monthly_value, unit,
                scope, co2_factor, data_quality
            ) VALUES (
                sandton_id,
                'generator_diesel',
                DATE '2025-01-01' + (i || ' months')::INTERVAL,
                base_diesel_l * (1.0 + (CASE WHEN i IN (5,6,7) THEN -0.3 ELSE 0.2 END)),
                'L',
                1,
                2.68,
                'estimated'
            );

            -- Grid electricity (Scope 2): Seasonal with summer peak
            INSERT INTO emissions_sources (
                building_id, source_type, measurement_date, monthly_value, unit,
                scope, co2_factor, data_quality
            ) VALUES (
                sandton_id,
                'grid_electricity',
                DATE '2025-01-01' + (i || ' months')::INTERVAL,
                base_grid_kwh * (1.0 + (CASE WHEN i IN (0,11) THEN 0.4 WHEN i IN (5,6,7) THEN -0.2 ELSE 0.1 END)),
                'kWh',
                2,
                0.95,
                'measured'
            );

            -- Water (Scope 3)
            INSERT INTO emissions_sources (
                building_id, source_type, measurement_date, monthly_value, unit,
                scope, co2_factor, data_quality
            ) VALUES (
                sandton_id,
                'water_supply',
                DATE '2025-01-01' + (i || ' months')::INTERVAL,
                base_water_m3 * (1.0 + RANDOM() * 0.3),
                'm3',
                3,
                0.45,
                'measured'
            );

            -- Waste (Scope 3)
            INSERT INTO emissions_sources (
                building_id, source_type, measurement_date, monthly_value, unit,
                scope, co2_factor, data_quality
            ) VALUES (
                sandton_id,
                'waste_landfill',
                DATE '2025-01-01' + (i || ' months')::INTERVAL,
                base_waste_kg * (1.0 + RANDOM() * 0.2),
                'kg',
                3,
                0.5,
                'estimated'
            );

            -- Employee commute (Scope 3): 100 occupants × 25 km avg commute
            INSERT INTO emissions_sources (
                building_id, source_type, measurement_date, monthly_value, unit,
                scope, co2_factor, data_quality
            ) VALUES (
                sandton_id,
                'employee_commute',
                DATE '2025-01-01' + (i || ' months')::INTERVAL,
                100 * 25 * 20,
                'km',
                3,
                0.21,
                'estimated'
            );
        END LOOP;

        -- Insert annual baseline for 2025
        INSERT INTO emissions_baseline (
            building_id, baseline_year, floor_area_m2, reduction_target_pct
        ) VALUES (
            sandton_id, 2025, 2000.0, 10.0
        );

        -- Insert Green Star SA tracking
        INSERT INTO certification_progress (
            building_id, cert_type, rating_version, current_score, target_score,
            status, categories
        ) VALUES (
            sandton_id,
            'green_star',
            '5.1',
            25,
            100,
            'in_progress',
            '[
                {"category": "Energy", "max_points": 30, "achieved_points": 12},
                {"category": "Water", "max_points": 25, "achieved_points": 8},
                {"category": "Materials", "max_points": 20, "achieved_points": 5},
                {"category": "Waste", "max_points": 15, "achieved_points": 0},
                {"category": "Indoor Environment", "max_points": 10, "achieved_points": 0}
            ]'::JSONB
        );
    END IF;
END $$;

-- =====================================================
-- Utility functions for sustainability calculations
-- =====================================================

-- Calculate total emissions for a building and period
CREATE OR REPLACE FUNCTION calculate_period_emissions(
    p_building_id UUID,
    p_start_date DATE,
    p_end_date DATE,
    p_scope INT DEFAULT NULL
)
RETURNS TABLE (
    scope INT,
    total_kg_co2e NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        es.scope,
        SUM(es.co2e_kg)::NUMERIC as total_kg_co2e
    FROM emissions_sources es
    WHERE es.building_id = p_building_id
        AND es.measurement_date >= p_start_date
        AND es.measurement_date <= p_end_date
        AND (p_scope IS NULL OR es.scope = p_scope)
    GROUP BY es.scope
    ORDER BY es.scope;
END;
$$ LANGUAGE plpgsql;

-- Calculate carbon intensity for a building
CREATE OR REPLACE FUNCTION calculate_carbon_intensity(
    p_building_id UUID,
    p_month DATE
)
RETURNS NUMERIC AS $$
DECLARE
    v_total_emissions NUMERIC;
    v_floor_area NUMERIC;
    v_intensity NUMERIC;
BEGIN
    SELECT SUM(co2e_kg) INTO v_total_emissions
    FROM emissions_sources
    WHERE building_id = p_building_id
        AND DATE_TRUNC('month', measurement_date) = DATE_TRUNC('month', p_month);

    SELECT floor_area_m2 INTO v_floor_area
    FROM emissions_baseline
    WHERE building_id = p_building_id
        AND baseline_year = EXTRACT(YEAR FROM p_month)
    LIMIT 1;

    IF v_floor_area IS NULL OR v_floor_area = 0 THEN
        RETURN NULL;
    END IF;

    v_intensity := ROUND((v_total_emissions / v_floor_area / 30)::NUMERIC, 3);
    RETURN v_intensity;
END;
$$ LANGUAGE plpgsql;

-- Update updated_at trigger for sustainability tables
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updated_at
CREATE TRIGGER trigger_emission_factors_updated_at
    BEFORE UPDATE ON emission_factors
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trigger_emissions_sources_updated_at
    BEFORE UPDATE ON emissions_sources
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trigger_emissions_baseline_updated_at
    BEFORE UPDATE ON emissions_baseline
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trigger_esg_metrics_updated_at
    BEFORE UPDATE ON esg_metrics
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trigger_certification_progress_updated_at
    BEFORE UPDATE ON certification_progress
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trigger_carbon_offset_projects_updated_at
    BEFORE UPDATE ON carbon_offset_projects
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Local schema compatibility for active backend queries.
-- The current app uses equipment codes (for example S002-AHU-001) as
-- equipment_id in baseline health paths, so these tables intentionally keep
-- equipment_id as text instead of a UUID foreign key.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS equipment_baselines (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    equipment_id TEXT NOT NULL,
    baseline_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    captured_by TEXT NOT NULL,
    baseline_type TEXT NOT NULL DEFAULT 'initial',
    status TEXT NOT NULL DEFAULT 'active',
    baseline_values JSONB NOT NULL DEFAULT '{}',
    measurement_conditions JSONB DEFAULT '{}',
    source_type TEXT NOT NULL DEFAULT 'manual',
    notes TEXT,
    attachment_urls TEXT[] DEFAULT ARRAY[]::TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_equipment_baselines_equipment_status
    ON equipment_baselines(equipment_id, status, baseline_date DESC);
CREATE INDEX IF NOT EXISTS idx_equipment_baselines_values
    ON equipment_baselines USING GIN (baseline_values);

CREATE TABLE IF NOT EXISTS equipment_elements (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    equipment_id TEXT NOT NULL,
    element_id TEXT NOT NULL,
    element_type TEXT NOT NULL,
    element_name TEXT,
    manufacturer TEXT,
    model TEXT,
    serial_number TEXT,
    installation_date TEXT,
    expected_life_days INTEGER,
    criticality TEXT NOT NULL DEFAULT 'medium',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(equipment_id, element_id)
);

CREATE INDEX IF NOT EXISTS idx_equipment_elements_equipment_id
    ON equipment_elements(equipment_id);

CREATE TABLE IF NOT EXISTS element_baselines (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    element_id UUID NOT NULL REFERENCES equipment_elements(id) ON DELETE CASCADE,
    baseline_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    captured_by TEXT NOT NULL,
    baseline_type TEXT NOT NULL DEFAULT 'initial',
    status TEXT NOT NULL DEFAULT 'active',
    baseline_values JSONB NOT NULL DEFAULT '{}',
    measurement_type TEXT NOT NULL,
    measurement_conditions JSONB DEFAULT '{}',
    source_type TEXT NOT NULL DEFAULT 'mobile_sensor',
    notes TEXT,
    attachment_urls TEXT[] DEFAULT ARRAY[]::TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_element_baselines_element_status
    ON element_baselines(element_id, status, baseline_date DESC);
CREATE INDEX IF NOT EXISTS idx_element_baselines_values
    ON element_baselines USING GIN (baseline_values);

CREATE TABLE IF NOT EXISTS baseline_comparisons (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    comparison_type TEXT NOT NULL,
    baseline_id TEXT NOT NULL,
    equipment_id TEXT NOT NULL,
    element_id TEXT,
    comparison_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    comparison_results JSONB NOT NULL DEFAULT '{}',
    overall_status TEXT NOT NULL DEFAULT 'normal',
    max_deviation_percent DOUBLE PRECISION NOT NULL DEFAULT 0,
    deviation_percent DOUBLE PRECISION,
    data_source TEXT NOT NULL DEFAULT 'unknown',
    comparison_notes TEXT,
    alert_generated BOOLEAN NOT NULL DEFAULT FALSE,
    alert_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_baseline_comparisons_equipment
    ON baseline_comparisons(equipment_id, comparison_date DESC);
CREATE INDEX IF NOT EXISTS idx_baseline_comparisons_status
    ON baseline_comparisons(overall_status, comparison_date DESC);
CREATE INDEX IF NOT EXISTS idx_baseline_comparisons_results
    ON baseline_comparisons USING GIN (comparison_results);

CREATE TABLE IF NOT EXISTS inspection_measurements (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    result_id UUID NOT NULL REFERENCES inspection_results(id),
    task_id UUID NOT NULL REFERENCES inspection_tasks(id),
    equipment_id UUID NOT NULL REFERENCES equipment(id),
    measurement_type TEXT NOT NULL,
    measurement_point TEXT NOT NULL,
    measured_value DECIMAL(15,4) NOT NULL,
    unit TEXT NOT NULL,
    measurement_date TIMESTAMPTZ NOT NULL,
    measured_by TEXT NOT NULL,
    baseline_value DECIMAL(15,4),
    baseline_deviation_percent DECIMAL(10,2),
    deviation_status TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_measurements_equipment
    ON inspection_measurements(equipment_id, measurement_date DESC);
CREATE INDEX IF NOT EXISTS idx_measurements_type
    ON inspection_measurements(measurement_type, measurement_date DESC);
CREATE INDEX IF NOT EXISTS idx_measurements_deviation
    ON inspection_measurements(deviation_status)
    WHERE deviation_status IN ('warning', 'critical');

CREATE OR REPLACE VIEW sustainability_metrics AS
SELECT
    id,
    site_id,
    date,
    COALESCE(grid_kwh, 0) + COALESCE(solar_generation_kwh, 0) AS total_kwh,
    NULL::NUMERIC AS outdoor_temp_c,
    '[]'::JSONB AS zone_deviations,
    created_at
FROM daily_sustainability_metrics;

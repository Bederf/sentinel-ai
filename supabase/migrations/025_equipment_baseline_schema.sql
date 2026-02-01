-- Migration: Equipment Baseline Assessment Schema
-- Description: Store baseline readings per equipment and element for asset management
-- Phase: 44 - Asset Baseline Assessment

-- ============================================================================
-- Table: equipment_baselines
-- Stores baseline readings captured for each equipment instance
-- ============================================================================
CREATE TABLE IF NOT EXISTS equipment_baselines (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    equipment_id TEXT NOT NULL REFERENCES equipment(equipment_id),
    baseline_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    captured_by TEXT NOT NULL, -- Engineer name or 'automated'
    baseline_type TEXT NOT NULL DEFAULT 'initial', -- initial, periodic, post_repair
    status TEXT NOT NULL DEFAULT 'active', -- active, archived, superseded

    -- Baseline values stored as JSONB for flexibility
    -- Example: {"chw_supply_temp": 7.2, "chw_return_temp": 12.5, "motor_current": 145}
    baseline_values JSONB NOT NULL DEFAULT '{}',

    -- Measurement conditions for context
    measurement_conditions JSONB DEFAULT '{}', -- ambient_temp, load_percent, etc.

    -- Source of baseline (manual entry, BMS sensor average, etc.)
    source_type TEXT NOT NULL DEFAULT 'manual', -- manual, bms_average, mobile_sensor

    -- Engineer notes about baseline capture
    notes TEXT,

    -- Related documentation
    attachment_urls TEXT[], -- URLs to photos, readings, lab results

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for equipment baseline queries
CREATE INDEX IF NOT EXISTS idx_equipment_baselines_equipment_id ON equipment_baselines(equipment_id);
CREATE INDEX IF NOT EXISTS idx_equipment_baselines_equipment_active ON equipment_baselines(equipment_id, status) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_equipment_baselines_date ON equipment_baselines(baseline_date DESC);
CREATE INDEX IF NOT EXISTS idx_equipment_baselines_type ON equipment_baselines(baseline_type);

-- Enable GIN index for JSONB queries on baseline_values
CREATE INDEX IF NOT EXISTS idx_equipment_baselines_values ON equipment_baselines USING GIN (baseline_values);

-- ============================================================================
-- Table: equipment_elements
-- Defines individual elements/components within equipment that have baselines
-- Example: Bearing #1, Filter Set A, Compressor Stage 1
-- ============================================================================
CREATE TABLE IF NOT EXISTS equipment_elements (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    equipment_id TEXT NOT NULL REFERENCES equipment(equipment_id),
    element_id TEXT NOT NULL, -- Unique within equipment (e.g., 'bearing_1', 'filter_A')

    element_type TEXT NOT NULL, -- bearing, filter, coil, compressor_stage, etc.
    element_name TEXT NOT NULL, -- Human-readable name

    -- Element-specific metadata
    manufacturer TEXT,
    model TEXT,
    serial_number TEXT,
    installation_date DATE,
    expected_life_days INTEGER, -- Expected lifespan for RUL calculation

    -- Criticality for maintenance prioritization
    criticality TEXT NOT NULL DEFAULT 'medium', -- low, medium, high, critical

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(equipment_id, element_id)
);

-- Indexes for element queries
CREATE INDEX IF NOT EXISTS idx_equipment_elements_equipment_id ON equipment_elements(equipment_id);
CREATE INDEX IF NOT EXISTS idx_equipment_elements_type ON equipment_elements(element_type);
CREATE INDEX IF NOT EXISTS idx_equipment_elements_criticality ON equipment_elements(criticality);

-- ============================================================================
-- Table: element_baselines
-- Stores baseline readings for individual elements (bearings, filters, etc.)
-- ============================================================================
CREATE TABLE IF NOT EXISTS element_baselines (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    element_id UUID NOT NULL REFERENCES equipment_elements(id) ON DELETE CASCADE,
    baseline_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    captured_by TEXT NOT NULL,
    baseline_type TEXT NOT NULL DEFAULT 'initial',
    status TEXT NOT NULL DEFAULT 'active',

    -- Element-specific baseline values
    -- Example for bearing: {"vibration_rms": 1.2, "temperature": 45.2, "frequency_1x": 50}
    baseline_values JSONB NOT NULL DEFAULT '{}',

    -- Measurement type and context
    measurement_type TEXT NOT NULL, -- vibration, temperature, visual_inspection
    measurement_conditions JSONB DEFAULT '{}',

    source_type TEXT NOT NULL DEFAULT 'mobile_sensor',
    notes TEXT,
    attachment_urls TEXT[],

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for element baseline queries
CREATE INDEX IF NOT EXISTS idx_element_baselines_element_id ON element_baselines(element_id);
CREATE INDEX IF NOT EXISTS idx_element_baselines_element_active ON element_baselines(element_id, status) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_element_baselines_date ON element_baselines(baseline_date DESC);
CREATE INDEX IF NOT EXISTS idx_element_baselines_measurement_type ON element_baselines(measurement_type);

-- GIN index for JSONB queries
CREATE INDEX IF NOT EXISTS idx_element_baselines_values ON element_baselines USING GIN (baseline_values);

-- ============================================================================
-- Table: baseline_comparisons
-- Stores automated comparison results between current readings and baselines
-- ============================================================================
CREATE TABLE IF NOT EXISTS baseline_comparisons (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- What we're comparing (equipment or element)
    comparison_type TEXT NOT NULL, -- equipment_baseline or element_baseline
    baseline_id UUID, -- References either equipment_baselines or element_baselines

    equipment_id TEXT REFERENCES equipment(equipment_id),
    element_id UUID REFERENCES equipment_elements(id),

    -- When the comparison was made
    comparison_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Comparison results
    -- Example: {"chw_supply_temp": {"baseline": 7.2, "current": 8.5, "deviation": 18.1, "status": "warning"}}
    comparison_results JSONB NOT NULL,

    -- Overall assessment
    overall_status TEXT NOT NULL, -- normal, warning, critical
    max_deviation_percent FLOAT NOT NULL, -- Maximum deviation found

    -- Context about the comparison
    data_source TEXT NOT NULL, -- bms_sensor, mobile_sensor, manual_entry
    comparison_notes TEXT,

    -- Alert generation flag
    alert_generated BOOLEAN NOT NULL DEFAULT FALSE,
    alert_id UUID REFERENCES alerts(id),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for comparison queries
CREATE INDEX IF NOT EXISTS idx_baseline_comparisons_equipment ON baseline_comparisons(equipment_id, comparison_date DESC);
CREATE INDEX IF NOT EXISTS idx_baseline_comparisons_element ON baseline_comparisons(element_id, comparison_date DESC);
CREATE INDEX IF NOT EXISTS idx_baseline_comparisons_status ON baseline_comparisons(overall_status) WHERE overall_status IN ('warning', 'critical');
CREATE INDEX IF NOT EXISTS idx_baseline_comparisons_date ON baseline_comparisons(comparison_date DESC);

-- GIN index for JSONB comparison results
CREATE INDEX IF NOT EXISTS idx_baseline_comparisons_results ON baseline_comparisons USING GIN (comparison_results);

-- ============================================================================
-- View: v_equipment_baseline_summary
-- Summary view showing current baseline status for all equipment
-- ============================================================================
CREATE OR REPLACE VIEW v_equipment_baseline_summary AS
SELECT
    e.equipment_id,
    e.equipment_name,
    e.equipment_type,
    e.site_id,
    COUNT DISTINCT eb.id) FILTER (WHERE eb.status = 'active') as active_baselines,
    MAX(eb.baseline_date) as last_baseline_date,
    -- Days since last baseline
    CURRENT_DATE - MAX(eb.baseline_date)::date as days_since_baseline,
    -- Count of elements that have baselines
    COUNT(DISTINCT el.id) as total_elements,
    COUNT(DISTINCT elb.id) FILTER (WHERE elb.status = 'active') as elements_with_baselines
FROM equipment e
LEFT JOIN equipment_baselines eb ON e.equipment_id = eb.equipment_id
LEFT JOIN equipment_elements el ON e.equipment_id = el.equipment_id
LEFT JOIN element_baselines elb ON el.id = elb.element_id
GROUP BY e.equipment_id, e.equipment_name, e.equipment_type, e.site_id;

-- ============================================================================
-- View: v_critical_baseline_deviations
-- View showing recent baseline comparisons with critical deviations
-- ============================================================================
CREATE OR REPLACE VIEW v_critical_baseline_deviations AS
SELECT
    bc.id,
    bc.comparison_date,
    bc.equipment_id,
    e.equipment_name,
    e.equipment_type,
    bc.comparison_type,
    bc.overall_status,
    bc.max_deviation_percent,
    bc.comparison_results,
    bc.data_source,
    -- Extract the specific metrics that are in warning/critical status
    jsonb_object_keys(bc.comparison_results) as metric_name
FROM baseline_comparisons bc
JOIN equipment e ON bc.equipment_id = e.equipment_id
WHERE bc.overall_status IN ('warning', 'critical')
  AND bc.comparison_date >= NOW() - INTERVAL '30 days'
ORDER BY bc.comparison_date DESC;

-- ============================================================================
-- Function: update_updated_at() - Auto-update timestamps
-- ============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create triggers for automatic timestamp updates
CREATE TRIGGER update_equipment_baselines_updated_at
    BEFORE UPDATE ON equipment_baselines
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_equipment_elements_updated_at
    BEFORE UPDATE ON equipment_elements
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_element_baselines_updated_at
    BEFORE UPDATE ON element_baselines
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- RLS (Row Level Security) Policies
-- ============================================================================
ALTER TABLE equipment_baselines ENABLE ROW LEVEL SECURITY;
ALTER TABLE equipment_elements ENABLE ROW LEVEL SECURITY;
ALTER TABLE element_baselines ENABLE ROW LEVEL SECURITY;
ALTER TABLE baseline_comparisons ENABLE ROW LEVEL SECURITY;

-- Allow read access to all authenticated users (fine-grained permissions in API)
CREATE POLICY "Allow read for authenticated users" ON equipment_baselines FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Allow read for authenticated users" ON equipment_elements FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Allow read for authenticated users" ON element_baselines FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Allow read for authenticated users" ON baseline_comparisons FOR SELECT USING (auth.role() = 'authenticated');

-- Allow insert/update for facility managers (role check in API)
CREATE POLICY "Allow write for authenticated users" ON equipment_baselines FOR ALL USING (auth.role() = 'authenticated');
CREATE POLICY "Allow write for authenticated users" ON equipment_elements FOR ALL USING (auth.role() = 'authenticated');
CREATE POLICY "Allow write for authenticated users" ON element_baselines FOR ALL USING (auth.role() = 'authenticated');
CREATE POLICY "Allow write for authenticated users" ON baseline_comparisons FOR ALL USING (auth.role() = 'authenticated');

-- ============================================================================
-- Comments for documentation
-- ============================================================================
COMMENT ON TABLE equipment_baselines IS 'Stores baseline readings captured for each equipment instance during onboarding and maintenance';
COMMENT ON TABLE equipment_elements IS 'Defines individual elements/components within equipment (bearings, filters, etc.)';
COMMENT ON TABLE element_baselines IS 'Stores baseline readings for individual equipment elements';
COMMENT ON TABLE baseline_comparisons IS 'Stores automated comparison results between current readings and baselines';

COMMENT ON VIEW v_equipment_baseline_summary IS 'Summary view showing current baseline status for all equipment';
COMMENT ON VIEW v_critical_baseline_deviations IS 'View showing recent baseline comparisons with critical deviations';

-- ============================================================================
-- Success message
-- ============================================================================
SELECT 'Equipment baseline assessment schema created successfully' as status;

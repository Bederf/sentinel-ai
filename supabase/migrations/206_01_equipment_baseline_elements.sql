-- Migration: Equipment Baseline Elements (Phase 206-01)
-- Description: Create equipment_baseline_elements table for Phase 44 baseline elements
-- Phase: 206-01 - Asset Onboarding Baseline Seeding

-- ============================================================================
-- Table: equipment_baseline_elements
-- Stores element-level baseline data for equipment components
-- (bearings, filters, coils, etc.)
-- ============================================================================
CREATE TABLE IF NOT EXISTS equipment_baseline_elements (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    baseline_id UUID NOT NULL REFERENCES equipment_baselines(id) ON DELETE CASCADE,

    -- Element identification
    element_name TEXT NOT NULL, -- Human-readable name (e.g., "Bearing A", "Filter Set 1")
    element_type TEXT NOT NULL, -- bearing, filter, coil, fan, motor, pump, valve

    -- Nominal baseline values
    nominal_value DOUBLE PRECISION NOT NULL,
    unit TEXT NOT NULL, -- Pa, °C, mm/s, A, Hz, etc.

    -- Tolerance configuration
    tolerance_pct DOUBLE PRECISION NOT NULL DEFAULT 10.0, -- Acceptable deviation %
    criticality TEXT NOT NULL DEFAULT 'medium', -- low, medium, high, critical

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for element queries
CREATE INDEX IF NOT EXISTS idx_equipment_baseline_elements_baseline_id ON equipment_baseline_elements(baseline_id);
CREATE INDEX IF NOT EXISTS idx_equipment_baseline_elements_type ON equipment_baseline_elements(element_type);
CREATE INDEX IF NOT EXISTS idx_equipment_baseline_elements_criticality ON equipment_baseline_elements(criticality);

-- Trigger for auto-updating timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_equipment_baseline_elements_updated_at ON equipment_baseline_elements;
CREATE TRIGGER update_equipment_baseline_elements_updated_at
    BEFORE UPDATE ON equipment_baseline_elements
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- RLS (Row Level Security)
ALTER TABLE equipment_baseline_elements ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow read for authenticated users" ON equipment_baseline_elements
    FOR SELECT USING (auth.role() = 'authenticated');

CREATE POLICY "Allow write for authenticated users" ON equipment_baseline_elements
    FOR ALL USING (auth.role() = 'authenticated');

-- ============================================================================
-- Success message
-- ============================================================================
SELECT 'equipment_baseline_elements table created successfully' as status;

-- Migration: Routine Inspection & Maintenance Schema
-- Description: Database schema for inspection scheduling, checklists, and results
-- Phase: 45 - Routine Inspection & Maintenance
-- Depends on: 025_equipment_baseline_schema.sql

-- ============================================================================
-- Table: inspection_schedules
-- Defines recurring inspection schedules for equipment
-- ============================================================================
CREATE TABLE IF NOT EXISTS inspection_schedules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- What to inspect
    equipment_id UUID NOT NULL REFERENCES equipment(id),
    element_id UUID REFERENCES equipment_elements(id), -- Optional: specific element

    -- Schedule definition
    schedule_name TEXT NOT NULL, -- e.g., "Monthly Generator Inspection"
    schedule_description TEXT,

    -- Frequency configuration
    frequency_type TEXT NOT NULL, -- weekly, monthly, quarterly, annual, custom
    frequency_days INTEGER, -- For custom frequency (e.g., 14 for bi-weekly)

    -- Scheduling details
    day_of_week INTEGER, -- For weekly: 0=Sunday, 1=Monday, etc.
    day_of_month INTEGER, -- For monthly: 1-31

    -- Timing
    estimated_duration_minutes INTEGER DEFAULT 60,
    preferred_time_of_day TEXT, -- morning, afternoon, any

    -- Assignment
    assigned_to TEXT, -- Technician name or role
    required_skills TEXT[], -- Skills required to perform inspection

    -- Status and tracking
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_generated_date TIMESTAMPTZ,
    next_due_date TIMESTAMPTZ,

    -- Metadata
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for inspection scheduling
CREATE INDEX IF NOT EXISTS idx_inspection_schedules_equipment ON inspection_schedules(equipment_id, is_active);
CREATE INDEX IF NOT EXISTS idx_inspection_schedules_next_due ON inspection_schedules(next_due_date) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_inspection_schedules_frequency ON inspection_schedules(frequency_type, is_active);

-- ============================================================================
-- Table: inspection_checklist_templates
-- Template definitions for inspection checklists
-- ============================================================================
CREATE TABLE IF NOT EXISTS inspection_checklist_templates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Template identification
    template_name TEXT NOT NULL, -- e.g., "Generator Monthly Inspection"
    equipment_type TEXT NOT NULL, -- generator, chiller, ahu, etc.
    inspection_type TEXT NOT NULL, -- routine, preventive, corrective

    -- Frequency and duration
    frequency_type TEXT NOT NULL, -- weekly, monthly, quarterly, annual
    estimated_duration_minutes INTEGER DEFAULT 60,

    -- Template status
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    version INTEGER DEFAULT 1,

    -- Checklist items (JSON array for flexibility)
    -- Each item has: id, description, method, acceptance_criteria, recording_required
    checklist_items JSONB NOT NULL DEFAULT '[]',

    -- Required tools and skills
    required_tools TEXT[],
    required_skills TEXT[],

    -- Safety requirements
    safety_requirements TEXT[],
    ppe_required TEXT[],

    -- Metadata
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for checklist templates
CREATE INDEX IF NOT EXISTS idx_checklist_templates_equipment_type ON inspection_checklist_templates(equipment_type, inspection_type, is_active);
CREATE INDEX IF NOT EXISTS idx_checklist_templates_frequency ON inspection_checklist_templates(frequency_type, is_active);

-- ============================================================================
-- Table: inspection_tasks
-- Individual scheduled inspection instances (generated from schedules)
-- ============================================================================
CREATE TABLE IF NOT EXISTS inspection_tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Source schedule
    schedule_id UUID REFERENCES inspection_schedules(id),

    -- Task identification
    task_name TEXT NOT NULL,
    task_description TEXT,

    -- What to inspect
    equipment_id UUID NOT NULL REFERENCES equipment(id),
    element_id UUID REFERENCES equipment_elements(id), -- Optional

    -- Scheduling
    scheduled_date TIMESTAMPTZ NOT NULL,
    due_date TIMESTAMPTZ NOT NULL,

    -- Assignment
    assigned_to TEXT, -- Technician assigned
    assigned_by TEXT, -- Who assigned the task

    -- Status tracking
    status TEXT NOT NULL DEFAULT 'scheduled', -- scheduled, in_progress, completed, overdue, cancelled

    -- Completion tracking
    completed_date TIMESTAMPTZ,
    completed_by TEXT,
    completion_notes TEXT,

    -- Duration
    estimated_duration_minutes INTEGER,
    actual_duration_minutes INTEGER,

    -- Priority and criticality
    priority TEXT DEFAULT 'normal', -- low, normal, high, urgent
    is_critical BOOLEAN DEFAULT FALSE, -- Based on critical elements from baseline

    -- Checklist used
    checklist_template_id UUID REFERENCES inspection_checklist_templates(id),

    -- References
    baseline_reference_id UUID REFERENCES equipment_baselines(id), -- Reference baseline for comparison

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for inspection tasks
CREATE INDEX IF NOT EXISTS idx_inspection_tasks_equipment ON inspection_tasks(equipment_id, status);
CREATE INDEX IF NOT EXISTS idx_inspection_tasks_assigned ON inspection_tasks(assigned_to, status) WHERE status IN ('scheduled', 'in_progress');
CREATE INDEX IF NOT EXISTS idx_inspection_tasks_due_date ON inspection_tasks(due_date, status) WHERE status = 'scheduled';
CREATE INDEX IF NOT EXISTS idx_inspection_tasks_status ON inspection_tasks(status, due_date);

-- ============================================================================
-- Table: inspection_results
-- Results from completed inspections
-- ============================================================================
CREATE TABLE IF NOT EXISTS inspection_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Reference to task
    task_id UUID NOT NULL REFERENCES inspection_tasks(id),

    -- Who performed inspection
    inspected_by TEXT NOT NULL,
    inspection_date TIMESTAMPTZ NOT NULL,

    -- Overall results
    overall_status TEXT NOT NULL, -- pass, fail, partial

    -- Detailed results (JSON array of checklist item results)
    -- Each item includes: checklist_item_id, status, measurement_value, notes, photo_urls
    item_results JSONB NOT NULL DEFAULT '[]',

    -- Measurements captured during inspection
    measurements JSONB DEFAULT '{}', -- Key-value pairs of measurements

    -- Findings summary
    deficiencies_found INTEGER DEFAULT 0,
    critical_findings INTEGER DEFAULT 0,

    -- Environmental conditions
    ambient_conditions JSONB DEFAULT '{}', -- temperature, humidity, etc.

    -- Time tracking
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    -- Notes and observations
    general_notes TEXT,
    recommendations TEXT,

    -- Photo documentation
    photo_urls TEXT[],

    -- Next inspection recommendation
    recommended_next_inspection_date TIMESTAMPTZ,

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for inspection results
CREATE INDEX IF NOT EXISTS idx_inspection_results_task ON inspection_results(task_id);
CREATE INDEX IF NOT EXISTS idx_inspection_results_date ON inspection_results(inspection_date);
CREATE INDEX IF NOT EXISTS idx_inspection_results_status ON inspection_results(overall_status);

-- GIN index for JSONB item_results queries
CREATE INDEX IF NOT EXISTS idx_inspection_results_items ON inspection_results USING GIN (item_results);

-- ============================================================================
-- Table: inspection_deficiencies
-- Issues/deficiencies found during inspections
-- ============================================================================
CREATE TABLE IF NOT EXISTS inspection_deficiencies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Source inspection
    result_id UUID NOT NULL REFERENCES inspection_results(id),
    task_id UUID NOT NULL REFERENCES inspection_tasks(id),
    equipment_id UUID NOT NULL REFERENCES equipment(id),

    -- Element affected (optional)
    element_id UUID REFERENCES equipment_elements(id),

    -- Deficiency details
    deficiency_title TEXT NOT NULL,
    deficiency_description TEXT,

    -- Severity and classification
    severity TEXT NOT NULL, -- minor, major, critical, safety
    category TEXT, -- mechanical, electrical, operational, safety

    -- Where found
    checklist_item_id TEXT, -- References checklist item
    location_detail TEXT, -- Specific location on equipment

    -- Photo evidence
    photo_urls TEXT[],

    -- Impact assessment
    impact_description TEXT,
    urgency TEXT, -- low, medium, high, urgent

    -- Recommended action
    recommended_action TEXT,
    estimated_repair_cost_min DECIMAL(10,2),
    estimated_repair_cost_max DECIMAL(10,2),
    estimated_repair_hours INTEGER,

    -- Resolution tracking
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_date TIMESTAMPTZ,
    resolved_by TEXT,
    resolution_notes TEXT,

    -- Work order tracking
    work_order_id TEXT, -- References work_orders table if integrated

    -- Metadata
    reported_by TEXT NOT NULL,
    reported_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for inspection deficiencies
CREATE INDEX IF NOT EXISTS idx_deficiencies_equipment ON inspection_deficiencies(equipment_id, is_resolved);
CREATE INDEX IF NOT EXISTS idx_deficiencies_severity ON inspection_deficiencies(severity, is_resolved) WHERE severity IN ('critical', 'safety');
CREATE INDEX IF NOT EXISTS idx_deficiencies_task ON inspection_deficiencies(task_id);
CREATE INDEX IF NOT EXISTS idx_deficiencies_date ON inspection_deficiencies(reported_date);

-- ============================================================================
-- Table: inspection_measurements
-- Detailed measurement records from inspections
-- ============================================================================
CREATE TABLE IF NOT EXISTS inspection_measurements (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Reference to inspection
    result_id UUID NOT NULL REFERENCES inspection_results(id),
    task_id UUID NOT NULL REFERENCES inspection_tasks(id),
    equipment_id UUID NOT NULL REFERENCES equipment(id),

    -- What was measured
    measurement_type TEXT NOT NULL, -- temperature, pressure, vibration, etc.
    measurement_point TEXT NOT NULL, -- sensor_id or measurement location

    -- The measurement
    measured_value DECIMAL(15,4) NOT NULL,
    unit TEXT NOT NULL, -- °C, bar, mm/s, dBA, etc.

    -- Context
    measurement_date TIMESTAMPTZ NOT NULL,
    measured_by TEXT NOT NULL,

    -- Comparison to baseline (if available)
    baseline_value DECIMAL(15,4),
    baseline_deviation_percent DECIMAL(10,2),
    deviation_status TEXT, -- normal, warning, critical

    -- Metadata
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for inspection measurements
CREATE INDEX IF NOT EXISTS idx_measurements_equipment ON inspection_measurements(equipment_id, measurement_date DESC);
CREATE INDEX IF NOT EXISTS idx_measurements_type ON inspection_measurements(measurement_type, measurement_date DESC);
CREATE INDEX IF NOT EXISTS idx_measurements_point ON inspection_measurements(measurement_point, measurement_date DESC);
CREATE INDEX IF NOT EXISTS idx_measurements_deviation ON inspection_measurements(deviation_status) WHERE deviation_status IN ('warning', 'critical');

-- ============================================================================
-- Views for Reporting and Dashboards
-- ============================================================================

-- View: v_inspection_overview
-- Summary of inspection status across all equipment
CREATE OR REPLACE VIEW v_inspection_overview AS
SELECT
    e.id,
    e.name,
    e.type,
    e.building_id,
    COUNT(DISTINCT s.id) as active_schedules,
    COUNT(DISTINCT t.id) FILTER (WHERE t.status = 'scheduled') as scheduled_tasks,
    COUNT(DISTINCT t.id) FILTER (WHERE t.status = 'in_progress') as in_progress_tasks,
    COUNT(DISTINCT t.id) FILTER (WHERE t.status = 'overdue') as overdue_tasks,
    COUNT(DISTINCT t.id) FILTER (WHERE t.status = 'completed' AND t.completed_date >= NOW() - INTERVAL '30 days') as completed_last_30_days,
    COUNT(DISTINCT d.id) FILTER (WHERE d.is_resolved = FALSE) as open_deficiencies,
    COUNT(DISTINCT d.id) FILTER (WHERE d.severity = 'critical' AND d.is_resolved = FALSE) as critical_deficiencies
FROM equipment e
LEFT JOIN inspection_schedules s ON e.id = s.equipment_id AND s.is_active = TRUE
LEFT JOIN inspection_tasks t ON e.id = t.equipment_id
LEFT JOIN inspection_deficiencies d ON e.id = d.equipment_id
GROUP BY e.id, e.name, e.type, e.building_id;

-- View: v_inspection_tasks_due
-- Upcoming and overdue inspection tasks
CREATE OR REPLACE VIEW v_inspection_tasks_due AS
SELECT
    t.id,
    t.task_name,
    t.equipment_id,
    e.name,
    t.element_id,
    t.assigned_to,
    t.scheduled_date,
    t.due_date,
    t.status,
    t.priority,
    t.is_critical,
    CASE
        WHEN t.due_date < NOW() THEN 'overdue'
        WHEN t.due_date <= NOW() + INTERVAL '7 days' THEN 'due_soon'
        ELSE 'scheduled'
    END as urgency
FROM inspection_tasks t
JOIN equipment e ON t.equipment_id = e.id
WHERE t.status IN ('scheduled', 'in_progress')
ORDER BY t.due_date ASC;

-- View: v_equipment_inspection_summary
-- Inspection statistics per equipment
CREATE OR REPLACE VIEW v_equipment_inspection_summary AS
SELECT
    e.id,
    e.name,
    COUNT(DISTINCT r.id) as total_inspections,
    AVG(EXTRACT(EPOCH FROM (r.completed_at - r.started_at))/60) FILTER (WHERE r.started_at IS NOT NULL AND r.completed_at IS NOT NULL) as avg_duration_minutes,
    COUNT(DISTINCT d.id) FILTER (WHERE d.is_resolved = FALSE) as open_deficiencies,
    COUNT(DISTINCT d.id) FILTER (WHERE d.severity = 'critical' AND d.is_resolved = FALSE) as critical_deficiencies,
    MAX(r.inspection_date) as last_inspection_date,
    AVG(CASE WHEN r.overall_status = 'pass' THEN 1 ELSE 0 END) as pass_rate
FROM equipment e
LEFT JOIN inspection_tasks t ON e.id = t.equipment_id
LEFT JOIN inspection_results r ON t.id = r.task_id
LEFT JOIN inspection_deficiencies d ON e.id = d.equipment_id
GROUP BY e.id, e.name;

-- View: v_critical_inspection_findings
-- Recent critical deficiencies
CREATE OR REPLACE VIEW v_critical_inspection_findings AS
SELECT
    d.id,
    d.deficiency_title,
    d.severity,
    d.equipment_id,
    e.name,
    d.reported_date,
    d.recommended_action,
    d.estimated_repair_cost_min,
    d.estimated_repair_cost_max,
    r.inspection_date,
    r.inspected_by
FROM inspection_deficiencies d
JOIN equipment e ON d.equipment_id = e.id
JOIN inspection_results r ON d.result_id = r.id
WHERE d.severity IN ('critical', 'safety')
  AND d.is_resolved = FALSE
ORDER BY d.reported_date DESC;

-- ============================================================================
-- Functions for Inspection Management
-- ============================================================================

-- Function: Update updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for automatic timestamp updates
CREATE TRIGGER update_inspection_schedules_updated_at
    BEFORE UPDATE ON inspection_schedules
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_inspection_checklist_templates_updated_at
    BEFORE UPDATE ON inspection_checklist_templates
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_inspection_tasks_updated_at
    BEFORE UPDATE ON inspection_tasks
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_inspection_results_updated_at
    BEFORE UPDATE ON inspection_results
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_inspection_deficiencies_updated_at
    BEFORE UPDATE ON inspection_deficiencies
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- Row Level Security (RLS) Policies
-- ============================================================================

ALTER TABLE inspection_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE inspection_checklist_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE inspection_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE inspection_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE inspection_deficiencies ENABLE ROW LEVEL SECURITY;
ALTER TABLE inspection_measurements ENABLE ROW LEVEL SECURITY;

-- Allow read access for authenticated users
CREATE POLICY "Allow read for authenticated users" ON inspection_schedules FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Allow read for authenticated users" ON inspection_checklist_templates FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Allow read for authenticated users" ON inspection_tasks FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Allow read for authenticated users" ON inspection_results FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Allow read for authenticated users" ON inspection_deficiencies FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Allow read for authenticated users" ON inspection_measurements FOR SELECT USING (auth.role() = 'authenticated');

-- Allow write access for authenticated users
CREATE POLICY "Allow write for authenticated users" ON inspection_schedules FOR ALL USING (auth.role() = 'authenticated');
CREATE POLICY "Allow write for authenticated users" ON inspection_checklist_templates FOR ALL USING (auth.role() = 'authenticated');
CREATE POLICY "Allow write for authenticated users" ON inspection_tasks FOR ALL USING (auth.role() = 'authenticated');
CREATE POLICY "Allow write for authenticated users" ON inspection_results FOR ALL USING (auth.role() = 'authenticated');
CREATE POLICY "Allow write for authenticated users" ON inspection_deficiencies FOR ALL USING (auth.role() = 'authenticated');
CREATE POLICY "Allow write for authenticated users" ON inspection_measurements FOR ALL USING (auth.role() = 'authenticated');

-- ============================================================================
-- Sample Data: Inspection Checklist Templates
-- ============================================================================

-- Generator Monthly Inspection Template
INSERT INTO inspection_checklist_templates (
    template_name, equipment_type, inspection_type, frequency_type,
    estimated_duration_minutes, checklist_items, required_tools, required_skills,
    safety_requirements, ppe_required, created_by
) VALUES (
    'Generator Monthly Inspection',
    'generator',
    'routine',
    'monthly',
    90,
    '[
        {
            "item_id": "gen_001",
            "description": "Check engine oil level and condition",
            "method": "visual_inspection",
            "acceptance_criteria": "Oil level between MIN and MAX marks, no contamination",
            "recording_required": ["oil_level", "condition", "photo"],
            "critical": false
        },
        {
            "item_id": "gen_002",
            "description": "Inspect for oil leaks",
            "method": "visual_inspection",
            "acceptance_criteria": "No active leaks, no oil accumulation",
            "recording_required": ["leak_status", "photo", "drip_rate_if_leaking"],
            "critical": true,
            "baseline_reference": "oil_system_leak"
        },
        {
            "item_id": "gen_003",
            "description": "Measure exhaust gas temperature at full load",
            "method": "thermal_gun_measurement",
            "acceptance_criteria": "Temperature < 450°C, within 15% of baseline",
            "recording_required": ["temperature", "load_percent", "photo"],
            "critical": false,
            "baseline_reference": "exhaust_temperature"
        },
        {
            "item_id": "gen_004",
            "description": "Check coolant level and condition",
            "method": "visual_inspection",
            "acceptance_criteria": "Level between MIN and MAX, no discoloration",
            "recording_required": ["level", "condition", "photo"],
            "critical": false
        },
        {
            "item_id": "gen_005",
            "description": "Measure vibration on engine block",
            "method": "vibration_analyzer",
            "acceptance_criteria": "RMS vibration < 4.5 mm/s, no significant change from baseline",
            "recording_required": ["vibration_rms", "vibration_peak", "spectrum", "photo"],
            "critical": true,
            "baseline_reference": "vibration_signature"
        },
        {
            "item_id": "gen_006",
            "description": "Check battery voltage and connections",
            "method": "multimeter_measurement",
            "acceptance_criteria": "Voltage > 12.6V, connections clean and tight",
            "recording_required": ["voltage", "connection_condition", "photo"],
            "critical": false
        },
        {
            "item_id": "gen_007",
            "description": "Check fuel system for leaks",
            "method": "visual_inspection",
            "acceptance_criteria": "No fuel leaks, no odor",
            "recording_required": ["leak_status", "photo"],
            "critical": true
        },
        {
            "item_id": "gen_008",
            "description": "Test generator under load",
            "method": "load_bank_test",
            "acceptance_criteria": "Generator runs smoothly at 50% and 100% load",
            "recording_required": ["load_percent", "runtime", "voltage_output", "frequency"],
            "critical": false
        }
    ]',
    ARRAY['flashlight', 'thermal_gun', 'vibration_analyzer', 'multimeter', 'load_bank'],
    ARRAY['generator_maintenance', 'vibration_analysis', 'thermal_imaging'],
    ARRAY['lockout_tagout', 'fire_extinguisher_nearby', 'ventilation_check'],
    ARRAY['safety_glasses', 'gloves', 'hearing_protection', 'face_shield'],
    'system'
) ON CONFLICT DO NOTHING;

-- Chiller Monthly Inspection Template
INSERT INTO inspection_checklist_templates (
    template_name, equipment_type, inspection_type, frequency_type,
    estimated_duration_minutes, checklist_items, required_tools, required_skills,
    safety_requirements, ppe_required, created_by
) VALUES (
    'Chiller Monthly Inspection',
    'chiller',
    'routine',
    'monthly',
    120,
    '[
        {
            "item_id": "ch_001",
            "description": "Check suction and discharge pressures",
            "method": "bms_sensor_reading",
            "acceptance_criteria": "Within normal range per baseline, no significant deviation",
            "recording_required": ["suction_pressure", "discharge_pressure"],
            "critical": true
        },
        {
            "item_id": "ch_002",
            "description": "Measure superheat and subcooling",
            "method": "gauge_measurement",
            "acceptance_criteria": "Superheat 4-8K, Subcooling 3-7K",
            "recording_required": ["superheat", "subcooling", "photo"],
            "critical": true
        },
        {
            "item_id": "ch_003",
            "description": "Check for refrigerant leaks",
            "method": "electronic_leak_detector",
            "acceptance_criteria": "No leaks detected",
            "recording_required": ["leak_test_result", "photo"],
            "critical": true
        },
        {
            "item_id": "ch_004",
            "description": "Measure compressor motor current",
            "method": "clamp_meter",
            "acceptance_criteria": "Within rated value, balanced across phases",
            "recording_required": ["current_l1", "current_l2", "current_l3"],
            "critical": false
        },
        {
            "item_id": "ch_005",
            "description": "Check oil level and pressure",
            "method": "visual_inspection_and_gauge",
            "acceptance_criteria": "Level in sight glass, pressure > 2.5 bar",
            "recording_required": ["oil_level", "oil_pressure", "photo"],
            "critical": true
        },
        {
            "item_id": "ch_006",
            "description": "Inspect condenser coils",
            "method": "visual_inspection",
            "acceptance_criteria": "Clean, no damage, proper airflow",
            "recording_required": ["cleanliness_rating", "photo"],
            "critical": false
        },
        {
            "item_id": "ch_007",
            "description": "Measure compressor vibration",
            "method": "vibration_analyzer",
            "acceptance_criteria": "RMS < 1.8 mm/s, no unusual frequencies",
            "recording_required": ["vibration_rms", "spectrum", "photo"],
            "critical": true
        },
        {
            "item_id": "ch_008",
            "description": "Check control panel alarms and status",
            "method": "control_panel_review",
            "acceptance_criteria": "No active alarms, all safeties functional",
            "recording_required": ["alarm_status", "photo_of_display"],
            "critical": false
        }
    ]',
    ARRAY['pressure_gauges', 'thermal_gun', 'clamp_meter', 'leak_detector', 'vibration_analyzer'],
    ARRAY['chiller_maintenance', 'refrigeration', 'vibration_analysis'],
    ARRAY['lockout_tagout', 'refrigerant_handling_cert', 'confined_space'],
    ARRAY['safety_glasses', 'gloves', 'refrigerant_gloves', 'face_shield'],
    'system'
) ON CONFLICT DO NOTHING;

-- ============================================================================
-- Comments
-- ============================================================================
COMMENT ON TABLE inspection_schedules IS 'Recurring inspection schedule definitions for equipment';
COMMENT ON TABLE inspection_checklist_templates IS 'Template definitions for inspection checklists by equipment type';
COMMENT ON TABLE inspection_tasks IS 'Individual scheduled inspection tasks generated from schedules';
COMMENT ON TABLE inspection_results IS 'Results from completed inspections including measurements and findings';
COMMENT ON TABLE inspection_deficiencies IS 'Issues/deficiencies found during inspections';
COMMENT ON TABLE inspection_measurements IS 'Detailed measurement records from inspections';

COMMENT ON VIEW v_inspection_overview IS 'Summary of inspection status across all equipment';
COMMENT ON VIEW v_inspection_tasks_due IS 'Upcoming and overdue inspection tasks';
COMMENT ON VIEW v_equipment_inspection_summary IS 'Inspection statistics per equipment';
COMMENT ON VIEW v_critical_inspection_findings IS 'Recent critical deficiencies requiring attention';

-- ============================================================================
-- Success message
-- ============================================================================
SELECT 'Routine Inspection schema created successfully with templates' as status;

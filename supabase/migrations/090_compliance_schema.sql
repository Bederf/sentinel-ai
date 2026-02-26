-- Migration: SENTINEL Compliance Management System
-- Description: Database schema for OHS, Fire Safety, Emergency Lighting, Legionella, Electrical, and Lift Compliance
-- Phase: 28 - SENTINEL Compliance
-- Depends on: 026_inspection_schema.sql (reuses inspection_schedules, inspection_tasks, inspection_results)

-- ============================================================================
-- Table: compliance_checklist_templates
-- Extends Phase 45 checklist templates with compliance-specific requirements
-- ============================================================================
CREATE TABLE IF NOT EXISTS compliance_checklist_templates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Compliance type classification
    compliance_type TEXT NOT NULL CHECK (compliance_type IN ('OHS', 'Fire', 'Electrical', 'Legionella', 'LiftSafety')),

    -- Standard reference (e.g., 'NFPA 10', 'IEC 62034', 'SABS 4066')
    requirement_standard TEXT NOT NULL,

    -- Template identification
    template_name TEXT NOT NULL,
    description TEXT,

    -- Checklist structure (array of items with id, description, frequency, evidence_required)
    checklist_items JSONB NOT NULL DEFAULT '[]',

    -- Risk classification
    risk_level TEXT NOT NULL CHECK (risk_level IN ('critical', 'high', 'medium', 'low')) DEFAULT 'medium',

    -- Status
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    version INTEGER DEFAULT 1,

    -- Audit trail
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_compliance_templates_type_status ON compliance_checklist_templates(compliance_type, is_active);
CREATE INDEX IF NOT EXISTS idx_compliance_templates_standard ON compliance_checklist_templates(requirement_standard);
CREATE INDEX IF NOT EXISTS idx_compliance_templates_risk ON compliance_checklist_templates(risk_level);

-- ============================================================================
-- Table: compliance_audits
-- Comprehensive audit trail for compliance inspections and findings
-- ============================================================================
CREATE TABLE IF NOT EXISTS compliance_audits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Site reference
    site_id UUID NOT NULL REFERENCES buildings(id),

    -- Audit classification
    compliance_type TEXT NOT NULL CHECK (compliance_type IN ('OHS', 'Fire', 'Electrical', 'Legionella', 'LiftSafety')),
    audit_type TEXT NOT NULL, -- 'scheduled', 'unannounced', 'certification'

    -- Auditor information
    auditor_id UUID,
    auditor_role TEXT, -- 'Fire Safety Officer', 'Legionella Assessor', 'OHS Inspector', etc.

    -- Audit findings (flexible JSONB for different compliance types)
    findings JSONB NOT NULL DEFAULT '{}', -- {critical_issues, recommendations, cost_estimates, action_items}

    -- Status lifecycle
    status TEXT NOT NULL CHECK (status IN ('draft', 'submitted', 'approved', 'remediation_pending', 'closed')) DEFAULT 'draft',

    -- Evidence and documentation
    evidence_url TEXT, -- Document storage path (R2 bucket or similar)
    notes TEXT,

    -- Timestamps
    audit_date TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_date TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_compliance_audits_site_type ON compliance_audits(site_id, compliance_type);
CREATE INDEX IF NOT EXISTS idx_compliance_audits_status ON compliance_audits(status);
CREATE INDEX IF NOT EXISTS idx_compliance_audits_created ON compliance_audits(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_compliance_audits_audit_type ON compliance_audits(audit_type, compliance_type);

-- ============================================================================
-- Table: fire_equipment_tracking
-- Fire safety equipment inventory and inspection scheduling (NFPA 10, SABS 4066)
-- ============================================================================
CREATE TABLE IF NOT EXISTS fire_equipment_tracking (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Site and location
    site_id UUID NOT NULL REFERENCES buildings(id),
    zone_id UUID REFERENCES zones(id),

    -- Equipment identification
    equipment_type TEXT NOT NULL CHECK (equipment_type IN ('extinguisher', 'hose_reel', 'hydrant', 'alarm', 'detector')),
    location_description TEXT NOT NULL, -- Human-readable location (e.g., "L1 Corridor B")
    unique_identifier TEXT, -- Serial number or tag number

    -- Inspection schedule
    last_inspection_date TIMESTAMPTZ,
    next_inspection_date TIMESTAMPTZ,
    inspection_frequency_months INTEGER DEFAULT 12,

    -- Pressure and charge management
    charge_pressure FLOAT, -- PSI
    pressure_test_date TIMESTAMPTZ,

    -- Certification
    certification_expiry TIMESTAMPTZ,
    certified_by TEXT, -- Inspector/contractor name

    -- Status
    status TEXT NOT NULL CHECK (status IN ('active', 'overdue', 'out_of_service', 'decommissioned')) DEFAULT 'active',

    -- Audit trail
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fire_equipment_site_zone ON fire_equipment_tracking(site_id, zone_id);
CREATE INDEX IF NOT EXISTS idx_fire_equipment_type ON fire_equipment_tracking(equipment_type);
CREATE INDEX IF NOT EXISTS idx_fire_equipment_next_due ON fire_equipment_tracking(next_inspection_date) WHERE status != 'decommissioned';
CREATE INDEX IF NOT EXISTS idx_fire_equipment_expiry ON fire_equipment_tracking(certification_expiry) WHERE status = 'active';

-- ============================================================================
-- Table: emergency_light_testing
-- Emergency lighting compliance (IEC 62034 automated testing)
-- ============================================================================
CREATE TABLE IF NOT EXISTS emergency_light_testing (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Site reference
    site_id UUID NOT NULL REFERENCES buildings(id),

    -- Equipment identification
    light_code TEXT NOT NULL, -- e.g., 'S002-EMERG-L2-001'
    fixture_location TEXT NOT NULL, -- Zone/area description
    control_point_id UUID, -- Link to device abstraction layer (FK deferred until equipment_points table exists)

    -- Testing schedule
    last_test_date TIMESTAMPTZ,
    test_interval_days INTEGER DEFAULT 365, -- IEC 62034 typically annual
    next_test_date TIMESTAMPTZ,

    -- Auto-testing configuration
    auto_test_enabled BOOLEAN DEFAULT TRUE,
    auto_test_time_utc TEXT DEFAULT '01:00', -- Test window (0100-0130 UTC)

    -- Battery health monitoring
    battery_health_percent INTEGER DEFAULT 100,
    battery_health_trend JSONB DEFAULT '[]', -- Historical battery %: [{date, value}, ...]
    battery_alert_threshold INTEGER DEFAULT 75, -- Alert if < 75% (IEC 62034: 3-hour runtime)

    -- Test results history
    test_results_history JSONB DEFAULT '[]', -- [{date, result, battery_health, notes}]

    -- Audit trail
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_emergency_light_site ON emergency_light_testing(site_id);
CREATE INDEX IF NOT EXISTS idx_emergency_light_next_test ON emergency_light_testing(next_test_date);
CREATE INDEX IF NOT EXISTS idx_emergency_light_auto_enabled ON emergency_light_testing(auto_test_enabled) WHERE auto_test_enabled = TRUE;
CREATE INDEX IF NOT EXISTS idx_emergency_light_battery_low ON emergency_light_testing(battery_health_percent) WHERE battery_health_percent < 75;

-- ============================================================================
-- Table: legionella_risk_assessment
-- Legionella management for cooling towers (SABS 4066 compliance)
-- ============================================================================
CREATE TABLE IF NOT EXISTS legionella_risk_assessment (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Site reference
    site_id UUID NOT NULL REFERENCES buildings(id),

    -- Equipment identification
    tower_code TEXT NOT NULL, -- e.g., 'S002-CT-B1-001'
    equipment_id UUID REFERENCES equipment(id),

    -- Risk classification
    risk_level TEXT NOT NULL CHECK (risk_level IN ('low', 'medium', 'high')) DEFAULT 'medium',

    -- Risk factors
    water_temperature FLOAT, -- Celsius
    water_test_date TIMESTAMPTZ,
    water_test_result_cfu BIGINT, -- CFU/mL (< 10^3 low risk, 10^3-10^4 medium, > 10^4 high)

    -- Treatment and control
    biocide_treatment_date TIMESTAMPTZ,
    biocide_treatment_interval_days INTEGER DEFAULT 30,

    temperature_monitoring BOOLEAN DEFAULT TRUE,
    temperature_setpoint_celsius FLOAT DEFAULT 30.0, -- Control target

    -- Control measures (flexible JSONB)
    control_measures JSONB DEFAULT '{}', -- {UV_systems: bool, filtration: TEXT, treatment_type: TEXT, frequency_schedule: TEXT}

    -- Assessment notes
    notes TEXT,
    assessed_by TEXT,
    assessment_date TIMESTAMPTZ,

    -- Status
    status TEXT NOT NULL CHECK (status IN ('compliant', 'at_risk', 'action_required', 'remediation_in_progress')) DEFAULT 'at_risk',

    -- Audit trail
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_legionella_site ON legionella_risk_assessment(site_id);
CREATE INDEX IF NOT EXISTS idx_legionella_risk_level ON legionella_risk_assessment(risk_level);
CREATE INDEX IF NOT EXISTS idx_legionella_equipment ON legionella_risk_assessment(equipment_id);
CREATE INDEX IF NOT EXISTS idx_legionella_next_treatment ON legionella_risk_assessment(biocide_treatment_date);
CREATE INDEX IF NOT EXISTS idx_legionella_water_test ON legionella_risk_assessment(water_test_date);

-- ============================================================================
-- Table: electrical_compliance
-- Electrical Certificate of Compliance (CoC) tracking (South African SABS standards)
-- ============================================================================
CREATE TABLE IF NOT EXISTS electrical_compliance (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Site reference
    site_id UUID NOT NULL REFERENCES buildings(id),

    -- Certificate identification
    certificate_type TEXT NOT NULL, -- 'CoC_new_installation', 'CoC_alterations', 'SABS_inspection'
    certificate_number TEXT UNIQUE,

    -- Issuer information
    issued_by TEXT NOT NULL, -- Registered electrician name
    issued_by_license TEXT, -- Registration number
    issued_by_contact TEXT, -- Email/phone for re-certification

    -- Dates (standard: 5-year validity in South Africa)
    issue_date TIMESTAMPTZ NOT NULL,
    expiry_date TIMESTAMPTZ NOT NULL,

    -- Scope
    scope TEXT NOT NULL, -- Equipment/area covered (e.g., 'L1-L2 distribution board upgrade')
    equipment_codes TEXT[], -- Equipment affected

    -- Status lifecycle
    status TEXT NOT NULL CHECK (status IN ('active', 'expiring_30days', 'expiring_90days', 'expired', 'remediation_in_progress')) DEFAULT 'active',

    -- Document storage
    certificate_url TEXT, -- R2 bucket path

    -- Metadata
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_electrical_site ON electrical_compliance(site_id);
CREATE INDEX IF NOT EXISTS idx_electrical_status ON electrical_compliance(status);
CREATE INDEX IF NOT EXISTS idx_electrical_expiry ON electrical_compliance(expiry_date) WHERE status IN ('active', 'expiring_30days', 'expiring_90days');
CREATE INDEX IF NOT EXISTS idx_electrical_cert_type ON electrical_compliance(certificate_type);

-- ============================================================================
-- Table: lift_inspection_tracking
-- Lift/Elevator safety inspection scheduling and test results
-- ============================================================================
CREATE TABLE IF NOT EXISTS lift_inspection_tracking (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Site reference
    site_id UUID NOT NULL REFERENCES buildings(id),

    -- Equipment identification
    lift_code TEXT NOT NULL, -- e.g., 'S002-LIFT-R-001'
    equipment_id UUID REFERENCES equipment(id),
    location_description TEXT NOT NULL,

    -- Inspection scheduling
    inspection_type TEXT NOT NULL, -- 'periodic_6monthly', 'annual_insurance', 'after_repair'
    last_inspection_date TIMESTAMPTZ,
    next_inspection_date TIMESTAMPTZ,

    -- Inspector information
    inspector_name TEXT,
    inspector_license_number TEXT,
    inspector_company TEXT,

    -- Test results (detailed JSONB structure)
    test_results JSONB DEFAULT '{}', -- {brake_load_test: TEXT, speed_governor: TEXT, emergency_stop_time: FLOAT, shaft_pressure: TEXT, car_buffer_test: TEXT, etc.}
    test_date TIMESTAMPTZ,

    -- Compliance
    non_compliance_items TEXT[], -- Array of issues found
    is_compliant BOOLEAN DEFAULT TRUE,

    -- Status
    status TEXT NOT NULL CHECK (status IN ('pending', 'completed', 'non_compliant', 'remediation_in_progress')) DEFAULT 'pending',

    -- Document storage
    inspection_report_url TEXT,
    inspection_notes TEXT,

    -- Audit trail
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lift_inspection_site ON lift_inspection_tracking(site_id);
CREATE INDEX IF NOT EXISTS idx_lift_inspection_type ON lift_inspection_tracking(inspection_type);
CREATE INDEX IF NOT EXISTS idx_lift_inspection_next_due ON lift_inspection_tracking(next_inspection_date) WHERE status != 'completed';
CREATE INDEX IF NOT EXISTS idx_lift_inspection_compliant ON lift_inspection_tracking(is_compliant);
CREATE INDEX IF NOT EXISTS idx_lift_inspection_created ON lift_inspection_tracking(created_at DESC);

-- ============================================================================
-- Triggers: Auto-create inspection schedules and alerts
-- ============================================================================

-- Trigger: When fire equipment is inserted, create inspection schedule
CREATE OR REPLACE FUNCTION create_fire_equipment_inspection_schedule()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO inspection_schedules (
        equipment_id,
        schedule_name,
        schedule_description,
        frequency_type,
        frequency_days,
        is_active,
        last_generated_date,
        next_due_date,
        created_by,
        created_at
    )
    VALUES (
        NEW.id,
        'Fire Equipment Inspection - ' || NEW.equipment_type,
        'Automatic ' || NEW.equipment_type || ' inspection per NFPA 10 / SABS 4066',
        'annual',
        365,
        TRUE,
        NOW(),
        NOW() + INTERVAL '365 days',
        'system',
        NOW()
    )
    ON CONFLICT DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_fire_equipment_schedule
AFTER INSERT ON fire_equipment_tracking
FOR EACH ROW
EXECUTE FUNCTION create_fire_equipment_inspection_schedule();

-- Trigger: When electrical certificate nears expiry, update status
CREATE OR REPLACE FUNCTION update_electrical_certificate_status()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.expiry_date <= NOW() THEN
        NEW.status := 'expired';
    ELSIF NEW.expiry_date <= NOW() + INTERVAL '30 days' THEN
        NEW.status := 'expiring_30days';
    ELSIF NEW.expiry_date <= NOW() + INTERVAL '90 days' THEN
        NEW.status := 'expiring_90days';
    ELSE
        NEW.status := 'active';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_electrical_status_update
BEFORE INSERT OR UPDATE ON electrical_compliance
FOR EACH ROW
EXECUTE FUNCTION update_electrical_certificate_status();

-- ============================================================================
-- Row Level Security (RLS) Policies
-- ============================================================================

-- Enable RLS on all compliance tables
ALTER TABLE compliance_checklist_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE compliance_audits ENABLE ROW LEVEL SECURITY;
ALTER TABLE fire_equipment_tracking ENABLE ROW LEVEL SECURITY;
ALTER TABLE emergency_light_testing ENABLE ROW LEVEL SECURITY;
ALTER TABLE legionella_risk_assessment ENABLE ROW LEVEL SECURITY;
ALTER TABLE electrical_compliance ENABLE ROW LEVEL SECURITY;
ALTER TABLE lift_inspection_tracking ENABLE ROW LEVEL SECURITY;

-- Policy: Read access for authenticated users (their buildings)
CREATE POLICY compliance_read_authenticated ON compliance_checklist_templates
    FOR SELECT USING (TRUE);

CREATE POLICY compliance_audits_read ON compliance_audits
    FOR SELECT USING (
        auth.jwt() ->> 'user_role' IN ('admin', 'operator', 'authenticated')
    );

CREATE POLICY fire_equipment_read ON fire_equipment_tracking
    FOR SELECT USING (
        auth.jwt() ->> 'user_role' IN ('admin', 'operator', 'authenticated')
    );

CREATE POLICY emergency_light_read ON emergency_light_testing
    FOR SELECT USING (
        auth.jwt() ->> 'user_role' IN ('admin', 'operator', 'authenticated')
    );

CREATE POLICY legionella_read ON legionella_risk_assessment
    FOR SELECT USING (
        auth.jwt() ->> 'user_role' IN ('admin', 'operator', 'authenticated')
    );

CREATE POLICY electrical_read ON electrical_compliance
    FOR SELECT USING (
        auth.jwt() ->> 'user_role' IN ('admin', 'operator', 'authenticated')
    );

CREATE POLICY lift_read ON lift_inspection_tracking
    FOR SELECT USING (
        auth.jwt() ->> 'user_role' IN ('admin', 'operator', 'authenticated')
    );

-- Policy: Write access for operators only
CREATE POLICY compliance_audits_write ON compliance_audits
    FOR INSERT WITH CHECK (
        auth.jwt() ->> 'user_role' = 'operator' OR auth.jwt() ->> 'user_role' = 'admin'
    );

CREATE POLICY fire_equipment_write ON fire_equipment_tracking
    FOR INSERT WITH CHECK (
        auth.jwt() ->> 'user_role' = 'operator' OR auth.jwt() ->> 'user_role' = 'admin'
    );

CREATE POLICY emergency_light_write ON emergency_light_testing
    FOR INSERT WITH CHECK (
        auth.jwt() ->> 'user_role' = 'operator' OR auth.jwt() ->> 'user_role' = 'admin'
    );

CREATE POLICY legionella_write ON legionella_risk_assessment
    FOR INSERT WITH CHECK (
        auth.jwt() ->> 'user_role' = 'operator' OR auth.jwt() ->> 'user_role' = 'admin'
    );

CREATE POLICY electrical_write ON electrical_compliance
    FOR INSERT WITH CHECK (
        auth.jwt() ->> 'user_role' = 'operator' OR auth.jwt() ->> 'user_role' = 'admin'
    );

CREATE POLICY lift_write ON lift_inspection_tracking
    FOR INSERT WITH CHECK (
        auth.jwt() ->> 'user_role' = 'operator' OR auth.jwt() ->> 'user_role' = 'admin'
    );

-- Policy: Update access for operators
CREATE POLICY compliance_audits_update ON compliance_audits
    FOR UPDATE USING (
        auth.jwt() ->> 'user_role' = 'operator' OR auth.jwt() ->> 'user_role' = 'admin'
    );

CREATE POLICY fire_equipment_update ON fire_equipment_tracking
    FOR UPDATE USING (
        auth.jwt() ->> 'user_role' = 'operator' OR auth.jwt() ->> 'user_role' = 'admin'
    );

CREATE POLICY emergency_light_update ON emergency_light_testing
    FOR UPDATE USING (
        auth.jwt() ->> 'user_role' = 'operator' OR auth.jwt() ->> 'user_role' = 'admin'
    );

CREATE POLICY legionella_update ON legionella_risk_assessment
    FOR UPDATE USING (
        auth.jwt() ->> 'user_role' = 'operator' OR auth.jwt() ->> 'user_role' = 'admin'
    );

CREATE POLICY electrical_update ON electrical_compliance
    FOR UPDATE USING (
        auth.jwt() ->> 'user_role' = 'operator' OR auth.jwt() ->> 'user_role' = 'admin'
    );

CREATE POLICY lift_update ON lift_inspection_tracking
    FOR UPDATE USING (
        auth.jwt() ->> 'user_role' = 'operator' OR auth.jwt() ->> 'user_role' = 'admin'
    );

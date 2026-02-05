-- ============================================================
-- SENSOR ANALYSIS SCHEMA (Phase 41-03)
-- ============================================================
-- Tables for storing phyphox sensor data, baselines, and anomalies.
-- Supports equipment condition monitoring and ML training.
--
-- Architecture:
-- - equipment_baselines: Reference values from onboarding/service
-- - sensor_recordings: Each phyphox data submission
-- - sensor_anomalies: Detected faults linked to recordings
-- - asset_run_reports: Base table for all asset types
-- - asset_ext_* tables: Asset-class specific extension tables
-- - health_score_weights: Configurable scoring weights
-- - asset_risk_multipliers: Risk factors for prioritization
--
-- Pattern: Base table + extension tables (like PostgreSQL inheritance)
-- ============================================================

-- Equipment baselines table (captured at onboarding/condition inspection)
CREATE TABLE IF NOT EXISTS equipment_baselines (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    equipment_id UUID NOT NULL REFERENCES equipment(id),

    -- Baseline metadata
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    captured_by TEXT,  -- Technician who captured baseline
    condition_at_capture VARCHAR(20) CHECK (condition_at_capture IN ('good', 'fair', 'poor', 'unknown')),
    notes TEXT,

    -- Vibration baseline (from Acceleration without g)
    vibration_rms_ms2 FLOAT,
    vibration_peak_frequencies_hz JSONB,  -- Array of dominant peaks
    vibration_peak_amplitudes JSONB,
    vibration_spectrum_shape VARCHAR(20),
    dominant_frequency_hz FLOAT,

    -- Audio baseline (from Audio Spectrum)
    audio_dominant_frequencies_hz JSONB,
    audio_noise_floor_db FLOAT,
    audio_spectrum_shape VARCHAR(20),

    -- Gyroscope baseline
    gyro_rms_rads FLOAT,
    gyro_stability VARCHAR(20),  -- 'stable', 'slight_wobble', 'unstable'

    -- Full extracted data for detailed comparison
    full_vibration_data JSONB,
    full_audio_data JSONB,
    full_gyro_data JSONB,

    -- Status
    is_active BOOLEAN NOT NULL DEFAULT true,  -- Only one active baseline per equipment
    superseded_by UUID REFERENCES equipment_baselines(id),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Only one active baseline per equipment
CREATE UNIQUE INDEX IF NOT EXISTS idx_equipment_baselines_active
    ON equipment_baselines(equipment_id)
    WHERE is_active = true;

CREATE INDEX IF NOT EXISTS idx_equipment_baselines_equipment ON equipment_baselines(equipment_id);

-- Sensor recordings table (phyphox data)
CREATE TABLE IF NOT EXISTS sensor_recordings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    equipment_id UUID NOT NULL REFERENCES equipment(id),
    service_record_id UUID REFERENCES service_records(id),

    -- Recording metadata
    measurement_type VARCHAR(20) NOT NULL CHECK (measurement_type IN ('vibration', 'audio', 'gyroscope')),
    source VARCHAR(20) NOT NULL CHECK (source IN ('screenshot', 'csv_export', 'json_export')),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- File storage
    file_path TEXT,  -- Path in Supabase storage
    file_size_bytes INTEGER,

    -- Extracted features (from phyphox)
    peak_frequencies_hz JSONB,  -- Array of peak frequencies
    peak_amplitudes JSONB,      -- Array of corresponding amplitudes
    dominant_frequency_hz FLOAT,
    dominant_amplitude FLOAT,
    rms_value FLOAT,
    spectrum_shape VARCHAR(20),

    -- Quality assessment
    quality_score INTEGER CHECK (quality_score BETWEEN 0 AND 100),
    quality_issues JSONB,
    confidence FLOAT CHECK (confidence BETWEEN 0 AND 1),

    -- Full extracted data
    extracted_data JSONB,

    -- Baseline comparison (auto-populated if baseline exists)
    baseline_id UUID REFERENCES equipment_baselines(id),
    baseline_comparison JSONB,  -- {"rms_change_pct": 25, "new_peaks": [...], "alerts": [...]}

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Sensor anomalies table
CREATE TABLE IF NOT EXISTS sensor_anomalies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sensor_recording_id UUID NOT NULL REFERENCES sensor_recordings(id),
    equipment_id UUID NOT NULL REFERENCES equipment(id),

    -- Anomaly details
    anomaly_type VARCHAR(50) NOT NULL,  -- 'bearing_defect', 'engine_knock', 'imbalance', etc.
    anomaly_subtype VARCHAR(50),        -- 'outer_race', 'inner_race', 'combustion', etc.
    confidence FLOAT NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),

    -- Detection details
    detected_frequency_hz FLOAT,
    detection_details JSONB,

    -- Recommendations
    recommendations JSONB,  -- Array of recommendation strings
    requires_followup BOOLEAN NOT NULL DEFAULT false,
    followup_created BOOLEAN NOT NULL DEFAULT false,
    followup_work_order_id UUID,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for sensor tables
CREATE INDEX IF NOT EXISTS idx_sensor_recordings_equipment ON sensor_recordings(equipment_id);
CREATE INDEX IF NOT EXISTS idx_sensor_recordings_service_record ON sensor_recordings(service_record_id);
CREATE INDEX IF NOT EXISTS idx_sensor_recordings_type ON sensor_recordings(measurement_type);
CREATE INDEX IF NOT EXISTS idx_sensor_recordings_created ON sensor_recordings(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_sensor_anomalies_equipment ON sensor_anomalies(equipment_id);
CREATE INDEX IF NOT EXISTS idx_sensor_anomalies_type ON sensor_anomalies(anomaly_type);
CREATE INDEX IF NOT EXISTS idx_sensor_anomalies_severity ON sensor_anomalies(severity);
CREATE INDEX IF NOT EXISTS idx_sensor_anomalies_followup ON sensor_anomalies(requires_followup) WHERE requires_followup = true;


-- ============================================================
-- UNIFIED ASSET HEALTH DATA MODEL
-- Base table + Extension tables per asset class
-- ============================================================

-- Asset run reports (BASE TABLE - same for every asset)
CREATE TABLE IF NOT EXISTS asset_run_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    equipment_id UUID NOT NULL REFERENCES equipment(id),
    site_id UUID REFERENCES buildings(id),

    -- Asset class determines which extension table to join
    asset_class VARCHAR(20) NOT NULL CHECK (asset_class IN (
        'generator', 'chiller', 'pump', 'ahu', 'cooling_tower',
        'ups', 'compressor', 'boiler', 'elevator'
    )),

    -- Test metadata
    test_datetime TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    technician_id TEXT,
    test_type VARCHAR(20) NOT NULL CHECK (test_type IN ('baseline', 'routine', 'post_repair')),
    phone_model TEXT,
    sensor_sample_rate_hz INTEGER,
    mounting_location TEXT,
    mounting_method VARCHAR(20) CHECK (mounting_method IN ('rigid', 'magnetic', 'clamp', 'handheld')),

    -- Operating context
    ambient_temp_c FLOAT,
    humidity_pct FLOAT,
    indoor_outdoor VARCHAR(10) CHECK (indoor_outdoor IN ('indoor', 'outdoor')),
    operating_mode VARCHAR(20) CHECK (operating_mode IN ('normal', 'peak', 'standby', 'startup', 'shutdown')),

    -- Run history
    total_run_hours FLOAT,
    hours_since_service FLOAT,
    starts_per_day FLOAT,
    known_alarms_since_service INTEGER,

    -- Sensor telemetry (auto from phyphox)
    sensor_recording_id UUID REFERENCES sensor_recordings(id),
    vibration_rms_x FLOAT,
    vibration_rms_y FLOAT,
    vibration_rms_z FLOAT,
    dominant_vib_freq_hz FLOAT,
    broadband_vib_level FLOAT,
    audio_rms FLOAT,
    dominant_audio_freq_hz FLOAT,
    audio_noise_floor FLOAT,
    frequency_variance FLOAT,

    -- Visual inspection flags (asset-specific in extension)
    visual_inspection JSONB,  -- {"oil_leak": true, "smoke": false, ...}

    -- Event flags (asset-specific in extension)
    event_flags JSONB,  -- {"failed_start": false, "alarm_active": true, ...}

    -- Maintenance context
    service_performed BOOLEAN DEFAULT false,
    parts_replaced JSONB,
    maintenance_notes TEXT,

    -- Outcome label (filled later by engineer for ML training)
    outcome_label VARCHAR(20) CHECK (outcome_label IN ('normal', 'watch', 'service_due', 'failed', 'false_alarm')),
    outcome_labeled_by TEXT,
    outcome_labeled_at TIMESTAMPTZ,

    -- Computed scores
    condition_score INTEGER CHECK (condition_score BETWEEN 0 AND 100),
    condition_grade VARCHAR(10) CHECK (condition_grade IN ('good', 'fair', 'poor', 'critical')),
    risk_score FLOAT,

    -- Baseline reference
    baseline_id UUID REFERENCES equipment_baselines(id),
    baseline_deviation_pct FLOAT,

    -- Data quality
    mounting_changed BOOLEAN DEFAULT false,  -- Tag if mounting differs from baseline

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_asset_run_reports_equipment ON asset_run_reports(equipment_id);
CREATE INDEX IF NOT EXISTS idx_asset_run_reports_class ON asset_run_reports(asset_class);
CREATE INDEX IF NOT EXISTS idx_asset_run_reports_date ON asset_run_reports(test_datetime DESC);
CREATE INDEX IF NOT EXISTS idx_asset_run_reports_outcome ON asset_run_reports(outcome_label) WHERE outcome_label IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_asset_run_reports_grade ON asset_run_reports(condition_grade);
CREATE INDEX IF NOT EXISTS idx_asset_run_reports_test_type ON asset_run_reports(test_type);


-- ============================================================
-- EXTENSION TABLES (asset-specific fields only)
-- ============================================================

-- Generator extension
CREATE TABLE IF NOT EXISTS asset_ext_generator (
    run_report_id UUID PRIMARY KEY REFERENCES asset_run_reports(id) ON DELETE CASCADE,
    load_pct FLOAT,
    rpm FLOAT,
    coolant_temp_c FLOAT,
    oil_temp_c FLOAT,
    oil_pressure_bar FLOAT,
    fuel_rate_lph FLOAT,
    exhaust_temp_c FLOAT,
    load_profile JSONB  -- [{load_pct, kw, kva, pf, duration_s}, ...]
);

-- Chiller extension
CREATE TABLE IF NOT EXISTS asset_ext_chiller (
    run_report_id UUID PRIMARY KEY REFERENCES asset_run_reports(id) ON DELETE CASCADE,
    chiller_type VARCHAR(20) CHECK (chiller_type IN ('air_cooled', 'water_cooled')),
    compressor_type VARCHAR(20) CHECK (compressor_type IN ('screw', 'scroll', 'centrifugal', 'reciprocating')),
    refrigerant_type VARCHAR(20),
    cooling_load_pct FLOAT,
    kw_input FLOAT,
    chw_supply_temp_c FLOAT,
    chw_return_temp_c FLOAT,
    delta_t_c FLOAT,
    chw_flow_rate FLOAT,
    suction_pressure FLOAT,
    discharge_pressure FLOAT,
    oil_pressure FLOAT,
    oil_temp_c FLOAT,
    superheat FLOAT,
    condenser_entering_temp_c FLOAT
);

-- Pump extension
CREATE TABLE IF NOT EXISTS asset_ext_pump (
    run_report_id UUID PRIMARY KEY REFERENCES asset_run_reports(id) ON DELETE CASCADE,
    flow_rate FLOAT,
    differential_pressure FLOAT,
    motor_current FLOAT,
    vfd_speed_pct FLOAT
);

-- AHU extension
CREATE TABLE IF NOT EXISTS asset_ext_ahu (
    run_report_id UUID PRIMARY KEY REFERENCES asset_run_reports(id) ON DELETE CASCADE,
    fan_speed_pct FLOAT,
    supply_air_temp_c FLOAT,
    return_air_temp_c FLOAT,
    filter_condition VARCHAR(20) CHECK (filter_condition IN ('clean', 'dirty', 'blocked', 'unknown'))
);

-- Cooling tower extension
CREATE TABLE IF NOT EXISTS asset_ext_cooling_tower (
    run_report_id UUID PRIMARY KEY REFERENCES asset_run_reports(id) ON DELETE CASCADE,
    fan_speed_pct FLOAT,
    motor_current FLOAT,
    basin_water_temp_c FLOAT,
    wet_bulb_estimate_c FLOAT
);

-- UPS extension
CREATE TABLE IF NOT EXISTS asset_ext_ups (
    run_report_id UUID PRIMARY KEY REFERENCES asset_run_reports(id) ON DELETE CASCADE,
    load_pct FLOAT,
    internal_temp_c FLOAT,
    battery_string_temps JSONB  -- Array of temps per string
);

-- Compressor extension (air compressor)
CREATE TABLE IF NOT EXISTS asset_ext_compressor (
    run_report_id UUID PRIMARY KEY REFERENCES asset_run_reports(id) ON DELETE CASCADE,
    discharge_pressure FLOAT,
    duty_cycle_pct FLOAT,
    load_unload_count INTEGER
);

-- Boiler extension
CREATE TABLE IF NOT EXISTS asset_ext_boiler (
    run_report_id UUID PRIMARY KEY REFERENCES asset_run_reports(id) ON DELETE CASCADE,
    supply_temp_c FLOAT,
    return_temp_c FLOAT,
    pressure_bar FLOAT,
    burner_modulation_pct FLOAT
);

-- Elevator extension
CREATE TABLE IF NOT EXISTS asset_ext_elevator (
    run_report_id UUID PRIMARY KEY REFERENCES asset_run_reports(id) ON DELETE CASCADE,
    speed_stability_metric FLOAT,
    starts_per_hour FLOAT
);


-- ============================================================
-- HEALTH SCORING CONFIGURATION
-- ============================================================

-- Asset class health weights (configurable by engineers)
CREATE TABLE IF NOT EXISTS health_score_weights (
    asset_class VARCHAR(20) PRIMARY KEY,
    mechanical_weight FLOAT NOT NULL DEFAULT 0.4,
    thermal_weight FLOAT NOT NULL DEFAULT 0.3,
    electrical_weight FLOAT NOT NULL DEFAULT 0.2,
    reliability_weight FLOAT NOT NULL DEFAULT 0.1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT
);

-- Insert default weights
INSERT INTO health_score_weights (asset_class, mechanical_weight, thermal_weight, electrical_weight, reliability_weight) VALUES
    ('generator', 0.40, 0.20, 0.20, 0.20),
    ('chiller', 0.30, 0.40, 0.20, 0.10),
    ('pump', 0.50, 0.30, 0.20, 0.00),
    ('ahu', 0.40, 0.40, 0.20, 0.00),
    ('cooling_tower', 0.40, 0.30, 0.20, 0.10),
    ('ups', 0.20, 0.30, 0.30, 0.20),
    ('compressor', 0.50, 0.20, 0.20, 0.10),
    ('boiler', 0.30, 0.50, 0.10, 0.10),
    ('elevator', 0.60, 0.10, 0.20, 0.10)
ON CONFLICT (asset_class) DO NOTHING;

-- Asset risk multipliers (for prioritization)
CREATE TABLE IF NOT EXISTS asset_risk_multipliers (
    equipment_id UUID PRIMARY KEY REFERENCES equipment(id),
    downtime_cost_factor FLOAT NOT NULL DEFAULT 1.0,
    redundancy_factor FLOAT NOT NULL DEFAULT 1.0,  -- 1.0 = no backup, 0.5 = N+1
    lead_time_factor FLOAT NOT NULL DEFAULT 1.0,   -- Higher = harder to get parts
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ============================================================
-- VIEWS
-- ============================================================

-- View for equipment anomaly summary
CREATE OR REPLACE VIEW v_equipment_anomaly_summary AS
SELECT
    e.id AS equipment_id,
    e.name AS equipment_name,
    e.type AS equipment_type,
    COUNT(DISTINCT sr.id) AS total_recordings,
    COUNT(DISTINCT sa.id) AS total_anomalies,
    COUNT(DISTINCT sa.id) FILTER (WHERE sa.severity IN ('high', 'critical')) AS critical_anomalies,
    MAX(sa.created_at) AS last_anomaly_date,
    AVG(sa.confidence) AS avg_anomaly_confidence
FROM equipment e
LEFT JOIN sensor_recordings sr ON e.id = sr.equipment_id
LEFT JOIN sensor_anomalies sa ON e.id = sa.equipment_id
GROUP BY e.id, e.name, e.type;

-- View for latest condition by equipment
CREATE OR REPLACE VIEW v_equipment_latest_condition AS
SELECT DISTINCT ON (equipment_id)
    equipment_id,
    condition_score,
    condition_grade,
    risk_score,
    test_datetime,
    test_type,
    asset_class
FROM asset_run_reports
ORDER BY equipment_id, test_datetime DESC;

-- View for equipment requiring attention
CREATE OR REPLACE VIEW v_equipment_attention_required AS
SELECT
    arr.equipment_id,
    e.name AS equipment_name,
    e.type AS equipment_type,
    arr.condition_score,
    arr.condition_grade,
    arr.test_datetime AS last_test,
    arr.outcome_label,
    CASE
        WHEN arr.condition_grade = 'critical' THEN 'ACT NOW'
        WHEN arr.condition_grade = 'poor' THEN 'PLAN SERVICE'
        WHEN arr.condition_grade = 'fair' THEN 'WATCH'
        ELSE 'RUN'
    END AS action_required
FROM asset_run_reports arr
JOIN equipment e ON arr.equipment_id = e.id
WHERE arr.test_datetime = (
    SELECT MAX(test_datetime)
    FROM asset_run_reports
    WHERE equipment_id = arr.equipment_id
)
AND arr.condition_grade IN ('fair', 'poor', 'critical')
ORDER BY
    CASE arr.condition_grade
        WHEN 'critical' THEN 1
        WHEN 'poor' THEN 2
        WHEN 'fair' THEN 3
        ELSE 4
    END,
    arr.test_datetime DESC;


-- ============================================================
-- COMMENTS
-- ============================================================

COMMENT ON TABLE equipment_baselines IS 'Reference sensor readings captured at onboarding or after service';
COMMENT ON TABLE sensor_recordings IS 'Individual phyphox data submissions (screenshots or exports)';
COMMENT ON TABLE sensor_anomalies IS 'Detected equipment faults linked to recordings';
COMMENT ON TABLE asset_run_reports IS 'Base table for asset health data - join with asset_ext_* for full data';
COMMENT ON TABLE health_score_weights IS 'Configurable weights for health score calculation per asset class';
COMMENT ON TABLE asset_risk_multipliers IS 'Risk factors for prioritizing maintenance actions';

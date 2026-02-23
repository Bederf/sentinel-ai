-- Migration 110: Site modules and cross-module links tables
-- Moves site module configuration and cross-module integration links
-- from JSON (site_modules.json) to Supabase as source of truth.

-- ============================================================
-- Table: site_modules
-- Stores per-site module instances (each activated module)
-- ============================================================
CREATE TABLE IF NOT EXISTS site_modules (
    instance_id     TEXT PRIMARY KEY,
    site_id         TEXT NOT NULL,
    module_type     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',
    activated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    config          JSONB NOT NULL DEFAULT '{}',
    health_score    REAL NOT NULL DEFAULT 100.0,
    last_telemetry  TIMESTAMPTZ,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_site_modules_site_id ON site_modules(site_id);
CREATE INDEX IF NOT EXISTS idx_site_modules_module_type ON site_modules(module_type);
CREATE UNIQUE INDEX IF NOT EXISTS idx_site_modules_site_type ON site_modules(site_id, module_type)
    WHERE status = 'active';

-- ============================================================
-- Table: cross_module_links
-- Defines integration bridges between modules on a site
-- ============================================================
CREATE TABLE IF NOT EXISTS cross_module_links (
    link_id             TEXT PRIMARY KEY,
    site_id             TEXT NOT NULL,
    source_module       TEXT NOT NULL,
    target_module       TEXT NOT NULL,
    integration_type    TEXT NOT NULL,
    enabled             BOOLEAN NOT NULL DEFAULT FALSE,
    config              JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cross_module_links_site_id ON cross_module_links(site_id);
CREATE INDEX IF NOT EXISTS idx_cross_module_links_enabled ON cross_module_links(site_id, enabled)
    WHERE enabled = TRUE;

-- ============================================================
-- Table: site_module_configs
-- Top-level site configuration flags (ai_enabled, auto_integration)
-- ============================================================
CREATE TABLE IF NOT EXISTS site_module_configs (
    site_id             TEXT PRIMARY KEY,
    site_name           TEXT NOT NULL,
    ai_enabled          BOOLEAN NOT NULL DEFAULT TRUE,
    auto_integration    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Seed: site-002 config
-- ============================================================
INSERT INTO site_module_configs (site_id, site_name, ai_enabled, auto_integration)
VALUES ('site-002', 'Sandton Data Centre', TRUE, TRUE)
ON CONFLICT (site_id) DO NOTHING;

-- ============================================================
-- Seed: site-002 active modules
-- ============================================================
INSERT INTO site_modules (instance_id, site_id, module_type, status, activated_at, config, health_score) VALUES
    ('sandton-control-001', 'site-002', 'control', 'active', '2025-01-15T08:00:00Z', '{"remote_control":true,"audit_logging":true,"safety_interlocks":true}', 100.0),
    ('sandton-assets-001', 'site-002', 'assets', 'active', '2025-01-15T08:00:00Z', '{"lifecycle_management":true,"baseline_assessment":true,"inspection_scheduling":true}', 100.0),
    ('sandton-simbiot-001', 'site-002', 'simbiot', 'active', '2025-01-15T08:00:00Z', '{"onboarding_wizard":true,"auto_discovery":true,"point_mapping":true}', 100.0),
    ('sandton-integrations-001', 'site-002', 'integrations', 'active', '2025-01-15T08:00:00Z', '{"bms_health_monitoring":true,"sync_tracking":true,"data_quality":true}', 100.0),
    ('sandton-notifications-001', 'site-002', 'notifications', 'active', '2025-01-15T08:00:00Z', '{"telegram":true,"email":false,"sms":false,"alert_cooldown_minutes":5}', 100.0),
    ('sandton-contracts-001', 'site-002', 'contracts', 'active', '2026-02-06T12:00:00Z', '{"sla_tracking":true,"budget_management":true,"profitability_analysis":true}', 98.0),
    ('sandton-energy-001', 'site-002', 'energy', 'active', '2025-01-15T08:00:00Z', '{"generator_scada":true,"ats_monitoring":true,"power_metering":true,"ups_monitoring":true,"predictive_maintenance":true}', 95.0),
    ('sandton-lighting-001', 'site-002', 'lighting', 'active', '2025-01-15T08:00:00Z', '{"dali_control":true,"scene_management":true,"daylight_harvesting":true}', 98.0),
    ('sandton-hvac-76e04af6', 'site-002', 'hvac', 'active', '2026-01-31T10:34:37.244925', '{}', 100.0),
    ('sandton-solar-001', 'site-002', 'solar', 'active', '2026-02-06T10:00:00Z', '{"ingestion_mode":"standalone","manufacturers":["huawei","schneider"],"bess_enabled":true,"compliance_monitoring":true,"tariff_type":"tou"}', 92.0),
    ('sandton-security-001', 'site-002', 'security', 'active', '2026-02-06T12:00:00Z', '{"access_control":true,"cctv_integration":true,"occupancy_tracking":true,"zone_management":true,"sellable":true,"display_name":"Security & Access Control","icon":"Shield","price_usd":500,"billing_frequency":"monthly","includes":["Access control monitoring","Real-time occupancy tracking","CCTV integration","Breach alerts","Occupancy-based automation triggers"],"integrations":[{"requires":["hvac"],"provides":"occupancy_data","feature":"Occupancy-based HVAC optimization"},{"requires":["lighting"],"provides":"occupancy_data","feature":"Occupancy-based lighting control"}],"dashboard_route":"/security","api_prefix":"/api/security"}', 96.0),
    ('sandton-sustainability-001', 'site-002', 'sustainability', 'active', '2026-02-06T12:00:00Z', '{"carbon_tracking":true,"water_monitoring":true,"waste_management":true,"esg_reporting":true,"green_building_certification":true}', 94.0),
    ('sandton-water-001', 'site-002', 'water', 'active', '2026-02-07T10:00:00Z', '{"leak_detection":true,"consumption_monitoring":true,"trending_analysis":true,"polling_interval_seconds":60}', 100.0),
    ('sandton-ml-001', 'site-002', 'ml', 'active', '2026-02-06T12:00:00Z', '{"lstm_predictions":true,"anomaly_detection":true,"fleet_analytics":true,"model_monitoring":true}', 97.0),
    ('site-002-fire-bff0cc50', 'site-002', 'fire', 'active', '2026-02-13T12:30:24.242686', '{}', 100.0),
    ('site-002-access-f579727d', 'site-002', 'access', 'active', '2026-02-13T12:30:30.133675', '{}', 100.0),
    ('site-002-kpi-24299fc1', 'site-002', 'kpi', 'active', '2026-02-22T06:11:46.394177', '{}', 100.0),
    ('site-002-maintenance-b3fe1d5b', 'site-002', 'maintenance', 'active', '2026-02-22T06:11:59.790086', '{}', 100.0),
    ('site-002-digital_twin-b58ec3a1', 'site-002', 'digital_twin', 'active', '2026-02-22T06:12:24.646186', '{}', 100.0)
ON CONFLICT (instance_id) DO NOTHING;

-- ============================================================
-- Seed: site-002 cross-module links
-- ============================================================
INSERT INTO cross_module_links (link_id, site_id, source_module, target_module, integration_type, enabled, config) VALUES
    ('sandton-energy_lighting_loadshed', 'site-002', 'energy', 'lighting', 'energy_lighting_loadshed', FALSE, '{}'),
    ('sandton-hvac_energy_loadshed', 'site-002', 'energy', 'hvac', 'hvac_energy_loadshed', FALSE, '{}'),
    ('sandton-hvac_energy_demand', 'site-002', 'energy', 'hvac', 'hvac_energy_demand', FALSE, '{}'),
    ('sandton-energy_solar_generation', 'site-002', 'solar', 'energy', 'energy_solar_generation', FALSE, '{}'),
    ('sandton-solar_generator_coordination', 'site-002', 'solar', 'energy', 'solar_generator_coordination', FALSE, '{}'),
    ('sandton-security_hvac_occupancy', 'site-002', 'security', 'hvac', 'security_hvac_occupancy', TRUE, '{"source":"dali_pir","bridge":"SENTINEL","min_occupancy_threshold_pct":10,"unoccupied_setpoint_offset_c":2.0,"unoccupied_damper_min_pct":15}'),
    ('sandton-security_lighting_occupancy', 'site-002', 'security', 'lighting', 'security_lighting_occupancy', TRUE, '{"source":"dali_pir","bridge":"SENTINEL","unoccupied_brightness_pct":20}'),
    ('sandton-ml_hvac_predictive', 'site-002', 'ml', 'hvac', 'ml_hvac_predictive', FALSE, '{}'),
    ('sandton-ml_energy_anomaly', 'site-002', 'ml', 'energy', 'ml_energy_anomaly', FALSE, '{}'),
    ('sandton-sustainability_energy_carbon', 'site-002', 'sustainability', 'energy', 'sustainability_energy_carbon', FALSE, '{}'),
    ('sandton-sustainability_solar_green', 'site-002', 'sustainability', 'solar', 'sustainability_solar_green', FALSE, '{}'),
    ('sandton-sustainability_water', 'site-002', 'sustainability', 'water', 'sustainability_water_monitoring', FALSE, '{}')
ON CONFLICT (link_id) DO UPDATE SET
    enabled = EXCLUDED.enabled,
    config = EXCLUDED.config,
    updated_at = NOW();

-- ============================================================
-- Seed: S002 (Sandton City) config
-- ============================================================
INSERT INTO site_module_configs (site_id, site_name, ai_enabled, auto_integration)
VALUES ('S002', 'Sandton City', TRUE, TRUE)
ON CONFLICT (site_id) DO NOTHING;

INSERT INTO site_modules (instance_id, site_id, module_type, status, activated_at, config, health_score)
VALUES ('S002-solar-d0e8b15e', 'S002', 'solar', 'active', '2026-02-12T17:18:01.876776', '{}', 100.0)
ON CONFLICT (instance_id) DO NOTHING;

-- ============================================================
-- RLS policies
-- ============================================================
ALTER TABLE site_modules ENABLE ROW LEVEL SECURITY;
ALTER TABLE cross_module_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE site_module_configs ENABLE ROW LEVEL SECURITY;

-- Service role has full access
CREATE POLICY "service_role_full_access_site_modules" ON site_modules
    FOR ALL USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "service_role_full_access_cross_module_links" ON cross_module_links
    FOR ALL USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "service_role_full_access_site_module_configs" ON site_module_configs
    FOR ALL USING (TRUE) WITH CHECK (TRUE);

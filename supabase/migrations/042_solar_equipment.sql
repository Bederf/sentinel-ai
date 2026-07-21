-- =============================================================================
-- Migration 043: Solar PV & BESS Equipment Schema
-- Phase 34-01: Solar ingestion engine data foundation
-- =============================================================================

-- Solar plants (L1 in hierarchy)
CREATE TABLE IF NOT EXISTS solar_plants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plant_id TEXT UNIQUE NOT NULL,
    site_id UUID REFERENCES buildings(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    capacity_kwp NUMERIC NOT NULL DEFAULT 0,
    panel_count INTEGER NOT NULL DEFAULT 0,
    inverter_count INTEGER NOT NULL DEFAULT 0,
    panel_model TEXT,
    panel_rating_w NUMERIC DEFAULT 0,
    commissioning_date DATE,
    latitude NUMERIC DEFAULT -26.2,
    longitude NUMERIC DEFAULT 28.0,
    orientation NUMERIC DEFAULT 0,
    tilt NUMERIC DEFAULT 20,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Solar inverters (L3 in hierarchy)
CREATE TABLE IF NOT EXISTS solar_inverters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inverter_id TEXT UNIQUE NOT NULL,
    plant_id TEXT REFERENCES solar_plants(plant_id) ON DELETE CASCADE,
    site_id UUID REFERENCES buildings(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    manufacturer TEXT NOT NULL,
    model TEXT NOT NULL,
    serial TEXT,
    rated_power_kva NUMERIC NOT NULL DEFAULT 0,
    mppt_count INTEGER DEFAULT 1,
    firmware_version TEXT,
    protocol TEXT DEFAULT 'modbus_tcp',
    ip_address TEXT,
    port INTEGER DEFAULT 502,
    unit_id INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- BESS containers (L5 in hierarchy)
CREATE TABLE IF NOT EXISTS bess_containers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    container_id TEXT UNIQUE NOT NULL,
    site_id UUID REFERENCES buildings(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    manufacturer TEXT NOT NULL,
    model TEXT NOT NULL,
    capacity_kwh NUMERIC NOT NULL DEFAULT 0,
    rated_power_kw NUMERIC NOT NULL DEFAULT 0,
    rack_count INTEGER DEFAULT 1,
    cell_chemistry TEXT DEFAULT 'LFP',
    protocol TEXT DEFAULT 'modbus_tcp',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Solar readings (normalised time-series data)
CREATE TABLE IF NOT EXISTS solar_readings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    equipment_id UUID NOT NULL,
    equipment_type TEXT NOT NULL CHECK (equipment_type IN (
        'inverter', 'bess', 'meter', 'string', 'plant'
    )),
    reading_type TEXT NOT NULL CHECK (reading_type IN (
        'power', 'energy', 'voltage', 'current', 'temperature',
        'soc', 'irradiance', 'frequency', 'power_factor', 'thd'
    )),
    value NUMERIC NOT NULL,
    unit TEXT NOT NULL,
    quality_flag TEXT NOT NULL DEFAULT 'good' CHECK (quality_flag IN (
        'good', 'stale', 'interpolated', 'suspect'
    )),
    source TEXT NOT NULL DEFAULT 'modbus' CHECK (source IN (
        'modbus', 'cloud_api', 'bms', 'simulated'
    )),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- BRIN index on timestamp for efficient time-range queries on solar_readings
CREATE INDEX IF NOT EXISTS idx_solar_readings_timestamp
    ON solar_readings USING BRIN (timestamp);

-- B-tree indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_solar_readings_equipment
    ON solar_readings (equipment_id, equipment_type);

CREATE INDEX IF NOT EXISTS idx_solar_readings_type
    ON solar_readings (reading_type, timestamp);

CREATE INDEX IF NOT EXISTS idx_solar_inverters_plant
    ON solar_inverters (plant_id);

CREATE INDEX IF NOT EXISTS idx_solar_inverters_site
    ON solar_inverters (site_id);

CREATE INDEX IF NOT EXISTS idx_solar_plants_site
    ON solar_plants (site_id);

CREATE INDEX IF NOT EXISTS idx_bess_containers_site
    ON bess_containers (site_id);


-- =============================================================================
-- Row Level Security
-- =============================================================================

ALTER TABLE solar_plants ENABLE ROW LEVEL SECURITY;
ALTER TABLE solar_inverters ENABLE ROW LEVEL SECURITY;
ALTER TABLE bess_containers ENABLE ROW LEVEL SECURITY;
ALTER TABLE solar_readings ENABLE ROW LEVEL SECURITY;

-- Service role: full access
CREATE POLICY solar_plants_service_all ON solar_plants
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY solar_inverters_service_all ON solar_inverters
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY bess_containers_service_all ON bess_containers
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY solar_readings_service_all ON solar_readings
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Authenticated users: read access
CREATE POLICY solar_plants_auth_read ON solar_plants
    FOR SELECT TO authenticated USING (true);

CREATE POLICY solar_inverters_auth_read ON solar_inverters
    FOR SELECT TO authenticated USING (true);

CREATE POLICY bess_containers_auth_read ON bess_containers
    FOR SELECT TO authenticated USING (true);

CREATE POLICY solar_readings_auth_read ON solar_readings
    FOR SELECT TO authenticated USING (true);

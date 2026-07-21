-- Phase 178-01: MRI Evolution Connector Schema
-- Canonical job card store for MRI Evolution / SENTINEL Maintenance Connector

-- Canonical job card store
CREATE TABLE IF NOT EXISTS maintenance_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    external_ref TEXT UNIQUE NOT NULL,        -- e.g. "FNBFW:30453"
    source_system TEXT NOT NULL DEFAULT 'mri_evolution',
    site_id UUID REFERENCES sites(id),
    org_id UUID,
    building TEXT,
    location TEXT,
    discipline TEXT,
    problem TEXT,
    priority_raw TEXT,                         -- as received from MRI: "Critical", "Routine" etc
    priority_normalised TEXT CHECK (priority_normalised IN ('P1','P2','P3','P4')),
    sla_respond_hours INTEGER,
    sla_attend_hours INTEGER,
    sla_temp_fix_hours INTEGER,
    sla_resolve_work_days INTEGER,
    is_ppm BOOLEAN DEFAULT FALSE,
    status TEXT,                               -- "ACTIVE", "ASSIGNED", "HISTORY", "CANCELLED"
    created_at_source TIMESTAMPTZ,             -- T=0 SLA clock
    assigned_at TIMESTAMPTZ,                   -- T1
    attended_at TIMESTAMPTZ,                   -- T2
    temp_fixed_at TIMESTAMPTZ,                 -- T3
    resolved_at TIMESTAMPTZ,                   -- T4
    level_of_completion TEXT,
    sla_pct NUMERIC(5,2),
    days_open INTEGER,
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    last_synced_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- SLA breach tracking
CREATE TABLE IF NOT EXISTS sla_breach_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    maintenance_event_id UUID REFERENCES maintenance_events(id),
    breach_type TEXT CHECK (breach_type IN ('respond','attend','temp_fix','resolve')),
    breached_at TIMESTAMPTZ DEFAULT NOW(),
    sla_threshold_hours INTEGER,
    actual_hours NUMERIC,
    notified BOOLEAN DEFAULT FALSE
);

-- Connector sync state (one row per adapter per site)
CREATE TABLE IF NOT EXISTS maintenance_connector_sync (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    adapter_source TEXT NOT NULL,               -- e.g. 'mri_evolution', 'servicenow'
    site_id UUID REFERENCES sites(id),
    last_successful_sync TIMESTAMPTZ,
    last_sync_attempted TIMESTAMPTZ,
    records_ingested INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    UNIQUE (adapter_source, site_id)
);

CREATE INDEX IF NOT EXISTS idx_maintenance_events_site ON maintenance_events(site_id);
CREATE INDEX IF NOT EXISTS idx_maintenance_events_status ON maintenance_events(status);
CREATE INDEX IF NOT EXISTS idx_maintenance_events_priority ON maintenance_events(priority_normalised);
CREATE INDEX IF NOT EXISTS idx_maintenance_events_created ON maintenance_events(created_at_source);

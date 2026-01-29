-- =====================================================
-- Migration 010: Integration Schema
-- SENTINEL overlay architecture - ingest from existing systems
-- =====================================================

-- Log sources configuration (where we get BMS/alarm data)
CREATE TABLE log_sources (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  building_id UUID REFERENCES buildings(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  source_type TEXT NOT NULL CHECK (source_type IN ('bms_alarm', 'bms_trend', 'cafm_asset', 'cafm_workorder', 'bcc_alarm')),

  -- Connection method
  connection_type TEXT NOT NULL CHECK (connection_type IN ('file_drop', 'sftp', 'database', 'api', 'manual_upload')),

  -- File-based sources
  file_pattern TEXT,  -- e.g., "AlarmLog_*.csv"
  folder_path TEXT,   -- e.g., "\\server\bms_exports\theplace\"

  -- Database sources
  connection_string TEXT,
  db_table TEXT,
  db_query TEXT,

  -- API sources
  api_endpoint TEXT,
  api_key_encrypted TEXT,

  -- Format detection
  file_format TEXT CHECK (file_format IN ('csv', 'excel', 'json', 'xml')),
  delimiter TEXT DEFAULT ',',
  date_format TEXT DEFAULT 'YYYY-MM-DD HH:MI:SS',
  timezone TEXT DEFAULT 'Africa/Johannesburg',
  vendor_pattern TEXT,  -- Detected: 'honeywell', 'siemens', 'jci', 'schneider', etc.

  -- Sync settings
  sync_frequency_minutes INTEGER DEFAULT 15,
  last_sync_at TIMESTAMPTZ,
  last_sync_status TEXT CHECK (last_sync_status IN ('success', 'partial', 'failed')),
  last_sync_records INTEGER,
  last_sync_error TEXT,

  -- Status
  is_active BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_log_sources_building ON log_sources(building_id);
CREATE INDEX idx_log_sources_type ON log_sources(source_type);
CREATE INDEX idx_log_sources_active ON log_sources(is_active) WHERE is_active = TRUE;

CREATE TRIGGER update_log_sources_updated_at BEFORE UPDATE ON log_sources
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Column mappings (map source columns to SENTINEL fields)
CREATE TABLE column_mappings (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  log_source_id UUID NOT NULL REFERENCES log_sources(id) ON DELETE CASCADE,

  source_column TEXT NOT NULL,        -- Column name in source file
  sentinel_field TEXT NOT NULL,       -- SENTINEL standard field
  transform TEXT,                      -- Optional transform: 'uppercase', 'parse_date', 'extract_asset', etc.
  transform_params JSONB,              -- Parameters for transform

  created_at TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(log_source_id, sentinel_field)
);

CREATE INDEX idx_column_mappings_source ON column_mappings(log_source_id);

-- Standard SENTINEL fields for alarms:
-- timestamp, point_id, alarm_code, description, value, threshold, severity, state, acknowledged_by, notes
-- Standard SENTINEL fields for trends:
-- timestamp, point_id, value, unit, quality

-- Point to asset mappings (link BMS points to CAFM assets)
CREATE TABLE point_asset_mappings (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,

  bms_point_id TEXT NOT NULL,         -- Raw point ID from BMS: "NAE01/AHU-L12-001.SAT"
  extracted_asset_id TEXT,            -- Extracted: "AHU-L12-001"
  cafm_asset_id TEXT,                 -- Matched CAFM asset tag
  cafm_asset_uuid UUID,               -- If we have UUID reference

  parameter_name TEXT,                -- Extracted parameter: "SAT" (Supply Air Temp)
  parameter_type TEXT,                -- Classified: 'temperature', 'pressure', 'status', etc.

  match_confidence TEXT CHECK (match_confidence IN ('exact', 'fuzzy', 'manual', 'unmatched')),
  is_verified BOOLEAN DEFAULT FALSE,  -- Human verified the match

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(building_id, bms_point_id)
);

CREATE INDEX idx_point_mappings_building ON point_asset_mappings(building_id);
CREATE INDEX idx_point_mappings_asset ON point_asset_mappings(cafm_asset_id);
CREATE INDEX idx_point_mappings_unmatched ON point_asset_mappings(match_confidence)
  WHERE match_confidence = 'unmatched';

CREATE TRIGGER update_point_asset_mappings_updated_at BEFORE UPDATE ON point_asset_mappings
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Alarm code mappings (normalize vendor codes to SENTINEL taxonomy)
CREATE TABLE alarm_code_mappings (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  log_source_id UUID REFERENCES log_sources(id) ON DELETE CASCADE,

  source_code TEXT NOT NULL,          -- Vendor alarm code: "HIGH", "HI_LIMIT", "OT"
  sentinel_code TEXT NOT NULL,        -- SENTINEL standard: "TEMP-HI"
  sentinel_category TEXT,             -- Category: "temperature", "pressure", "equipment"

  created_at TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(log_source_id, source_code)
);

-- Default alarm code taxonomy (global, not per-source)
CREATE TABLE alarm_taxonomy (
  code TEXT PRIMARY KEY,              -- "TEMP-HI"
  description TEXT NOT NULL,          -- "High temperature"
  category TEXT NOT NULL,             -- "temperature"
  default_severity TEXT,              -- "high"
  common_source_codes TEXT[]          -- Array of common vendor codes that map here
);

-- Seed standard taxonomy
INSERT INTO alarm_taxonomy (code, description, category, default_severity, common_source_codes) VALUES
  ('TEMP-HI', 'High temperature', 'temperature', 'high', ARRAY['HIGH', 'HI_LIMIT', 'TEMP_HIGH', 'OT', 'HIGH_LIMIT']),
  ('TEMP-LO', 'Low temperature', 'temperature', 'medium', ARRAY['LOW', 'LO_LIMIT', 'TEMP_LOW', 'UT', 'LOW_LIMIT']),
  ('TEMP-FAIL', 'Temperature sensor failure', 'temperature', 'high', ARRAY['FAIL', 'SENSOR_FAULT', 'BAD_INPUT']),
  ('PRESS-HI', 'High pressure', 'pressure', 'high', ARRAY['HI_PRESS', 'PRESSURE_HIGH', 'HP']),
  ('PRESS-LO', 'Low pressure', 'pressure', 'critical', ARRAY['LO_PRESS', 'PRESSURE_LOW', 'LP']),
  ('FLOW-HI', 'High flow', 'flow', 'medium', ARRAY['HI_FLOW', 'FLOW_HIGH']),
  ('FLOW-LO', 'Low/no flow', 'flow', 'high', ARRAY['LO_FLOW', 'FLOW_LOW', 'NO_FLOW']),
  ('VIB-HI', 'High vibration', 'vibration', 'high', ARRAY['VIB_ALARM', 'VIBRATION', 'VIB']),
  ('VIB-CRIT', 'Critical vibration', 'vibration', 'critical', ARRAY['VIB_TRIP', 'VIB_CRITICAL']),
  ('CURR-HI', 'High current/overload', 'electrical', 'high', ARRAY['OVERLOAD', 'OL', 'OVERCURRENT']),
  ('TRIP', 'Equipment trip', 'equipment', 'critical', ARRAY['TRIP', 'TRIPPED', 'FAULT']),
  ('START-FAIL', 'Failed to start', 'equipment', 'critical', ARRAY['FAIL_START', 'NO_START', 'FSF']),
  ('COMM-FAIL', 'Communication failure', 'communication', 'high', ARRAY['OFFLINE', 'COMM_LOSS', 'NO_COMMS']),
  ('MAINT-DUE', 'Maintenance due', 'maintenance', 'low', ARRAY['SERVICE', 'PPM_DUE', 'MAINT']),
  ('GEN-RUN', 'Generator running', 'power', 'medium', ARRAY['GEN_ON', 'RUNNING', 'ON_GEN']),
  ('GEN-FAIL', 'Generator failure', 'power', 'critical', ARRAY['GEN_FAULT', 'GEN_FAIL']),
  ('MAINS-FAIL', 'Mains power failure', 'power', 'critical', ARRAY['POWER_FAIL', 'UTILITY_FAIL']),
  ('FIRE', 'Fire alarm', 'life_safety', 'critical', ARRAY['FIRE', 'FA', 'SMOKE']);

-- Severity mapping table
CREATE TABLE severity_mappings (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  log_source_id UUID REFERENCES log_sources(id) ON DELETE CASCADE,

  source_value TEXT NOT NULL,         -- "1", "URGENT", "CRITICAL"
  sentinel_severity TEXT NOT NULL CHECK (sentinel_severity IN ('critical', 'high', 'medium', 'low')),

  UNIQUE(log_source_id, source_value)
);

-- Default severity mappings (global)
INSERT INTO severity_mappings (id, log_source_id, source_value, sentinel_severity) VALUES
  (uuid_generate_v4(), NULL, '1', 'critical'),
  (uuid_generate_v4(), NULL, '2', 'high'),
  (uuid_generate_v4(), NULL, '3', 'medium'),
  (uuid_generate_v4(), NULL, '4', 'low'),
  (uuid_generate_v4(), NULL, 'CRITICAL', 'critical'),
  (uuid_generate_v4(), NULL, 'URGENT', 'critical'),
  (uuid_generate_v4(), NULL, 'EMERGENCY', 'critical'),
  (uuid_generate_v4(), NULL, 'HIGH', 'high'),
  (uuid_generate_v4(), NULL, 'MAJOR', 'high'),
  (uuid_generate_v4(), NULL, 'MEDIUM', 'medium'),
  (uuid_generate_v4(), NULL, 'NORMAL', 'medium'),
  (uuid_generate_v4(), NULL, 'LOW', 'low'),
  (uuid_generate_v4(), NULL, 'INFO', 'low');

-- Ingested alarms (normalized alarm history)
CREATE TABLE ingested_alarms (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  log_source_id UUID NOT NULL REFERENCES log_sources(id) ON DELETE CASCADE,
  building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,

  -- Normalized fields
  occurred_at TIMESTAMPTZ NOT NULL,
  point_id TEXT NOT NULL,             -- Original BMS point ID
  asset_id TEXT,                      -- Matched CAFM asset (via point_asset_mappings)

  alarm_code TEXT,                    -- Original vendor code
  sentinel_code TEXT,                 -- Normalized SENTINEL code
  description TEXT,

  value DECIMAL(12, 4),
  threshold DECIMAL(12, 4),
  unit TEXT,

  severity TEXT CHECK (severity IN ('critical', 'high', 'medium', 'low')),
  state TEXT CHECK (state IN ('active', 'acknowledged', 'cleared')),

  acknowledged_by TEXT,
  acknowledged_at TIMESTAMPTZ,
  cleared_at TIMESTAMPTZ,
  notes TEXT,

  -- Metadata
  raw_data JSONB,                     -- Original record for debugging
  ingested_at TIMESTAMPTZ DEFAULT NOW(),

  -- Deduplication
  source_hash TEXT,                   -- Hash of key fields for duplicate detection

  UNIQUE(log_source_id, source_hash)
);

CREATE INDEX idx_ingested_alarms_building ON ingested_alarms(building_id);
CREATE INDEX idx_ingested_alarms_asset ON ingested_alarms(asset_id);
CREATE INDEX idx_ingested_alarms_time ON ingested_alarms(occurred_at DESC);
CREATE INDEX idx_ingested_alarms_severity ON ingested_alarms(severity, state);
CREATE INDEX idx_ingested_alarms_code ON ingested_alarms(sentinel_code);

-- Ingested trends (normalized telemetry history)
CREATE TABLE ingested_trends (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  log_source_id UUID NOT NULL REFERENCES log_sources(id) ON DELETE CASCADE,
  building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,

  -- Normalized fields
  recorded_at TIMESTAMPTZ NOT NULL,
  point_id TEXT NOT NULL,
  asset_id TEXT,                      -- Matched CAFM asset
  parameter_name TEXT,                -- "SAT", "RAT", "FanSpd", etc.

  value DECIMAL(12, 4) NOT NULL,
  unit TEXT,
  quality TEXT CHECK (quality IN ('good', 'bad', 'uncertain')),

  -- Metadata
  ingested_at TIMESTAMPTZ DEFAULT NOW(),

  -- For time-series optimization
  UNIQUE(log_source_id, point_id, recorded_at)
);

CREATE INDEX idx_ingested_trends_building ON ingested_trends(building_id);
CREATE INDEX idx_ingested_trends_asset ON ingested_trends(asset_id);
CREATE INDEX idx_ingested_trends_time ON ingested_trends(recorded_at DESC);
CREATE INDEX idx_ingested_trends_point ON ingested_trends(point_id, recorded_at DESC);

-- Sync jobs (track each ingestion run)
CREATE TABLE sync_jobs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  log_source_id UUID NOT NULL REFERENCES log_sources(id) ON DELETE CASCADE,

  started_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  status TEXT CHECK (status IN ('running', 'success', 'partial', 'failed')),

  -- Metrics
  records_processed INTEGER DEFAULT 0,
  records_inserted INTEGER DEFAULT 0,
  records_skipped INTEGER DEFAULT 0,  -- Duplicates
  records_failed INTEGER DEFAULT 0,

  -- Details
  file_name TEXT,
  file_size_bytes INTEGER,
  error_message TEXT,
  error_details JSONB,

  -- Performance
  processing_time_ms INTEGER
);

CREATE INDEX idx_sync_jobs_source ON sync_jobs(log_source_id);
CREATE INDEX idx_sync_jobs_time ON sync_jobs(started_at DESC);
CREATE INDEX idx_sync_jobs_status ON sync_jobs(status) WHERE status != 'success';

-- CAFM synced assets (cached copy from client's CAFM)
CREATE TABLE cafm_assets (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
  log_source_id UUID REFERENCES log_sources(id) ON DELETE SET NULL,

  -- CAFM fields (flexible - different CAFM systems have different fields)
  cafm_id TEXT NOT NULL,              -- ID in source CAFM system
  asset_tag TEXT NOT NULL,
  description TEXT,
  category TEXT,
  asset_type TEXT,
  sub_type TEXT,

  manufacturer TEXT,
  model TEXT,
  serial_number TEXT,

  location_floor TEXT,
  location_zone TEXT,
  location_room TEXT,

  install_date DATE,
  condition TEXT,
  criticality TEXT,

  -- PPM info
  ppm_frequency TEXT,
  last_ppm_date DATE,
  next_ppm_due DATE,

  -- Additional CAFM fields stored as JSON
  cafm_metadata JSONB,

  -- Sync tracking
  last_synced_at TIMESTAMPTZ DEFAULT NOW(),
  cafm_updated_at TIMESTAMPTZ,        -- When it was updated in source CAFM

  UNIQUE(building_id, cafm_id)
);

CREATE INDEX idx_cafm_assets_building ON cafm_assets(building_id);
CREATE INDEX idx_cafm_assets_tag ON cafm_assets(asset_tag);
CREATE INDEX idx_cafm_assets_type ON cafm_assets(category, asset_type);

-- CAFM synced work orders (for pattern analysis)
CREATE TABLE cafm_workorders (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
  log_source_id UUID REFERENCES log_sources(id) ON DELETE SET NULL,

  cafm_id TEXT NOT NULL,              -- WO number in source CAFM
  asset_id TEXT,                      -- Related asset

  wo_type TEXT,                       -- 'corrective', 'preventive', 'emergency'
  priority TEXT,
  status TEXT,

  description TEXT,
  resolution TEXT,

  created_at_source TIMESTAMPTZ,
  completed_at_source TIMESTAMPTZ,

  -- Cost info (if available)
  labor_cost DECIMAL(10, 2),
  parts_cost DECIMAL(10, 2),
  total_cost DECIMAL(10, 2),

  -- For NLP extraction
  failure_codes TEXT[],
  parts_used JSONB,

  -- Additional fields as JSON
  cafm_metadata JSONB,

  -- Sync tracking
  last_synced_at TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(building_id, cafm_id)
);

CREATE INDEX idx_cafm_workorders_building ON cafm_workorders(building_id);
CREATE INDEX idx_cafm_workorders_asset ON cafm_workorders(asset_id);
CREATE INDEX idx_cafm_workorders_created ON cafm_workorders(created_at_source DESC);
CREATE INDEX idx_cafm_workorders_type ON cafm_workorders(wo_type);

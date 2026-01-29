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

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

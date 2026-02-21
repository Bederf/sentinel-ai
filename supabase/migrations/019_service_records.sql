-- =====================================================
-- Migration 019: Service Records Schema
-- For ML engineer knowledge capture via Sentry bot
-- =====================================================

-- Service records (one per service visit)
CREATE TABLE service_records (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  code TEXT UNIQUE NOT NULL,              -- SR-2026-001234
  work_order_id UUID REFERENCES work_orders(id),
  equipment_id UUID NOT NULL REFERENCES equipment(id),
  building_id UUID NOT NULL REFERENCES buildings(id),

  -- Service details
  service_type TEXT CHECK (service_type IN ('minor', 'major', 'breakdown', 'callout')),
  technician_id TEXT NOT NULL,            -- Telegram ID or email
  technician_name TEXT NOT NULL,

  -- Timestamps
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,

  -- Status
  status TEXT CHECK (status IN ('notified', 'in_progress', 'data_collection', 'complete', 'closed')) DEFAULT 'notified',

  -- Conversation tracking
  telegram_chat_id TEXT,
  telegram_message_id TEXT,
  current_prompt TEXT,                    -- Which item we're waiting for
  items_collected JSONB DEFAULT '[]',     -- List of collected items

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_service_records_wo ON service_records(work_order_id);
CREATE INDEX idx_service_records_equipment ON service_records(equipment_id);
CREATE INDEX idx_service_records_status ON service_records(status);
CREATE INDEX idx_service_records_tech ON service_records(technician_id);
CREATE INDEX idx_service_records_building ON service_records(building_id);

CREATE TRIGGER update_service_records_updated_at BEFORE UPDATE ON service_records
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Service readings (OCR extracted from service sheet)
CREATE TABLE service_readings (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  service_record_id UUID NOT NULL REFERENCES service_records(id) ON DELETE CASCADE,

  reading_type TEXT NOT NULL,             -- hour_meter, battery_voltage, oil_level, etc.
  value TEXT NOT NULL,                    -- Stored as text, parsed by type
  unit TEXT,                              -- hours, V, °C, etc.
  numeric_value DECIMAL(12, 4),           -- Parsed numeric for trending

  source TEXT CHECK (source IN ('ocr', 'manual', 'sensor')),
  confidence DECIMAL(3, 2),               -- OCR confidence 0-1

  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_service_readings_record ON service_readings(service_record_id);
CREATE INDEX idx_service_readings_type ON service_readings(reading_type);

-- Service attachments (photos, audio, documents)
CREATE TABLE service_attachments (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  service_record_id UUID NOT NULL REFERENCES service_records(id) ON DELETE CASCADE,

  attachment_type TEXT CHECK (attachment_type IN (
    'service_sheet',
    'audio_recording',
    'oil_sample',
    'diesel_sample',
    'thermal_image',
    'issue_photo',
    'before_photo',
    'after_photo',
    'load_test_video',
    'oil_analysis_report'
  )),

  file_path TEXT NOT NULL,                -- Path in Supabase storage
  file_name TEXT,
  file_size_bytes INTEGER,
  mime_type TEXT,

  extracted_data JSONB,                   -- OCR or audio analysis results
  analysis_status TEXT CHECK (analysis_status IN ('pending', 'completed', 'failed')),

  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_service_attachments_record ON service_attachments(service_record_id);
CREATE INDEX idx_service_attachments_type ON service_attachments(attachment_type);

-- Service observations (technician voice notes or text observations)
CREATE TABLE service_observations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  service_record_id UUID NOT NULL REFERENCES service_records(id) ON DELETE CASCADE,

  observation_type TEXT CHECK (observation_type IN ('voice_note', 'text')),
  content TEXT NOT NULL,                  -- Text content or transcription
  audio_file_path TEXT,                   -- If voice note, path to audio
  duration_seconds REAL,

  -- ML analysis
  sentiment TEXT CHECK (sentiment IN ('positive', 'neutral', 'concerned', 'critical')),
  key_phrases JSONB,                      -- Extracted phrases for ML
  issue_flags JSONB,                      -- Flagged issues (e.g., ['oil_leak', 'belt_wear'])

  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_service_observations_record ON service_observations(service_record_id);

-- OCR attempts (audit trail for ML training)
CREATE TABLE ocr_attempts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  service_record_id UUID REFERENCES service_records(id),
  attachment_id UUID REFERENCES service_attachments(id),

  image_file_name TEXT,
  equipment_type TEXT,                    -- For template selection
  service_type TEXT,

  -- OCR results
  extracted_data JSONB,                   -- Raw extracted data
  validated_data JSONB,                   -- After validation
  validation_issues JSONB,                -- Issues found

  confidence_scores JSONB,                -- Per-field confidence
  corrections_made JSONB,                 -- Technician corrections

  -- Processing info
  model_used TEXT,                        -- Claude model version
  processing_time_ms INTEGER,

  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ocr_attempts_record ON ocr_attempts(service_record_id);
CREATE INDEX idx_ocr_attempts_attachment ON ocr_attempts(attachment_id);

-- Audio analysis results
CREATE TABLE audio_analysis (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  service_record_id UUID REFERENCES service_records(id),
  attachment_id UUID REFERENCES service_attachments(id),

  -- Features extracted
  features JSONB,                         -- MFCC, spectral centroid, etc.

  -- Anomaly detection
  anomalies_detected BOOLEAN,
  anomaly_types JSONB,                    -- ['bearing_defect', 'engine_knock']
  confidence_scores JSONB,                -- Per-anomaly confidence

  -- Recommendations
  recommendation TEXT,                    -- Human-readable recommendation
  severity TEXT CHECK (severity IN ('low', 'medium', 'high', 'critical')),

  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audio_analysis_record ON audio_analysis(service_record_id);
CREATE INDEX idx_audio_analysis_anomalies ON audio_analysis(anomalies_detected) WHERE anomalies_detected = true;

-- Comments
COMMENT ON TABLE service_records IS 'Service visit records for ML training (Phase 41)';
COMMENT ON TABLE service_readings IS 'OCR extracted readings from service sheets';
COMMENT ON TABLE service_attachments IS 'Photos, audio, documents from service visits';
COMMENT ON TABLE service_observations IS 'Technician observations (voice/text)';
COMMENT ON TABLE ocr_attempts IS 'Audit trail for OCR extraction (ML training data)';
COMMENT ON TABLE audio_analysis IS 'Audio feature extraction and anomaly detection';

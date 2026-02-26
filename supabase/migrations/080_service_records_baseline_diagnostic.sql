-- Phase 080: Service Records for Baseline Diagnostic Workflow
-- Purpose: Store technician inspection data and attachments for equipment baseline assessments
-- Tables: service_records, service_record_attachments
-- Relationships: WO-2026-0042 → SR-2026-ABC123 → phyphox files + photos

BEGIN;

-- ============================================================================
-- service_records table
-- ============================================================================
-- Stores baseline diagnostic inspection sessions linked to work orders
-- Each inspection generates one service record (SR-YYYY-XXXXXX code)
-- Status flow: NOTIFIED → DATA_COLLECTION → COMPLETE → ML_PROCESSING_COMPLETE

CREATE TABLE IF NOT EXISTS service_records (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Identifiers
  code TEXT NOT NULL UNIQUE,  -- e.g., "SR-2026-ABC123" (auto-generated)
  work_order_id UUID NOT NULL,
  equipment_id UUID NOT NULL,
  building_id UUID,

  -- Service Details
  service_type TEXT NOT NULL DEFAULT 'diagnostic_assessment',  -- 'diagnostic_assessment', 'breakdown', 'routine_maintenance'
  status TEXT NOT NULL DEFAULT 'NOTIFIED',  -- NOTIFIED, DATA_COLLECTION, COMPLETE, ML_PROCESSING_COMPLETE, ARCHIVED

  -- Technician Information
  technician_id TEXT,  -- Email or Telegram ID
  technician_name TEXT,

  -- Data Collection Tracking
  items_collected TEXT[] DEFAULT ARRAY[]::TEXT[],  -- ["rpm", "oil_pressure", "vibration_engine_block", "audio_engine_bay", ...]
  current_prompt TEXT,  -- For breakdown service: current step in collection flow

  -- Diagnostic Context (from alert/prediction that triggered this service)
  diagnostic_context JSONB,  -- Stores alert context for breakdown repairs
  -- Example: {"fault_type": "fuel_cavitation", "health_score": 42, "alert_id": "uuid", "prediction_id": "uuid"}

  -- Results After Analysis
  confirmed_fault TEXT,  -- Root cause identified (e.g., "fuel_cavitation", "governor_hunting", "bearing_wear")
  actual_repair TEXT,  -- Repair action taken (e.g., "fuel_pump_replaced", "governor_controller_replaced")

  -- Observations & Notes
  observations JSONB DEFAULT '{}'::JSONB,  -- Array of observation objects
  -- Example: [{"type": "fault_confirmation", "content": "Yes, fuel pump failed"}, ...]

  -- Metadata
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  completed_at TIMESTAMP WITH TIME ZONE,

  -- Constraints
  CONSTRAINT fk_work_order FOREIGN KEY (work_order_id) REFERENCES work_orders(id) ON DELETE CASCADE,
  CONSTRAINT fk_equipment FOREIGN KEY (equipment_id) REFERENCES equipment(id) ON DELETE CASCADE,
  CONSTRAINT fk_building FOREIGN KEY (building_id) REFERENCES buildings(id) ON DELETE SET NULL
);

-- Add columns that may be missing if table existed from earlier migration (019)
ALTER TABLE service_records ADD COLUMN IF NOT EXISTS code TEXT;
ALTER TABLE service_records ADD COLUMN IF NOT EXISTS building_id UUID;
ALTER TABLE service_records ADD COLUMN IF NOT EXISTS service_type TEXT DEFAULT 'diagnostic_assessment';
ALTER TABLE service_records ADD COLUMN IF NOT EXISTS technician_name TEXT;
ALTER TABLE service_records ADD COLUMN IF NOT EXISTS items_collected JSONB DEFAULT '[]';
ALTER TABLE service_records ADD COLUMN IF NOT EXISTS current_prompt TEXT;
ALTER TABLE service_records ADD COLUMN IF NOT EXISTS diagnostic_context JSONB;
ALTER TABLE service_records ADD COLUMN IF NOT EXISTS confirmed_fault TEXT;
ALTER TABLE service_records ADD COLUMN IF NOT EXISTS actual_repair TEXT;
ALTER TABLE service_records ADD COLUMN IF NOT EXISTS observations JSONB DEFAULT '{}'::JSONB;
ALTER TABLE service_records ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_service_records_code ON service_records(code);
CREATE INDEX IF NOT EXISTS idx_service_records_work_order ON service_records(work_order_id);
CREATE INDEX IF NOT EXISTS idx_service_records_equipment ON service_records(equipment_id);
CREATE INDEX IF NOT EXISTS idx_service_records_status ON service_records(status);
CREATE INDEX IF NOT EXISTS idx_service_records_created_at ON service_records(created_at DESC);

-- ============================================================================
-- service_record_attachments table
-- ============================================================================
-- Stores metadata for files uploaded during baseline diagnostic inspection
-- Files are stored in S3/cloud storage; this table tracks metadata + analysis results

CREATE TABLE IF NOT EXISTS service_record_attachments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Relationships
  service_record_id UUID NOT NULL,

  -- File Metadata
  attachment_type TEXT NOT NULL,  -- vibration_recording, audio_recording, photo_before, photo_after, service_sheet, thermal_image, oil_sample, diesel_sample, issue_photo, parts_replaced, load_test_video
  file_name TEXT NOT NULL,  -- e.g., "GEN5_BASELINE_VIBRATION_ENGINE_BLOCK_IDLE_20260212.csv"
  file_path TEXT NOT NULL,  -- Cloud storage path: s3://sentinel-storage/service-records/SR-2026-ABC123/...
  file_size_bytes INTEGER,  -- For quota/storage tracking
  mime_type TEXT,  -- text/csv, audio/wav, image/jpeg, video/mp4

  -- Analysis Status & Results
  analysis_status TEXT DEFAULT 'pending',  -- pending, in_progress, complete, failed
  analysis_result JSONB DEFAULT NULL,  -- Stores FFT analysis, OCR results, cavitation detection, etc.
  -- Example for vibration: {"fft_peaks": [...], "max_frequency": 0.8, "bearing_wear_confidence": 0.85}
  -- Example for audio: {"cavitation_detected": true, "freq_200_400hz_db": 2.3}
  -- Example for photo: {"text_extracted": "...OCR output...", "labels": [...]}

  -- Optional: Corrections (for OCR validation flow)
  original_value TEXT,  -- Before technician correction
  corrected_value TEXT,  -- After technician provides correction
  correction_timestamp TIMESTAMP WITH TIME ZONE,

  -- Metadata
  uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  analyzed_at TIMESTAMP WITH TIME ZONE,

  -- Constraints
  CONSTRAINT fk_service_record FOREIGN KEY (service_record_id) REFERENCES service_records(id) ON DELETE CASCADE
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_service_record_attachments_service_record ON service_record_attachments(service_record_id);
CREATE INDEX IF NOT EXISTS idx_service_record_attachments_type ON service_record_attachments(attachment_type);
CREATE INDEX IF NOT EXISTS idx_service_record_attachments_status ON service_record_attachments(analysis_status);
CREATE INDEX IF NOT EXISTS idx_service_record_attachments_uploaded_at ON service_record_attachments(uploaded_at DESC);

-- ============================================================================
-- Enable Row Level Security (RLS)
-- ============================================================================

ALTER TABLE service_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE service_record_attachments ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- RLS Policies
-- ============================================================================

-- Allow authenticated users to view their own service records
CREATE POLICY "Users can view service records for their equipment"
  ON service_records FOR SELECT
  USING (auth.role() = 'authenticated');

-- Allow authenticated users to view attachments for their service records
CREATE POLICY "Users can view attachments for their service records"
  ON service_record_attachments FOR SELECT
  USING (
    auth.role() = 'authenticated' AND
    service_record_id IN (
      SELECT id FROM service_records WHERE equipment_id IN (
        SELECT id FROM equipment WHERE building_id IN (
          SELECT id FROM buildings WHERE id IS NOT NULL
        )
      )
    )
  );

-- Allow system (authenticated) to insert service records
CREATE POLICY "System can create service records"
  ON service_records FOR INSERT
  WITH CHECK (auth.role() = 'authenticated');

-- Allow system to insert attachments
CREATE POLICY "System can create attachments"
  ON service_record_attachments FOR INSERT
  WITH CHECK (auth.role() = 'authenticated');

-- Allow system to update service records (status, analysis results)
CREATE POLICY "System can update service records"
  ON service_records FOR UPDATE
  USING (auth.role() = 'authenticated')
  WITH CHECK (auth.role() = 'authenticated');

-- Allow system to update attachments (analysis results)
CREATE POLICY "System can update attachments"
  ON service_record_attachments FOR UPDATE
  USING (auth.role() = 'authenticated')
  WITH CHECK (auth.role() = 'authenticated');

-- ============================================================================
-- Helpful Views
-- ============================================================================

-- View: Service records with equipment and work order details
CREATE OR REPLACE VIEW service_records_with_details AS
SELECT
  sr.id,
  sr.code,
  sr.work_order_id,
  wo.code AS work_order_code,
  sr.equipment_id,
  e.code AS equipment_code,
  e.name AS equipment_name,
  e.type AS equipment_type,
  sr.service_type,
  sr.status,
  sr.technician_name,
  sr.confirmed_fault,
  sr.actual_repair,
  jsonb_array_length(COALESCE(sr.items_collected, '[]'::jsonb)) AS items_count,
  sr.created_at,
  sr.completed_at
FROM service_records sr
LEFT JOIN work_orders wo ON sr.work_order_id = wo.id
LEFT JOIN equipment e ON sr.equipment_id = e.id;

-- View: Attachment statistics by service record
CREATE OR REPLACE VIEW attachment_statistics AS
SELECT
  sr.id,
  sr.code AS service_record_code,
  sr.equipment_id,
  COUNT(*) AS total_attachments,
  COUNT(CASE WHEN sra.attachment_type = 'vibration_recording' THEN 1 END) AS vibration_files,
  COUNT(CASE WHEN sra.attachment_type = 'audio_recording' THEN 1 END) AS audio_files,
  COUNT(CASE WHEN sra.attachment_type LIKE 'photo_%' THEN 1 END) AS photo_files,
  COUNT(CASE WHEN sra.attachment_type LIKE '%_sample' THEN 1 END) AS sample_files,
  SUM(sra.file_size_bytes) AS total_size_bytes,
  COUNT(CASE WHEN sra.analysis_status = 'complete' THEN 1 END) AS analyzed_count,
  COUNT(CASE WHEN sra.analysis_status = 'pending' THEN 1 END) AS pending_count
FROM service_records sr
LEFT JOIN service_record_attachments sra ON sr.id = sra.service_record_id
GROUP BY sr.id, sr.code, sr.equipment_id;

COMMIT;

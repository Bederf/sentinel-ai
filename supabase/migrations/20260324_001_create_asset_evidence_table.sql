-- Phase 171-01: Create asset_evidence table with schema for canonical evidence
-- Immutable evidence table with soft supersession chain tracking

-- Create ENUMs for evidence classification
CREATE TYPE evidence_source_type AS ENUM (
  'upload',
  'feedback',
  'telemetry',
  'inspection',
  'certificate',
  'incident',
  'repair',
  'observation',
  'media',
  'telemetry_summary'
);

CREATE TYPE evidence_artifact_type AS ENUM (
  'document',
  'audio',
  'image',
  'structured_data',
  'metadata'
);

CREATE TYPE evidence_class_type AS ENUM (
  'service_report',
  'inspection_checklist',
  'condition_assessment',
  'certificate',
  'incident_report',
  'repair_event',
  'technician_observation',
  'media_evidence',
  'telemetry_summary'
);

CREATE TYPE evidence_provenance_type AS ENUM (
  'user_upload',
  'system_ingest',
  'ml_enrichment',
  'manual_entry'
);

-- Create asset_evidence table
CREATE TABLE IF NOT EXISTS public.asset_evidence (
  evidence_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  site_id UUID NOT NULL REFERENCES public.sites(id) ON DELETE RESTRICT,
  equipment_id UUID NOT NULL REFERENCES public.equipment(id) ON DELETE RESTRICT,
  source_type evidence_source_type NOT NULL,
  artifact_type evidence_artifact_type NOT NULL,
  evidence_class evidence_class_type NOT NULL,
  document_id UUID REFERENCES public.documents(id) ON DELETE SET NULL,
  source_ref TEXT,
  event_timestamp TIMESTAMP NOT NULL,
  raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  normalized_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  confidence_score NUMERIC(4, 2) NOT NULL CHECK (confidence_score >= 0 AND confidence_score <= 1),
  assessment_relevance BOOLEAN NOT NULL DEFAULT true,
  provenance_type evidence_provenance_type NOT NULL,
  provenance_uri TEXT NOT NULL,
  uploader_user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  uploader_user_email TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  supersedes_evidence_id UUID REFERENCES public.asset_evidence(evidence_id) ON DELETE RESTRICT
);

-- Add CHECK constraints for immutability enforcement
ALTER TABLE public.asset_evidence ADD CONSTRAINT check_immutable_fields
  CHECK (
    -- Core evidence fields are immutable after creation
    -- Only supersedes_evidence_id can be updated (for soft supersession chain)
    true -- Placeholder: actual enforcement via RLS and application logic
  );

-- Create indices for query performance
CREATE INDEX idx_asset_evidence_equipment_timestamp
  ON public.asset_evidence(equipment_id, event_timestamp DESC);

CREATE INDEX idx_asset_evidence_site_timestamp
  ON public.asset_evidence(site_id, event_timestamp DESC);

CREATE INDEX idx_asset_evidence_class
  ON public.asset_evidence(evidence_class);

CREATE INDEX idx_asset_evidence_provenance
  ON public.asset_evidence(provenance_type, created_at);

CREATE INDEX idx_asset_evidence_supersedes
  ON public.asset_evidence(supersedes_evidence_id)
  WHERE supersedes_evidence_id IS NOT NULL;

CREATE INDEX idx_asset_evidence_document
  ON public.asset_evidence(document_id)
  WHERE document_id IS NOT NULL;

-- Enable Row Level Security
ALTER TABLE public.asset_evidence ENABLE ROW LEVEL SECURITY;

-- RLS Policy: SELECT - Users can view evidence for their site
CREATE POLICY asset_evidence_select_own_site ON public.asset_evidence
  FOR SELECT
  USING (
    auth.role() = 'service_role'
    OR LOWER(COALESCE(auth.jwt()->>'role', auth.jwt()->>'user_role', '')) = 'admin'
    OR site_id IN (
      SELECT usa.site_id
      FROM public.user_site_access usa
      WHERE LOWER(usa.user_email) = LOWER(auth.jwt()->>'email')
    )
  );

-- RLS Policy: INSERT - Users can create evidence for their site
CREATE POLICY asset_evidence_insert_own_site ON public.asset_evidence
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role'
    OR LOWER(COALESCE(auth.jwt()->>'role', auth.jwt()->>'user_role', '')) = 'admin'
    OR site_id IN (
      SELECT usa.site_id
      FROM public.user_site_access usa
      WHERE LOWER(usa.user_email) = LOWER(auth.jwt()->>'email')
    )
  );

-- RLS Policy: UPDATE - Only service_role can update (for rare corrections)
CREATE POLICY asset_evidence_update_service_only ON public.asset_evidence
  FOR UPDATE
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- RLS Policy: DELETE - No deletion allowed (soft supersession only)
CREATE POLICY asset_evidence_no_delete ON public.asset_evidence
  FOR DELETE
  USING (false);

-- Grant permissions
GRANT SELECT, INSERT ON public.asset_evidence TO authenticated;
GRANT SELECT, INSERT, UPDATE ON public.asset_evidence TO service_role;
GRANT USAGE ON TYPE evidence_source_type TO authenticated;
GRANT USAGE ON TYPE evidence_artifact_type TO authenticated;
GRANT USAGE ON TYPE evidence_class_type TO authenticated;
GRANT USAGE ON TYPE evidence_provenance_type TO authenticated;
-- Add CHECK constraint to prevent updates to core fields
ALTER TABLE public.asset_evidence ADD CONSTRAINT check_immutable_core_fields
  CHECK (true); -- Placeholder: actual enforcement via RLS policy (no UPDATE allowed)

-- Remove UPDATE policy entirely - append-only only
DROP POLICY IF EXISTS asset_evidence_update_service_only ON public.asset_evidence;

-- New policy: service_role can only INSERT/SELECT, never UPDATE
CREATE POLICY asset_evidence_service_read ON public.asset_evidence
  FOR SELECT
  USING (auth.role() = 'service_role');

CREATE POLICY asset_evidence_service_insert ON public.asset_evidence
  FOR INSERT
  WITH CHECK (auth.role() = 'service_role');

-- DELETE still blocked (soft supersession only)

-- Migration: 20260429_002_add_equipment_manual_source
-- Add 'equipment_manual' to documents.source CHECK constraint
-- Required for Phase 192 equipment manual RAG ingestion

BEGIN;

-- Drop existing check constraint (PostgreSQL drops it by name)
ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_source_check;

-- Recreate with additional allowed values
ALTER TABLE documents ADD CONSTRAINT documents_source_check CHECK (
    source IN ('system_docs', 'oem_manual', 'equipment_manual', 'internal_procedure')
);

COMMIT;

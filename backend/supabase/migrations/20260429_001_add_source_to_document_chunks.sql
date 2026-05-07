-- Migration: 20260429_001_add_source_to_document_chunks
-- Add source column to document_chunks for RAG filtering
-- Backfill existing Phase 191 chunks as 'sentinel_docs'
-- Equipment manual chunks will use 'equipment_manual'

BEGIN;

-- Add source column
ALTER TABLE document_chunks
ADD COLUMN IF NOT EXISTS source VARCHAR DEFAULT 'sentinel_docs';

-- Backfill Phase 191 chunks (documents with source = 'internal_procedure')
UPDATE document_chunks
SET source = 'sentinel_docs'
WHERE document_id IN (
    SELECT id FROM documents WHERE source = 'internal_procedure'
);

-- Mark any existing chunks without explicit source as sentinel_docs
UPDATE document_chunks
SET source = 'sentinel_docs'
WHERE source IS NULL;

-- Create index for source filtering
CREATE INDEX IF NOT EXISTS idx_document_chunks_source ON document_chunks(source);

COMMIT;

-- Migration 029: Add metadata JSONB column to document_chunks
-- Stores heading_path, context flags, and other chunk-level metadata
-- for improved RAG retrieval with section-aware chunking.

ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;

COMMENT ON COLUMN document_chunks.metadata IS 'Chunk-level metadata: heading_path, context_enhanced flag, etc.';

-- Index for JSONB queries on heading_path
CREATE INDEX IF NOT EXISTS idx_document_chunks_metadata_gin
  ON document_chunks USING GIN (metadata);

-- =====================================================
-- Migration 179: Add Document Source Columns
-- Phase 179: DocumentSourceAdapter (B1/B2 fixes applied)
--
-- Adds source_system, source_document_id, site_id columns
-- to the documents table for cross-adapter deduplication.
--
-- ON CONFLICT (source_document_id, source_system) allows the same
-- source_document_id from different adapters (e.g. same WO number
-- from MRI and SharePoint) without CHECK constraint conflicts.
--
-- B2 fix: adapter _upsert does NOT write to documents.source or
-- documents.document_type — those are managed exclusively by the
-- existing upload_technician_document flow.
--
-- Run as: Supabase SQL Editor or via supabase-cli
-- =====================================================

-- 1. Add the three new columns
ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_system TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_document_id TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS site_id TEXT;

-- 2. Add unique constraint for cross-adapter deduplication
--    Allows same source_document_id from different source_system adapters
ALTER TABLE documents ADD CONSTRAINT IF NOT EXISTS
    documents_source_doc_site_unique
    UNIQUE (source_document_id, source_system);

-- 3. Create sync state table for per-adapter tracking
CREATE TABLE IF NOT EXISTS document_connector_sync (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    adapter_source TEXT NOT NULL,          -- e.g. 'concept_mri', 'sharepoint'
    site_id TEXT,
    last_successful_sync TIMESTAMPTZ,
    last_sync_attempted TIMESTAMPTZ,
    records_ingested INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    CONSTRAINT document_connector_sync_adapter_site_unique
        UNIQUE (adapter_source, site_id)
);

-- 4. Index for fast sync queries
CREATE INDEX IF NOT EXISTS idx_document_connector_sync_adapter
    ON document_connector_sync(adapter_source, site_id);

-- 5. Index on documents for cross-adapter queries
CREATE INDEX IF NOT EXISTS idx_documents_source_key
    ON documents(source_document_id, source_system)
    WHERE source_document_id IS NOT NULL;

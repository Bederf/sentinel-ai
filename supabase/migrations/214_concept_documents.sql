-- Migration 204: Concept Document Catalog
-- Separate vector store for Concept search results (site-001 only)
CREATE TABLE IF NOT EXISTS concept_documents (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  code TEXT NOT NULL,
  title TEXT NOT NULL,
  document_type TEXT NOT NULL,
  equipment_type TEXT NOT NULL,
  full_text TEXT NOT NULL,
  concept_document_id TEXT NOT NULL,
  concept_url TEXT NOT NULL,
  site_id UUID REFERENCES sites(id) ON DELETE SET NULL,
  source TEXT NOT NULL DEFAULT 'concept_tsv',
  metadata JSONB DEFAULT '{}'::jsonb,
  indexing_status TEXT CHECK (indexing_status IN ('pending','chunking','embedded','failed')) DEFAULT 'pending',
  indexed_at TIMESTAMPTZ,
  chunk_count INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS concept_document_chunks (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_id UUID NOT NULL REFERENCES concept_documents(id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  content TEXT NOT NULL,
  content_length INTEGER NOT NULL,
  embedding vector(384) NOT NULL,
  section_title TEXT,
  page_number INTEGER,
  equipment_type TEXT NOT NULL,
  document_type TEXT NOT NULL,
  manufacturer TEXT,
  model TEXT,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_concept_documents_site ON concept_documents(site_id);
CREATE INDEX IF NOT EXISTS idx_concept_chunks_document ON concept_document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_concept_chunks_equipment ON concept_document_chunks(equipment_type);
CREATE INDEX IF NOT EXISTS idx_concept_chunks_document_type ON concept_document_chunks(document_type);

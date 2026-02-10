-- =====================================================
-- Building-Scoped Document Upload for AI Chat
-- =====================================================

-- Phase X: Building-scoped RAG documents
-- Adds building association to documents table for user-uploaded building-specific documentation
-- System documentation remains unscoped (building_id = NULL)

-- Add building_id column to documents table (nullable for backward compat with system docs)
ALTER TABLE documents ADD COLUMN building_id UUID REFERENCES buildings(id) ON DELETE CASCADE;

-- Add building_id column to document_chunks table (denormalized for query performance)
ALTER TABLE document_chunks ADD COLUMN building_id UUID;

-- Indexes for building-scoped queries
CREATE INDEX idx_documents_building ON documents(building_id) WHERE building_id IS NOT NULL;
CREATE INDEX idx_chunks_building ON document_chunks(building_id) WHERE building_id IS NOT NULL;

-- Update search function to accept optional building filter
CREATE OR REPLACE FUNCTION match_document_chunks(
  query_embedding vector(384),
  match_count integer DEFAULT 5,
  filter_equipment_type text DEFAULT NULL,
  filter_document_type text DEFAULT NULL,
  filter_manufacturer text DEFAULT NULL,
  filter_building_id uuid DEFAULT NULL,
  similarity_threshold decimal DEFAULT 0.7
)
RETURNS TABLE (
  chunk_id uuid,
  document_id uuid,
  content text,
  section_title text,
  equipment_type text,
  document_type text,
  manufacturer text,
  model text,
  similarity decimal,
  document_title text,
  document_source text,
  building_id uuid
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    dc.id,
    dc.document_id,
    dc.content,
    dc.section_title,
    dc.equipment_type,
    dc.document_type,
    dc.manufacturer,
    dc.model,
    ROUND((1 - (dc.embedding <=> query_embedding))::numeric, 4) AS similarity,
    d.title AS document_title,
    d.source AS document_source,
    dc.building_id
  FROM document_chunks dc
  JOIN documents d ON dc.document_id = d.id
  WHERE
    (filter_equipment_type IS NULL OR dc.equipment_type = filter_equipment_type)
    AND (filter_document_type IS NULL OR dc.document_type = filter_document_type)
    AND (filter_manufacturer IS NULL OR dc.manufacturer = filter_manufacturer)
    AND d.is_latest = TRUE
    AND d.indexing_status = 'embedded'
    AND (1 - (dc.embedding <=> query_embedding)) >= similarity_threshold
    -- Building filter: return building-specific docs OR system docs (building_id IS NULL)
    AND (filter_building_id IS NULL 
         OR dc.building_id = filter_building_id 
         OR dc.building_id IS NULL)
  ORDER BY dc.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- Update hybrid search function to accept optional building filter
CREATE OR REPLACE FUNCTION hybrid_search_chunks(
  query_text text,
  query_embedding vector(384),
  match_count integer DEFAULT 5,
  filter_equipment_type text DEFAULT NULL,
  filter_building_id uuid DEFAULT NULL,
  keyword_weight decimal DEFAULT 0.3,
  semantic_weight decimal DEFAULT 0.7
)
RETURNS TABLE (
  chunk_id uuid,
  content text,
  equipment_type text,
  document_title text,
  hybrid_score decimal,
  keyword_score decimal,
  semantic_score decimal,
  building_id uuid
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  WITH keyword_search AS (
    SELECT
      dc.id,
      dc.content,
      dc.equipment_type,
      d.title AS document_title,
      dc.building_id,
      ts_rank(to_tsvector('english', dc.content), plainto_tsquery('english', query_text)) AS kw_score
    FROM document_chunks dc
    JOIN documents d ON dc.document_id = d.id
    WHERE
      to_tsvector('english', dc.content) @@ plainto_tsquery('english', query_text)
      AND (filter_equipment_type IS NULL OR dc.equipment_type = filter_equipment_type)
      AND d.is_latest = TRUE
      AND (filter_building_id IS NULL 
           OR dc.building_id = filter_building_id 
           OR dc.building_id IS NULL)
  ),
  semantic_search AS (
    SELECT
      dc.id,
      dc.content,
      dc.equipment_type,
      d.title AS document_title,
      dc.building_id,
      (1 - (dc.embedding <=> query_embedding)) AS sem_score
    FROM document_chunks dc
    JOIN documents d ON dc.document_id = d.id
    WHERE
      (filter_equipment_type IS NULL OR dc.equipment_type = filter_equipment_type)
      AND d.is_latest = TRUE
      AND (filter_building_id IS NULL 
           OR dc.building_id = filter_building_id 
           OR dc.building_id IS NULL)
  )
  SELECT
    COALESCE(ks.id, ss.id) AS chunk_id,
    COALESCE(ks.content, ss.content) AS content,
    COALESCE(ks.equipment_type, ss.equipment_type) AS equipment_type,
    COALESCE(ks.document_title, ss.document_title) AS document_title,
    ROUND((
      (COALESCE(ks.kw_score, 0) * keyword_weight) +
      (COALESCE(ss.sem_score, 0) * semantic_weight)
    )::numeric, 4) AS hybrid_score,
    ROUND(COALESCE(ks.kw_score, 0)::numeric, 4) AS keyword_score,
    ROUND(COALESCE(ss.sem_score, 0)::numeric, 4) AS semantic_score,
    COALESCE(ks.building_id, ss.building_id) AS building_id
  FROM keyword_search ks
  FULL OUTER JOIN semantic_search ss ON ks.id = ss.id
  ORDER BY hybrid_score DESC
  LIMIT match_count;
END;
$$;

-- Backfill existing chunks with building_id = NULL (system documentation)
-- All existing chunks are system docs, so they inherit NULL building_id (which is the default)
-- No data migration needed since columns default to NULL

COMMENT ON COLUMN documents.building_id IS 'Building association for user-uploaded documents. NULL for system documentation.';
COMMENT ON COLUMN document_chunks.building_id IS 'Denormalized from parent document for query performance';

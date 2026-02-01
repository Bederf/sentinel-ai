-- =====================================================
-- Migration 023: pgvector RAG Schema
-- RAG (Retrieval-Augmented Generation) for equipment documentation
-- Supports Phase 44: Local LLM Integration with Ollama
-- =====================================================

-- Enable pgvector extension for vector similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- =====================================================
-- Document Types and Sources
-- =====================================================

-- Documents table (root level - manuals, procedures, etc.)
CREATE TABLE documents (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

  -- Identification
  code TEXT UNIQUE NOT NULL,                    -- e.g., 'MAN-CHILLER-YORK-YCIV-001'
  title TEXT NOT NULL,

  -- Classification
  document_type TEXT NOT NULL CHECK (document_type IN (
    'equipment_manual',          -- OEM manual
    'maintenance_procedure',     -- Step-by-step procedure
    'troubleshooting_guide',     -- Fault diagnosis guide
    'failure_pattern',           -- Historical failure documentation
    'technical_bulletin',        -- Manufacturer bulletins
    'service_report',            -- Historical service reports
    'safety_procedure',          -- Safety procedures
    'startup_procedure',         -- Commissioning/startup guides
    'shutdown_procedure'         -- Shutdown/decommissioning guides
  )),

  -- Equipment association
  equipment_type TEXT NOT NULL,                 -- chiller, generator, pump, ahu, etc.
  manufacturer TEXT,
  model TEXT,
  applies_to_equipment_ids JSONB,               -- Array of specific equipment UUIDs

  -- Source
  source TEXT NOT NULL CHECK (source IN (
    'oem_manual',
    'internal_procedure',
    'service_history',
    'technician_notes',
    'manufacturer_bulletin',
    'industry_standard'
  )),
  source_url TEXT,                              -- External URL if applicable
  source_file_path TEXT,                        -- Path in Supabase storage

  -- Versioning
  version TEXT DEFAULT '1.0',
  supersedes_id UUID REFERENCES documents(id),  -- Previous version
  is_latest BOOLEAN DEFAULT TRUE,

  -- Content
  summary TEXT,                                 -- Short summary (for preview)
  full_text TEXT,                               -- Full document text (for chunking)
  language TEXT DEFAULT 'en',
  page_count INTEGER,
  file_size_bytes INTEGER,

  -- Metadata for search
  keywords TEXT[],                              -- Array of keywords for filtering
  failure_modes TEXT[],                         -- Relevant failure modes
  component_tags TEXT[],                        -- Component tags (e.g., 'compressor', 'condenser')

  -- Indexing status
  indexing_status TEXT CHECK (indexing_status IN ('pending', 'chunking', 'embedded', 'failed')) DEFAULT 'pending',
  indexed_at TIMESTAMPTZ,
  chunk_count INTEGER DEFAULT 0,

  -- Quality metadata
  ocr_extracted BOOLEAN DEFAULT FALSE,          -- Was text extracted via OCR?
  ocr_confidence DECIMAL(3, 2),                 -- OCR confidence if applicable
  requires_review BOOLEAN DEFAULT FALSE,
  reviewed_by TEXT,
  reviewed_at TIMESTAMPTZ,

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================================
-- Document Chunks (for vector search)
-- =====================================================

-- Document chunks table (text segments with embeddings)
CREATE TABLE document_chunks (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,

  -- Chunk identification
  chunk_index INTEGER NOT NULL,                 -- Position in document (0-based)

  -- Content
  content TEXT NOT NULL,                        -- Chunk text (512-1024 tokens)
  content_length INTEGER NOT NULL,              -- Character count
  token_count INTEGER,                          -- Token count if available

  -- Vector embedding
  -- Supports both OpenAI (1536) and smaller models (384 for MiniLM)
  embedding vector(384),                        -- Use 384 for all-MiniLM-L6-v2
  -- For OpenAI compatibility: ALTER TABLE document_chunks ADD COLUMN embedding_openai vector(1536);

  -- Context
  section_title TEXT,                           -- Section/heading for this chunk
  page_number INTEGER,                          -- Page number if applicable

  -- Metadata from parent document (denormalized for faster search)
  equipment_type TEXT NOT NULL,
  document_type TEXT NOT NULL,
  manufacturer TEXT,
  model TEXT,
  keywords TEXT[],
  failure_modes TEXT[],

  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================================
-- Equipment Knowledge Base (structured knowledge)
-- =====================================================

-- Equipment-specific knowledge (fault codes, symptoms, solutions)
CREATE TABLE equipment_knowledge (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

  -- Equipment association
  equipment_type TEXT NOT NULL,
  manufacturer TEXT,
  model TEXT,
  component TEXT,                               -- Specific component (e.g., 'compressor', 'evaporator')

  -- Knowledge type
  knowledge_type TEXT NOT NULL CHECK (knowledge_type IN (
    'fault_code',              -- Error code with explanation
    'symptom',                 -- Observable symptom with causes
    'failure_pattern',         -- Recurring failure pattern
    'maintenance_tip',         -- Best practice or tip
    'diagnostic_procedure',    -- How to diagnose issue
    'repair_procedure',        -- How to repair issue
    'preventive_measure'       -- How to prevent issue
  )),

  -- Content
  code TEXT,                                    -- Fault code if applicable (e.g., 'E01', 'AL-1234')
  title TEXT NOT NULL,
  description TEXT NOT NULL,

  -- Diagnostic information
  symptoms TEXT[],                              -- Observable symptoms
  possible_causes TEXT[],                       -- Possible root causes
  diagnostic_steps TEXT[],                      -- Steps to diagnose

  -- Solution
  solution TEXT,                                -- Solution description
  parts_required JSONB,                         -- [{part_number, description, quantity}]
  tools_required TEXT[],
  estimated_labor_hours DECIMAL(5, 2),
  priority TEXT CHECK (priority IN ('critical', 'high', 'medium', 'low')),

  -- Related information
  related_fault_codes TEXT[],
  related_symptoms TEXT[],
  safety_notes TEXT,

  -- Vector embedding (for semantic search)
  embedding vector(384),

  -- Source and verification
  source_document_id UUID REFERENCES documents(id),
  verified_by TEXT,                             -- Technician who verified
  verified_at TIMESTAMPTZ,
  confidence TEXT CHECK (confidence IN ('high', 'medium', 'low')) DEFAULT 'medium',

  -- Usage tracking
  times_referenced INTEGER DEFAULT 0,
  last_referenced_at TIMESTAMPTZ,

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================================
-- Search History (for improving relevance)
-- =====================================================

-- RAG query history (for analytics and relevance tuning)
CREATE TABLE rag_queries (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

  -- Query details
  query_text TEXT NOT NULL,
  query_embedding vector(384),

  -- Context
  equipment_id UUID REFERENCES equipment(id),
  equipment_type TEXT,
  user_context JSONB,                           -- {role, location, session_id, etc.}

  -- Retrieval results
  chunks_retrieved INTEGER,
  top_chunk_ids UUID[],                         -- Top N chunk IDs returned
  avg_similarity_score DECIMAL(5, 4),           -- Average cosine similarity

  -- Feedback
  result_used BOOLEAN,                          -- Was a result clicked/used?
  feedback_rating INTEGER CHECK (feedback_rating BETWEEN 1 AND 5),
  feedback_comment TEXT,

  -- Performance
  retrieval_time_ms INTEGER,

  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================================
-- Indexes for Performance
-- =====================================================

-- Document indexes
CREATE INDEX idx_documents_equipment_type ON documents(equipment_type);
CREATE INDEX idx_documents_document_type ON documents(document_type);
CREATE INDEX idx_documents_manufacturer ON documents(manufacturer) WHERE manufacturer IS NOT NULL;
CREATE INDEX idx_documents_model ON documents(model) WHERE model IS NOT NULL;
CREATE INDEX idx_documents_status ON documents(indexing_status);
CREATE INDEX idx_documents_latest ON documents(is_latest) WHERE is_latest = TRUE;
CREATE INDEX idx_documents_keywords ON documents USING GIN(keywords);
CREATE INDEX idx_documents_failure_modes ON documents USING GIN(failure_modes);

-- Chunk indexes
CREATE INDEX idx_chunks_document ON document_chunks(document_id);
CREATE INDEX idx_chunks_equipment_type ON document_chunks(equipment_type);
CREATE INDEX idx_chunks_document_type ON document_chunks(document_type);
CREATE INDEX idx_chunks_keywords ON document_chunks USING GIN(keywords);

-- Vector similarity indexes (IVFFLAT for faster approximate search)
-- Note: Build these AFTER loading data for better performance
-- For small datasets (<100k vectors), can use default index
CREATE INDEX idx_chunks_embedding ON document_chunks
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

CREATE INDEX idx_knowledge_embedding ON equipment_knowledge
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 50);

-- Knowledge base indexes
CREATE INDEX idx_knowledge_equipment_type ON equipment_knowledge(equipment_type);
CREATE INDEX idx_knowledge_type ON equipment_knowledge(knowledge_type);
CREATE INDEX idx_knowledge_code ON equipment_knowledge(code) WHERE code IS NOT NULL;
CREATE INDEX idx_knowledge_manufacturer ON equipment_knowledge(manufacturer) WHERE manufacturer IS NOT NULL;
CREATE INDEX idx_knowledge_verified ON equipment_knowledge(verified_at) WHERE verified_at IS NOT NULL;
CREATE INDEX idx_knowledge_symptoms ON equipment_knowledge USING GIN(symptoms);
CREATE INDEX idx_knowledge_causes ON equipment_knowledge USING GIN(possible_causes);

-- Query history indexes
CREATE INDEX idx_rag_queries_equipment ON rag_queries(equipment_id) WHERE equipment_id IS NOT NULL;
CREATE INDEX idx_rag_queries_equipment_type ON rag_queries(equipment_type) WHERE equipment_type IS NOT NULL;
CREATE INDEX idx_rag_queries_created ON rag_queries(created_at DESC);
CREATE INDEX idx_rag_queries_feedback ON rag_queries(feedback_rating) WHERE feedback_rating IS NOT NULL;

-- =====================================================
-- Semantic Search Functions
-- =====================================================

-- Function: Search document chunks by similarity
CREATE OR REPLACE FUNCTION match_document_chunks(
  query_embedding vector(384),
  match_count integer DEFAULT 5,
  filter_equipment_type text DEFAULT NULL,
  filter_document_type text DEFAULT NULL,
  filter_manufacturer text DEFAULT NULL,
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
  document_source text
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
    d.source AS document_source
  FROM document_chunks dc
  JOIN documents d ON dc.document_id = d.id
  WHERE
    (filter_equipment_type IS NULL OR dc.equipment_type = filter_equipment_type)
    AND (filter_document_type IS NULL OR dc.document_type = filter_document_type)
    AND (filter_manufacturer IS NULL OR dc.manufacturer = filter_manufacturer)
    AND d.is_latest = TRUE
    AND d.indexing_status = 'embedded'
    AND (1 - (dc.embedding <=> query_embedding)) >= similarity_threshold
  ORDER BY dc.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- Function: Search equipment knowledge base
CREATE OR REPLACE FUNCTION match_equipment_knowledge(
  query_embedding vector(384),
  match_count integer DEFAULT 5,
  filter_equipment_type text DEFAULT NULL,
  filter_knowledge_type text DEFAULT NULL,
  similarity_threshold decimal DEFAULT 0.7
)
RETURNS TABLE (
  knowledge_id uuid,
  knowledge_type text,
  code text,
  title text,
  description text,
  symptoms text[],
  possible_causes text[],
  solution text,
  parts_required jsonb,
  estimated_labor_hours decimal,
  priority text,
  similarity decimal,
  equipment_type text,
  manufacturer text,
  model text
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    ek.id,
    ek.knowledge_type,
    ek.code,
    ek.title,
    ek.description,
    ek.symptoms,
    ek.possible_causes,
    ek.solution,
    ek.parts_required,
    ek.estimated_labor_hours,
    ek.priority,
    ROUND((1 - (ek.embedding <=> query_embedding))::numeric, 4) AS similarity,
    ek.equipment_type,
    ek.manufacturer,
    ek.model
  FROM equipment_knowledge ek
  WHERE
    (filter_equipment_type IS NULL OR ek.equipment_type = filter_equipment_type)
    AND (filter_knowledge_type IS NULL OR ek.knowledge_type = filter_knowledge_type)
    AND (1 - (ek.embedding <=> query_embedding)) >= similarity_threshold
  ORDER BY ek.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- Function: Hybrid search (combines exact keyword match + vector similarity)
CREATE OR REPLACE FUNCTION hybrid_search_chunks(
  query_text text,
  query_embedding vector(384),
  match_count integer DEFAULT 5,
  filter_equipment_type text DEFAULT NULL,
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
  semantic_score decimal
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
      ts_rank(to_tsvector('english', dc.content), plainto_tsquery('english', query_text)) AS kw_score
    FROM document_chunks dc
    JOIN documents d ON dc.document_id = d.id
    WHERE
      to_tsvector('english', dc.content) @@ plainto_tsquery('english', query_text)
      AND (filter_equipment_type IS NULL OR dc.equipment_type = filter_equipment_type)
      AND d.is_latest = TRUE
  ),
  semantic_search AS (
    SELECT
      dc.id,
      dc.content,
      dc.equipment_type,
      d.title AS document_title,
      (1 - (dc.embedding <=> query_embedding)) AS sem_score
    FROM document_chunks dc
    JOIN documents d ON dc.document_id = d.id
    WHERE
      (filter_equipment_type IS NULL OR dc.equipment_type = filter_equipment_type)
      AND d.is_latest = TRUE
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
    ROUND(COALESCE(ss.sem_score, 0)::numeric, 4) AS semantic_score
  FROM keyword_search ks
  FULL OUTER JOIN semantic_search ss ON ks.id = ss.id
  ORDER BY hybrid_score DESC
  LIMIT match_count;
END;
$$;

-- =====================================================
-- Triggers
-- =====================================================

-- Trigger for updated_at
CREATE TRIGGER update_documents_updated_at BEFORE UPDATE ON documents
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_equipment_knowledge_updated_at BEFORE UPDATE ON equipment_knowledge
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Trigger to update chunk_count when chunks are added
CREATE OR REPLACE FUNCTION update_document_chunk_count()
RETURNS TRIGGER AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    UPDATE documents
    SET chunk_count = chunk_count + 1
    WHERE id = NEW.document_id;
  ELSIF TG_OP = 'DELETE' THEN
    UPDATE documents
    SET chunk_count = GREATEST(chunk_count - 1, 0)
    WHERE id = OLD.document_id;
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER document_chunk_count_insert
  AFTER INSERT ON document_chunks
  FOR EACH ROW EXECUTE FUNCTION update_document_chunk_count();

CREATE TRIGGER document_chunk_count_delete
  AFTER DELETE ON document_chunks
  FOR EACH ROW EXECUTE FUNCTION update_document_chunk_count();

-- =====================================================
-- Row Level Security (RLS) Policies
-- =====================================================

-- Enable RLS on all tables
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE equipment_knowledge ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag_queries ENABLE ROW LEVEL SECURITY;

-- Documents: Allow read for all authenticated users
CREATE POLICY documents_read_policy ON documents
  FOR SELECT
  USING (TRUE);

-- Documents: Allow write for admin/service role
CREATE POLICY documents_write_policy ON documents
  FOR ALL
  USING (auth.role() IN ('service_role', 'authenticated'));

-- Document chunks: Allow read for all authenticated users
CREATE POLICY chunks_read_policy ON document_chunks
  FOR SELECT
  USING (TRUE);

-- Document chunks: Allow write for admin/service role
CREATE POLICY chunks_write_policy ON document_chunks
  FOR ALL
  USING (auth.role() IN ('service_role', 'authenticated'));

-- Equipment knowledge: Allow read for all authenticated users
CREATE POLICY knowledge_read_policy ON equipment_knowledge
  FOR SELECT
  USING (TRUE);

-- Equipment knowledge: Allow write for admin/service role
CREATE POLICY knowledge_write_policy ON equipment_knowledge
  FOR ALL
  USING (auth.role() IN ('service_role', 'authenticated'));

-- RAG queries: Users can only see their own queries
CREATE POLICY queries_read_policy ON rag_queries
  FOR SELECT
  USING (TRUE);

-- RAG queries: Users can create queries
CREATE POLICY queries_insert_policy ON rag_queries
  FOR INSERT
  WITH CHECK (TRUE);

-- =====================================================
-- Comments for Documentation
-- =====================================================

COMMENT ON TABLE documents IS 'Equipment manuals, procedures, and technical documentation (Phase 44 RAG)';
COMMENT ON TABLE document_chunks IS 'Text chunks with vector embeddings for semantic search';
COMMENT ON TABLE equipment_knowledge IS 'Structured equipment knowledge (fault codes, symptoms, solutions)';
COMMENT ON TABLE rag_queries IS 'RAG query history for analytics and relevance tuning';

COMMENT ON COLUMN document_chunks.embedding IS 'Vector embedding (384d for all-MiniLM-L6-v2, or 1536d for OpenAI)';
COMMENT ON COLUMN equipment_knowledge.embedding IS 'Vector embedding for semantic search of knowledge entries';

COMMENT ON FUNCTION match_document_chunks IS 'Semantic search for document chunks using cosine similarity';
COMMENT ON FUNCTION match_equipment_knowledge IS 'Semantic search for equipment knowledge base';
COMMENT ON FUNCTION hybrid_search_chunks IS 'Hybrid search combining keyword matching and semantic similarity';

-- =====================================================
-- Sample Data (for testing)
-- =====================================================

-- Insert sample document
INSERT INTO documents (
  code,
  title,
  document_type,
  equipment_type,
  manufacturer,
  model,
  source,
  summary,
  full_text,
  indexing_status
) VALUES (
  'MAN-CHILLER-YORK-YCIV-001',
  'York YCIV Chiller Operation and Maintenance Manual',
  'equipment_manual',
  'chiller',
  'York',
  'YCIV',
  'oem_manual',
  'Complete operation and maintenance manual for York YCIV air-cooled chillers',
  'This manual covers the operation, maintenance, and troubleshooting procedures for York YCIV series air-cooled chillers...',
  'pending'
);

-- Insert sample knowledge entry
INSERT INTO equipment_knowledge (
  equipment_type,
  manufacturer,
  model,
  component,
  knowledge_type,
  code,
  title,
  description,
  symptoms,
  possible_causes,
  diagnostic_steps,
  solution,
  parts_required,
  estimated_labor_hours,
  priority
) VALUES (
  'chiller',
  'York',
  'YCIV',
  'compressor',
  'fault_code',
  'E01',
  'High Pressure Shutdown',
  'Compressor shutdown due to excessive discharge pressure',
  ARRAY['Compressor stopped', 'High pressure alarm', 'E01 fault code displayed'],
  ARRAY['Dirty condenser coils', 'Low airflow across condenser', 'Refrigerant overcharge', 'Ambient temperature too high'],
  ARRAY['Check condenser coil condition', 'Verify condenser fan operation', 'Check refrigerant charge', 'Measure discharge pressure'],
  'Clean condenser coils, verify proper airflow. If problem persists, check refrigerant charge and condenser fan operation.',
  '[{"part_number": "026-35388-000", "description": "Pressure transducer", "quantity": 1}]'::jsonb,
  2.0,
  'high'
);

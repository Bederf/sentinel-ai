-- Phase 184: Voyage v4 embedding dimension migration
--
-- Voyage v4 defaults to 1024 dimensions. Existing MiniLM vectors are 384 dimensions
-- and are not compatible with the new vector columns. This migration deletes chunk
-- rows and resets document indexing state so the corpus can be re-embedded from the
-- source document rows/storage after operator approval.

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

DROP FUNCTION IF EXISTS match_document_chunks(vector, integer, text, text, text, uuid, decimal);
DROP FUNCTION IF EXISTS match_equipment_knowledge(vector, integer, text, text, decimal);
DROP FUNCTION IF EXISTS hybrid_search_chunks(text, vector, integer, text, uuid, decimal, decimal);

DROP INDEX IF EXISTS idx_chunks_embedding;
DROP INDEX IF EXISTS idx_knowledge_embedding;
DROP INDEX IF EXISTS idx_concept_chunks_embedding;

-- Existing 384-dim chunk vectors cannot be cast to 1024-dim vectors.
DELETE FROM document_chunks;
UPDATE documents
SET indexing_status = 'pending',
    indexed_at = NULL,
    chunk_count = 0
WHERE indexing_status = 'embedded';

DO $$
BEGIN
    IF to_regclass('public.concept_document_chunks') IS NOT NULL THEN
        DELETE FROM concept_document_chunks;
    END IF;

    IF to_regclass('public.concept_documents') IS NOT NULL THEN
        UPDATE concept_documents
        SET indexing_status = 'pending',
            indexed_at = NULL,
            chunk_count = 0
        WHERE indexing_status = 'embedded';
    END IF;
END;
$$;

UPDATE equipment_knowledge
SET embedding = NULL
WHERE embedding IS NOT NULL;

UPDATE rag_queries
SET query_embedding = NULL
WHERE query_embedding IS NOT NULL;

ALTER TABLE document_chunks
    ALTER COLUMN embedding TYPE vector(1024) USING NULL::vector(1024);

ALTER TABLE equipment_knowledge
    ALTER COLUMN embedding TYPE vector(1024) USING NULL::vector(1024);

ALTER TABLE rag_queries
    ALTER COLUMN query_embedding TYPE vector(1024) USING NULL::vector(1024);

DO $$
BEGIN
    IF to_regclass('public.concept_document_chunks') IS NOT NULL THEN
        ALTER TABLE concept_document_chunks
            ALTER COLUMN embedding TYPE vector(1024) USING NULL::vector(1024);
    END IF;
END;
$$;

CREATE INDEX idx_chunks_embedding ON document_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 130);

CREATE INDEX idx_knowledge_embedding ON equipment_knowledge
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 10);

DO $$
BEGIN
    IF to_regclass('public.concept_document_chunks') IS NOT NULL THEN
        CREATE INDEX idx_concept_chunks_embedding ON concept_document_chunks
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 10);
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION match_document_chunks(
    query_embedding vector(1024),
    match_count integer DEFAULT 5,
    filter_equipment_type text DEFAULT NULL,
    filter_document_type text DEFAULT NULL,
    filter_manufacturer text DEFAULT NULL,
    filter_site_id uuid DEFAULT NULL,
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
    site_id uuid
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
        dc.site_id
    FROM document_chunks dc
    JOIN documents d ON dc.document_id = d.id
    WHERE
        dc.embedding IS NOT NULL
        AND (filter_equipment_type IS NULL OR dc.equipment_type = filter_equipment_type)
        AND (filter_document_type IS NULL OR dc.document_type = filter_document_type)
        AND (filter_manufacturer IS NULL OR dc.manufacturer = filter_manufacturer)
        AND d.is_latest = TRUE
        AND d.indexing_status = 'embedded'
        AND (1 - (dc.embedding <=> query_embedding)) >= similarity_threshold
        AND (filter_site_id IS NULL
             OR dc.site_id = filter_site_id
             OR dc.site_id IS NULL)
    ORDER BY dc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

CREATE OR REPLACE FUNCTION match_equipment_knowledge(
    query_embedding vector(1024),
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
        ek.embedding IS NOT NULL
        AND (filter_equipment_type IS NULL OR ek.equipment_type = filter_equipment_type)
        AND (filter_knowledge_type IS NULL OR ek.knowledge_type = filter_knowledge_type)
        AND (1 - (ek.embedding <=> query_embedding)) >= similarity_threshold
    ORDER BY ek.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

CREATE OR REPLACE FUNCTION hybrid_search_chunks(
    query_text text,
    query_embedding vector(1024),
    match_count integer DEFAULT 5,
    filter_equipment_type text DEFAULT NULL,
    filter_site_id uuid DEFAULT NULL,
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
    site_id uuid,
    density text,
    element_type text
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH keyword_search AS (
        SELECT
            dc.id, dc.content, dc.equipment_type,
            d.title AS document_title, dc.site_id,
            dc.density, dc.element_type,
            ts_rank(to_tsvector('english', dc.content), plainto_tsquery('english', query_text)) AS kw_score
        FROM document_chunks dc
        JOIN documents d ON dc.document_id = d.id
        WHERE
            to_tsvector('english', dc.content) @@ plainto_tsquery('english', query_text)
            AND (filter_equipment_type IS NULL OR dc.equipment_type = filter_equipment_type)
            AND d.is_latest = TRUE
            AND (filter_site_id IS NULL
                 OR dc.site_id = filter_site_id
                 OR dc.site_id IS NULL)
    ),
    semantic_search AS (
        SELECT
            dc.id, dc.content, dc.equipment_type,
            d.title AS document_title, dc.site_id,
            dc.density, dc.element_type,
            (1 - (dc.embedding <=> query_embedding)) AS sem_score
        FROM document_chunks dc
        JOIN documents d ON dc.document_id = d.id
        WHERE
            dc.embedding IS NOT NULL
            AND (filter_equipment_type IS NULL OR dc.equipment_type = filter_equipment_type)
            AND d.is_latest = TRUE
            AND (filter_site_id IS NULL
                 OR dc.site_id = filter_site_id
                 OR dc.site_id IS NULL)
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
        COALESCE(ks.site_id, ss.site_id) AS site_id,
        COALESCE(ks.density, ss.density) AS density,
        COALESCE(ks.element_type, ss.element_type) AS element_type
    FROM keyword_search ks
    FULL OUTER JOIN semantic_search ss ON ks.id = ss.id
    ORDER BY hybrid_score DESC
    LIMIT match_count;
END;
$$;

COMMENT ON COLUMN document_chunks.embedding IS 'Vector embedding (1024d for Voyage v4)';
COMMENT ON COLUMN equipment_knowledge.embedding IS 'Vector embedding (1024d for Voyage v4)';
COMMENT ON COLUMN rag_queries.query_embedding IS 'Query embedding (1024d for Voyage v4)';
DO $$
BEGIN
    IF to_regclass('public.concept_document_chunks') IS NOT NULL THEN
        COMMENT ON COLUMN concept_document_chunks.embedding IS 'Vector embedding (1024d for Voyage v4)';
    END IF;
END;
$$;
COMMENT ON FUNCTION match_document_chunks(vector, integer, text, text, text, uuid, numeric) IS 'Semantic search for document chunks using Voyage v4 1024d cosine similarity';
COMMENT ON FUNCTION match_equipment_knowledge(vector, integer, text, text, numeric) IS 'Semantic search for equipment knowledge using Voyage v4 1024d cosine similarity';
COMMENT ON FUNCTION hybrid_search_chunks(text, vector, integer, text, uuid, numeric, numeric) IS 'Hybrid search with Voyage v4 1024d semantic vectors and adaptive chunk metadata';

COMMIT;

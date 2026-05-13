-- Add density + element_type to hybrid_search_chunks for Phase C filtered retrieval
-- Phase: adaptive-chunking quick win (Phase C)
-- Date: 2026-05-08

BEGIN;

-- Drop ALL existing overloads before recreating (CASCADE removes all signatures)
DROP FUNCTION IF EXISTS hybrid_search_chunks CASCADE;

-- Recreate with density + element_type in RETURN TABLE and CTAs
CREATE OR REPLACE FUNCTION hybrid_search_chunks(
    query_text text,
    query_embedding vector(384),
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
            (filter_equipment_type IS NULL OR dc.equipment_type = filter_equipment_type)
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

COMMENT ON FUNCTION hybrid_search_chunks IS
    'Hybrid search with adaptive-chunking metadata: density and element_type for filtered retrieval';

COMMIT;

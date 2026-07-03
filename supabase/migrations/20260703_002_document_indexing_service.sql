-- DocumentIndexingService lifecycle support.

ALTER TABLE public.documents ADD COLUMN IF NOT EXISTS asset_id text;
ALTER TABLE public.documents ADD COLUMN IF NOT EXISTS indexing_error text;

ALTER TABLE public.documents DROP CONSTRAINT IF EXISTS documents_indexing_status_check;
ALTER TABLE public.documents ADD CONSTRAINT documents_indexing_status_check
CHECK (
    indexing_status = ANY (
        ARRAY[
            'pending',
            'extracting',
            'embedding',
            'complete',
            'failed',
            'quarantine',
            -- legacy values still present in older rows/scripts
            'chunking',
            'embedded',
            'site_network_only'
        ]::text[]
    )
);

DROP FUNCTION IF EXISTS public.match_document_chunks(vector, integer, text, text, text, uuid, decimal, text);

CREATE OR REPLACE FUNCTION public.match_document_chunks(
    query_embedding vector(1024),
    match_count integer DEFAULT 5,
    filter_equipment_type text DEFAULT NULL,
    filter_document_type text DEFAULT NULL,
    filter_manufacturer text DEFAULT NULL,
    filter_site_id uuid DEFAULT NULL,
    similarity_threshold decimal DEFAULT 0.7,
    filter_doc_class text DEFAULT NULL
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
    site_id uuid,
    doc_class text
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
        dc.site_id,
        dc.doc_class
    FROM public.document_chunks dc
    JOIN public.documents d ON dc.document_id = d.id
    WHERE
        dc.embedding IS NOT NULL
        AND (filter_doc_class IS NULL OR dc.doc_class = filter_doc_class)
        AND (filter_equipment_type IS NULL OR dc.equipment_type = filter_equipment_type)
        AND (filter_document_type IS NULL OR dc.document_type = filter_document_type)
        AND (filter_manufacturer IS NULL OR dc.manufacturer = filter_manufacturer)
        AND d.is_latest = TRUE
        AND d.indexing_status IN ('embedded', 'complete')
        AND (1 - (dc.embedding <=> query_embedding)) >= similarity_threshold
        AND (filter_site_id IS NULL
             OR dc.site_id = filter_site_id
             OR dc.site_id IS NULL)
    ORDER BY dc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

DROP FUNCTION IF EXISTS public.hybrid_search_chunks(text, vector, integer, text, uuid, decimal, decimal, text);

CREATE OR REPLACE FUNCTION public.hybrid_search_chunks(
    query_text text,
    query_embedding vector(1024),
    match_count integer DEFAULT 5,
    filter_equipment_type text DEFAULT NULL,
    filter_site_id uuid DEFAULT NULL,
    keyword_weight decimal DEFAULT 0.3,
    semantic_weight decimal DEFAULT 0.7,
    filter_doc_class text DEFAULT NULL
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
    element_type text,
    doc_class text
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH keyword_search AS (
        SELECT
            dc.id, dc.content, dc.equipment_type,
            d.title AS document_title, dc.site_id,
            dc.density, dc.element_type, dc.doc_class,
            ts_rank(to_tsvector('english', dc.content), plainto_tsquery('english', query_text)) AS kw_score
        FROM public.document_chunks dc
        JOIN public.documents d ON dc.document_id = d.id
        WHERE
            to_tsvector('english', dc.content) @@ plainto_tsquery('english', query_text)
            AND (filter_doc_class IS NULL OR dc.doc_class = filter_doc_class)
            AND (filter_equipment_type IS NULL OR dc.equipment_type = filter_equipment_type)
            AND d.is_latest = TRUE
            AND d.indexing_status IN ('embedded', 'complete')
            AND (filter_site_id IS NULL
                 OR dc.site_id = filter_site_id
                 OR dc.site_id IS NULL)
    ),
    semantic_search AS (
        SELECT
            dc.id, dc.content, dc.equipment_type,
            d.title AS document_title, dc.site_id,
            dc.density, dc.element_type, dc.doc_class,
            (1 - (dc.embedding <=> query_embedding)) AS sem_score
        FROM public.document_chunks dc
        JOIN public.documents d ON dc.document_id = d.id
        WHERE
            dc.embedding IS NOT NULL
            AND (filter_doc_class IS NULL OR dc.doc_class = filter_doc_class)
            AND (filter_equipment_type IS NULL OR dc.equipment_type = filter_equipment_type)
            AND d.is_latest = TRUE
            AND d.indexing_status IN ('embedded', 'complete')
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
        COALESCE(ks.element_type, ss.element_type) AS element_type,
        COALESCE(ks.doc_class, ss.doc_class) AS doc_class
    FROM keyword_search ks
    FULL OUTER JOIN semantic_search ss ON ks.id = ss.id
    ORDER BY hybrid_score DESC
    LIMIT match_count;
END;
$$;

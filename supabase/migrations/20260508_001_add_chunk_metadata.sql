-- Add chunk density and element_type columns for adaptive chunking retrieval
-- Phase: adaptive-chunking quick win
-- Date: 2026-05-08

BEGIN;

ALTER TABLE document_chunks
    ADD COLUMN IF NOT EXISTS density TEXT DEFAULT 'balanced'
        CHECK (density IN ('dense', 'balanced', 'light')),
    ADD COLUMN IF NOT EXISTS element_type TEXT DEFAULT 'paragraph'
        CHECK (element_type IN (
            'paragraph', 'heading', 'table', 'table_row',
            'list', 'formula', 'caption', 'image'
        ));

-- Index for filtered retrieval by density band
CREATE INDEX IF NOT EXISTS idx_chunks_density
    ON document_chunks (density)
    WHERE density IS NOT NULL;

-- Index for filtered retrieval by element type
CREATE INDEX IF NOT EXISTS idx_chunks_element_type
    ON document_chunks (element_type)
    WHERE element_type IS NOT NULL;

COMMENT ON COLUMN document_chunks.density IS
    'Semantic density band used for chunking: dense (200w), balanced (512w), light (800w)';
COMMENT ON COLUMN document_chunks.element_type IS
    'OpenDataLoader element type at time of chunking';

COMMIT;

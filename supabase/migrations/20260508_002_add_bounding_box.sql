-- Add bounding_box column for spatial citation support in tech chat
-- Phase: adaptive-chunking B (OpenDataLoader swap)
-- Date: 2026-05-08

BEGIN;

ALTER TABLE document_chunks
    ADD COLUMN IF NOT EXISTS bounding_box jsonb
        DEFAULT null
        CHECK (bounding_box IS NULL OR (
            jsonb_typeof(bounding_box) = 'array'
            AND jsonb_array_length(bounding_box) = 4
            AND jsonb_path_exists(bounding_box, '$[*] ? (@ != 0)')
        ));

COMMENT ON COLUMN document_chunks.bounding_box IS
    'Bounding box [l, t, r, b] for element-level citation in tech chat. null when using legacy chunking path.';

CREATE INDEX IF NOT EXISTS idx_chunks_bounding_box
    ON document_chunks USING GIN (bounding_box)
    WHERE bounding_box IS NOT NULL;

COMMIT;

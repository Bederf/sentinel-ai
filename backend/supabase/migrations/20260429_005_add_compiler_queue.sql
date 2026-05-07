-- Migration 20260429_005: Add compiler_queue table for wiki compilation pipeline
-- Required by: WikiCompilerService.poll_and_process() — Phase 179-181 asset documentation pipeline

BEGIN;

CREATE TABLE IF NOT EXISTS compiler_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id TEXT NOT NULL,
    document_id UUID NOT NULL,
    queued_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    priority INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for unprocessed entries (polling query)
CREATE INDEX IF NOT EXISTS idx_compiler_queue_unprocessed
    ON compiler_queue(processed_at NULLS FIRST, queued_at)
    WHERE processed_at IS NULL;

-- Index for asset lookup
CREATE INDEX IF NOT EXISTS idx_compiler_queue_asset
    ON compiler_queue(asset_id, queued_at DESC);

COMMENT ON TABLE compiler_queue IS 'Queue for async wiki compilation of asset documents';

COMMIT;

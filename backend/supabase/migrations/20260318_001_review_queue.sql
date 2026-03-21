-- Review Queue for Semantic Classifications (Phase 162A)
-- Plan 05: Human-in-the-loop review interface for semantic classification decisions

CREATE TABLE IF NOT EXISTS review_queue (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id text NOT NULL,
    equipment_id text NOT NULL,
    point_id text NOT NULL,
    classification_id uuid NOT NULL,  -- References point_classification.id

    -- Classification details
    semantic_tags text[] NOT NULL,  -- Array of semantic tags
    confidence_score float NOT NULL,
    confidence_level text NOT NULL,  -- HIGH, MEDIUM, LOW
    safety_class text NOT NULL,  -- LOW, MEDIUM, HIGH
    automation_tier text NOT NULL,  -- observe_only, supervised, automatic

    -- Validation results
    validation_passed boolean NOT NULL DEFAULT false,
    validation_errors jsonb,  -- Array of validation errors
    completeness_score float,

    -- Review metadata
    status text NOT NULL DEFAULT 'pending',  -- pending, approved, rejected, overridden
    priority integer NOT NULL DEFAULT 100,  -- Lower = higher priority

    -- Audit trail
    classified_by text NOT NULL,  -- 'rule_based_v1' or other classifier ID
    classified_at timestamptz NOT NULL DEFAULT now(),

    -- Review decision
    reviewed_by text,  -- User ID who made the decision
    reviewed_at timestamptz,
    review_notes text,
    decision_reason text,  -- accept, reject, override_mismatch, override_incomplete

    -- Override data (if manually corrected)
    override_tags text[],
    override_confidence float,
    override_justification text,

    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_review_queue_site ON review_queue (site_id) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_review_queue_priority ON review_queue (priority) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_review_queue_safety_class ON review_queue (safety_class) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_review_queue_confidence ON review_queue (confidence_score) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_review_queue_equipment ON review_queue (equipment_id) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_review_queue_classified_at ON review_queue (classified_at) WHERE status = 'pending';

-- Enable RLS
ALTER TABLE review_queue ENABLE ROW LEVEL SECURITY;
CREATE POLICY IF NOT EXISTS review_queue_read ON review_queue FOR SELECT USING (true);
CREATE POLICY IF NOT EXISTS review_queue_write ON review_queue FOR UPDATE USING (auth.uid() IS NOT NULL);

-- Review decisions log (audit trail)
CREATE TABLE IF NOT EXISTS review_decisions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    review_queue_id uuid NOT NULL REFERENCES review_queue(id),
    decision_type text NOT NULL,  -- approve, reject, override
    decision_reason text,
    reviewed_by text NOT NULL,
    reviewed_at timestamptz NOT NULL DEFAULT now(),
    review_notes text,
    metadata jsonb,  -- Additional context

    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_review_decisions_queue_id ON review_decisions (review_queue_id);
CREATE INDEX IF NOT EXISTS idx_review_decisions_reviewed_by ON review_decisions (reviewed_by);
CREATE INDEX IF NOT EXISTS idx_review_decisions_reviewed_at ON review_decisions (reviewed_at);

-- Phase 131: SENTINEL Email Intake Pipeline
-- Creates email_intakes table for automated FM email processing
-- Supports: intake, dedup, follow-up linking, BMS enrichment, Concept integration

CREATE TABLE IF NOT EXISTS email_intakes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Requester identity
    from_email      TEXT NOT NULL,
    from_name       TEXT,
    from_phone      TEXT,
    from_department  TEXT,

    -- Email metadata
    subject         TEXT NOT NULL,
    body_plain      TEXT,
    message_id      TEXT UNIQUE,                 -- RFC 822 Message-ID for dedup
    in_reply_to     TEXT,                        -- threading
    received_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- AI extraction fields (populated by n8n GPT-4.1 step)
    site_id         TEXT,                        -- no FK in v1
    zone_hint       TEXT,
    floor_hint      TEXT,
    issue_category  TEXT,                        -- hvac, electrical, plumbing, fire, access, elevator, pest, general
    issue_summary   TEXT,
    urgency         TEXT DEFAULT 'normal',       -- low, normal, high, critical
    extraction_confidence FLOAT DEFAULT 0.0,
    extraction_model TEXT,
    extraction_raw  JSONB,                       -- full AI response for audit

    -- BMS enrichment (populated by backend)
    bms_context     JSONB,                       -- active alerts, recent WOs, equipment health
    enrichment_ts   TIMESTAMPTZ,

    -- Pipeline status
    pipeline_status TEXT NOT NULL DEFAULT 'received',
    -- received → enriched → routed → submitted → closed
    action_taken    TEXT,                         -- new_intake, linked_existing, duplicate, request_info, auto_submit, manual_review
    routing_reason  TEXT,

    -- Concept / external WO integration
    existing_reference TEXT,                      -- e.g. FNBFW:12345
    concept_ref     TEXT,                        -- Concept work order ref once created
    local_wo_id     UUID REFERENCES work_orders(id),

    -- Follow-up / duplicate tracking
    parent_intake_id UUID REFERENCES email_intakes(id),
    follow_up_count  INT DEFAULT 0,

    -- Attachments metadata
    attachment_count INT DEFAULT 0,
    attachment_refs  JSONB,                      -- [{filename, mime, size_kb, storage_key}]

    -- Audit
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_by    TEXT DEFAULT 'sentinel',
    notes           TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_email_intakes_status
    ON email_intakes (pipeline_status);
CREATE INDEX IF NOT EXISTS idx_email_intakes_from
    ON email_intakes (from_email);
CREATE INDEX IF NOT EXISTS idx_email_intakes_site
    ON email_intakes (site_id);
CREATE INDEX IF NOT EXISTS idx_email_intakes_concept_ref
    ON email_intakes (concept_ref) WHERE concept_ref IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_email_intakes_received
    ON email_intakes (received_at DESC);
CREATE INDEX IF NOT EXISTS idx_email_intakes_category
    ON email_intakes (issue_category);
CREATE INDEX IF NOT EXISTS idx_email_intakes_urgency
    ON email_intakes (urgency) WHERE urgency IN ('high', 'critical');
CREATE INDEX IF NOT EXISTS idx_email_intakes_dedup
    ON email_intakes (from_email, site_id, issue_category, received_at DESC);

-- Auto-update trigger
CREATE OR REPLACE FUNCTION update_email_intakes_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_email_intakes_updated_at ON email_intakes;
CREATE TRIGGER trg_email_intakes_updated_at
    BEFORE UPDATE ON email_intakes
    FOR EACH ROW
    EXECUTE FUNCTION update_email_intakes_updated_at();

-- RLS: service_role only
ALTER TABLE email_intakes ENABLE ROW LEVEL SECURITY;

CREATE POLICY email_intakes_service_role
    ON email_intakes
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

COMMENT ON TABLE email_intakes IS 'Phase 131: Automated FM email intake pipeline — stores parsed, enriched, and routed email requests';
COMMENT ON COLUMN email_intakes.message_id IS 'RFC 822 Message-ID header for exact dedup';
COMMENT ON COLUMN email_intakes.existing_reference IS 'External reference code (e.g. FNBFW:12345) detected in email';
COMMENT ON COLUMN email_intakes.extraction_confidence IS 'AI classification confidence 0.0-1.0 from n8n GPT step';
COMMENT ON COLUMN email_intakes.pipeline_status IS 'received → enriched → routed → submitted → closed';

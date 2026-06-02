-- Migration: residential_recommendations
-- Purpose: Store delivered AI recommendations for residential sites
-- Enables outcome tracking and dedup across delivery attempts

CREATE TABLE residential_recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES residential_sites(id),
    chat_id BIGINT,
    platform VARCHAR DEFAULT 'solarman',

    -- Recommendation content
    title VARCHAR NOT NULL,
    message TEXT NOT NULL,
    action_app VARCHAR,  -- "SOLARMAN app" | "Victron VRM portal" | "Home Assistant"
    severity VARCHAR NOT NULL,  -- "advisory" | "opportunity" | "warning"
    trigger VARCHAR,  -- what condition triggered this
    expected_benefit TEXT,
    cost_impact_zar FLOAT,  -- null if no estimate
    confidence FLOAT,  -- 0.0-1.0 from AI model

    -- Delivery tracking
    delivered_at TIMESTAMPTZ DEFAULT NOW(),
    outcome_improved BOOLEAN,  -- null = not yet measured, true/false after outcome check
    outcome_measured_at TIMESTAMPTZ,

    -- Deduplication key (SHA1 of title:severity)
    dedup_hash VARCHAR(12)
);

CREATE INDEX idx_res_recs_site_id ON residential_recommendations(site_id);
CREATE INDEX idx_res_recs_delivered_at ON residential_recommendations(delivered_at DESC);
CREATE INDEX idx_res_recs_dedup ON residential_recommendations(site_id, dedup_hash);

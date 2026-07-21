-- Migration 233: Progression Engine — Trust Ladder Foundation
-- Purpose: Tables for tracking recommendation validation outcomes and per-class trust readiness.
-- Phase A of the SENTINEL Autonomous Building Operator progression engine.
-- Creates: recommendation_validations, recommendation_class_readiness
-- Alters: recommendations (adds predicted_delta column)

BEGIN;

-- ============================================================================
-- Table: recommendation_validations
-- Tracks every recommendation's predicted vs actual outcome.
-- The atomic evidence unit for trust-ladder progression.
-- ============================================================================
CREATE TABLE IF NOT EXISTS recommendation_validations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recommendation_id   UUID NOT NULL REFERENCES recommendations(id) ON DELETE CASCADE,
    site_id             TEXT NOT NULL,
    action_type         TEXT NOT NULL,
    equipment_code      TEXT,

    -- Predicted outcome (from ML context + action metadata)
    predicted_delta     JSONB,
    predicted_confidence FLOAT,

    -- Actual outcome (from telemetry delta after execution)
    actual_delta        JSONB,
    outcome_accuracy    FLOAT,

    -- Operator feedback
    operator_feedback   TEXT,
    operator_note       TEXT,

    -- Status tracking
    validation_status   TEXT NOT NULL DEFAULT 'pending_operator'
                        CHECK (validation_status IN ('pending_operator', 'pending_telemetry', 'validated', 'disputed')),
    accuracy_category   TEXT,
    validation_class    TEXT NOT NULL,
    outcome_status      TEXT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    validated_at        TIMESTAMPTZ
);

-- Query indexes
CREATE INDEX IF NOT EXISTS idx_recommendation_validations_recommendation_id
    ON recommendation_validations(recommendation_id);
CREATE INDEX IF NOT EXISTS idx_recommendation_validations_site_id
    ON recommendation_validations(site_id);
CREATE INDEX IF NOT EXISTS idx_recommendation_validations_class
    ON recommendation_validations(validation_class);
CREATE INDEX IF NOT EXISTS idx_recommendation_validations_site_class_validated
    ON recommendation_validations(site_id, validation_class, validated_at)
    WHERE validated_at IS NOT NULL;

-- ============================================================================
-- Table: recommendation_class_readiness
-- Rolling accuracy and trust level per recommendation class per site.
-- Enables per-class progression (e.g., schedule_corrections at Level 3 while
-- hvac_setpoint_change stays at Level 2).
-- ============================================================================
CREATE TABLE IF NOT EXISTS recommendation_class_readiness (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id                 TEXT NOT NULL,
    class_name              TEXT NOT NULL,

    -- Trust level (0=Shadow, 1=Advisory, 2=Supervised, 3=Autonomous)
    current_trust_level     INT NOT NULL DEFAULT 1
                            CHECK (current_trust_level >= 0 AND current_trust_level <= 3),

    -- Evidence and accuracy
    evidence_count          INT NOT NULL DEFAULT 0,
    accuracy_pct_7d         FLOAT,
    accuracy_pct_30d        FLOAT,

    -- Consecutive tracking for demotion detection
    consecutive_successes   INT NOT NULL DEFAULT 0,
    consecutive_failures    INT NOT NULL DEFAULT 0,

    -- Timestamps
    last_validation_at      TIMESTAMPTZ,
    last_demotion_at        TIMESTAMPTZ,
    demotion_reason         TEXT,

    -- Operator overrides
    operator_hold_until     DATE,
    operator_override_level INT,

    -- Metadata
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(site_id, class_name)
);

CREATE INDEX IF NOT EXISTS idx_recommendation_class_readiness_site
    ON recommendation_class_readiness(site_id);

-- ============================================================================
-- Alter recommendations table: add predicted_delta column
-- Captures the predicted deltas at recommendation creation time for later
-- comparison against actual telemetry deltas post-execution.
-- ============================================================================
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS predicted_delta JSONB;

COMMIT;

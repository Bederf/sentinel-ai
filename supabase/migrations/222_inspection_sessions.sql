-- Migration: 222_inspection_sessions
-- Phase: Post-221 hardening — Persist Tier 3 checklist state on each item answer
-- Purpose: InspectionSession was in-memory only (process-local dict in
--          telegram_conversation_manager). If openclaw restarts mid-checklist,
--          current_index and responses dict are lost — tech gets no feedback.
--
-- This table enables the closeout skill to upsert state per answer and resume
-- on reconnect. Keyed on (wo_code, telegram_user_id) for one active session
-- per technician per WO.

CREATE TABLE IF NOT EXISTS sentry_inspection_sessions (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    wo_code         text        NOT NULL,
    telegram_user_id text       NOT NULL,
    equipment_code  text,
    equipment_type  text,
    checklist_items jsonb       NOT NULL DEFAULT '[]'::jsonb,
    responses       jsonb       NOT NULL DEFAULT '{}'::jsonb,
    current_index   integer     NOT NULL DEFAULT 0,
    status          text        NOT NULL DEFAULT 'in_progress'
                                CHECK (status IN ('in_progress', 'completed', 'abandoned')),
    started_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (wo_code, telegram_user_id)
);

CREATE INDEX IF NOT EXISTS idx_inspection_sessions_status ON sentry_inspection_sessions (status);
CREATE INDEX IF NOT EXISTS idx_inspection_sessions_wo     ON sentry_inspection_sessions (wo_code);

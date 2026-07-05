-- ============================================================================
-- Service Records — child tables for structured technician readings
-- Migration: 20260705_service_records_child_tables.sql
-- Created: 2026-07-05
-- Purpose: Phase A.1 — surface periodic baseline rollups
--
-- The ServiceRecordRepository in backend/app/database/repositories/
-- service_record_repository.py (lines 66-96) already implements
-- add_reading / add_attachment / add_observation against these tables,
-- but the tables themselves have never been created in the deployed
-- Supabase schema. This migration creates them.
--
-- Why: failure-predictions page needs structured numeric readings
-- (vibration mm/s, acoustic dB, oil pressure PSI, coolant temp °C, …)
-- separate from the FM-facing inspection_results status enum.
-- Rollup service (Phase B) consumes service_readings; FM notif keeps
-- its existing contract against inspection_results.
--
-- Naming: matches the row samples captured at /equipment_baselines for
-- equipment_baselines. service_records is the parent; these three
-- tables FK to service_records.id with ON DELETE CASCADE so cleanup
-- of a service record removes its children.
-- ============================================================================

-- ── service_readings ────────────────────────────────────────────────────────
-- One row per numeric measurement per service visit. The rollup service
-- computes the equipment_baselines.baseline_values.sigma / n / value
-- per element_id from this table across the last W=8 visits.

CREATE TABLE IF NOT EXISTS public.service_readings (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    service_record_id  uuid NOT NULL REFERENCES public.service_records(id) ON DELETE CASCADE,
    reading_type       text,
    element_id         text,
    value              text,
    numeric_value      double precision,
    unit               text,
    source             text NOT NULL DEFAULT 'manual',
    confidence         double precision CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    captured_at        timestamptz NOT NULL DEFAULT now(),
    raw_text           text,
    attachment_id      uuid,
    created_at         timestamptz NOT NULL DEFAULT now(),
    CHECK (reading_type IS NOT NULL OR element_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_service_readings_record
    ON public.service_readings (service_record_id);

CREATE INDEX IF NOT EXISTS idx_service_readings_element
    ON public.service_readings (element_id, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_service_readings_type
    ON public.service_readings (reading_type, captured_at DESC);

-- ── service_attachments ─────────────────────────────────────────────────────
-- File references for service visits (balancer PDF, IR image, oil-analysis
-- sheet, photo of meter reading). file_id is the existing documents.id or
-- a Telegram file_id string — we don't enforce FK so we can support both
-- pre-ingested and Telegram-direct uploads.

CREATE TABLE IF NOT EXISTS public.service_attachments (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    service_record_id  uuid NOT NULL REFERENCES public.service_records(id) ON DELETE CASCADE,
    attachment_type    text,
    file_path          text,
    file_name          text,
    file_size_bytes    bigint,
    mime_type          text,
    extracted_data     jsonb,
    analysis_status    text NOT NULL DEFAULT 'pending',
    file_id            text,
    file_type          text,
    captured_at        timestamptz NOT NULL DEFAULT now(),
    ocr_processed      boolean NOT NULL DEFAULT false,
    created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_service_attachments_record
    ON public.service_attachments (service_record_id);

-- ── service_observations ────────────────────────────────────────────────────
-- Narrative answers (closeout debrief). Stored alongside the structured
-- service_readings rows. Distinct from inspection_results.items[] which
-- keeps the FM-facing status enum contract.

CREATE TABLE IF NOT EXISTS public.service_observations (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    service_record_id  uuid NOT NULL REFERENCES public.service_records(id) ON DELETE CASCADE,
    observation_type   text,
    content            text,
    audio_file_path    text,
    duration_seconds   double precision,
    sentiment          text,
    key_phrases        text[],
    issue_flags        text[],
    question           text,
    answer             text,
    status             text NOT NULL DEFAULT 'ok'
        CHECK (status IN ('ok', 'warning', 'critical', 'skipped')),
    captured_at        timestamptz NOT NULL DEFAULT now(),
    created_at         timestamptz NOT NULL DEFAULT now(),
    CHECK (observation_type IS NOT NULL OR question IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_service_observations_record
    ON public.service_observations (service_record_id);

-- ── RLS: service_record_id is internal — keep service-account RW, anon R-off ─
-- The existing service_records table has its own RLS; defer matching RLS on
-- these child tables to a follow-up migration (Phase E audit hardening) so
-- this migration stays scoped to "create the structure" without behaviour
-- change.

-- ── Rollback (for reference — keep as comment, no separate rollback file) ───
-- DROP TABLE IF EXISTS public.service_observations;
-- DROP TABLE IF EXISTS public.service_attachments;
-- DROP TABLE IF EXISTS public.service_readings;

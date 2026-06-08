-- Migration: inspection_schedules, inspection_tasks, inspection_results, inspection_deficiencies
-- Phase 45: Routine Inspection & Maintenance persistence layer
-- Created: 2026-06-06

BEGIN;

-- ─── inspection_schedules ─────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.inspection_schedules (
    id                          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    equipment_id                text NOT NULL,
    element_id                  text,
    schedule_name               text NOT NULL,
    schedule_description        text,
    frequency_type              text NOT NULL,      -- daily|weekly|monthly|quarterly|annually|custom
    frequency_days              integer,
    day_of_week                 integer,
    day_of_month                integer,
    estimated_duration_minutes  integer NOT NULL DEFAULT 60,
    preferred_time_of_day       text,
    assigned_to                 text,
    required_skills             text[],
    is_active                   boolean NOT NULL DEFAULT true,
    last_generated_date         timestamptz,
    next_due_date               timestamptz,
    created_by                  text NOT NULL,
    created_at                  timestamptz NOT NULL DEFAULT now(),
    updated_at                  timestamptz NOT NULL DEFAULT now()
);

-- ─── inspection_tasks ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.inspection_tasks (
    id                          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    schedule_id                 uuid REFERENCES public.inspection_schedules(id) ON DELETE SET NULL,
    task_name                   text NOT NULL,
    task_description            text,
    equipment_id                text NOT NULL,
    element_id                  text,
    scheduled_date              timestamptz NOT NULL,
    due_date                    timestamptz NOT NULL,
    assigned_to                 text,
    assigned_by                 text,
    status                      text NOT NULL DEFAULT 'scheduled',  -- scheduled|in_progress|completed|cancelled|overdue
    completed_date              timestamptz,
    completed_by                text,
    completion_notes            text,
    estimated_duration_minutes  integer,
    actual_duration_minutes     integer,
    priority                    text NOT NULL DEFAULT 'normal',      -- low|normal|high|critical
    is_critical                 boolean NOT NULL DEFAULT false,
    checklist_template_id       uuid,
    baseline_reference_id       uuid,
    created_at                  timestamptz NOT NULL DEFAULT now(),
    updated_at                  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_inspection_tasks_equipment ON public.inspection_tasks(equipment_id);
CREATE INDEX IF NOT EXISTS idx_inspection_tasks_status ON public.inspection_tasks(status);
CREATE INDEX IF NOT EXISTS idx_inspection_tasks_due_date ON public.inspection_tasks(due_date);

-- ─── inspection_results ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.inspection_results (
    id                              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id                         uuid NOT NULL REFERENCES public.inspection_tasks(id) ON DELETE CASCADE,
    equipment_id                    text NOT NULL,
    inspected_by                    text NOT NULL,
    inspection_date                 timestamptz NOT NULL DEFAULT now(),
    overall_status                  text NOT NULL,   -- pass|fail|pass_with_issues
    item_results                    jsonb NOT NULL DEFAULT '[]'::jsonb,
    measurements                    jsonb,
    deficiencies_found              integer NOT NULL DEFAULT 0,
    critical_findings               integer NOT NULL DEFAULT 0,
    ambient_conditions              jsonb,
    started_at                      timestamptz,
    completed_at                    timestamptz,
    general_notes                   text,
    recommendations                 text,
    photo_urls                      text[],
    recommended_next_inspection_date timestamptz,
    created_at                      timestamptz NOT NULL DEFAULT now(),
    updated_at                      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_inspection_results_equipment ON public.inspection_results(equipment_id);
CREATE INDEX IF NOT EXISTS idx_inspection_results_task ON public.inspection_results(task_id);
CREATE INDEX IF NOT EXISTS idx_inspection_results_date ON public.inspection_results(inspection_date DESC);

-- ─── inspection_deficiencies ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.inspection_deficiencies (
    id                          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    result_id                   uuid REFERENCES public.inspection_results(id) ON DELETE CASCADE,
    task_id                     uuid REFERENCES public.inspection_tasks(id) ON DELETE SET NULL,
    equipment_id                text NOT NULL,
    element_id                  text,
    deficiency_title            text NOT NULL,
    deficiency_description      text,
    severity                    text NOT NULL,       -- minor|moderate|major|critical
    category                    text,               -- mechanical|electrical|operational|safety|environmental|other
    location_detail             text,
    checklist_item_id           text,
    impact_description          text,
    urgency                     text,
    recommended_action          text,
    estimated_repair_cost_min   numeric(10,2),
    estimated_repair_cost_max   numeric(10,2),
    estimated_repair_hours      integer,
    is_resolved                 boolean NOT NULL DEFAULT false,
    resolved_date               timestamptz,
    resolved_by                 text,
    resolution_notes            text,
    work_order_id               text,
    reported_by                 text,
    photo_urls                  text[],
    created_at                  timestamptz NOT NULL DEFAULT now(),
    updated_at                  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_inspection_deficiencies_equipment ON public.inspection_deficiencies(equipment_id);
CREATE INDEX IF NOT EXISTS idx_inspection_deficiencies_unresolved ON public.inspection_deficiencies(is_resolved) WHERE is_resolved = false;

-- ─── updated_at triggers ──────────────────────────────────────────────────────

CREATE OR REPLACE TRIGGER update_inspection_schedules_updated_at
    BEFORE UPDATE ON public.inspection_schedules
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE OR REPLACE TRIGGER update_inspection_tasks_updated_at
    BEFORE UPDATE ON public.inspection_tasks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE OR REPLACE TRIGGER update_inspection_results_updated_at
    BEFORE UPDATE ON public.inspection_results
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE OR REPLACE TRIGGER update_inspection_deficiencies_updated_at
    BEFORE UPDATE ON public.inspection_deficiencies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMIT;

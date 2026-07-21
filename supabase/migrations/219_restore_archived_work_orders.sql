-- Phase 209-01: Restore archived tables that broke production code paths
-- Migration: 209-01_restore_archived_work_orders.sql
-- Date: 2026-05-10
-- Problem: Phase 208-10 archived work_orders, audit_log, and notification_delivery_logs
--   to _deprecated schema, breaking 3 production code paths:
--     1. AuditRepository.create() — INSERT silently fails (audit_log missing)
--     2. POST /api/sentry/create-work-order — table doesn't exist
--     3. PATCH /api/sentry/wo-milestone — table doesn't exist
-- Investigation (2026-05-10): archived tables are 0 rows (work_orders, audit_log)
--   or 16 rows with FK to work_orders (notification_delivery_logs)
--
-- Restored tables (all 0 rows except notification_delivery_logs=16):
--   work_orders: 0 rows — milestone/sla columns already present in archived version
--   audit_log: 0 rows — 33 code refs, INSERT silently fails (pre-existing bug)
--   notification_delivery_logs: 16 rows — FK to work_orders (will be re-added)
--   ml_feedback_state: 1 row — ML feedback state (critical)

BEGIN;

-- work_orders: 0 rows, all columns (49) including milestone_status, sla_* cols
CREATE TABLE public.work_orders (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  code text,
  site_id uuid,
  equipment_id uuid,
  title text,
  description text,
  priority text,
  status text DEFAULT 'open',
  scheduled_date date,
  scheduled_start time without time zone,
  scheduled_end time without time zone,
  estimated_duration_hours integer,
  assigned_to text,
  assigned_team text,
  started_at timestamptz,
  completed_at timestamptz,
  actual_duration_hours integer,
  labor_cost_zar numeric,
  parts_cost_zar numeric,
  total_cost_zar numeric,
  parts_required text[],
  parts_used jsonb DEFAULT '{}',
  work_performed text,
  findings text,
  follow_up_required boolean DEFAULT false,
  follow_up_notes text,
  parent_work_order_id uuid,
  related_work_orders text[],
  created_at timestamptz DEFAULT NOW(),
  updated_at timestamptz DEFAULT NOW(),
  created_by text,
  contract_id uuid,
  assigned_to_internal_team boolean DEFAULT false,
  escalated_to_service_provider boolean DEFAULT false,
  escalation_reason text,
  escalation_date timestamptz,
  service_provider_name text,
  service_provider_email text,
  service_provider_phone text,
  service_provider_specialty text,
  reporter_telegram_id text,
  reporter_chat_id text,
  milestone_status text,
  assigned_at timestamptz,
  in_progress_at timestamptz,
  resolved_at timestamptz,
  verified_at timestamptz,
  sla_hours jsonb,
  sla_deadline_at timestamptz
);

-- audit_log: 0 rows, 23 columns
CREATE TABLE public.audit_log (
  id uuid DEFAULT gen_random_uuid(),
  timestamp timestamptz DEFAULT NOW(),
  user_id text,
  user_name text,
  session_id text,
  action text,
  entity_type text,
  entity_id uuid,
  device_id uuid,
  point_name text,
  old_value jsonb,
  new_value jsonb,
  result text,
  error_message text,
  safety_validation jsonb,
  safety_rules_checked text[],
  safety_rules_passed text[],
  safety_rules_failed text[],
  ip_address text,
  user_agent text,
  correlation_id text,
  metadata jsonb DEFAULT '{}',
  work_order_id uuid
);

-- notification_delivery_logs: 16 rows, FK to work_orders (deferred — work_orders is empty)
CREATE TABLE public.notification_delivery_logs (
  id uuid DEFAULT gen_random_uuid(),
  work_order_id uuid,
  technician_id text,
  notification_type text,
  title text,
  body text,
  channel_type text,
  recipient_identifier text,
  status text,
  error_message text,
  error_code text,
  external_message_id text,
  sent_at timestamptz,
  delivered_at timestamptz,
  provider text,
  provider_response jsonb,
  retry_count integer DEFAULT 0,
  last_retry_at timestamptz,
  max_retries integer DEFAULT 3,
  created_at timestamptz DEFAULT NOW(),
  updated_at timestamptz DEFAULT NOW()
);

-- ml_feedback_state: 1 row
CREATE TABLE public.ml_feedback_state (
  state_key text PRIMARY KEY,
  payload jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT NOW(),
  updated_at timestamptz NOT NULL DEFAULT NOW()
);

-- Restore data from _deprecated (explicit column list due to schema differences)
INSERT INTO public.work_orders SELECT * FROM _deprecated.work_orders;
INSERT INTO public.audit_log SELECT * FROM _deprecated.audit_log;
INSERT INTO public.ml_feedback_state SELECT * FROM _deprecated.ml_feedback_state;
INSERT INTO public.notification_delivery_logs (
  id, work_order_id, technician_id, notification_type, title, body,
  channel_type, recipient_identifier, status, error_message, error_code,
  external_message_id, sent_at, delivered_at, provider, provider_response,
  retry_count, last_retry_at, max_retries, created_at, updated_at
) SELECT id, work_order_id, technician_id, notification_type, title, body,
  channel_type, recipient_identifier, status, error_message, error_code,
  external_message_id, sent_at, delivered_at, provider, provider_response,
  retry_count, last_retry_at, max_retries, created_at, updated_at
FROM _deprecated.notification_delivery_logs;

-- Now add FK constraint (work_orders has 0 rows, no violation possible)
ALTER TABLE public.notification_delivery_logs
  ADD CONSTRAINT notification_delivery_logs_work_order_id_fkey
  FOREIGN KEY (work_order_id) REFERENCES public.work_orders(id);

-- Restore triggers (standard updated_at)
DROP TRIGGER IF EXISTS update_work_orders_updated_at ON public.work_orders;
CREATE TRIGGER update_work_orders_updated_at
  BEFORE UPDATE ON public.work_orders
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_audit_log_updated_at ON public.audit_log;
CREATE TRIGGER update_audit_log_updated_at
  BEFORE UPDATE ON public.audit_log
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_notification_delivery_logs_updated_at ON public.notification_delivery_logs;
CREATE TRIGGER update_notification_delivery_logs_updated_at
  BEFORE UPDATE ON public.notification_delivery_logs
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_ml_feedback_state_updated_at ON public.ml_feedback_state;
CREATE TRIGGER update_ml_feedback_state_updated_at
  BEFORE UPDATE ON public.ml_feedback_state
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Grant
GRANT SELECT, INSERT, UPDATE, DELETE ON public.work_orders TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.audit_log TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.notification_delivery_logs TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ml_feedback_state TO service_role;

COMMIT;

DO $$
BEGIN
  RAISE NOTICE '209-01 restore: work_orders=0, audit_log=0, notification_delivery_logs=16, ml_feedback_state=1';
END;
$$;

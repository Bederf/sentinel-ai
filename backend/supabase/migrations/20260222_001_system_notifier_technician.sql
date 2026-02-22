/**
 * Phase 109: Notification Hardening
 * Ensure a persistent technician row exists for system-generated alert delivery logs.
 *
 * This row is used when alert notifications are emitted by backend services
 * (no human technician context) but notification_delivery_log enforces
 * technician_id FK -> technicians(id).
 */

INSERT INTO public.technicians (
  id,
  code,
  name,
  email,
  phone,
  active,
  created_at,
  updated_at
)
VALUES (
  '00000000-0000-0000-0000-000000000001',
  'TECH-SYSTEM-NOTIFIER',
  'System Notifier',
  'system-notifier@sentinel.local',
  NULL,
  TRUE,
  NOW(),
  NOW()
)
ON CONFLICT (code) DO UPDATE SET
  active = TRUE,
  updated_at = NOW();

-- Correlation & Issue Intelligence Layer — Extensions and Enums
-- Phase 155-01, Task 1
-- Creates all 14 enum types for the correlation schema

-- Extensions (idempotent — may already exist)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. source_module_enum (11 values)
CREATE TYPE source_module_enum AS ENUM (
  'email_helpdesk',
  'email_escalation',
  'email_resolution',
  'occupancy_sensor',
  'booking_system',
  'maintenance_system',
  'hvac_telemetry',
  'energy_meter',
  'security_system',
  'manual_entry',
  'external_api'
);

-- 2. signal_type_enum (27 values)
CREATE TYPE signal_type_enum AS ENUM (
  'complaint_email',
  'escalation_email',
  'resolution_email',
  'information_email',
  'occupancy_anomaly',
  'occupancy_normal',
  'occupancy_trend',
  'booking_conflict',
  'booking_released',
  'booking_no_show',
  'booking_saturation',
  'booking_underutilisation',
  'fragmented_usage',
  'shadow_scheduling',
  'no_show_pattern',
  'maintenance_request',
  'maintenance_completed',
  'maintenance_overdue',
  'hvac_fault',
  'hvac_setpoint_deviation',
  'hvac_efficiency_drop',
  'energy_spike',
  'energy_anomaly',
  'security_alert',
  'security_resolved',
  'manual_observation',
  'external_event'
);

-- 3. signal_subtype_enum (6 values)
CREATE TYPE signal_subtype_enum AS ENUM (
  'initial_report',
  'follow_up',
  'escalation',
  'resolution',
  'acknowledgement',
  'status_update'
);

-- 4. severity_enum (4 values)
CREATE TYPE severity_enum AS ENUM (
  'low',
  'medium',
  'high',
  'critical'
);

-- 5. resolution_state_enum (4 values)
CREATE TYPE resolution_state_enum AS ENUM (
  'active',
  'resolved',
  'suppressed',
  'expired'
);

-- 6. cluster_state_enum (5 values)
CREATE TYPE cluster_state_enum AS ENUM (
  'emerging',
  'active',
  'escalated',
  'resolved',
  'suppressed'
);

-- 7. escalation_level_enum (3 values)
CREATE TYPE escalation_level_enum AS ENUM (
  'operational',
  'management',
  'executive'
);

-- 8. classification_domain_enum (7 values)
CREATE TYPE classification_domain_enum AS ENUM (
  'space_optimisation',
  'workplace_experience',
  'hvac',
  'maintenance',
  'energy',
  'security',
  'compliance'
);

-- 9. entity_type_enum (9 values)
CREATE TYPE entity_type_enum AS ENUM (
  'person',
  'room',
  'building',
  'floor',
  'quadrant',
  'department',
  'asset',
  'booking_ref',
  'work_order'
);

-- 10. node_type_enum (3 values)
CREATE TYPE node_type_enum AS ENUM (
  'cluster',
  'signal',
  'entity'
);

-- 11. edge_type_enum (8 values)
CREATE TYPE edge_type_enum AS ENUM (
  'evidenced_by',
  'involves',
  'reported_by',
  'affects',
  'contradicts',
  'supersedes',
  'related_to',
  'caused_by'
);

-- 12. role_type_enum (6 values)
CREATE TYPE role_type_enum AS ENUM (
  'concierge',
  'management',
  'facilities',
  'executive',
  'technician',
  'external'
);

-- 13. contradiction_rule_enum (4 values)
CREATE TYPE contradiction_rule_enum AS ENUM (
  'resolution_contradicts_complaint',
  'occupancy_normal_contradicts_anomaly',
  'booking_released_contradicts_conflict',
  'resolved_contradicts_active'
);

-- 14. site_resolution_status_enum (4 values)
CREATE TYPE site_resolution_status_enum AS ENUM (
  'resolved_managed',
  'resolved_unmanaged',
  'unresolved',
  'ambiguous'
);

-- Correlation & Issue Intelligence Layer — Core Tables
-- Phase 155-01, Task 2
-- Creates all 9 tables with columns, constraints, and generated columns

-- 1. email_thread — stores email thread metadata
CREATE TABLE email_thread (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  thread_hash text NOT NULL UNIQUE,
  subject text NOT NULL,
  participants text[] NOT NULL DEFAULT '{}',
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  email_count integer NOT NULL DEFAULT 1
);

COMMENT ON TABLE email_thread IS 'Email thread metadata. One thread can produce many signals over time.';

-- 2. issue_cluster (with duration_days generated column)
CREATE TABLE issue_cluster (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title text NOT NULL,
  cluster_state cluster_state_enum NOT NULL DEFAULT 'emerging',
  severity severity_enum NOT NULL DEFAULT 'medium',
  escalation_level escalation_level_enum NOT NULL DEFAULT 'operational',
  confidence_score numeric(3,2) NOT NULL DEFAULT 0.50,
  likely_root_cause text,
  site_id uuid,
  is_managed boolean NOT NULL DEFAULT false,
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz,
  duration_days integer NOT NULL DEFAULT 0,
  signal_count integer NOT NULL DEFAULT 0,
  entity_count integer NOT NULL DEFAULT 0,
  metadata jsonb DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT chk_issue_cluster_managed CHECK (is_managed = false OR site_id IS NOT NULL),
  CONSTRAINT chk_issue_cluster_confidence CHECK (confidence_score >= 0 AND confidence_score <= 1)
);

COMMENT ON TABLE issue_cluster IS 'Groups correlated signals into actionable issues.';
COMMENT ON COLUMN issue_cluster.duration_days IS 'Auto-computed days since first_seen_at. Uses resolved_at if resolved, otherwise now().';

-- 3. signal — the core event record
-- Multi-site rules:
--   - Ingest ALL signals regardless of site — never drop unmanaged signals
--   - is_managed = true ONLY when site_id points to a SENTINEL-managed site
--   - Dashboard routing requires is_managed = true (enforced in application layer, not DB)
--   - One email can emit multiple signals with different site contexts
CREATE TABLE signal (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email_thread_id uuid,
  source_module source_module_enum NOT NULL,
  signal_type signal_type_enum NOT NULL,
  signal_subtype signal_subtype_enum,
  severity severity_enum NOT NULL DEFAULT 'medium',
  confidence numeric(3,2) NOT NULL DEFAULT 0.50,
  resolution_state resolution_state_enum NOT NULL DEFAULT 'active',
  location_ref text NOT NULL,
  site_id uuid,
  is_managed boolean NOT NULL DEFAULT false,
  site_resolution_status site_resolution_status_enum NOT NULL DEFAULT 'unresolved',
  issue_cluster_id uuid,
  emits_multiple boolean NOT NULL DEFAULT false,
  parent_signal_id uuid,
  embedding vector(1536),
  raw_content text,
  metadata jsonb DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT chk_signal_managed CHECK (is_managed = false OR site_id IS NOT NULL),
  CONSTRAINT chk_signal_confidence CHECK (confidence >= 0 AND confidence <= 1)
);

COMMENT ON TABLE signal IS 'Core event record. Every intake (email, sensor, booking) produces one or more signals.';
COMMENT ON COLUMN signal.location_ref IS 'Structured room code path: {campus}/{building}/{floor}Q{quadrant}/{type}{number}';
COMMENT ON COLUMN signal.site_id IS 'FK to sites(id). NULL when site unresolved.';
COMMENT ON COLUMN signal.is_managed IS 'true only when site_id resolves to a SENTINEL-managed site';
COMMENT ON COLUMN signal.site_resolution_status IS 'Tracks site resolution lifecycle';

-- 4. issue_classification (unique constraint on cluster+domain)
CREATE TABLE issue_classification (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  issue_cluster_id uuid NOT NULL,
  domain classification_domain_enum NOT NULL,
  confidence numeric(3,2) NOT NULL DEFAULT 0.50,
  classified_at timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT uq_classification_cluster_domain UNIQUE (issue_cluster_id, domain),
  CONSTRAINT chk_classification_confidence CHECK (confidence >= 0 AND confidence <= 1)
);

COMMENT ON TABLE issue_classification IS 'Maps clusters to classification domains with confidence scores.';

-- 5. entity
CREATE TABLE entity (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  signal_id uuid,
  issue_cluster_id uuid,
  entity_type entity_type_enum NOT NULL,
  entity_value text NOT NULL,
  metadata jsonb DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE entity IS 'Named entities extracted from signals (people, rooms, buildings, etc).';

-- 6. relationship (with no_self_loop constraint)
CREATE TABLE relationship (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id uuid NOT NULL,
  target_id uuid NOT NULL,
  source_type node_type_enum NOT NULL,
  target_type node_type_enum NOT NULL,
  edge_type edge_type_enum NOT NULL,
  confidence numeric(3,2) NOT NULL DEFAULT 0.50,
  evidence_basis text,
  created_at timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT chk_relationship_no_self_loop CHECK (source_id != target_id),
  CONSTRAINT chk_relationship_confidence CHECK (confidence >= 0 AND confidence <= 1)
);

COMMENT ON TABLE relationship IS 'Graph edges linking clusters, signals, and entities.';
COMMENT ON COLUMN relationship.evidence_basis IS 'E.g. contradiction_rule name when edge_type is contradicts.';

-- 7. issue_evidence
CREATE TABLE issue_evidence (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  issue_cluster_id uuid NOT NULL,
  evidence_type text NOT NULL,
  evidence_ref text NOT NULL,
  summary text,
  created_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE issue_evidence IS 'Evidence records linking clusters to source data (emails, sensors, bookings).';

-- 8. role_assignment (with issue_domains array of classification_domain_enum)
CREATE TABLE role_assignment (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  person_name text NOT NULL,
  role_type role_type_enum NOT NULL,
  location_scope text NOT NULL,
  issue_domains classification_domain_enum[] NOT NULL DEFAULT '{}',
  contact_info jsonb DEFAULT '{}',
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE role_assignment IS 'Maps people to roles, location scopes, and issue domains for dashboard routing.';
COMMENT ON COLUMN role_assignment.location_scope IS 'Wildcard pattern e.g. "Fairlands/*/*/*" matching campus/building/floorQuadrant/room';

-- 9. dashboard_card
CREATE TABLE dashboard_card (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  issue_cluster_id uuid NOT NULL,
  recipient_role_assignment_id uuid NOT NULL,
  title text NOT NULL,
  card_content jsonb NOT NULL DEFAULT '{}',
  advisory_label text NOT NULL DEFAULT 'These actions are suggestions. Human decision required.',
  surfaced_at timestamptz NOT NULL DEFAULT now(),
  acknowledged_at timestamptz,
  dismissed_at timestamptz
);

COMMENT ON TABLE dashboard_card IS 'Actionable cards surfaced to role holders based on issue clusters.';

-- Auto-compute duration_days on issue_cluster insert/update
-- PostgreSQL GENERATED ALWAYS AS requires immutable expressions; now() is mutable.
-- Use a trigger instead.
CREATE OR REPLACE FUNCTION compute_issue_cluster_duration()
RETURNS TRIGGER AS $$
BEGIN
  NEW.duration_days := EXTRACT(DAY FROM (COALESCE(NEW.resolved_at, now()) - NEW.first_seen_at))::integer;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_issue_cluster_duration
  BEFORE INSERT OR UPDATE ON issue_cluster
  FOR EACH ROW
  EXECUTE FUNCTION compute_issue_cluster_duration();

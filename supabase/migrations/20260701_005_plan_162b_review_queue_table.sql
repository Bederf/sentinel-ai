-- PLAN-162B: Create review_queue table (Phase 162 gap — never created on this instance)
-- Includes reset_reason column for trust reset operator visibility.

CREATE TABLE IF NOT EXISTS review_queue (
  id                  text NOT NULL,
  site_id             text NOT NULL,
  equipment_id        text NOT NULL,
  point_id            text NOT NULL,
  classification_id   text NOT NULL,
  semantic_tags       jsonb NOT NULL DEFAULT '[]',
  confidence_score    double precision NOT NULL DEFAULT 0.0,
  confidence_level    text NOT NULL DEFAULT 'LOW',
  safety_class        text NOT NULL DEFAULT 'LOW',
  automation_tier     text NOT NULL DEFAULT 'observe_only',
  validation_passed   boolean NOT NULL DEFAULT false,
  validation_errors   jsonb NOT NULL DEFAULT '[]',
  completeness_score  double precision,
  status              text NOT NULL DEFAULT 'pending',
  priority            integer NOT NULL DEFAULT 100,
  classified_by       text NOT NULL DEFAULT '',
  classified_at       timestamptz NOT NULL DEFAULT now(),
  reviewed_by         text,
  reviewed_at         timestamptz,
  review_notes        text,
  decision_reason     text,
  override_tags       jsonb,
  override_confidence double precision,
  override_justification text,
  reset_reason        text,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_review_queue_site_status ON review_queue (site_id, status);
CREATE INDEX IF NOT EXISTS idx_review_queue_equipment ON review_queue (equipment_id);

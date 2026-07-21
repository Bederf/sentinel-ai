-- PLAN-162B: Trust reset events audit trail
-- Records every trust profile reset or decay with prior snapshot,
-- trigger type, and trigger ID for operator accountability.

CREATE TABLE IF NOT EXISTS trust_reset_events (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  equipment_id    text NOT NULL,
  site_id         text NOT NULL,
  trigger_type    text NOT NULL,  -- 'wo_replacement', 'wo_retrofit', 'drift_severe', 'drift_moderate'
  trigger_id      text,            -- WO code or drift event UUID
  prior_trust     jsonb NOT NULL,  -- snapshot of TrustProfile before reset
  reset_action    text NOT NULL,   -- 'hard_reset', 'partial_decay', 'moderate_decay'
  occurred_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_trust_reset_events_equipment ON trust_reset_events (equipment_id);
CREATE INDEX IF NOT EXISTS idx_trust_reset_events_occurred ON trust_reset_events (occurred_at DESC);

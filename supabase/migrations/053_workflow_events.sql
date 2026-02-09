-- =====================================================
-- Migration 053: Workflow Events Log
-- =====================================================

CREATE TABLE IF NOT EXISTS workflow_events (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  equipment_id UUID,
  trigger_type TEXT NOT NULL,
  action_taken TEXT NOT NULL,
  source TEXT DEFAULT 'workflow',
  work_order_id TEXT,
  inspection_id TEXT,
  details JSONB DEFAULT '{}',
  success BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workflow_events_equipment
  ON workflow_events(equipment_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_workflow_events_trigger
  ON workflow_events(trigger_type, created_at DESC);

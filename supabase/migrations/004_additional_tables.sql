-- =====================================================
-- Migration 004: Additional Tables
-- Anomalies, Work Orders, and Audit Log
-- =====================================================

-- Anomalies table (detected issues + root cause analysis)
CREATE TABLE anomalies (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  code TEXT UNIQUE NOT NULL,
  equipment_id UUID REFERENCES equipment(id) ON DELETE CASCADE,
  building_id UUID REFERENCES buildings(id) ON DELETE CASCADE,
  sensor_id UUID REFERENCES sensors(id) ON DELETE SET NULL,

  -- Anomaly details
  type TEXT NOT NULL,
  severity TEXT CHECK (severity IN ('info', 'warning', 'critical')),
  status TEXT CHECK (status IN ('active', 'investigating', 'resolved', 'false_positive')),
  detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  -- Analysis
  description TEXT NOT NULL,
  root_cause TEXT,
  confidence DECIMAL(3, 2), -- 0.00 to 1.00

  -- Related data
  sensor_values JSONB, -- Snapshot of sensor readings
  patterns JSONB, -- Detected patterns
  similar_anomalies UUID[], -- Related anomaly IDs

  -- Resolution
  resolved_at TIMESTAMPTZ,
  resolved_by TEXT,
  resolution_notes TEXT,

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Work orders table (maintenance management)
CREATE TABLE work_orders (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  code TEXT UNIQUE NOT NULL, -- Auto-generated: WO-2026-0001
  building_id UUID REFERENCES buildings(id) ON DELETE CASCADE,
  equipment_id UUID REFERENCES equipment(id) ON DELETE SET NULL,
  prediction_id UUID REFERENCES predictions(id) ON DELETE SET NULL,
  anomaly_id UUID REFERENCES anomalies(id) ON DELETE SET NULL,

  -- Work order details
  title TEXT NOT NULL,
  description TEXT,
  priority TEXT CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
  status TEXT CHECK (status IN ('draft', 'scheduled', 'in_progress', 'completed', 'cancelled')),

  -- Scheduling
  scheduled_date DATE,
  scheduled_start TIME,
  scheduled_end TIME,
  estimated_duration_hours INTEGER,

  -- Assignment
  assigned_to TEXT,
  assigned_team TEXT,

  -- Execution
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  actual_duration_hours INTEGER,

  -- Costs
  labor_cost_zar DECIMAL(10, 2),
  parts_cost_zar DECIMAL(10, 2),
  total_cost_zar DECIMAL(10, 2),

  -- Parts and materials
  parts_required TEXT[],
  parts_used JSONB,

  -- Outcome
  work_performed TEXT,
  findings TEXT,
  follow_up_required BOOLEAN DEFAULT FALSE,
  follow_up_notes TEXT,

  -- Related work orders
  parent_work_order_id UUID REFERENCES work_orders(id) ON DELETE SET NULL,
  related_work_orders UUID[],

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  created_by TEXT
);

-- Audit log table (control system change tracking)
CREATE TABLE audit_log (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  -- Who
  user_id TEXT,
  user_name TEXT,
  session_id TEXT,

  -- What
  action TEXT NOT NULL CHECK (action IN ('DEVICE_CONTROL', 'SAFETY_VALIDATION', 'SYSTEM_EVENT', 'CONFIG_CHANGE', 'WORK_ORDER_CREATE', 'WORK_ORDER_UPDATE')),
  entity_type TEXT,
  entity_id UUID,

  -- Device control specific
  device_id UUID REFERENCES equipment(id) ON DELETE SET NULL,
  point_name TEXT,
  old_value JSONB,
  new_value JSONB,

  -- Result
  result TEXT CHECK (result IN ('SUCCESS', 'FAILED', 'BLOCKED', 'WARNING')),
  error_message TEXT,

  -- Safety validation
  safety_validation JSONB,
  safety_rules_checked TEXT[],
  safety_rules_passed TEXT[],
  safety_rules_failed TEXT[],

  -- Metadata
  ip_address TEXT,
  user_agent TEXT,
  correlation_id TEXT,
  metadata JSONB DEFAULT '{}',

  -- Related entities
  work_order_id UUID REFERENCES work_orders(id) ON DELETE SET NULL
);

-- Indexes for new tables
CREATE INDEX idx_anomalies_equipment ON anomalies(equipment_id);
CREATE INDEX idx_anomalies_building ON anomalies(building_id);
CREATE INDEX idx_anomalies_sensor ON anomalies(sensor_id);
CREATE INDEX idx_anomalies_status ON anomalies(status, severity);
CREATE INDEX idx_anomalies_detected_at ON anomalies(detected_at DESC);

CREATE INDEX idx_work_orders_building ON work_orders(building_id);
CREATE INDEX idx_work_orders_equipment ON work_orders(equipment_id);
CREATE INDEX idx_work_orders_prediction ON work_orders(prediction_id);
CREATE INDEX idx_work_orders_anomaly ON work_orders(anomaly_id);
CREATE INDEX idx_work_orders_status ON work_orders(status, priority);
CREATE INDEX idx_work_orders_scheduled ON work_orders(scheduled_date) WHERE status IN ('scheduled', 'in_progress');
CREATE INDEX idx_work_orders_assigned ON work_orders(assigned_to);

CREATE INDEX idx_audit_log_timestamp ON audit_log(timestamp DESC);
CREATE INDEX idx_audit_log_user ON audit_log(user_id, timestamp DESC);
CREATE INDEX idx_audit_log_action ON audit_log(action, timestamp DESC);
CREATE INDEX idx_audit_log_device ON audit_log(device_id, timestamp DESC);
CREATE INDEX idx_audit_log_entity ON audit_log(entity_type, entity_id);
CREATE INDEX idx_audit_log_result ON audit_log(result, timestamp DESC);
CREATE INDEX idx_audit_log_correlation ON audit_log(correlation_id);

-- Triggers for updated_at
CREATE TRIGGER update_anomalies_updated_at BEFORE UPDATE ON anomalies
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_work_orders_updated_at BEFORE UPDATE ON work_orders
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

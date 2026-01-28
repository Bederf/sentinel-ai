-- =====================================================
-- Migration 005: Materialized Views and Advanced Triggers
-- =====================================================

-- =====================================================
-- MATERIALIZED VIEWS: Dashboard KPIs
-- =====================================================

-- Dashboard summary view (KPI aggregates)
CREATE MATERIALIZED VIEW v_dashboard_summary AS
SELECT
  COUNT(DISTINCT b.id) as total_buildings,
  COUNT(DISTINCT e.id) as total_equipment,
  COUNT(DISTINCT e.id) FILTER (WHERE e.status = 'critical') as critical_equipment,
  COUNT(DISTINCT e.id) FILTER (WHERE e.status = 'warning') as warning_equipment,
  COUNT(DISTINCT e.id) FILTER (WHERE e.status = 'normal') as normal_equipment,
  AVG(e.health_score) as avg_health_score,
  COUNT(a.id) FILTER (WHERE a.status = 'active') as active_alerts,
  COUNT(a.id) FILTER (WHERE a.severity = 'critical' AND a.status = 'active') as critical_alerts,
  COUNT(p.id) FILTER (WHERE p.status = 'active') as active_predictions,
  COUNT(w.id) FILTER (WHERE w.status IN ('scheduled', 'in_progress')) as pending_work_orders,
  COUNT(an.id) FILTER (WHERE an.status = 'active') as active_anomalies
FROM buildings b
LEFT JOIN equipment e ON e.building_id = b.id
LEFT JOIN alerts a ON a.building_id = b.id
LEFT JOIN predictions p ON p.building_id = b.id
LEFT JOIN work_orders w ON w.building_id = b.id
LEFT JOIN anomalies an ON an.building_id = b.id;

-- Building status view (sites with computed status)
CREATE MATERIALIZED VIEW v_building_status AS
SELECT
  b.id,
  b.code,
  b.name,
  b.region,
  b.type,
  COUNT(e.id) as equipment_count,
  COUNT(e.id) FILTER (WHERE e.status = 'critical') as critical_count,
  COUNT(e.id) FILTER (WHERE e.status = 'warning') as warning_count,
  COUNT(e.id) FILTER (WHERE e.status = 'normal') as normal_count,
  COALESCE(AVG(e.health_score), 0) as avg_health_score,
  COUNT(a.id) FILTER (WHERE a.status = 'active') as active_alerts,
  COUNT(a.id) FILTER (WHERE a.severity = 'critical' AND a.status = 'active') as critical_alerts,
  COUNT(p.id) FILTER (WHERE p.status = 'active') as active_predictions,
  CASE
    WHEN COUNT(a.id) FILTER (WHERE a.severity = 'critical' AND a.status = 'active') > 0 THEN 'critical'
    WHEN COUNT(a.id) FILTER (WHERE a.status = 'active') > 0 OR COUNT(e.id) FILTER (WHERE e.status = 'critical') > 0 THEN 'warning'
    ELSE 'normal'
  END as computed_status,
  b.updated_at
FROM buildings b
LEFT JOIN equipment e ON e.building_id = b.id
LEFT JOIN alerts a ON a.building_id = b.id
LEFT JOIN predictions p ON p.building_id = b.id
GROUP BY b.id, b.code, b.name, b.region, b.type, b.updated_at;

-- Equipment health view (assets with alert/prediction counts)
CREATE MATERIALIZED VIEW v_equipment_health AS
SELECT
  e.id,
  e.code,
  e.name,
  e.type,
  e.status,
  e.health_score,
  b.id as building_id,
  b.code as building_code,
  b.name as building_name,
  b.region,
  COUNT(a.id) FILTER (WHERE a.status = 'active') as active_alerts,
  COUNT(p.id) FILTER (WHERE p.status = 'active') as active_predictions,
  COUNT(an.id) FILTER (WHERE an.status = 'active') as active_anomalies,
  COUNT(w.id) FILTER (WHERE w.status IN ('scheduled', 'in_progress')) as pending_work_orders,
  CASE
    WHEN e.status = 'critical' OR COUNT(a.id) FILTER (WHERE a.severity = 'critical' AND a.status = 'active') > 0 THEN 'critical'
    WHEN e.status = 'warning' OR COUNT(a.id) FILTER (WHERE a.status = 'active') > 0 THEN 'warning'
    ELSE 'normal'
  END as computed_status,
  e.updated_at
FROM equipment e
JOIN buildings b ON e.building_id = b.id
LEFT JOIN alerts a ON a.equipment_id = e.id
LEFT JOIN predictions p ON p.equipment_id = e.id
LEFT JOIN anomalies an ON an.equipment_id = e.id
LEFT JOIN work_orders w ON w.equipment_id = e.id
GROUP BY e.id, e.code, e.name, e.type, e.status, e.health_score, b.id, b.code, b.name, b.region, e.updated_at;

-- Active alerts view (filtered alert list with joins)
CREATE MATERIALIZED VIEW v_active_alerts AS
SELECT
  a.id,
  a.type,
  a.severity,
  a.status,
  a.title,
  a.message,
  a.created_at,
  a.acknowledged_at,
  a.acknowledged_by,
  e.id as equipment_id,
  e.code as equipment_code,
  e.name as equipment_name,
  e.type as equipment_type,
  b.id as building_id,
  b.code as building_code,
  b.name as building_name,
  b.region,
  b.address
FROM alerts a
LEFT JOIN equipment e ON a.equipment_id = e.id
LEFT JOIN buildings b ON a.building_id = b.id
WHERE a.status = 'active'
ORDER BY
  a.severity DESC,
  a.created_at DESC;

-- Create indexes on materialized views for performance
CREATE INDEX idx_dashboard_summary_building_count ON v_dashboard_summary(total_buildings);
CREATE INDEX idx_building_status_region ON v_building_status(region);
CREATE INDEX idx_building_status_computed_status ON v_building_status(computed_status);
CREATE INDEX idx_equipment_health_building_id ON v_equipment_health(building_id);
CREATE INDEX idx_equipment_health_computed_status ON v_equipment_health(computed_status);
CREATE INDEX idx_equipment_health_type ON v_equipment_health(type);
CREATE INDEX idx_active_alerts_severity ON v_active_alerts(severity DESC);
CREATE INDEX idx_active_alerts_building_id ON v_active_alerts(building_id);

-- =====================================================
-- ADVANCED TRIGGERS: Auto-compute fields and maintain integrity
-- =====================================================

-- Function: Auto-update building equipment counts
CREATE OR REPLACE FUNCTION update_building_equipment_counts()
RETURNS TRIGGER AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    UPDATE buildings
    SET equipment_count = equipment_count + 1
    WHERE id = NEW.building_id;
    RETURN NEW;
  ELSIF TG_OP = 'DELETE' THEN
    UPDATE buildings
    SET equipment_count = GREATEST(equipment_count - 1, 0)
    WHERE id = OLD.building_id;
    RETURN OLD;
  ELSIF TG_OP = 'UPDATE' AND OLD.building_id != NEW.building_id THEN
    -- Equipment moved to different building
    UPDATE buildings
    SET equipment_count = equipment_count - 1
    WHERE id = OLD.building_id;
    UPDATE buildings
    SET equipment_count = equipment_count + 1
    WHERE id = NEW.building_id;
    RETURN NEW;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger: Update building equipment counts
CREATE TRIGGER trigger_update_building_equipment_counts
  AFTER INSERT OR UPDATE OR DELETE ON equipment
  FOR EACH ROW EXECUTE FUNCTION update_building_equipment_counts();

-- Function: Auto-update sensor last value from readings
CREATE OR REPLACE FUNCTION update_sensor_last_value()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE sensors
  SET current_value = NEW.value,
      updated_at = NOW()
  WHERE id = NEW.sensor_id;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger: Update sensor current value on new reading
CREATE TRIGGER trigger_update_sensor_last_value
  AFTER INSERT ON sensor_readings
  FOR EACH ROW EXECUTE FUNCTION update_sensor_last_value();

-- Function: Auto-generate work order codes
CREATE OR REPLACE FUNCTION generate_work_order_code()
RETURNS TRIGGER AS $$
DECLARE
  year TEXT := EXTRACT(YEAR FROM CURRENT_DATE)::TEXT;
  seq_num INTEGER;
  new_code TEXT;
BEGIN
  -- Only generate code for new work orders without one
  IF NEW.code IS NOT NULL OR TG_OP != 'INSERT' THEN
    RETURN NEW;
  END IF;

  -- Get next sequence number for this year
  SELECT COALESCE(MAX(CAST(SUBSTRING(code FROM 12) AS INTEGER)), 0) + 1
  INTO seq_num
  FROM work_orders
  WHERE code LIKE 'WO-' || year || '-%';

  -- Generate code: WO-2026-0001
  new_code := 'WO-' || year || '-' || LPAD(seq_num::TEXT, 4, '0');
  NEW.code := new_code;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger: Auto-generate work order codes
CREATE TRIGGER trigger_generate_work_order_code
  BEFORE INSERT ON work_orders
  FOR EACH ROW EXECUTE FUNCTION generate_work_order_code();

-- =====================================================
-- ADDITIONAL INDEXES FOR PERFORMANCE
-- =====================================================

-- Buildings table indexes
CREATE INDEX idx_buildings_region ON buildings(region);
CREATE INDEX idx_buildings_type ON buildings(type);
CREATE INDEX idx_buildings_optimization_enabled ON buildings(optimization_enabled) WHERE optimization_enabled = TRUE;

-- Equipment table additional indexes
CREATE INDEX idx_equipment_type_status ON equipment(type, status);
CREATE INDEX idx_equipment_health_threshold ON equipment(health_score) WHERE health_score < 70;
CREATE INDEX idx_equipment_last_service ON equipment(last_service) WHERE last_service IS NOT NULL;

-- Alerts additional indexes
CREATE INDEX idx_alerts_building_severity ON alerts(building_id, severity) WHERE status = 'active';
CREATE INDEX idx_alerts_created_at ON alerts(created_at DESC);

-- Predictions additional indexes
CREATE INDEX idx_predictions_confidence ON predictions(confidence, probability_percent);
CREATE INDEX idx_predictions_equipment_severity ON predictions(equipment_id, severity);

-- Sensor readings time-series indexes (TimescaleDB specific)
-- Note: idx_sensor_readings_time is already created in migration 002
CREATE INDEX IF NOT EXISTS idx_sensor_readings_value ON sensor_readings(value);

-- Work orders additional indexes
CREATE INDEX idx_work_orders_date_status ON work_orders(scheduled_date, status);
CREATE INDEX idx_work_orders_created_at ON work_orders(created_at DESC);

-- Anomalies additional indexes
CREATE INDEX idx_anomalies_type_severity ON anomalies(type, severity) WHERE status = 'active';

-- Audit log additional indexes
CREATE INDEX idx_audit_log_entity_type_time ON audit_log(entity_type, timestamp DESC);
CREATE INDEX idx_audit_log_action_result ON audit_log(action, result);

-- Composite indexes for common query patterns
CREATE INDEX idx_equipment_building_health ON equipment(building_id, health_score);
CREATE INDEX idx_alerts_equipment_status ON alerts(equipment_id, status);
CREATE INDEX idx_predictions_building_status ON predictions(building_id, status);
CREATE INDEX idx_work_orders_equipment_status ON work_orders(equipment_id, status);

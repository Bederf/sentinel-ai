-- Phase 75-01: Site Summary RPC Function
-- Supabase RPC function to support batch site aggregation endpoints
-- Provides single-query access to equipment, safety, alerts, predictions aggregated by site

-- RPC function to get complete site equipment summary
-- Joins equipment, device_safety_status, alerts, predictions tables
-- Aggregates counts by type, severity, and risk level
-- Returns JSON with all summary metrics
CREATE OR REPLACE FUNCTION get_site_equipment_summary(p_site_id TEXT)
RETURNS TABLE(
    site_id TEXT,
    equipment_total INT,
    equipment_by_type JSONB,
    safety_checked INT,
    safety_safe INT,
    safety_warning INT,
    safety_critical INT,
    alerts_total INT,
    alerts_critical INT,
    alerts_warning INT,
    alerts_info INT,
    predictions_total INT,
    predictions_critical INT,
    predictions_warning INT
) AS $$
BEGIN
  RETURN QUERY
  SELECT
    p_site_id as site_id,
    -- Equipment counts
    COUNT(DISTINCT e.id)::INT as equipment_total,
    jsonb_object_agg(
      COALESCE(e.type, 'unknown'),
      COUNT(e.id)
    ) FILTER (WHERE e.id IS NOT NULL) as equipment_by_type,
    -- Safety metrics
    COUNT(DISTINCT dss.id)::INT as safety_checked,
    COUNT(DISTINCT dss.id) FILTER (WHERE dss.severity = 'SAFE')::INT as safety_safe,
    COUNT(DISTINCT dss.id) FILTER (WHERE dss.severity = 'WARNING')::INT as safety_warning,
    COUNT(DISTINCT dss.id) FILTER (WHERE dss.severity = 'CRITICAL')::INT as safety_critical,
    -- Alert metrics
    COUNT(DISTINCT a.id)::INT as alerts_total,
    COUNT(DISTINCT a.id) FILTER (WHERE a.severity = 'critical')::INT as alerts_critical,
    COUNT(DISTINCT a.id) FILTER (WHERE a.severity = 'warning')::INT as alerts_warning,
    COUNT(DISTINCT a.id) FILTER (WHERE a.severity = 'info')::INT as alerts_info,
    -- Prediction metrics
    COUNT(DISTINCT p.id)::INT as predictions_total,
    COUNT(DISTINCT p.id) FILTER (WHERE p.severity = 'critical')::INT as predictions_critical,
    COUNT(DISTINCT p.id) FILTER (WHERE p.severity = 'warning')::INT as predictions_warning
  FROM
    -- Equipment for this site
    equipment e
    LEFT JOIN buildings b ON e.building_id = b.id
    -- Join with safety status if it exists
    LEFT JOIN device_safety_status dss ON e.id = dss.device_id
    -- Join with alerts for this site
    LEFT JOIN alerts a ON (a.building_id = b.id OR a.site_id = p_site_id)
    -- Join with predictions for this site
    LEFT JOIN predictions p ON (p.building_id = b.id OR p.site_id = p_site_id)
  WHERE
    b.id::TEXT = p_site_id OR b.code = p_site_id;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION get_site_equipment_summary(TEXT) IS 'Aggregate equipment, safety, alerts, and predictions for a site. Returns counts by type and severity for dashboard summary.';

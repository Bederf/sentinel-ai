-- Add escalation tracking fields to work_orders table
-- Tracks workflow: Internal Team → Cannot Fix → Service Provider Escalation

ALTER TABLE work_orders
  ADD COLUMN IF NOT EXISTS assigned_to_internal_team BOOLEAN DEFAULT true,
  ADD COLUMN IF NOT EXISTS escalated_to_service_provider BOOLEAN DEFAULT false,
  ADD COLUMN IF NOT EXISTS escalation_reason TEXT,
  ADD COLUMN IF NOT EXISTS escalation_date TIMESTAMP WITH TIME ZONE,
  ADD COLUMN IF NOT EXISTS service_provider_name TEXT,
  ADD COLUMN IF NOT EXISTS service_provider_email TEXT,
  ADD COLUMN IF NOT EXISTS service_provider_phone TEXT,
  ADD COLUMN IF NOT EXISTS service_provider_specialty TEXT;

-- Add comments for clarity
COMMENT ON COLUMN work_orders.assigned_to_internal_team IS 'Whether work order is initially assigned to internal team (true) or external service provider (false)';
COMMENT ON COLUMN work_orders.escalated_to_service_provider IS 'Whether work order has been escalated from internal team to service provider';
COMMENT ON COLUMN work_orders.escalation_reason IS 'Reason for escalation (e.g., "cannot fix", "parts not available", "requires specialist")';
COMMENT ON COLUMN work_orders.escalation_date IS 'Date/time when work order was escalated to service provider';
COMMENT ON COLUMN work_orders.service_provider_name IS 'Name of service provider assigned after escalation';
COMMENT ON COLUMN work_orders.service_provider_email IS 'Email of service provider for escalation notifications';
COMMENT ON COLUMN work_orders.service_provider_phone IS 'Phone of service provider for escalation notifications';
COMMENT ON COLUMN work_orders.service_provider_specialty IS 'Specialty of service provider (hvac, electrical, plumbing, dali, fire, security, general)';

-- Create indexes for escalation workflow
CREATE INDEX IF NOT EXISTS idx_work_orders_escalation_status
  ON work_orders(escalated_to_service_provider, status);

CREATE INDEX IF NOT EXISTS idx_work_orders_service_provider_email
  ON work_orders(service_provider_email)
  WHERE escalated_to_service_provider = true;

-- Create view for escalated work orders
CREATE OR REPLACE VIEW escalated_work_orders AS
  SELECT
    wo.id,
    wo.code,
    e.code as equipment_code,
    wo.title,
    wo.priority,
    wo.status,
    wo.assigned_to,
    wo.escalation_reason,
    wo.escalation_date,
    wo.service_provider_name,
    wo.service_provider_email,
    wo.service_provider_phone,
    wo.service_provider_specialty
  FROM work_orders wo
  LEFT JOIN equipment e ON wo.equipment_id = e.id
  WHERE wo.escalated_to_service_provider = true
  ORDER BY wo.escalation_date DESC;

COMMENT ON VIEW escalated_work_orders IS 'Shows all work orders that have been escalated to service providers';

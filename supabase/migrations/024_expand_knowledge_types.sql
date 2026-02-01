-- Migration 024: Expand knowledge_type options
-- Add more knowledge types to equipment_knowledge table

-- Drop and recreate the check constraint with additional types
ALTER TABLE equipment_knowledge DROP CONSTRAINT IF EXISTS equipment_knowledge_knowledge_type_check;

ALTER TABLE equipment_knowledge ADD CONSTRAINT equipment_knowledge_knowledge_type_check
  CHECK (knowledge_type IN (
    'fault_code',              -- Error code with explanation
    'symptom',                 -- Observable symptom with causes
    'failure_pattern',         -- Recurring failure pattern
    'maintenance_tip',         -- Best practice or tip
    'diagnostic_procedure',    -- How to diagnose issue
    'repair_procedure',        -- How to repair issue
    'preventive_measure',      -- How to prevent issue
    'maintenance_procedure',   -- Scheduled maintenance procedure
    'troubleshooting_guide',   -- Step-by-step troubleshooting
    'operation_guide',         -- How to operate equipment
    'safety_procedure',        -- Safety-related procedure
    'specification'            -- Equipment specifications
  ));

-- Add comment
COMMENT ON TABLE equipment_knowledge IS 'Equipment knowledge base with expanded knowledge types for RAG (Phase 44)';

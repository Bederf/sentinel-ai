-- Migration 103: Add security_policy document type
-- Required for RAG ingestion of docs/09-security/ files

ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_document_type_check;

ALTER TABLE documents ADD CONSTRAINT documents_document_type_check
  CHECK (document_type IN (
    'equipment_manual',
    'maintenance_procedure',
    'troubleshooting_guide',
    'failure_pattern',
    'technical_bulletin',
    'service_report',
    'safety_procedure',
    'startup_procedure',
    'shutdown_procedure',
    'system_documentation',
    'integration_guide',
    'api_reference',
    'security_policy'
  ));

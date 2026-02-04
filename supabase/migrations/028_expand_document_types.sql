-- Migration 028: Expand document_type options for system documentation
-- Allow ingesting SENTINEL system docs (architecture, integration guides, API references)

-- Migrate legacy 'documentation' type to 'system_documentation'
UPDATE documents SET document_type = 'system_documentation' WHERE document_type = 'documentation';

ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_document_type_check;

ALTER TABLE documents ADD CONSTRAINT documents_document_type_check
  CHECK (document_type IN (
    'equipment_manual',          -- OEM manual
    'maintenance_procedure',     -- Step-by-step procedure
    'troubleshooting_guide',     -- Fault diagnosis guide
    'failure_pattern',           -- Historical failure documentation
    'technical_bulletin',        -- Manufacturer bulletins
    'service_report',            -- Historical service reports
    'safety_procedure',          -- Safety procedures
    'startup_procedure',         -- Commissioning/startup guides
    'shutdown_procedure',        -- Shutdown/decommissioning guides
    'system_documentation',      -- SENTINEL system docs (architecture, features, API)
    'integration_guide',         -- Integration guides (Niagara, DALI, CAFM)
    'api_reference'              -- API endpoint documentation
  ));

-- Expand source constraint to include 'system_docs'
ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_source_check;

ALTER TABLE documents ADD CONSTRAINT documents_source_check
  CHECK (source IN (
    'oem_manual',                -- OEM manuals
    'internal_procedure',        -- Internal SOPs
    'service_history',           -- Service reports
    'technician_notes',          -- Field notes
    'manufacturer_bulletin',     -- Tech bulletins
    'industry_standard',         -- Standards (ASHRAE, etc.)
    'project_docs',              -- Project documentation
    'system_docs'                -- SENTINEL system documentation (from docs/)
  ));

COMMENT ON TABLE documents IS 'Document store with expanded types for system documentation RAG (Phase 60)';

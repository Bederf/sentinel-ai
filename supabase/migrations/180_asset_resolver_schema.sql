-- Phase 180: Asset ID Resolver schema
-- =====================================
-- Adds resolution metadata columns to documents table and creates the
-- asset_resolver_aliases lookup table.
--
-- NOT auto-applied — output for DBA review before running manually.

-- --------------------------------------------------------------------------- --
-- 1. Add resolution columns to documents
-- --------------------------------------------------------------------------- --
ALTER TABLE documents ADD COLUMN IF NOT EXISTS resolution_method TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS resolution_confidence FLOAT;

COMMENT ON COLUMN documents.resolution_method IS
  'How the asset_id was resolved: exact | fuzzy | llm_assisted | unresolved';
COMMENT ON COLUMN documents.resolution_confidence IS
  'Raw confidence score 0.0-1.0 from the resolver stage that produced the match';

-- --------------------------------------------------------------------------- --
-- 2. Index on resolved asset_id (speed up downstream joins)
-- --------------------------------------------------------------------------- --
CREATE INDEX IF NOT EXISTS idx_documents_asset_id
  ON documents(asset_id)
  WHERE asset_id IS NOT NULL;

-- --------------------------------------------------------------------------- --
-- 3. Alias lookup table
-- --------------------------------------------------------------------------- --
CREATE TABLE IF NOT EXISTS asset_resolver_aliases (
    site_id      TEXT NOT NULL,
    alias        TEXT NOT NULL,
    asset_id     TEXT NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY  (site_id, alias)
);

COMMENT ON TABLE asset_resolver_aliases IS
  'Normalised alias → equipment asset_id mappings per site.  Used by Stage 1 of AssetIDResolver.';
COMMENT ON COLUMN asset_resolver_aliases.site_id IS 'SENTINEL site identifier (e.g. site-002)';
COMMENT ON COLUMN asset_resolver_aliases.alias IS 'Normalised alias key (lowercase, no punctuation)';
COMMENT ON COLUMN asset_resolver_aliases.asset_id IS 'SENTINEL equipment code (e.g. S002-CHILLER-B1-001)';

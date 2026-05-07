ALTER TABLE point_asset_mappings
ADD COLUMN IF NOT EXISTS mapping_source TEXT DEFAULT 'catalog_resolver';

COMMENT ON COLUMN point_asset_mappings.mapping_source IS
'How this mapping was established: catalog_resolver | manual | wizard | import';

GRANT INSERT, UPDATE, DELETE ON point_asset_mappings TO service_role;

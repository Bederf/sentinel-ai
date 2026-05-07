ALTER TABLE recommendations
ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}';

COMMENT ON COLUMN recommendations.metadata IS
'Additional context for recommendations — e.g., affected_equipment list for grouped ZONE_GROUP recs';

GRANT UPDATE ON recommendations TO service_role;

-- Building geometry for cockpit 3D rendering
-- Stores per-site building shape extracted from photos via Claude Vision

ALTER TABLE sites ADD COLUMN IF NOT EXISTS building_geometry JSONB;

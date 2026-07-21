-- Add unique constraint on ml_models for ON CONFLICT upsert support
-- The ml_registry_sync service upserts by (equipment_type, model_type)
ALTER TABLE ml_models
ADD CONSTRAINT ml_models_equipment_model_type_unique
UNIQUE (equipment_type, model_type);

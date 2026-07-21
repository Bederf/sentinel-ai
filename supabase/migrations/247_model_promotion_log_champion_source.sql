ALTER TABLE model_promotion_log
ADD COLUMN IF NOT EXISTS champion_source TEXT
CHECK (champion_source IS NULL OR champion_source IN ('site', 'global_fallback'));

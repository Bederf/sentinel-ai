-- Enforce canonical prediction severity values on write.
-- Canonical states: critical, warning, healthy
-- Legacy inputs are normalized:
--   high, medium -> warning
--   low -> healthy

BEGIN;

-- Keep historical rows clean as a safety net.
UPDATE predictions
SET severity = CASE
    WHEN severity IN ('high', 'medium') THEN 'warning'
    WHEN severity = 'low' THEN 'healthy'
    ELSE severity
END
WHERE severity IN ('high', 'medium', 'low');

-- Normalization trigger for inserts/updates from any legacy writer.
CREATE OR REPLACE FUNCTION normalize_prediction_severity()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.severity IS NULL THEN
        RETURN NEW;
    END IF;

    NEW.severity := lower(trim(NEW.severity));

    IF NEW.severity IN ('high', 'medium') THEN
        NEW.severity := 'warning';
    ELSIF NEW.severity = 'low' THEN
        NEW.severity := 'healthy';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_normalize_prediction_severity ON predictions;
CREATE TRIGGER trg_normalize_prediction_severity
BEFORE INSERT OR UPDATE ON predictions
FOR EACH ROW
EXECUTE FUNCTION normalize_prediction_severity();

-- Re-assert canonical check constraint.
ALTER TABLE predictions DROP CONSTRAINT IF EXISTS predictions_severity_check;
ALTER TABLE predictions
ADD CONSTRAINT predictions_severity_check
CHECK (severity IN ('critical', 'warning', 'healthy'));

COMMIT;

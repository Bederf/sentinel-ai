-- Fix prediction severity to match system states: critical, warning, healthy
-- Instead of: critical, high, medium, low

-- Step 1: Drop old check constraint
ALTER TABLE predictions DROP CONSTRAINT IF EXISTS predictions_severity_check;

-- Step 2: Update existing data to match new severity values
-- high and medium become warning (health 60-80%)
-- critical stays critical (health < 60%)
-- low becomes healthy (health >= 80%)
UPDATE predictions
SET severity = CASE
    WHEN severity IN ('high', 'medium') THEN 'warning'
    WHEN severity = 'critical' THEN 'critical'
    WHEN severity = 'low' THEN 'healthy'
    ELSE severity
END;

-- Step 3: Add new check constraint with correct values
ALTER TABLE predictions
ADD CONSTRAINT predictions_severity_check
CHECK (severity = ANY (ARRAY['critical'::text, 'warning'::text, 'healthy'::text]));

-- Verify the changes
DO \$\$
DECLARE
    critical_count INTEGER;
    warning_count INTEGER;
    healthy_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO critical_count FROM predictions WHERE severity = 'critical';
    SELECT COUNT(*) INTO warning_count FROM predictions WHERE severity = 'warning';
    SELECT COUNT(*) INTO healthy_count FROM predictions WHERE severity = 'healthy';

    RAISE NOTICE 'Severity distribution after fix:';
    RAISE NOTICE '  critical: %', critical_count;
    RAISE NOTICE '  warning: %', warning_count;
    RAISE NOTICE '  healthy: %', healthy_count;
END $$;

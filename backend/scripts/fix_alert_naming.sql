-- Fix Alert Naming: Update alert titles to use actual equipment codes
-- Phase 081-03: Standardize alert naming from generic "Equipment #X" to actual equipment codes
--
-- This script updates all alerts to use the actual equipment code instead of generic numbering.
-- Run once to fix historical alerts, then all new alerts will use correct naming automatically.

BEGIN;

-- Create backup of alerts in case something goes wrong
CREATE TABLE IF NOT EXISTS alerts_backup_20260213 AS 
SELECT * FROM alerts WHERE created_at > NOW() - INTERVAL '7 days';

-- Update alerts to use equipment code in title
-- Pattern: Update "WARNING: Equipment #X" → "WARNING: S002-FCU-101 (FCU) - FCU Zone-101"
UPDATE alerts a
SET title = CONCAT(
    SUBSTRING_INDEX(a.title, ':', 1), ': ',
    COALESCE(e.code, 'UNKNOWN'), ' (',
    COALESCE(UPPER(e.type), 'EQUIPMENT'), ') - ',
    COALESCE(e.name, 'Unknown Equipment')
)
FROM equipment e
WHERE a.equipment_id = e.id
  AND a.title LIKE '%Equipment #%'  -- Only fix old-style alerts
  AND a.created_at > NOW() - INTERVAL '30 days';  -- Last 30 days only

-- Log the changes
SELECT 
    COUNT(*) as alerts_updated,
    MIN(a.created_at) as earliest_update,
    MAX(a.created_at) as latest_update
FROM alerts a
WHERE a.title LIKE '%S0%-%'  -- New format check
  AND a.updated_at > NOW() - INTERVAL '1 second';

COMMIT;

-- Verification: Show alerts with actual equipment codes
SELECT 
    a.id,
    a.severity,
    a.title,
    e.code,
    e.type,
    e.name,
    a.created_at
FROM alerts a
LEFT JOIN equipment e ON a.equipment_id = e.id
WHERE a.severity IN ('critical', 'warning')
  AND a.status = 'active'
ORDER BY a.created_at DESC
LIMIT 10;

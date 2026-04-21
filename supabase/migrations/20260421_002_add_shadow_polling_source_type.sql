-- Add shadow_polling to allowed source_type values in log_sources
-- Required for ShadowModePollingService to upsert log_sources without constraint violation

ALTER TABLE log_sources
DROP CONSTRAINT IF EXISTS log_sources_source_type_check;

ALTER TABLE log_sources
ADD CONSTRAINT log_sources_source_type_check
    CHECK (source_type = ANY (ARRAY[
        'bms_alarm',
        'bms_trend',
        'cafm_asset',
        'cafm_workorder',
        'bcc_alarm',
        'shadow_polling'
    ]));

-- DALI bridge telemetry for S002 exposes zone-level power and dim level, not a
-- reliable per-zone active luminaire count. Keep active_luminaires nullable so
-- ingestion can store measured watts/dim data without fabricating a count.

ALTER TABLE public.lighting_energy
ALTER COLUMN active_luminaires DROP NOT NULL;

-- Remove stale raw DALI lighting telemetry.
--
-- lighting_energy is raw telemetry. Current ingestion now writes canonical
-- site_id and zone_id values from the bridge. Historical seed rows older than
-- the raw telemetry retention window used legacy Z-* zone labels and should not
-- remain visible to live dashboards or reflex scans.

DELETE FROM public.lighting_energy
WHERE time < now() - interval '7 days';

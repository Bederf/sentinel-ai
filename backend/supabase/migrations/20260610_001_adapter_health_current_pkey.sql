-- Clean duplicate rows and add primary key to adapter_health_current
-- Without PK, every upsert() call silently INSERTed instead of UPDATEing,
-- creating ~700K duplicate rows over time.

DO $$
BEGIN
    -- Remove duplicates: keep the latest row per (site_id, adapter_name)
    DELETE FROM adapter_health_current a
    WHERE a.ctid NOT IN (
        SELECT MIN(b.ctid)
        FROM adapter_health_current b
        GROUP BY b.site_id, b.adapter_name
    );

    -- Add primary key so postgrest upsert(on_conflict='site_id,adapter_name') works
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'adapter_health_current'::regclass
        AND conname = 'adapter_health_current_pkey'
    ) THEN
        ALTER TABLE adapter_health_current
            ADD CONSTRAINT adapter_health_current_pkey
            PRIMARY KEY (site_id, adapter_name);
    END IF;
END $$;

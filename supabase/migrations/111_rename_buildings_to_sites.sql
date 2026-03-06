-- =====================================================
-- Migration 111: Rename buildings → sites, building_id → site_id
-- Full consistency rename across all tables, views, functions, triggers
-- =====================================================

BEGIN;

-- =====================================================
-- Phase 1: Drop materialized views (store query text, must be recreated)
-- =====================================================
DROP MATERIALIZED VIEW IF EXISTS v_dashboard_summary CASCADE;
DROP MATERIALIZED VIEW IF EXISTS v_building_status CASCADE;
DROP MATERIALIZED VIEW IF EXISTS v_equipment_health CASCADE;
DROP MATERIALIZED VIEW IF EXISTS v_active_alerts CASCADE;

-- =====================================================
-- Phase 2: Drop regular views that need name/column changes
-- =====================================================
DROP VIEW IF EXISTS v_building_asset_summary CASCADE;

-- =====================================================
-- Phase 3a: Drop triggers that depend on functions we're about to drop
-- =====================================================
DROP TRIGGER IF EXISTS trigger_update_building_equipment_counts ON equipment;
DROP TRIGGER IF EXISTS trigger_update_site_equipment_counts ON equipment;
DROP TRIGGER IF EXISTS trigger_building_3d_configs_timestamp ON building_3d_configs;
DROP TRIGGER IF EXISTS update_buildings_updated_at ON buildings;

-- =====================================================
-- Phase 3b: Drop functions that reference building_id in body text
-- =====================================================
DROP FUNCTION IF EXISTS get_user_accessible_buildings(TEXT, TEXT);
DROP FUNCTION IF EXISTS update_building_equipment_counts();
DROP FUNCTION IF EXISTS update_building_3d_configs_timestamp();
DROP FUNCTION IF EXISTS calculate_period_emissions(UUID, DATE, DATE, INT);
DROP FUNCTION IF EXISTS calculate_carbon_intensity(UUID, DATE);
DROP FUNCTION IF EXISTS get_technician_for_equipment_code(TEXT);
DROP FUNCTION IF EXISTS match_document_chunks(vector, integer, text, text, text, uuid, decimal);
DROP FUNCTION IF EXISTS hybrid_search_chunks(text, vector, integer, text, uuid, decimal, decimal);
DROP FUNCTION IF EXISTS refresh_all_materialized_views();

-- =====================================================
-- Phase 4: Rename the main table
-- =====================================================
ALTER TABLE buildings RENAME TO sites;

-- =====================================================
-- Phase 5: Handle building_3d_configs special case
-- (has both building_id UUID and site_id TEXT columns)
-- =====================================================
ALTER TABLE building_3d_configs RENAME COLUMN site_id TO site_code;
ALTER TABLE building_3d_configs RENAME COLUMN building_id TO site_id;
ALTER TABLE building_3d_configs RENAME TO site_3d_configs;

-- =====================================================
-- Phase 6: Rename building_id → site_id in all child tables
-- Uses dynamic block with exception handling for tables that may not exist
-- =====================================================
DO $$
DECLARE
    t TEXT;
    tables_to_rename TEXT[] := ARRAY[
        'alerts',
        'anomalies',
        'asset_health_snapshots',
        'baseline_service_records',
        'bms_alarms',
        'bms_trends',
        'cafm_assets',
        'cafm_workorders',
        'carbon_offset_projects',
        'certification_progress',
        'complaints',
        'condition_assessments',
        'contracts',
        'daily_sustainability_metrics',
        'dali_controllers',
        'dali_groups',
        'dali_luminaires',
        'dali_sensors',
        'dali_zone_mapping',
        'dali_zones',
        'desks',
        'devices',
        'diesel_tanks',
        'document_chunks',
        'documents',
        'emissions_baseline',
        'emissions_sources',
        'energy_centres',
        'energy_consumption_history',
        'equipment',
        'equipment_sensor_readings',
        'esg_metrics',
        'fire_action_log',
        'fire_alarms',
        'fire_cause_effect',
        'fire_dampers',
        'fire_pressurization',
        'fire_zones',
        'generator_groups',
        'generator_run_history',
        'generator_run_log',
        'generators',
        'hvac_zone_history',
        'hvac_zone_readings',
        'hvac_zones',
        'ingested_alarms',
        'ingested_trends',
        'log_sources',
        'point_asset_mappings',
        'predictions',
        'security_access_zones',
        'service_records',
        'site_technicians',
        'user_site_access',
        'work_orders',
        'zones'
    ];
BEGIN
    FOREACH t IN ARRAY tables_to_rename LOOP
        BEGIN
            EXECUTE format('ALTER TABLE %I RENAME COLUMN building_id TO site_id', t);
            RAISE NOTICE 'Renamed building_id → site_id in %', t;
        EXCEPTION
            WHEN undefined_table THEN
                RAISE NOTICE 'Table % does not exist, skipping', t;
            WHEN undefined_column THEN
                RAISE NOTICE 'Column building_id not found in %, skipping', t;
        END;
    END LOOP;
END $$;

-- =====================================================
-- Phase 7: Rename indexes containing 'building'
-- =====================================================
DO $$
DECLARE
    r RECORD;
    new_name TEXT;
BEGIN
    FOR r IN
        SELECT indexname
        FROM pg_indexes
        WHERE indexname LIKE '%building%'
    LOOP
        new_name := replace(r.indexname, 'building', 'site');
        BEGIN
            EXECUTE format('ALTER INDEX %I RENAME TO %I', r.indexname, new_name);
            RAISE NOTICE 'Renamed index % → %', r.indexname, new_name;
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'Could not rename index %: %', r.indexname, SQLERRM;
        END;
    END LOOP;
END $$;

-- =====================================================
-- Phase 8: Rename constraints containing 'building'
-- =====================================================
DO $$
DECLARE
    r RECORD;
    new_name TEXT;
BEGIN
    FOR r IN
        SELECT conname, conrelid::regclass AS tablename
        FROM pg_constraint
        WHERE conname LIKE '%building%'
    LOOP
        new_name := replace(r.conname, 'building', 'site');
        BEGIN
            EXECUTE format('ALTER TABLE %s RENAME CONSTRAINT %I TO %I',
                           r.tablename, r.conname, new_name);
            RAISE NOTICE 'Renamed constraint % → %', r.conname, new_name;
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'Could not rename constraint %: %', r.conname, SQLERRM;
        END;
    END LOOP;
END $$;

-- =====================================================
-- Phase 9: Recreate functions
-- =====================================================

-- 9a: get_user_accessible_sites (was get_user_accessible_buildings)
CREATE OR REPLACE FUNCTION get_user_accessible_sites(
    p_user_email TEXT,
    p_user_role TEXT DEFAULT 'auditor'
) RETURNS TABLE (site_id UUID, site_code TEXT) AS $$
BEGIN
    IF p_user_role = 'admin' THEN
        RETURN QUERY SELECT s.id, s.code FROM sites s;
    ELSE
        RETURN QUERY
        SELECT s.id, s.code FROM sites s
        JOIN user_site_access usa ON usa.site_id = s.id
        WHERE usa.user_email = LOWER(p_user_email);
    END IF;
END;
$$ LANGUAGE plpgsql;

-- 9b: update_site_equipment_counts (was update_building_equipment_counts)
CREATE OR REPLACE FUNCTION update_site_equipment_counts()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE sites SET equipment_count = equipment_count + 1
        WHERE id = NEW.site_id;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE sites SET equipment_count = GREATEST(equipment_count - 1, 0)
        WHERE id = OLD.site_id;
        RETURN OLD;
    ELSIF TG_OP = 'UPDATE' AND OLD.site_id != NEW.site_id THEN
        UPDATE sites SET equipment_count = equipment_count - 1
        WHERE id = OLD.site_id;
        UPDATE sites SET equipment_count = equipment_count + 1
        WHERE id = NEW.site_id;
        RETURN NEW;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 9c: update_site_3d_configs_timestamp (was update_building_3d_configs_timestamp)
CREATE OR REPLACE FUNCTION update_site_3d_configs_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 9d: calculate_period_emissions (renamed params)
CREATE OR REPLACE FUNCTION calculate_period_emissions(
    p_site_id UUID,
    p_start_date DATE,
    p_end_date DATE,
    p_scope INT DEFAULT NULL
)
RETURNS TABLE (
    scope INT,
    total_kg_co2e NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        es.scope,
        SUM(es.co2e_kg)::NUMERIC as total_kg_co2e
    FROM emissions_sources es
    WHERE es.site_id = p_site_id
        AND es.measurement_date >= p_start_date
        AND es.measurement_date <= p_end_date
        AND (p_scope IS NULL OR es.scope = p_scope)
    GROUP BY es.scope
    ORDER BY es.scope;
END;
$$ LANGUAGE plpgsql;

-- 9e: calculate_carbon_intensity (renamed params)
CREATE OR REPLACE FUNCTION calculate_carbon_intensity(
    p_site_id UUID,
    p_month DATE
)
RETURNS NUMERIC AS $$
DECLARE
    v_total_emissions NUMERIC;
    v_floor_area NUMERIC;
    v_intensity NUMERIC;
BEGIN
    SELECT SUM(co2e_kg) INTO v_total_emissions
    FROM emissions_sources
    WHERE site_id = p_site_id
        AND DATE_TRUNC('month', measurement_date) = DATE_TRUNC('month', p_month);

    SELECT floor_area_m2 INTO v_floor_area
    FROM emissions_baseline
    WHERE site_id = p_site_id
        AND baseline_year = EXTRACT(YEAR FROM p_month)
    LIMIT 1;

    IF v_floor_area IS NULL OR v_floor_area = 0 THEN
        RETURN NULL;
    END IF;

    v_intensity := ROUND((v_total_emissions / v_floor_area / 30)::NUMERIC, 3);
    RETURN v_intensity;
END;
$$ LANGUAGE plpgsql;

-- 9f: get_technician_for_equipment_code (renamed column refs)
CREATE OR REPLACE FUNCTION get_technician_for_equipment_code(p_equipment_code TEXT)
RETURNS TABLE (
    technician_id UUID,
    technician_name TEXT,
    technician_email TEXT,
    technician_phone TEXT,
    technician_telegram_id TEXT,
    specialty TEXT,
    site_id UUID
) AS $$
DECLARE
    v_site_id UUID;
    v_specialty TEXT;
    v_type_segment TEXT;
BEGIN
    SELECT e.site_id INTO v_site_id
    FROM equipment e
    WHERE e.code = p_equipment_code;

    IF v_site_id IS NULL THEN
        RETURN;
    END IF;

    v_type_segment := UPPER(SPLIT_PART(p_equipment_code, '-', 2));

    v_specialty := CASE
        WHEN v_type_segment IN ('CHILLER', 'AHU', 'FCU', 'VAV', 'SPLIT', 'CT', 'CRAC', 'PUMP', 'ZONE') THEN 'hvac'
        WHEN v_type_segment IN ('DALI', 'LUM') THEN 'dali'
        WHEN v_type_segment IN ('GEN', 'TX', 'UPS', 'ATS', 'MSB', 'MTR', 'PFC', 'FDR', 'MV', 'DB') THEN 'electrical'
        WHEN v_type_segment = 'FIRE' THEN 'fire'
        WHEN v_type_segment IN ('ACC', 'CCTV') THEN 'security'
        ELSE 'general'
    END;

    RETURN QUERY
    SELECT
        t.id, t.name, t.email, t.phone, t.telegram_id,
        st.specialty, st.site_id
    FROM site_technicians st
    JOIN technicians t ON st.technician_id = t.id
    WHERE st.site_id = v_site_id
    AND st.specialty = v_specialty
    AND st.is_primary = TRUE
    LIMIT 1;

    IF NOT FOUND THEN
        RETURN QUERY
        SELECT
            t.id, t.name, t.email, t.phone, t.telegram_id,
            st.specialty, st.site_id
        FROM site_technicians st
        JOIN technicians t ON st.technician_id = t.id
        WHERE st.site_id = v_site_id
        AND st.specialty = 'general'
        AND st.is_primary = TRUE
        LIMIT 1;
    END IF;
END;
$$ LANGUAGE plpgsql STABLE;

-- 9g: match_document_chunks (renamed params and column refs)
CREATE OR REPLACE FUNCTION match_document_chunks(
    query_embedding vector(384),
    match_count integer DEFAULT 5,
    filter_equipment_type text DEFAULT NULL,
    filter_document_type text DEFAULT NULL,
    filter_manufacturer text DEFAULT NULL,
    filter_site_id uuid DEFAULT NULL,
    similarity_threshold decimal DEFAULT 0.7
)
RETURNS TABLE (
    chunk_id uuid,
    document_id uuid,
    content text,
    section_title text,
    equipment_type text,
    document_type text,
    manufacturer text,
    model text,
    similarity decimal,
    document_title text,
    document_source text,
    site_id uuid
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        dc.id, dc.document_id, dc.content, dc.section_title,
        dc.equipment_type, dc.document_type, dc.manufacturer, dc.model,
        ROUND((1 - (dc.embedding <=> query_embedding))::numeric, 4) AS similarity,
        d.title AS document_title, d.source AS document_source,
        dc.site_id
    FROM document_chunks dc
    JOIN documents d ON dc.document_id = d.id
    WHERE
        (filter_equipment_type IS NULL OR dc.equipment_type = filter_equipment_type)
        AND (filter_document_type IS NULL OR dc.document_type = filter_document_type)
        AND (filter_manufacturer IS NULL OR dc.manufacturer = filter_manufacturer)
        AND d.is_latest = TRUE
        AND d.indexing_status = 'embedded'
        AND (1 - (dc.embedding <=> query_embedding)) >= similarity_threshold
        AND (filter_site_id IS NULL
             OR dc.site_id = filter_site_id
             OR dc.site_id IS NULL)
    ORDER BY dc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- 9h: hybrid_search_chunks (renamed params and column refs)
CREATE OR REPLACE FUNCTION hybrid_search_chunks(
    query_text text,
    query_embedding vector(384),
    match_count integer DEFAULT 5,
    filter_equipment_type text DEFAULT NULL,
    filter_site_id uuid DEFAULT NULL,
    keyword_weight decimal DEFAULT 0.3,
    semantic_weight decimal DEFAULT 0.7
)
RETURNS TABLE (
    chunk_id uuid,
    content text,
    equipment_type text,
    document_title text,
    hybrid_score decimal,
    keyword_score decimal,
    semantic_score decimal,
    site_id uuid
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH keyword_search AS (
        SELECT
            dc.id, dc.content, dc.equipment_type,
            d.title AS document_title, dc.site_id,
            ts_rank(to_tsvector('english', dc.content), plainto_tsquery('english', query_text)) AS kw_score
        FROM document_chunks dc
        JOIN documents d ON dc.document_id = d.id
        WHERE
            to_tsvector('english', dc.content) @@ plainto_tsquery('english', query_text)
            AND (filter_equipment_type IS NULL OR dc.equipment_type = filter_equipment_type)
            AND d.is_latest = TRUE
            AND (filter_site_id IS NULL
                 OR dc.site_id = filter_site_id
                 OR dc.site_id IS NULL)
    ),
    semantic_search AS (
        SELECT
            dc.id, dc.content, dc.equipment_type,
            d.title AS document_title, dc.site_id,
            (1 - (dc.embedding <=> query_embedding)) AS sem_score
        FROM document_chunks dc
        JOIN documents d ON dc.document_id = d.id
        WHERE
            (filter_equipment_type IS NULL OR dc.equipment_type = filter_equipment_type)
            AND d.is_latest = TRUE
            AND (filter_site_id IS NULL
                 OR dc.site_id = filter_site_id
                 OR dc.site_id IS NULL)
    )
    SELECT
        COALESCE(ks.id, ss.id) AS chunk_id,
        COALESCE(ks.content, ss.content) AS content,
        COALESCE(ks.equipment_type, ss.equipment_type) AS equipment_type,
        COALESCE(ks.document_title, ss.document_title) AS document_title,
        ROUND((
            (COALESCE(ks.kw_score, 0) * keyword_weight) +
            (COALESCE(ss.sem_score, 0) * semantic_weight)
        )::numeric, 4) AS hybrid_score,
        ROUND(COALESCE(ks.kw_score, 0)::numeric, 4) AS keyword_score,
        ROUND(COALESCE(ss.sem_score, 0)::numeric, 4) AS semantic_score,
        COALESCE(ks.site_id, ss.site_id) AS site_id
    FROM keyword_search ks
    FULL OUTER JOIN semantic_search ss ON ks.id = ss.id
    ORDER BY hybrid_score DESC
    LIMIT match_count;
END;
$$;

-- =====================================================
-- Phase 10: Recreate triggers
-- =====================================================

-- 10a: Equipment count trigger on equipment table
CREATE TRIGGER trigger_update_site_equipment_counts
    AFTER INSERT OR UPDATE OR DELETE ON equipment
    FOR EACH ROW EXECUTE FUNCTION update_site_equipment_counts();

-- 10b: Timestamp trigger on site_3d_configs
CREATE TRIGGER trigger_site_3d_configs_timestamp
    BEFORE UPDATE ON site_3d_configs
    FOR EACH ROW EXECUTE FUNCTION update_site_3d_configs_timestamp();

-- 10c: Updated_at trigger on sites table
CREATE TRIGGER update_sites_updated_at
    BEFORE UPDATE ON sites
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- Phase 11: Recreate materialized views
-- =====================================================

-- 11a: v_dashboard_summary (from migration 040)
CREATE MATERIALIZED VIEW v_dashboard_summary AS
WITH site_stats AS (
    SELECT COUNT(*) as total_sites FROM sites
),
equipment_stats AS (
    SELECT
        COUNT(*) as total_equipment,
        COUNT(*) FILTER (WHERE status = 'critical') as critical_equipment,
        COUNT(*) FILTER (WHERE status = 'warning') as warning_equipment,
        COUNT(*) FILTER (WHERE status = 'normal') as normal_equipment,
        COALESCE(AVG(health_score), 0) as avg_health_score
    FROM equipment
),
alert_stats AS (
    SELECT
        COUNT(*) FILTER (WHERE status = 'active') as active_alerts,
        COUNT(*) FILTER (WHERE status = 'active' AND severity = 'critical') as critical_alerts
    FROM alerts
    WHERE created_at >= NOW() - INTERVAL '30 days'
),
prediction_stats AS (
    SELECT COUNT(*) FILTER (WHERE status = 'active') as active_predictions
    FROM predictions
    WHERE created_at >= NOW() - INTERVAL '30 days'
),
work_order_stats AS (
    SELECT COUNT(*) as pending_work_orders
    FROM work_orders
    WHERE status IN ('scheduled', 'in_progress')
),
anomaly_stats AS (
    SELECT COUNT(*) as active_anomalies
    FROM anomalies
    WHERE status = 'active'
)
SELECT
    ss.total_sites,
    es.total_equipment,
    es.critical_equipment,
    es.warning_equipment,
    es.normal_equipment,
    es.avg_health_score,
    COALESCE(als.active_alerts, 0) as active_alerts,
    COALESCE(als.critical_alerts, 0) as critical_alerts,
    COALESCE(ps.active_predictions, 0) as active_predictions,
    COALESCE(wos.pending_work_orders, 0) as pending_work_orders,
    COALESCE(ans.active_anomalies, 0) as active_anomalies
FROM site_stats ss, equipment_stats es, alert_stats als,
     prediction_stats ps, work_order_stats wos, anomaly_stats ans;

CREATE INDEX idx_dashboard_summary_site_count ON v_dashboard_summary(total_sites);

-- 11b: v_site_status (was v_building_status, from migration 005)
CREATE MATERIALIZED VIEW v_site_status AS
SELECT
    s.id,
    s.code,
    s.name,
    s.region,
    s.type,
    COUNT(e.id) as equipment_count,
    COUNT(e.id) FILTER (WHERE e.status = 'critical') as critical_count,
    COUNT(e.id) FILTER (WHERE e.status = 'warning') as warning_count,
    COUNT(e.id) FILTER (WHERE e.status = 'normal') as normal_count,
    COALESCE(AVG(e.health_score), 0) as avg_health_score,
    COUNT(a.id) FILTER (WHERE a.status = 'active') as active_alerts,
    COUNT(a.id) FILTER (WHERE a.severity = 'critical' AND a.status = 'active') as critical_alerts,
    COUNT(p.id) FILTER (WHERE p.status = 'active') as active_predictions,
    CASE
        WHEN COUNT(a.id) FILTER (WHERE a.severity = 'critical' AND a.status = 'active') > 0 THEN 'critical'
        WHEN COUNT(a.id) FILTER (WHERE a.status = 'active') > 0 OR COUNT(e.id) FILTER (WHERE e.status = 'critical') > 0 THEN 'warning'
        ELSE 'normal'
    END as computed_status,
    s.updated_at
FROM sites s
LEFT JOIN equipment e ON e.site_id = s.id
LEFT JOIN alerts a ON a.site_id = s.id
LEFT JOIN predictions p ON p.site_id = s.id
GROUP BY s.id, s.code, s.name, s.region, s.type, s.updated_at;

CREATE INDEX idx_site_status_region ON v_site_status(region);
CREATE INDEX idx_site_status_computed_status ON v_site_status(computed_status);

-- 11c: v_equipment_health (from migration 040)
CREATE MATERIALIZED VIEW v_equipment_health AS
SELECT
    e.id,
    e.code,
    e.name,
    e.type,
    e.status,
    e.health_score,
    s.id as site_id,
    s.code as site_code,
    s.name as site_name,
    s.region,
    COALESCE(alert_counts.cnt, 0) as active_alerts,
    COALESCE(prediction_counts.cnt, 0) as active_predictions,
    COALESCE(anomaly_counts.cnt, 0) as active_anomalies,
    COALESCE(work_order_counts.cnt, 0) as pending_work_orders,
    CASE
        WHEN e.status = 'critical' OR COALESCE(critical_alert_counts.cnt, 0) > 0 THEN 'critical'
        WHEN e.status = 'warning' OR COALESCE(alert_counts.cnt, 0) > 0 THEN 'warning'
        ELSE 'normal'
    END as computed_status,
    e.updated_at
FROM equipment e
JOIN sites s ON e.site_id = s.id
LEFT JOIN (
    SELECT equipment_id, COUNT(*) as cnt FROM alerts WHERE status = 'active' GROUP BY equipment_id
) alert_counts ON alert_counts.equipment_id = e.id
LEFT JOIN (
    SELECT equipment_id, COUNT(*) as cnt FROM alerts WHERE status = 'active' AND severity = 'critical' GROUP BY equipment_id
) critical_alert_counts ON critical_alert_counts.equipment_id = e.id
LEFT JOIN (
    SELECT equipment_id, COUNT(*) as cnt FROM predictions WHERE status = 'active' GROUP BY equipment_id
) prediction_counts ON prediction_counts.equipment_id = e.id
LEFT JOIN (
    SELECT equipment_id, COUNT(*) as cnt FROM anomalies WHERE status = 'active' GROUP BY equipment_id
) anomaly_counts ON anomaly_counts.equipment_id = e.id
LEFT JOIN (
    SELECT equipment_id, COUNT(*) as cnt FROM work_orders WHERE status IN ('scheduled', 'in_progress') GROUP BY equipment_id
) work_order_counts ON work_order_counts.equipment_id = e.id;

CREATE INDEX idx_equipment_health_site_id ON v_equipment_health(site_id);
CREATE INDEX idx_equipment_health_computed_status ON v_equipment_health(computed_status);
CREATE INDEX idx_equipment_health_type ON v_equipment_health(type);
CREATE INDEX idx_equipment_health_score ON v_equipment_health(health_score DESC);

-- 11d: v_active_alerts (from migration 005)
CREATE MATERIALIZED VIEW v_active_alerts AS
SELECT
    a.id,
    a.type,
    a.severity,
    a.status,
    a.title,
    a.message,
    a.created_at,
    a.acknowledged_at,
    a.acknowledged_by,
    e.id as equipment_id,
    e.code as equipment_code,
    e.name as equipment_name,
    e.type as equipment_type,
    s.id as site_id,
    s.code as site_code,
    s.name as site_name,
    s.region,
    s.address
FROM alerts a
LEFT JOIN equipment e ON a.equipment_id = e.id
LEFT JOIN sites s ON a.site_id = s.id
WHERE a.status = 'active'
ORDER BY a.severity DESC, a.created_at DESC;

CREATE INDEX idx_active_alerts_severity ON v_active_alerts(severity DESC);
CREATE INDEX idx_active_alerts_site_id ON v_active_alerts(site_id);

-- =====================================================
-- Phase 12: Recreate regular views
-- =====================================================

-- 12a: v_site_asset_summary (was v_building_asset_summary, from migration 017)
CREATE OR REPLACE VIEW v_site_asset_summary AS
SELECT
    s.id AS site_id,
    s.code AS site_code,
    s.name AS site_name,
    COALESCE(eq.equipment_count, 0) AS equipment_count,
    COALESCE(hz.hvac_zone_count, 0) AS hvac_zone_count,
    COALESCE(gen.generator_count, 0) AS generator_count,
    COALESCE(grp.generator_group_count, 0) AS generator_group_count,
    COALESCE(tank.diesel_tank_count, 0) AS diesel_tank_count,
    COALESCE(ec.energy_centre_count, 0) AS energy_centre_count,
    COALESCE(mv.mv_incomer_count, 0) AS mv_incomer_count,
    COALESCE(tx.transformer_count, 0) AS transformer_count,
    COALESCE(lv.lv_switchboard_count, 0) AS lv_switchboard_count,
    COALESCE(ats.ats_count, 0) AS ats_count,
    COALESCE(mtr.power_meter_count, 0) AS power_meter_count,
    COALESCE(pfc.pfc_bank_count, 0) AS pfc_bank_count,
    COALESCE(ups.ups_count, 0) AS ups_count,
    COALESCE(fdr.feeder_count, 0) AS feeder_count,
    COALESCE(dali.dali_controller_count, 0) AS dali_controller_count,
    (
        COALESCE(eq.equipment_count, 0) +
        COALESCE(hz.hvac_zone_count, 0) +
        COALESCE(gen.generator_count, 0) +
        COALESCE(grp.generator_group_count, 0) +
        COALESCE(tank.diesel_tank_count, 0) +
        COALESCE(ec.energy_centre_count, 0) +
        COALESCE(mv.mv_incomer_count, 0) +
        COALESCE(tx.transformer_count, 0) +
        COALESCE(lv.lv_switchboard_count, 0) +
        COALESCE(ats.ats_count, 0) +
        COALESCE(mtr.power_meter_count, 0) +
        COALESCE(pfc.pfc_bank_count, 0) +
        COALESCE(ups.ups_count, 0) +
        COALESCE(fdr.feeder_count, 0) +
        COALESCE(dali.dali_controller_count, 0)
    ) AS total_assets,
    COALESCE(desks.desk_count, 0) AS desk_count,
    COALESCE(lum.luminaire_count, 0) AS luminaire_count,
    COALESCE(sens.dali_sensor_count, 0) AS dali_sensor_count
FROM sites s
LEFT JOIN (SELECT site_id, COUNT(*) AS equipment_count FROM equipment GROUP BY site_id) eq ON eq.site_id = s.id
LEFT JOIN (SELECT site_id, COUNT(*) AS hvac_zone_count FROM hvac_zones GROUP BY site_id) hz ON hz.site_id = s.id
LEFT JOIN (SELECT site_id, COUNT(*) AS generator_count FROM generators GROUP BY site_id) gen ON gen.site_id = s.id
LEFT JOIN (SELECT site_id, COUNT(*) AS generator_group_count FROM generator_groups GROUP BY site_id) grp ON grp.site_id = s.id
LEFT JOIN (SELECT site_id, COUNT(*) AS diesel_tank_count FROM diesel_tanks GROUP BY site_id) tank ON tank.site_id = s.id
LEFT JOIN (SELECT site_id, COUNT(*) AS energy_centre_count FROM energy_centres GROUP BY site_id) ec ON ec.site_id = s.id
LEFT JOIN (SELECT ec.site_id, COUNT(*) AS mv_incomer_count FROM mv_incomers mv JOIN energy_centres ec ON ec.id = mv.energy_centre_id GROUP BY ec.site_id) mv ON mv.site_id = s.id
LEFT JOIN (SELECT ec.site_id, COUNT(*) AS transformer_count FROM transformers tx JOIN energy_centres ec ON ec.id = tx.energy_centre_id GROUP BY ec.site_id) tx ON tx.site_id = s.id
LEFT JOIN (SELECT ec.site_id, COUNT(*) AS lv_switchboard_count FROM lv_switchboards lv JOIN energy_centres ec ON ec.id = lv.energy_centre_id GROUP BY ec.site_id) lv ON lv.site_id = s.id
LEFT JOIN (SELECT ec.site_id, COUNT(*) AS ats_count FROM ats_units ats JOIN energy_centres ec ON ec.id = ats.energy_centre_id GROUP BY ec.site_id) ats ON ats.site_id = s.id
LEFT JOIN (SELECT ec.site_id, COUNT(*) AS power_meter_count FROM power_meters pm JOIN energy_centres ec ON ec.id = pm.energy_centre_id GROUP BY ec.site_id) mtr ON mtr.site_id = s.id
LEFT JOIN (SELECT ec.site_id, COUNT(*) AS pfc_bank_count FROM pfc_banks pfc JOIN energy_centres ec ON ec.id = pfc.energy_centre_id GROUP BY ec.site_id) pfc ON pfc.site_id = s.id
LEFT JOIN (SELECT ec.site_id, COUNT(*) AS ups_count FROM ups_systems ups JOIN energy_centres ec ON ec.id = ups.energy_centre_id GROUP BY ec.site_id) ups ON ups.site_id = s.id
LEFT JOIN (SELECT ec.site_id, COUNT(*) AS feeder_count FROM feeders f JOIN energy_centres ec ON ec.id = f.energy_centre_id GROUP BY ec.site_id) fdr ON fdr.site_id = s.id
LEFT JOIN (SELECT site_id, COUNT(*) AS dali_controller_count FROM dali_controllers GROUP BY site_id) dali ON dali.site_id = s.code
LEFT JOIN (SELECT site_id, COUNT(*) AS desk_count FROM desks GROUP BY site_id) desks ON desks.site_id = s.id
LEFT JOIN (SELECT dc.site_id, COUNT(*) AS luminaire_count FROM dali_luminaires dl JOIN dali_controllers dc ON dc.id = dl.controller_id GROUP BY dc.site_id) lum ON lum.site_id = s.code
LEFT JOIN (SELECT dc.site_id, COUNT(*) AS dali_sensor_count FROM dali_sensors ds JOIN dali_controllers dc ON dc.id = ds.controller_id GROUP BY dc.site_id) sens ON sens.site_id = s.code;

COMMENT ON VIEW v_site_asset_summary IS 'Aggregated asset counts by category for each site. Used by sites API and dashboard.';

-- =====================================================
-- Phase 13: Recreate refresh function (references view names)
-- =====================================================
CREATE OR REPLACE FUNCTION refresh_all_materialized_views()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY v_dashboard_summary;
    REFRESH MATERIALIZED VIEW CONCURRENTLY v_equipment_health;
    REFRESH MATERIALIZED VIEW CONCURRENTLY v_site_status;
    REFRESH MATERIALIZED VIEW CONCURRENTLY v_active_alerts;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =====================================================
-- Phase 14: Compatibility aliases (safety net, drop later)
-- =====================================================

-- View alias so any leftover code referencing 'buildings' table still works
CREATE VIEW buildings AS SELECT * FROM sites;

-- View alias for old asset summary view name
CREATE VIEW v_building_asset_summary AS SELECT * FROM v_site_asset_summary;

-- Function alias for old accessible buildings function
CREATE OR REPLACE FUNCTION get_user_accessible_buildings(
    p_user_email TEXT,
    p_user_role TEXT DEFAULT 'auditor'
) RETURNS TABLE (building_id UUID, building_code TEXT) AS $$
BEGIN
    RETURN QUERY SELECT site_id, site_code FROM get_user_accessible_sites(p_user_email, p_user_role);
END;
$$ LANGUAGE plpgsql;

COMMIT;

-- =====================================================
-- Migration 017: Asset Count Aggregation View
-- Provides categorized asset counts per building
-- Used by sites API and SiteCard component
-- =====================================================

-- View for building asset summary
CREATE OR REPLACE VIEW v_building_asset_summary AS
SELECT
  b.id AS building_id,
  b.code AS building_code,
  b.name AS building_name,

  -- Equipment (legacy table)
  COALESCE(eq.equipment_count, 0) AS equipment_count,

  -- HVAC Zones
  COALESCE(hz.hvac_zone_count, 0) AS hvac_zone_count,

  -- Generators, Groups, Tanks
  COALESCE(gen.generator_count, 0) AS generator_count,
  COALESCE(grp.generator_group_count, 0) AS generator_group_count,
  COALESCE(tank.diesel_tank_count, 0) AS diesel_tank_count,

  -- Energy Centre components
  COALESCE(ec.energy_centre_count, 0) AS energy_centre_count,
  COALESCE(mv.mv_incomer_count, 0) AS mv_incomer_count,
  COALESCE(tx.transformer_count, 0) AS transformer_count,
  COALESCE(lv.lv_switchboard_count, 0) AS lv_switchboard_count,
  COALESCE(ats.ats_count, 0) AS ats_count,
  COALESCE(mtr.power_meter_count, 0) AS power_meter_count,
  COALESCE(pfc.pfc_bank_count, 0) AS pfc_bank_count,
  COALESCE(ups.ups_count, 0) AS ups_count,
  COALESCE(fdr.feeder_count, 0) AS feeder_count,

  -- DALI Controllers
  COALESCE(dali.dali_controller_count, 0) AS dali_controller_count,

  -- Total assets (excluding desks and luminaires)
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

  -- Supplementary counts (not included in total_assets)
  COALESCE(desks.desk_count, 0) AS desk_count,
  COALESCE(lum.luminaire_count, 0) AS luminaire_count,
  COALESCE(sens.dali_sensor_count, 0) AS dali_sensor_count

FROM buildings b

-- Equipment (legacy)
LEFT JOIN (
  SELECT building_id, COUNT(*) AS equipment_count
  FROM equipment
  GROUP BY building_id
) eq ON eq.building_id = b.id

-- HVAC Zones
LEFT JOIN (
  SELECT building_id, COUNT(*) AS hvac_zone_count
  FROM hvac_zones
  GROUP BY building_id
) hz ON hz.building_id = b.id

-- Generators
LEFT JOIN (
  SELECT building_id, COUNT(*) AS generator_count
  FROM generators
  GROUP BY building_id
) gen ON gen.building_id = b.id

-- Generator Groups
LEFT JOIN (
  SELECT building_id, COUNT(*) AS generator_group_count
  FROM generator_groups
  GROUP BY building_id
) grp ON grp.building_id = b.id

-- Diesel Tanks
LEFT JOIN (
  SELECT building_id, COUNT(*) AS diesel_tank_count
  FROM diesel_tanks
  GROUP BY building_id
) tank ON tank.building_id = b.id

-- Energy Centres
LEFT JOIN (
  SELECT building_id, COUNT(*) AS energy_centre_count
  FROM energy_centres
  GROUP BY building_id
) ec ON ec.building_id = b.id

-- MV Incomers (via energy centre)
LEFT JOIN (
  SELECT ec.building_id, COUNT(*) AS mv_incomer_count
  FROM mv_incomers mv
  JOIN energy_centres ec ON ec.id = mv.energy_centre_id
  GROUP BY ec.building_id
) mv ON mv.building_id = b.id

-- Transformers (via energy centre)
LEFT JOIN (
  SELECT ec.building_id, COUNT(*) AS transformer_count
  FROM transformers tx
  JOIN energy_centres ec ON ec.id = tx.energy_centre_id
  GROUP BY ec.building_id
) tx ON tx.building_id = b.id

-- LV Switchboards (via energy centre)
LEFT JOIN (
  SELECT ec.building_id, COUNT(*) AS lv_switchboard_count
  FROM lv_switchboards lv
  JOIN energy_centres ec ON ec.id = lv.energy_centre_id
  GROUP BY ec.building_id
) lv ON lv.building_id = b.id

-- ATS Units (via energy centre)
LEFT JOIN (
  SELECT ec.building_id, COUNT(*) AS ats_count
  FROM ats_units ats
  JOIN energy_centres ec ON ec.id = ats.energy_centre_id
  GROUP BY ec.building_id
) ats ON ats.building_id = b.id

-- Power Meters (via energy centre)
LEFT JOIN (
  SELECT ec.building_id, COUNT(*) AS power_meter_count
  FROM power_meters pm
  JOIN energy_centres ec ON ec.id = pm.energy_centre_id
  GROUP BY ec.building_id
) mtr ON mtr.building_id = b.id

-- PFC Banks (via energy centre)
LEFT JOIN (
  SELECT ec.building_id, COUNT(*) AS pfc_bank_count
  FROM pfc_banks pfc
  JOIN energy_centres ec ON ec.id = pfc.energy_centre_id
  GROUP BY ec.building_id
) pfc ON pfc.building_id = b.id

-- UPS Systems (via energy centre)
LEFT JOIN (
  SELECT ec.building_id, COUNT(*) AS ups_count
  FROM ups_systems ups
  JOIN energy_centres ec ON ec.id = ups.energy_centre_id
  GROUP BY ec.building_id
) ups ON ups.building_id = b.id

-- Feeders (via energy centre)
LEFT JOIN (
  SELECT ec.building_id, COUNT(*) AS feeder_count
  FROM feeders f
  JOIN energy_centres ec ON ec.id = f.energy_centre_id
  GROUP BY ec.building_id
) fdr ON fdr.building_id = b.id

-- DALI Controllers (via site_id matching building code)
LEFT JOIN (
  SELECT site_id, COUNT(*) AS dali_controller_count
  FROM dali_controllers
  GROUP BY site_id
) dali ON dali.site_id = b.code

-- Desks (supplementary, not in total)
LEFT JOIN (
  SELECT building_id, COUNT(*) AS desk_count
  FROM desks
  GROUP BY building_id
) desks ON desks.building_id = b.id

-- DALI Luminaires (supplementary, not in total)
LEFT JOIN (
  SELECT dc.site_id, COUNT(*) AS luminaire_count
  FROM dali_luminaires dl
  JOIN dali_controllers dc ON dc.id = dl.controller_id
  GROUP BY dc.site_id
) lum ON lum.site_id = b.code

-- DALI Sensors (supplementary, not in total)
LEFT JOIN (
  SELECT dc.site_id, COUNT(*) AS dali_sensor_count
  FROM dali_sensors ds
  JOIN dali_controllers dc ON dc.id = ds.controller_id
  GROUP BY dc.site_id
) sens ON sens.site_id = b.code;

-- Comments
COMMENT ON VIEW v_building_asset_summary IS 'Aggregated asset counts by category for each building. Used by sites API and dashboard.';

-- Materialized view for performance (optional, refresh periodically)
-- Uncomment if query performance becomes an issue
/*
CREATE MATERIALIZED VIEW mv_building_asset_summary AS
SELECT * FROM v_building_asset_summary;

CREATE UNIQUE INDEX idx_mv_asset_summary_building ON mv_building_asset_summary(building_id);

-- Refresh function
CREATE OR REPLACE FUNCTION refresh_asset_summary()
RETURNS TRIGGER AS $$
BEGIN
  REFRESH MATERIALIZED VIEW CONCURRENTLY mv_building_asset_summary;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;
*/

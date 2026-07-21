-- =====================================================
-- Migration: ML model config per site + equipment type
-- Source of truth for which ML models train on which
-- equipment types and what features they use.
--
-- site_id = NULL means global default template.
-- Per-site rows override the global template for that site.
-- Populated automatically during SIMBIOT onboarding wizard.
-- =====================================================

CREATE TABLE IF NOT EXISTS ml_model_config (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id text,
  equipment_type text NOT NULL,
  lstm_features jsonb,
  autoencoder_features jsonb,
  failure_types jsonb,
  expected_life_years numeric,
  ml_trainable boolean DEFAULT true,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  UNIQUE (site_id, equipment_type)
);

-- Seed global templates (site_id = NULL means apply to all sites unless overridden)
INSERT INTO ml_model_config (site_id, equipment_type, lstm_features, autoencoder_features, failure_types, expected_life_years, ml_trainable) VALUES
  -- ── Mechanical HVAC + electrical with degradation ──
  (NULL,'chiller',    '["chw_supply_temp","chw_return_temp","suction_pressure","discharge_pressure","compressor_current"]'::jsonb, '["chw_supply_temp","chw_return_temp","suction_pressure","discharge_pressure","compressor_current"]'::jsonb, '["compressor_failure","refrigerant_leak","condenser_fouling","oil_issue","electrical"]'::jsonb, 20, true),
  (NULL,'ahu',        '["supply_temp","return_temp","filter_dp","fan_current","mixed_air_temp"]'::jsonb, '["supply_temp","return_temp","filter_dp","fan_current","mixed_air_temp"]'::jsonb, '["fan_motor","belt_failure","coil_fouling","damper_actuator","filter_blockage"]'::jsonb, 15, true),
  (NULL,'fcu',        '["supply_temp","fan_current","valve_position"]'::jsonb, '["supply_temp","fan_current","valve_position"]'::jsonb, '["fan_motor","valve_actuator","thermostat","filter_blockage"]'::jsonb, 12, true),
  (NULL,'vav',        '["airflow","damper_position","zone_temp","supply_temp"]'::jsonb, '["airflow","damper_position","zone_temp","supply_temp"]'::jsonb, NULL, 15, true),
  (NULL,'pump',       '["flow_rate","discharge_pressure","motor_current","vibration","temperature"]'::jsonb, '["flow_rate","discharge_pressure","motor_current","vibration","temperature"]'::jsonb, NULL, 10, true),
  (NULL,'cooling_tower', '["basin_temp","fan_speed","water_level","fan_current"]'::jsonb, '["basin_temp","fan_speed","water_level","fan_current"]'::jsonb, NULL, 15, true),
  (NULL,'generator',  '["battery_voltage","oil_pressure","coolant_temp","load_pct"]'::jsonb, '["battery_voltage","oil_pressure","coolant_temp","load_pct"]'::jsonb, '["battery_failure","fuel_system","starter_motor","alternator","cooling_system"]'::jsonb, 20, true),
  (NULL,'ups',        '["battery_voltage","load_pct","temperature"]'::jsonb, '["battery_voltage","load_pct","temperature"]'::jsonb, '["battery_failure","inverter","capacitor","overload"]'::jsonb, 10, true),
  (NULL,'bess',       '["soc_pct","charge_power_kw","discharge_power_kw","cell_temp"]'::jsonb, '["soc_pct","charge_power_kw","discharge_power_kw","cell_temp"]'::jsonb, NULL, 10, true),
  (NULL,'inverter',   '["dc_input_power_kw","ac_output_power_kw","efficiency_pct","inverter_temp"]'::jsonb, '["dc_input_power_kw","ac_output_power_kw","efficiency_pct","inverter_temp"]'::jsonb, NULL, 12, true),
  (NULL,'split',      '["room_temp","supply_temp","fan_speed","valve_position"]'::jsonb, '["room_temp","supply_temp","fan_speed","valve_position"]'::jsonb, NULL, 10, true),
  (NULL,'transformer','["winding_temp","oil_temp","load_pct","tap_position"]'::jsonb, '["winding_temp","oil_temp","load_pct","tap_position"]'::jsonb, NULL, 25, true),
  (NULL,'crac',       '["supply_temp","return_temp","humidity_pct","compressor_current"]'::jsonb, '["supply_temp","return_temp","humidity_pct","compressor_current"]'::jsonb, NULL, 12, true),
  (NULL,'ats',        '["mains_voltage","generator_voltage","position","transfer_status"]'::jsonb, '["mains_voltage","generator_voltage","position","transfer_status"]'::jsonb, NULL, 15, true),
  (NULL,'pfc',        '["power_factor","reactive_power_kvar","current_a","voltage_v"]'::jsonb, '["power_factor","reactive_power_kvar","current_a","voltage_v"]'::jsonb, NULL, 10, true),
  -- ── Individual mechanical components ──
  (NULL,'compressor', '["motor_current","discharge_pressure","suction_pressure","temperature"]'::jsonb, '["motor_current","discharge_pressure","suction_pressure","temperature"]'::jsonb, NULL, 10, true),
  (NULL,'fan',        '["fan_current","fan_speed","vibration"]'::jsonb, '["fan_current","fan_speed","vibration"]'::jsonb, NULL, 8, true),
  (NULL,'motor',      '["motor_current","temperature","vibration"]'::jsonb, '["motor_current","temperature","vibration"]'::jsonb, NULL, 10, true),
  -- ── Solar / renewable ──
  (NULL,'solar_panel','["power_kw","voltage_v","current_a","efficiency_pct"]'::jsonb, '["power_kw","voltage_v","current_a","efficiency_pct"]'::jsonb, NULL, 25, true),
  (NULL,'pv_array',   '["power_kw","voltage_v","current_a","efficiency_pct"]'::jsonb, '["power_kw","voltage_v","current_a","efficiency_pct"]'::jsonb, NULL, 25, true),
  -- ── Lighting / DALI ──
  (NULL,'dali_controller', '["power_watts","brightness","lux","occupancy","lamp_hours","driver_temp"]'::jsonb, '["power_watts","brightness","lux","occupancy","lamp_hours","driver_temp"]'::jsonb, '["lamp_failure","driver_fault","emergency_battery_fault"]'::jsonb, 7, true),
  (NULL,'luminaire',  '["power_watts","brightness","lamp_hours"]'::jsonb, '["power_watts","brightness","lamp_hours"]'::jsonb, NULL, 7, true),
  -- ── Meters ──
  (NULL,'meter',      '["active_power_kw","energy_kwh","power_factor"]'::jsonb, '["active_power_kw","energy_kwh","power_factor"]'::jsonb, NULL, 15, true),
  (NULL,'water_meter','["flow_rate","totalizer","pressure"]'::jsonb, '["flow_rate","totalizer","pressure"]'::jsonb, NULL, 10, true),
  (NULL,'flow_meter', '["flow_rate","totalizer","pressure"]'::jsonb, '["flow_rate","totalizer","pressure"]'::jsonb, NULL, 10, true),
  -- ── Security / access ──
  (NULL,'door',       '["door_status","cycle_count"]'::jsonb, NULL, NULL, 5, true),
  (NULL,'badge_reader','["access_count","auth_fail_count"]'::jsonb, NULL, NULL, 5, true),
  (NULL,'camera',     '["health_status","bitrate","fps"]'::jsonb, NULL, NULL, 5, true),
  (NULL,'access_control', '["access_count","auth_fail_count","door_status"]'::jsonb, NULL, NULL, 5, true),
  -- ── Fire / safety ──
  (NULL,'fire_panel', '["alarm_count","fault_count","power_status"]'::jsonb, NULL, NULL, 10, true),
  (NULL,'detector',   '["smoke_level","temperature","health_status"]'::jsonb, NULL, NULL, 10, true)
ON CONFLICT (site_id, equipment_type) DO NOTHING;

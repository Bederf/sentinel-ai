-- Site-specific seed: site-005 building profile (Busamed Gateway Private Hospital)
--
-- This file contains site-specific seed data and must NOT be included in the
-- base migration image. It is run during SIMBIOT onboarding for a specific site.
--
-- Deployment model: ONE Jetson = ONE building = ONE Supabase instance.
-- The base migration (20260322_001_building_profile.sql) ships the schema to every
-- deployment. This seed file is applied AFTER the site is known.
--
-- Run during SIMBIOT onboarding for site-005. SITE_ID injected from edge.conf.
-- Idempotent — safe to re-run (guarded by WHERE code = 'site-005').
--
-- HOSPITAL PROFILE — deviates from office defaults in the following ways:
--   operating_hours : 24/7 — no after-hours cost-optimized posture (clinical operations never stop)
--   comfort weight  : 0.85 — patient safety overrides cost efficiency
--   cost weight     : 0.05 — cost nearly irrelevant; patient comfort and equipment uptime dominate
--   asset weight    : 0.10 — critical medical equipment continuity
--   CO₂ limit       : 700 ppm (stricter than office 800 ppm — ICU/theatre zones)
--   max_drift       : 1.0°C (tighter than office 2.0°C — clinical temperature control)
--   urgency_threshold: 0.60 (lower = more sensitive — fault response faster in clinical setting)
--   dismiss_window  : 15 min (shorter than office 30 min — clinical staff must re-confirm faster)
--   discomfort_alert: 5 min  (faster escalation — patient impact threshold is lower)

UPDATE buildings
SET profile = '{
  "deployment_mode": "ghost",
  "operating_postures": {
    "active_posture": "comfort_priority",
    "schedules": {
      "business_hours": {"start": "00:00", "end": "23:59", "posture": "comfort_priority"},
      "after_hours":    {"start": "00:00", "end": "23:59", "posture": "comfort_priority"}
    },
    "weights": {"comfort": 0.85, "cost": 0.05, "asset": 0.10}
  },
  "thresholds": {
    "comfort":  {"temp_setpoint": 22.0, "max_drift": 1.0, "co2_limit_ppm": 700},
    "temporal": {"thermal_mass": null, "insulation_factor": null, "heat_transfer_coefficient": null}
  },
  "crisis_logic": {
    "urgency_threshold": 0.60,
    "dismiss_window_minutes": 15,
    "min_time_to_discomfort_alert": 5
  },
  "module_display": {
    "hvac":      "hidden",
    "energy":    "hidden",
    "lighting":  "hidden",
    "solar":     "hidden",
    "occupancy": "hidden",
    "fire":      "hidden",
    "security":  "hidden",
    "water":     "hidden"
  }
}'::jsonb
WHERE code = 'site-005'
  AND (profile IS NULL OR profile = '{}'::jsonb);

-- Structural validation — confirms hospital-grade values are in place
-- Run after the UPDATE to verify the profile was applied correctly.
-- Safe to skip in automated pipelines (RAISE NOTICE, not EXCEPTION on missing row).
DO $$
DECLARE v_profile JSONB;
BEGIN
  SELECT profile INTO v_profile FROM buildings WHERE code = 'site-005';

  IF v_profile IS NULL THEN
    RAISE NOTICE 'site-005 row not found — run SIMBIOT onboarding first to create the buildings row';
    RETURN;
  END IF;

  -- weights must sum to 1.0
  IF ABS(
    (v_profile->'operating_postures'->'weights'->>'comfort')::float +
    (v_profile->'operating_postures'->'weights'->>'cost')::float +
    (v_profile->'operating_postures'->'weights'->>'asset')::float - 1.0
  ) > 0.001 THEN
    RAISE EXCEPTION 'site-005 posture weights must sum to 1.0';
  END IF;

  -- comfort weight must be >= 0.80 — patient safety requires it
  IF (v_profile->'operating_postures'->'weights'->>'comfort')::float < 0.80 THEN
    RAISE EXCEPTION 'site-005 comfort weight must be >= 0.80 (hospital patient safety requirement)';
  END IF;

  -- CO₂ limit must be <= 750 ppm for clinical zones
  IF (v_profile->'thresholds'->'comfort'->>'co2_limit_ppm')::int > 750 THEN
    RAISE EXCEPTION 'site-005 CO₂ limit must be <= 750 ppm (clinical zone requirement)';
  END IF;

  -- thermal_mass must not be 0 (zero causes division error in thermal runway calc)
  IF (v_profile->'thresholds'->'temporal'->>'thermal_mass') = '0' THEN
    RAISE EXCEPTION 'thermal_mass must be null, not 0 — zero causes division error';
  END IF;

  RAISE NOTICE 'site-005 hospital profile validated OK — weights sum to 1.0, CO₂ and comfort thresholds correct';
END $$;

-- Site-specific seed: site-002 building profile (Sandton City)
--
-- This file contains site-specific seed data and must NOT be included in the
-- base migration image. It is run during SIMBIOT onboarding for a specific site.
--
-- Deployment model: ONE Jetson = ONE building = ONE Supabase instance.
-- The base migration (20260322_001_building_profile.sql) ships the schema to every
-- deployment. This seed file is applied AFTER the site is known.
--
-- Run during SIMBIOT onboarding for site-002. SITE_ID injected from edge.conf.
-- Idempotent — safe to re-run (guarded by WHERE code = 'site-002').

UPDATE buildings
SET profile = '{
  "deployment_mode": "ghost",
  "operating_postures": {
    "active_posture": "comfort_priority",
    "schedules": {
      "business_hours": {"start": "07:00", "end": "18:00", "posture": "comfort_priority"},
      "after_hours":    {"start": "18:01", "end": "06:59", "posture": "cost_optimized"}
    },
    "weights": {"comfort": 0.70, "cost": 0.15, "asset": 0.15}
  },
  "thresholds": {
    "comfort":  {"temp_setpoint": 22.0, "max_drift": 2.0, "co2_limit_ppm": 800},
    "temporal": {"thermal_mass": null, "insulation_factor": null, "heat_transfer_coefficient": null}
  },
  "crisis_logic": {
    "urgency_threshold": 0.70,
    "dismiss_window_minutes": 30,
    "min_time_to_discomfort_alert": 15
  }
}'::jsonb
WHERE code = 'site-002'
  AND (profile IS NULL OR profile = '{}'::jsonb);

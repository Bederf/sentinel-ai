-- Migration 20260322_001: Add profile JSONB column to buildings table
--
-- Purpose: Store building-level operational profile — deployment mode, posture weights,
--          setpoints, thermal parameters, CO₂ limits, and crisis logic thresholds.
--          Used by DecisionMomentAggregator (Phase 164) and Kiosk frontend (Phase 165).
--
-- Deployment context:
--   Fresh deployment: skeleton buildings row only. Profile defaults ship here.
--   SIMBIOT populates equipment on first connection.
--   Onboarding wizard (future phase) lets FM customise weights and thresholds.
--   thermal_params fields ship as NULL — never fabricate a countdown without real data.
--   A null thermal_mass is correct. A zero thermal_mass causes division error in
--   calculate_thermal_runway() — do NOT default to 0.
--
-- Source of truth: Supabase buildings.profile (NOT building.json)

ALTER TABLE buildings
  ADD COLUMN IF NOT EXISTS profile JSONB NOT NULL DEFAULT '{
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
  }'::jsonb;

-- Seed Site 002 row (idempotent — safe to re-run)
-- Uses code column (stable TEXT identifier) NOT id (UUID, environment-specific)
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

-- GIN index (enables @> containment operators on profile fields)
CREATE INDEX IF NOT EXISTS idx_buildings_profile
  ON buildings USING GIN (profile);

-- Safety assertions — fail migration if invariants violated
DO $$
DECLARE v_profile JSONB;
BEGIN
  -- Column must exist
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'buildings' AND column_name = 'profile'
  ) THEN
    RAISE EXCEPTION 'profile column not found on buildings table';
  END IF;

  -- Fetch site-002 profile and verify critical fields
  SELECT profile INTO v_profile FROM buildings WHERE code = 'site-002';
  IF v_profile IS NOT NULL THEN
    -- deployment_mode must be 'ghost' not null
    IF v_profile->>'deployment_mode' IS NULL THEN
      RAISE EXCEPTION 'deployment_mode missing from site-002 profile';
    END IF;
    -- thermal_mass must be null, not 0 (zero causes division error in thermal model)
    IF (v_profile->'thresholds'->'temporal'->>'thermal_mass') = '0' THEN
      RAISE EXCEPTION 'thermal_mass must be null, not 0 — zero causes division error';
    END IF;
    -- weights must sum to 1.0
    IF ABS(
      (v_profile->'operating_postures'->'weights'->>'comfort')::float +
      (v_profile->'operating_postures'->'weights'->>'cost')::float +
      (v_profile->'operating_postures'->'weights'->>'asset')::float - 1.0
    ) > 0.001 THEN
      RAISE EXCEPTION 'posture weights must sum to 1.0';
    END IF;
  END IF;
END $$;

-- ─── ROLLBACK (run manually if migration must be reverted) ───────────────────
-- WARNING: This drops all profile data. Back up first.
-- DROP INDEX IF EXISTS idx_buildings_profile;
-- ALTER TABLE buildings DROP COLUMN IF EXISTS profile;
-- ─────────────────────────────────────────────────────────────────────────────

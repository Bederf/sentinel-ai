-- Seed canonical zone inventory for active site-005 during onboarding/shadow_live.
--
-- Runtime bridge polling must not create zones. Site-005 is still in onboarding
-- (shadow_live), and its fcu_zone_state stream already contains the zone ids
-- used by the hospital telemetry. Reflex reconciliation needs those ids in
-- Supabase's canonical zone inventory before it can resolve findings.

ALTER TABLE public.zones
DROP CONSTRAINT IF EXISTS valid_zone_type;

ALTER TABLE public.zones
ADD CONSTRAINT valid_zone_type
CHECK (
  zone_type = ANY (
    ARRAY[
      'open_office'::text,
      'meeting_room'::text,
      'plant_room'::text,
      'storage'::text,
      'stairwell'::text,
      'corridor'::text,
      'lobby'::text,
      'restroom'::text,
      'cafeteria'::text,
      'server_room'::text,
      'comms_room'::text,
      'mechanical'::text,
      'electrical'::text,
      'hospital_zone'::text,
      'clinical'::text,
      'icu'::text,
      'theatre'::text
    ]
  )
);

WITH latest_zone_state AS (
  SELECT DISTINCT ON (zone_id)
    zone_id,
    room_temp_c,
    setpoint_c,
    fcu_inferred_running,
    timestamp
  FROM public.fcu_zone_state
  WHERE site_id = 'site-005'
    AND zone_id IS NOT NULL
    AND zone_id <> ''
  ORDER BY zone_id, timestamp DESC
),
prepared AS (
  SELECT
    s.id AS site_uuid,
    l.zone_id,
    CASE
      WHEN l.zone_id LIKE 'Zone-G-%' THEN 'Ground ' || replace(substring(l.zone_id from 'Zone-G-(.*)$'), '-', ' ')
      WHEN l.zone_id LIKE 'Zone-L%-ICU' THEN 'Level ' || substring(l.zone_id from 'Zone-L([0-9]+)-') || ' ICU'
      WHEN l.zone_id LIKE 'Zone-L%-TH%' THEN 'Level ' || substring(l.zone_id from 'Zone-L([0-9]+)-') || ' Theatre ' || substring(l.zone_id from 'Zone-L[0-9]+-(.*)$')
      WHEN l.zone_id LIKE 'Zone-L%-%' THEN 'Level ' || substring(l.zone_id from 'Zone-L([0-9]+)-') || ' Zone ' || substring(l.zone_id from 'Zone-L[0-9]+-(.*)$')
      ELSE l.zone_id
    END AS zone_name,
    CASE
      WHEN l.zone_id LIKE 'Zone-G-%' THEN 'G'
      WHEN l.zone_id LIKE 'Zone-L%-%' THEN 'L' || substring(l.zone_id from 'Zone-L([0-9]+)-')
      ELSE 'unknown'
    END AS floor,
    CASE
      WHEN l.zone_id LIKE 'Zone-%-%' THEN substring(l.zone_id from 'Zone-[^-]+-(.*)$')
      ELSE NULL
    END AS zone_letter,
    CASE
      WHEN l.zone_id LIKE '%-ICU' THEN 'icu'
      WHEN l.zone_id LIKE '%-TH%' THEN 'theatre'
      ELSE 'hospital_zone'
    END AS zone_type,
    COALESCE(l.room_temp_c, NULL) AS current_temp,
    COALESCE(l.setpoint_c, 22.0) AS setpoint,
    CASE WHEN l.fcu_inferred_running THEN 'running' ELSE 'idle' END AS status,
    l.timestamp
  FROM latest_zone_state l
  JOIN public.sites s ON s.code = 'site-005'
)
INSERT INTO public.zones (
  site_id,
  zone_id,
  zone_name,
  floor,
  zone_letter,
  zone_type,
  typical_occupancy
)
SELECT
  site_uuid,
  zone_id,
  zone_name,
  floor,
  zone_letter,
  zone_type,
  NULL
FROM prepared
ON CONFLICT (site_id, zone_id) DO UPDATE
SET
  zone_name = EXCLUDED.zone_name,
  floor = EXCLUDED.floor,
  zone_letter = EXCLUDED.zone_letter,
  zone_type = EXCLUDED.zone_type,
  updated_at = now();

WITH latest_zone_state AS (
  SELECT DISTINCT ON (zone_id)
    zone_id,
    room_temp_c,
    setpoint_c,
    fcu_inferred_running,
    timestamp
  FROM public.fcu_zone_state
  WHERE site_id = 'site-005'
    AND zone_id IS NOT NULL
    AND zone_id <> ''
  ORDER BY zone_id, timestamp DESC
),
prepared AS (
  SELECT
    s.id AS site_uuid,
    l.zone_id,
    CASE
      WHEN l.zone_id LIKE 'Zone-G-%' THEN 'Ground ' || replace(substring(l.zone_id from 'Zone-G-(.*)$'), '-', ' ')
      WHEN l.zone_id LIKE 'Zone-L%-ICU' THEN 'Level ' || substring(l.zone_id from 'Zone-L([0-9]+)-') || ' ICU'
      WHEN l.zone_id LIKE 'Zone-L%-TH%' THEN 'Level ' || substring(l.zone_id from 'Zone-L([0-9]+)-') || ' Theatre ' || substring(l.zone_id from 'Zone-L[0-9]+-(.*)$')
      WHEN l.zone_id LIKE 'Zone-L%-%' THEN 'Level ' || substring(l.zone_id from 'Zone-L([0-9]+)-') || ' Zone ' || substring(l.zone_id from 'Zone-L[0-9]+-(.*)$')
      ELSE l.zone_id
    END AS zone_name,
    CASE
      WHEN l.zone_id LIKE 'Zone-G-%' THEN 'G'
      WHEN l.zone_id LIKE 'Zone-L%-%' THEN 'L' || substring(l.zone_id from 'Zone-L([0-9]+)-')
      ELSE 'unknown'
    END AS floor,
    COALESCE(l.room_temp_c, NULL) AS current_temp,
    COALESCE(l.setpoint_c, 22.0) AS setpoint,
    CASE WHEN l.fcu_inferred_running THEN 'running' ELSE 'idle' END AS status,
    l.timestamp
  FROM latest_zone_state l
  JOIN public.sites s ON s.code = 'site-005'
)
INSERT INTO public.hvac_zones (
  zone_id,
  zone_name,
  site_id,
  floor,
  typical_occupancy,
  area_sqm,
  priority,
  setpoint,
  current_temp,
  status,
  mode,
  fan_speed,
  last_updated
)
SELECT
  zone_id,
  zone_name,
  site_uuid,
  floor,
  NULL,
  NULL,
  CASE
    WHEN zone_id LIKE '%-ICU' OR zone_id LIKE '%-TH%' THEN 'P1'
    ELSE 'P3'
  END,
  setpoint,
  current_temp,
  status,
  'auto',
  'auto',
  timestamp
FROM prepared
ON CONFLICT (zone_id) DO UPDATE
SET
  zone_name = EXCLUDED.zone_name,
  site_id = EXCLUDED.site_id,
  floor = EXCLUDED.floor,
  priority = EXCLUDED.priority,
  setpoint = EXCLUDED.setpoint,
  current_temp = EXCLUDED.current_temp,
  status = EXCLUDED.status,
  last_updated = EXCLUDED.last_updated,
  updated_at = now();

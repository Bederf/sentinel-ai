-- Collapse active reflex recommendations to one state row per
-- site/zone/system/rule/action_type and prevent future active duplicates.

WITH active_reflex AS (
    SELECT
        id,
        site_id,
        target_equipment,
        action_type,
        "timestamp",
        COALESCE(metadata, '{}'::jsonb) AS metadata,
        COALESCE(metadata->>'system_type', action->>'system_type') AS system_type,
        COALESCE(metadata->>'rule_key', action->>'rule_key') AS rule_key
    FROM public.recommendations
    WHERE source = 'reflex_reconciliation'
      AND status IN ('pending', 'advisory_info')
      AND action_type IN ('operational_mismatch', 'comfort_risk', 'schedule_defect')
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY site_id, target_equipment, system_type, rule_key, action_type
            ORDER BY "timestamp" DESC, id DESC
        ) AS rn,
        MIN("timestamp") OVER (
            PARTITION BY site_id, target_equipment, system_type, rule_key, action_type
        ) AS first_observed_at,
        MAX("timestamp") OVER (
            PARTITION BY site_id, target_equipment, system_type, rule_key, action_type
        ) AS last_observed_at,
        COUNT(*) OVER (
            PARTITION BY site_id, target_equipment, system_type, rule_key, action_type
        ) AS observation_count
    FROM active_reflex
    WHERE system_type IS NOT NULL
      AND rule_key IS NOT NULL
),
keepers AS (
    SELECT *
    FROM ranked
    WHERE rn = 1
)
UPDATE public.recommendations AS rec
SET metadata = COALESCE(rec.metadata, '{}'::jsonb)
    || jsonb_build_object(
        'first_observed_at', keepers.first_observed_at,
        'last_observed_at', keepers.last_observed_at,
        'observation_count', keepers.observation_count,
        'state_dedup_backfilled_at', NOW()
    )
FROM keepers
WHERE rec.id = keepers.id;

WITH active_reflex AS (
    SELECT
        id,
        site_id,
        target_equipment,
        action_type,
        "timestamp",
        COALESCE(metadata, '{}'::jsonb) AS metadata,
        COALESCE(metadata->>'system_type', action->>'system_type') AS system_type,
        COALESCE(metadata->>'rule_key', action->>'rule_key') AS rule_key
    FROM public.recommendations
    WHERE source = 'reflex_reconciliation'
      AND status IN ('pending', 'advisory_info')
      AND action_type IN ('operational_mismatch', 'comfort_risk', 'schedule_defect')
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY site_id, target_equipment, system_type, rule_key, action_type
            ORDER BY "timestamp" DESC, id DESC
        ) AS rn
    FROM active_reflex
    WHERE system_type IS NOT NULL
      AND rule_key IS NOT NULL
)
UPDATE public.recommendations AS rec
SET status = 'expired',
    metadata = COALESCE(rec.metadata, '{}'::jsonb)
    || jsonb_build_object(
        'resolved_at', NOW(),
        'resolution_reason', 'superseded_by_reflex_state_dedup'
    )
FROM ranked
WHERE rec.id = ranked.id
  AND ranked.rn > 1;

WITH active_reflex AS (
    SELECT
        id,
        site_id,
        target_equipment,
        action_type,
        COALESCE(metadata->>'system_type', action->>'system_type') AS system_type,
        COALESCE(metadata->>'rule_key', action->>'rule_key') AS rule_key
    FROM public.recommendations
    WHERE source = 'reflex_reconciliation'
      AND status IN ('pending', 'advisory_info')
      AND action_type IN ('operational_mismatch', 'comfort_risk', 'schedule_defect')
),
schedule_defects AS (
    SELECT site_id, target_equipment, system_type, rule_key
    FROM active_reflex
    WHERE action_type = 'schedule_defect'
),
superseded_points AS (
    SELECT points.id
    FROM active_reflex AS points
    JOIN schedule_defects AS defects
      ON defects.site_id = points.site_id
     AND defects.target_equipment = points.target_equipment
     AND defects.system_type = points.system_type
     AND defects.rule_key = points.rule_key
    WHERE points.action_type IN ('operational_mismatch', 'comfort_risk')
)
UPDATE public.recommendations AS rec
SET status = 'expired',
    metadata = COALESCE(rec.metadata, '{}'::jsonb)
    || jsonb_build_object(
        'resolved_at', NOW(),
        'resolution_reason', 'superseded_by_schedule_defect'
    )
FROM superseded_points
WHERE rec.id = superseded_points.id;

CREATE UNIQUE INDEX IF NOT EXISTS idx_recommendations_reflex_active_state
    ON public.recommendations (
        site_id,
        target_equipment,
        action_type,
        (COALESCE(metadata->>'system_type', action->>'system_type')),
        (COALESCE(metadata->>'rule_key', action->>'rule_key'))
    )
    WHERE source = 'reflex_reconciliation'
      AND status IN ('pending', 'advisory_info')
      AND action_type IN ('operational_mismatch', 'comfort_risk', 'schedule_defect');

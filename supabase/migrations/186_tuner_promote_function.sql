-- ============================================================
-- Migration 20260622_002: Atomic promote/rollback function
--
-- Adds tuner_promote_thresholds — a single SECURITY DEFINER
-- function that atomically:
--   1. Reads current row from site_thresholds (for old values)
--   2. Finds the most recent change_log entry (for chain)
--   3. Upserts site_thresholds with new values
--   4. Calls tuner_active_set_hash to compute hash (single source of truth)
--   5. Writes threshold_change_log (old → new, with hash)
--   6. If triggered by a proposal, marks it approved
--
-- All in one transaction. If any step fails, all roll back.
-- Hash is computed by calling tuner_active_set_hash (not inline) to
-- prevent formula drift between the two functions.
--
-- Called by:
--   - Operator direct edit (triggered_by='operator')
--   - Proposal promotion (triggered_by='tuner_proposal')
--   - Rollback to prior state (triggered_by='rollback')
--
-- NOT granted to sentinel_tuner — promote is operator-only
-- (gated by require_role(4) at the API layer).
-- ============================================================

BEGIN;

CREATE OR REPLACE FUNCTION public.tuner_promote_thresholds(
    p_site_id      text,
    p_new_health   jsonb,
    p_new_risk     jsonb,
    p_triggered_by text,
    p_proposal_id  bigint DEFAULT NULL,
    p_approved_by  text   DEFAULT NULL
)
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
    v_old_health      jsonb;
    v_old_risk        jsonb;
    v_previous_log_id bigint;
    v_log_id          bigint;
    v_hash            text;
BEGIN
    -- Validate triggered_by (must match CHECK constraint on change_log)
    IF p_triggered_by NOT IN ('operator', 'tuner_proposal', 'rollback') THEN
        RAISE EXCEPTION 'Invalid triggered_by: %', p_triggered_by
            USING ERRCODE = 'check_violation';
    END IF;

    -- Pre-check: key presence (table CHECK enforces ordering/boundaries)
    IF NOT (p_new_health ? 'healthy' AND p_new_health ? 'warning' AND p_new_health ? 'critical') THEN
        RAISE EXCEPTION 'Health thresholds must include healthy, warning, and critical keys'
            USING ERRCODE = 'check_violation';
    END IF;
    IF NOT (p_new_risk ? 'medium' AND p_new_risk ? 'high' AND p_new_risk ? 'critical') THEN
        RAISE EXCEPTION 'Risk thresholds must include medium, high, and critical keys'
            USING ERRCODE = 'check_violation';
    END IF;

    -- 1. Read current state (NULL if no row exists yet — first-time setup)
    SELECT health, risk INTO v_old_health, v_old_risk
    FROM site_thresholds WHERE site_id = p_site_id;

    -- 2. Find most recent change_log entry for chain
    SELECT log_id INTO v_previous_log_id
    FROM threshold_change_log
    WHERE site_id = p_site_id
    ORDER BY changed_at DESC LIMIT 1;

    -- 3. Upsert active thresholds (table CHECK enforces ordering/boundaries)
    INSERT INTO site_thresholds (site_id, health, risk)
    VALUES (p_site_id, p_new_health, p_new_risk)
    ON CONFLICT (site_id) DO UPDATE
        SET health = EXCLUDED.health,
            risk = EXCLUDED.risk,
            updated_at = now();

    -- 4. Compute hash by calling tuner_active_set_hash — single source of truth.
    --    No inline formula to drift. Reads the now-active values from the table.
    v_hash := tuner_active_set_hash(p_site_id);

    -- 5. Write change_log (old state from step 1, hash from step 4, chain from step 2)
    INSERT INTO threshold_change_log (
        site_id, old_health, old_risk, new_health, new_risk,
        triggered_by, proposal_id, approved_by, previous_log_id, active_hash
    ) VALUES (
        p_site_id, v_old_health, v_old_risk, p_new_health, p_new_risk,
        p_triggered_by, p_proposal_id, p_approved_by, v_previous_log_id, v_hash
    ) RETURNING log_id INTO v_log_id;

    -- 6. If this was a proposal promotion, mark it approved
    IF p_proposal_id IS NOT NULL AND p_triggered_by = 'tuner_proposal' THEN
        UPDATE site_threshold_proposals
        SET status = 'approved',
            reviewed_at = now(),
            reviewed_by = p_approved_by,
            change_log_id = v_log_id
        WHERE proposal_id = p_proposal_id AND status = 'pending';
    END IF;

    RETURN v_log_id;
END;
$function$;

-- Grant EXECUTE to service_role (backend) and postgres.
-- NOT granted to sentinel_tuner — promote is operator-only.
GRANT EXECUTE ON FUNCTION public.tuner_promote_thresholds(text, jsonb, jsonb, text, bigint, text) TO service_role;

COMMIT;

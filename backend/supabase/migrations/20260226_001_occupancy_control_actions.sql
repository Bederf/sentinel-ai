-- Phase 130: Occupancy-driven control actions audit trail
-- Records every HVAC setpoint change and lighting adjustment triggered by occupancy changes.
-- This is the M&V evidence table — proves SENTINEL responded correctly to occupancy data.

CREATE TABLE IF NOT EXISTS occupancy_control_actions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp       timestamptz NOT NULL DEFAULT now(),
    site_id         text NOT NULL,
    zone_id         text NOT NULL,

    -- Occupancy context at time of action
    occupancy_source    text NOT NULL,          -- 'dali_pir', 'badge', 'combined'
    occupancy_percent   real,                   -- 0-100 from DALI sensors
    occupancy_count     integer,                -- headcount from badge readers
    occupancy_status    text,                   -- 'empty', 'quiet', 'moderate', 'busy'

    -- Action taken
    module          text NOT NULL,              -- 'hvac' or 'lighting'
    action_type     text NOT NULL,              -- 'relax_setpoint', 'restore_setpoint', 'dim_to_minimum', 'dim_partial', 'restore_brightness'
    target_equipment text,                      -- equipment code (e.g., 'S002-FCU-L1-A') or zone_id

    -- Before/after state
    previous_value  real,                       -- setpoint °C or brightness %
    new_value       real,                       -- setpoint °C or brightness %
    offset_applied  real,                       -- delta (e.g., +2.0°C or -80%)

    -- Execution result
    status          text NOT NULL DEFAULT 'executed',  -- 'executed', 'failed', 'skipped', 'safety_blocked'
    error_message   text,

    -- Provenance
    triggered_by    text NOT NULL DEFAULT 'occupancy_poller',  -- 'occupancy_poller', 'manual', 'api'
    correlation_id  text,                       -- links to related actions in same cycle

    created_at      timestamptz NOT NULL DEFAULT now()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_occ_actions_zone_time
    ON occupancy_control_actions (zone_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_occ_actions_site_time
    ON occupancy_control_actions (site_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_occ_actions_module
    ON occupancy_control_actions (module, action_type);
CREATE INDEX IF NOT EXISTS idx_occ_actions_status
    ON occupancy_control_actions (status)
    WHERE status != 'executed';
CREATE INDEX IF NOT EXISTS idx_occ_actions_correlation
    ON occupancy_control_actions (correlation_id)
    WHERE correlation_id IS NOT NULL;

-- Comment for documentation
COMMENT ON TABLE occupancy_control_actions IS
    'Phase 130: Audit trail for occupancy-driven HVAC/lighting control actions. '
    'Records every setpoint relaxation and brightness adjustment triggered by DALI PIR '
    'or badge-reader occupancy changes. Used for M&V verification and compliance.';

# Agent Contract Appendix: Quality Gate Metrics & Safety Boundary Rules

> **Version:** 1.0 | **Last Updated:** 2026-02-22
> **Source:** `quality_gate_policy.py`, `safety_boundary_service.py`, `safety_rules.py`

---

## A. Quality Gate — 14 Metrics (complete threshold table)

### Metric definitions

| # | Metric | Source service | Direction | What it measures |
|---|--------|---------------|-----------|------------------|
| 1 | `freshness_minutes` | MonitoringService | lower_is_better | Time since last successful data ingest |
| 2 | `ingest_error_rate_pct_1h` | MonitoringService | lower_is_better | % of ingest attempts that errored in last hour |
| 3 | `match_coverage_pct` | MonitoringService | higher_is_better | % of discovered points matched to equipment |
| 4 | `manual_source_pct` | MonitoringService provenance | lower_is_better | % of data from JSON fallback (not live BMS) |
| 5 | `unmatched_points_pct` | MonitoringService | lower_is_better | % of points with no equipment mapping |
| 6 | `commissioning_all_gates_passed` | CommissioningService | higher_is_better | 1 if all commissioning gates passed, 0 if not |
| 7 | `truth_check_pass_rate_pct` | CommissioningService | higher_is_better | % of truth-check assertions passing |
| 8 | `consecutive_pass_days` | CommissioningService | higher_is_better | Days of consecutive gate passes |
| 9 | `mv_accuracy_7d_pct` | MVVerificationService | higher_is_better | M&V prediction accuracy over 7 days |
| 10 | `comfort_violation_rate_7d_pct` | MVVerificationService | lower_is_better | % of hours with comfort violations over 7 days |
| 11 | `rollback_rate_7d_pct` | MVVerificationService | lower_is_better | % of executed recommendations rolled back over 7 days |
| 12 | `feedback_capture_rate_7d_pct` | MLFeedbackService | higher_is_better | % of recommendations with outcome labels over 7 days |
| 13 | `label_lag_p95_hours` | MLFeedbackService | lower_is_better | 95th percentile delay between action and outcome label |
| 14 | `drift_critical_alerts_24h` | Audit log | lower_is_better | Count of critical drift alerts in last 24 hours |

### Threshold registry (14 x 3 = 42 entries)

#### SIMULATION mode (lenient — development and demos)

| Metric | PASS | WARN | FAIL | NA? |
|--------|------|------|------|-----|
| `freshness_minutes` | <= 1440 | <= 4320 | > 4320 | |
| `ingest_error_rate_pct_1h` | <= 15 | <= 25 | > 25 | |
| `match_coverage_pct` | >= 60 | >= 40 | < 40 | |
| `manual_source_pct` | — | — | — | NA |
| `unmatched_points_pct` | <= 40 | <= 60 | > 60 | |
| `commissioning_all_gates_passed` | — | — | — | NA |
| `truth_check_pass_rate_pct` | — | — | — | NA |
| `consecutive_pass_days` | — | — | — | NA |
| `mv_accuracy_7d_pct` | >= 50 | >= 40 | < 40 | |
| `comfort_violation_rate_7d_pct` | <= 20 | <= 35 | > 35 | |
| `rollback_rate_7d_pct` | <= 15 | <= 25 | > 25 | |
| `feedback_capture_rate_7d_pct` | >= 70 | >= 50 | < 50 | |
| `label_lag_p95_hours` | <= 72 | <= 120 | > 120 | |
| `drift_critical_alerts_24h` | <= 2 | (no warn) | > 2 | |

#### SHADOW_LIVE mode (medium — read-only testing against live BMS)

| Metric | PASS | WARN | FAIL |
|--------|------|------|------|
| `freshness_minutes` | <= 120 | <= 360 | > 360 |
| `ingest_error_rate_pct_1h` | <= 3 | <= 5 | > 5 |
| `match_coverage_pct` | >= 90 | >= 80 | < 80 |
| `manual_source_pct` | == 0 | (no warn) | > 0 |
| `unmatched_points_pct` | <= 10 | <= 20 | > 20 |
| `commissioning_all_gates_passed` | >= 1 | (no warn) | < 1 |
| `truth_check_pass_rate_pct` | >= 98 | >= 95 | < 95 |
| `consecutive_pass_days` | >= 2 | >= 1 | < 1 |
| `mv_accuracy_7d_pct` | >= 75 | >= 65 | < 65 |
| `comfort_violation_rate_7d_pct` | <= 8 | <= 12 | > 12 |
| `rollback_rate_7d_pct` | <= 5 | <= 8 | > 8 |
| `feedback_capture_rate_7d_pct` | >= 90 | >= 80 | < 80 |
| `label_lag_p95_hours` | <= 24 | <= 36 | > 36 |
| `drift_critical_alerts_24h` | == 0 | <= 1 | > 1 |

#### LIVE_CONTROL mode (strict — production with real BMS writes)

| Metric | PASS | WARN | FAIL |
|--------|------|------|------|
| `freshness_minutes` | <= 15 | <= 60 | > 60 |
| `ingest_error_rate_pct_1h` | <= 1 | <= 2 | > 2 |
| `match_coverage_pct` | >= 98 | >= 95 | < 95 |
| `manual_source_pct` | == 0 | (no warn) | > 0 |
| `unmatched_points_pct` | <= 2 | <= 5 | > 5 |
| `commissioning_all_gates_passed` | >= 1 | (no warn) | < 1 |
| `truth_check_pass_rate_pct` | >= 98 | (no warn) | < 98 |
| `consecutive_pass_days` | >= 2 | (no warn) | < 2 |
| `mv_accuracy_7d_pct` | >= 85 | >= 75 | < 75 |
| `comfort_violation_rate_7d_pct` | <= 3 | <= 5 | > 5 |
| `rollback_rate_7d_pct` | <= 2 | <= 4 | > 4 |
| `feedback_capture_rate_7d_pct` | >= 97 | >= 93 | < 93 |
| `label_lag_p95_hours` | <= 6 | <= 12 | > 12 |
| `drift_critical_alerts_24h` | == 0 | (no warn) | > 0 |

### Enforcement mapping

| Mode | Gate result | Enforcement action | Effect |
|------|------------|-------------------|--------|
| simulation | PASS | NORMAL | Full pipeline |
| simulation | WARN | NORMAL | Full pipeline |
| simulation | FAIL | CAP_CONFIDENCE | Confidence capped at 0.59 (forces Tier 1) |
| shadow_live | PASS | NORMAL | Full pipeline (no writes anyway) |
| shadow_live | WARN | NORMAL | Full pipeline |
| shadow_live | FAIL | SUPPRESS_TIER3 | Tier 3 auto-execute disabled |
| live_control | PASS | NORMAL | Full pipeline including writes |
| live_control | WARN | SUPPRESS_TIER3 | Tier 3 disabled, Tier 2 approval still works |
| live_control | FAIL | BLOCK_WRITES | All device writes blocked |

### Reason codes (machine-readable)

| Code | Triggered by metric |
|------|-------------------|
| `data_freshness_fail` | freshness_minutes |
| `ingest_error_rate_fail` | ingest_error_rate_pct_1h |
| `match_coverage_fail` | match_coverage_pct |
| `json_in_live_fail` | manual_source_pct |
| `commissioning_fail` | commissioning_all_gates_passed |
| `truth_check_fail` | truth_check_pass_rate_pct |
| `mv_accuracy_fail` | mv_accuracy_7d_pct |
| `feedback_coverage_fail` | feedback_capture_rate_7d_pct |
| `drift_critical_fail` | drift_critical_alerts_24h |
| `quality_gate_block` | unmatched_points_pct, consecutive_pass_days, comfort_violation_rate_7d_pct, rollback_rate_7d_pct, label_lag_p95_hours |

### Evaluation semantics

```python
# MetricThreshold evaluation logic (frozen dataclass)
@dataclass(frozen=True)
class MetricThreshold:
    pass_bound: Optional[float]
    warn_bound: Optional[float]
    direction: str  # "lower_is_better" | "higher_is_better"
    na: bool = False

    def evaluate(self, value: float) -> RuleState:
        if self.na:
            return NA

        if direction == "lower_is_better":
            value <= pass_bound -> PASS
            value <= warn_bound -> WARN
            else -> FAIL

        if direction == "higher_is_better":
            value >= pass_bound -> PASS
            value >= warn_bound -> WARN
            else -> FAIL
```

When `warn_bound` is None, there is no WARN band — value is either PASS or FAIL directly.

---

## B. Safety Boundary Rules — Format and Types

### Rule base class

Every safety rule has these fields:

```
id:           str           # Unique rule ID
name:         str           # Human-readable name
rule_type:    RuleType      # One of the 6 types below
severity:     RuleSeverity  # "warning" | "block" | "alarm"
description:  str           # Human-readable explanation
device_type:  Optional[str] # Scope to equipment type (e.g., "CHILLER")
device_id:    Optional[str] # Scope to specific equipment
point_name:   Optional[str] # Scope to specific control point
enabled:      bool          # Can be toggled without deleting
metadata:     Dict          # Arbitrary key-value pairs
```

### Severity levels

| Severity | Behavior |
|----------|----------|
| `warning` | Allow operation, show warning in UI |
| `block` | Prevent operation entirely |
| `alarm` | Trigger alarm, may allow with explicit override |

### Rule types

#### 1. TEMPERATURE_RANGE

```
min_temp:  float  # Default 16.0 C
max_temp:  float  # Default 28.0 C
unit:      str    # "C"
```

Check: `value < min_temp OR value > max_temp` -> violation
Used by: HVAC setpoint writes, chiller supply temp, zone temp overrides

#### 2. PRESSURE_LIMIT

```
min_pressure:  float  # Default 0.0 kPa
max_pressure:  float  # Default 100.0 kPa
unit:          str    # "kPa"
```

Check: `value < min_pressure OR value > max_pressure` -> violation
Used by: Chilled water pressure, fire suppression systems

#### 3. INTERLOCK

```
trigger_device_id:  str   # Device that triggers the interlock
trigger_point:      str   # Point on trigger device
trigger_value:      Any   # Value that activates the interlock
action:             str   # "disable" | "enable" | "set_value"
action_value:       Any   # Value to set if action is "set_value"
```

Check: When trigger device point equals trigger value, interlock activates
Used by: Fire alarm -> disable HVAC, chiller fault -> disable pumps

#### 4. RUNTIME_LIMIT

```
min_runtime_minutes:  int  # Default 5 (compressor protection)
max_starts_per_hour:  int  # Default 4 (anti-short-cycling)
```

Check: `runtime < min_runtime_minutes OR starts_this_hour >= max_starts_per_hour` -> violation
Used by: Compressor protection, motor start limiting

#### 5. BRIGHTNESS_LIMIT

```
min_brightness:  int  # Default 0 (%)
max_brightness:  int  # Default 100 (%)
```

Check: `value < min OR value > max` -> violation
Used by: DALI lighting control, emergency lighting minimum levels

#### 6. CUSTOM

```
validation_logic:  str  # Arbitrary expression
```

Check: Evaluates custom logic (placeholder in current implementation)
Used by: Site-specific rules

### Boundary monitoring (safety_boundary_service.py)

The safety boundary service continuously monitors how close current values are to rule limits.

**Approach calculation:**
- For two-sided boundaries (e.g., temperature 16-28): uses 25% of range as buffer zone
- For one-sided boundaries (e.g., brightness max 100): uses absolute percentage

**Escalation levels based on approach percentage:**

| Approach % | Level | Numeric | Action |
|------------|-------|---------|--------|
| < 50% | NONE | 0 | Normal operation |
| >= 50% | WARNING | 1 | Logged |
| >= 75% | ALERT | 2 | Email notification |
| >= 85% | CRITICAL | 3 | Slack + dashboard |
| >= 95% | EMERGENCY | 4 | Stop + emergency protocol |
| 100% (breach) | EMERGENCY | 4 | Immediate action |

**Example with temperature range 16-28 C (range=12, buffer=3):**

```
Value 25.0 -> 0.0% approach to max (outside buffer)     -> NONE
Value 26.0 -> 33% approach to max (inside 25-28 buffer)  -> NONE
Value 26.5 -> 50% approach to max                        -> WARNING
Value 27.0 -> 67% approach to max                        -> WARNING
Value 27.3 -> 77% approach to max                        -> ALERT
Value 27.6 -> 87% approach to max                        -> CRITICAL
Value 27.9 -> 97% approach to max                        -> EMERGENCY
Value 28.5 -> 100% (breach)                              -> EMERGENCY
```

### BoundaryStatus output format

```python
@dataclass
class BoundaryStatus:
    device_id: str
    point_name: str
    current_value: float
    boundary_min: Optional[float]
    boundary_max: Optional[float]
    approach_percentage: float       # 0-100, clamped
    escalation_level: EscalationLevel
    warnings: List[str]             # Human-readable warning messages
    last_updated: datetime
```

### Where safety rules are checked in the pipeline

```
1. Recommendation creation
   -> SafetyEngine.validate_control_change(equipment, point, proposed_value)
   -> Gets rules via get_rules_for_device(device, point_name)
   -> Runs each rule's check() method
   -> If any rule returns allowed=False with severity=BLOCK -> reject

2. Approval execution (defense-in-depth, re-validates)
   -> Same SafetyEngine.validate_control_change() call
   -> Even if recommendation was created earlier, re-check at execution time
   -> Catches state changes between creation and execution

3. Boundary monitoring (continuous)
   -> SafetyBoundaryService.check_boundary_approach()
   -> Runs independently of recommendations
   -> Feeds escalation into dashboard and notification system
```

---

## C. Data model cross-reference

### QualityGateResult (output of gate evaluation)

```python
@dataclass
class QualityGateResult:
    overall: GateStatus              # "pass" | "warn" | "fail"
    rule_results: List[MetricRuleResult]  # Per-metric results
    failed_rules: List[str]          # Metric names that failed
    warn_rules: List[str]            # Metric names that warned
    enforcement: EnforcementAction   # "normal" | "cap_confidence" | "suppress_tier3" | "block_writes"
    reason_codes: List[ReasonCode]   # Machine-readable failure reasons
    mode: str                        # "simulation" | "shadow_live" | "live_control"
    evaluated_at: str                # ISO timestamp
```

### MetricRuleResult (per-metric output)

```python
@dataclass
class MetricRuleResult:
    metric: str                      # Metric name
    value: float                     # Actual value
    state: RuleState                 # "pass" | "warn" | "fail" | "na"
    threshold: MetricThreshold       # Threshold used for evaluation
    reason_code: Optional[ReasonCode]  # If failed, which reason code
```

---

## D. ParasiteDecision audit record schema

> **Source:** `app/models/parasite_decision.py`, `app/database/repositories/parasite_decision_repository.py`

Every Tier 1/2/3 decision produces one record, enriched through its lifecycle.

### Identity fields

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | UUID | auto | Primary key |
| `correlation_id` | UUID | yes | Links related records across services |
| `recommendation_id` | str | yes | Source recommendation |
| `site_id` | str | NOT NULL in live_control | Multi-site queries and kill switches need it |
| `equipment_code` | str | yes | Equipment naming identity (e.g. `S002-CHILLER-B1-001`) |
| `device_id` | str | optional | Canonical control routing identity |

### Decision context (A)

| Field | Type | Values | Reason |
|-------|------|--------|--------|
| `mode` | str | `simulation` `shadow_live` `live_control` | Audit and policy evaluation depends on mode |
| `gate_status` | str | `pass` `warn` `fail` | Proves why Tier 3 was allowed or suppressed |
| `enforcement` | str | `normal` `cap_confidence` `suppress_tier3` `block_writes` | Shows what the system did with the gate result |
| `gate_snapshot_id` | UUID/str | | Hard link to the exact 14-metric snapshot used |

### Safety context (B)

| Field | Type | Notes |
|-------|------|-------|
| `safety_check_version` | str | Ruleset hash or incrementing version for replayability |
| `safety_rules_evaluated` | array of str | Rule IDs checked — proves what was checked |
| `safety_rules_triggered` | array of {rule_id, severity} | Explains blocks, alarms, and overrides |
| `safety_result` | str | `allowed` `blocked` `alarmed` — single flag for querying |

### Execution context (C)

| Field | Type | Notes |
|-------|------|-------|
| `actor` | str | `auto_tier3` `human_tier2` `api` `system` — distinguishes autonomy from approval |
| `approval_id` | str (nullable) | Links tier2 approvals to a user action and UI record |
| `command_id` | UUID | Links set_value and read_value calls and retries |
| `tier` | str | `tier1` `tier2` `tier3` |
| `decision_type` | str | `tier2_approved` `tier2_rejected` `tier3_auto_execute` etc. |
| `write_status` | str | `success` `failed` `rejected` `skipped` |
| `write_attempt_count` | int | Retries matter for diagnosing BACnet latency |
| `failure_reason` | str (nullable) | When write_status is failed |

### Target identity (D)

| Field | Type | Notes |
|-------|------|-------|
| `point_name` | str | **Canonical** control point name |
| `control_point` | str | **Deprecated alias** for point_name (backward compat) |

### Values

| Field | Type | Notes |
|-------|------|-------|
| `original_value` | JSON-typed | Pre-write reading. Must be JSON-serializable, never a string dump of a coroutine |
| `target_value` | JSON-typed | Proposed value |
| `actual_value` | JSON-typed | Post-write read-back |

### COV verification

| Field | Type | Notes |
|-------|------|-------|
| `cov_verified` | bool | Read-back matched expected? |
| `cov_tolerance` | float or dict | COV pass means nothing without tolerance context |
| `cov_latency_ms` | int | Needed to tune per-equipment timeouts |

### Timing

| Field | Type | Notes |
|-------|------|-------|
| `device_response_latency_ms` | int | Separates BMS slow response from service issues |
| `confidence_score` | float (nullable) | Required when a model produced a score; null with reason if missing |
| `created_at` | ISO str | auto |
| `updated_at` | ISO str | auto |

### Outcome and learning (E)

| Field | Type | Notes |
|-------|------|-------|
| `outcome` | dict | Measured outcome payload |
| `outcome_matched_prediction` | bool | Did outcome match? |
| `outcome_measured_at` | ISO str | |
| `predicted_impact` | dict | `{energy_kwh, comfort_delta, runtime_delta, cost}` — lets you measure "within 20%" |
| `measured_impact` | dict | Same keys as predicted_impact |

### Rollback

| Field | Type | Notes |
|-------|------|-------|
| `rolled_back` | bool | default false |
| `rollback_reason` | str | |
| `rollback_at` | ISO str | |

### Classification

| Field | Type | Notes |
|-------|------|-------|
| `contributing_factors` | dict | Structured approval info, threshold details |
| `decision_details` | dict | Action type, reasoning |
| `rejection_category` | str | `safety_block` `gate_block` `confidence_cap` `rate_limited` `user_rejected` `validation_error` — stable label for analytics |

### Serialization guard

All records are validated before persistence. The repository rejects:
- Coroutine objects
- AsyncMock / MagicMock instances
- Any non-JSON-serializable value in `original_value`, `target_value`, `actual_value`, `cov_tolerance`

### Recommended indexes

```
(site_id, created_at)
(recommendation_id)
(correlation_id)
(equipment_code, created_at)
(device_id, point_name, created_at)
(mode, gate_status, enforcement)
(rolled_back, cov_verified)
```

---

## E. Training Readiness Thresholds

> **Source:** `app/services/data_quality_service.py`, `app/api/data_quality.py`

ML model retraining requires sufficient data quality. Thresholds are mode-aware — stricter in production, lenient in development.

### Mode-specific thresholds

| Threshold | live_control | shadow_live | simulation |
|-----------|-------------|-------------|------------|
| `min_quality` (avg score 0-1) | >= 0.85 | >= 0.75 | >= 0.50 |
| `min_days` (data history) | >= 180 | >= 120 | >= 30 |
| `min_equipment` (count per type) | >= 5 | >= 3 | >= 1 |

### Quality gate integration

Training readiness feeds into the quality gate via two metrics:
- `feedback_capture_rate_7d_pct` — percentage of recommendations with outcome labels
- `label_lag_p95_hours` — 95th percentile delay between action and outcome label

### Endpoint

```
GET /api/data-quality/training-readiness/{equipment_type}
    ?minimum_equipment=5
    &minimum_days=30
    &minimum_quality=80.0
    &mode=simulation
```

Returns: `ready` boolean, `gaps` list, `mode` used, `thresholds_used` dict.

---

## F. Cross-reference index

| Document | Content | Path |
|----------|---------|------|
| Agent Contract | Agent specs, permissions, workflows, caching, gaps | [`agent-contract.md`](agent-contract.md) |
| Write Policy & Rollout | Mode-by-mode table, rollout checklist, kill switches | [`write-policy-and-rollout.md`](write-policy-and-rollout.md) |
| Quality Gate API | Endpoint reference, enforcement mapping | [`../03-api-reference/quality-gate-api.md`](../03-api-reference/quality-gate-api.md) |
| AI Recommendation Agent Spec | Full PARASITE pipeline, 10 services, 7 APIs | [`ai-recommendation-agent-spec.md`](ai-recommendation-agent-spec.md) |
| Sentry Desk Complaint Agent Spec | Desk agent workflows, tools, complaint types | [`../05-integrations/sentry-desk-complaint-agent-spec.md`](../05-integrations/sentry-desk-complaint-agent-spec.md) |
| Audit Logging | AuditLog + DecisionEventLogger + parasite_decisions | [`../06-safety-compliance/audit-logging.md`](../06-safety-compliance/audit-logging.md) |
| Optimization API | Tier routing matrix, profile management | [`../03-api-reference/optimization.md`](../03-api-reference/optimization.md) |
| Recommendations API | Approval/rejection endpoints | [`../03-api-reference/recommendations-api.md`](../03-api-reference/recommendations-api.md) |
| MLOps API | Training readiness, outcome recording | [`../03-api-reference/mlops-api.md`](../03-api-reference/mlops-api.md) |

### Implementation files

| File | Content |
|------|---------|
| `app/models/parasite_decision.py` | ParasiteDecision dataclass, enums, serialization guard |
| `app/database/repositories/parasite_decision_repository.py` | Supabase + JSON CRUD with validation |
| `app/services/quality_gate_policy.py` | Frozen 42-entry threshold registry |
| `app/services/quality_gate_evaluator.py` | Metric collection, evaluation, enforcement |
| `app/api/optimization_quality.py` | Quality gate endpoint |
| `app/models/safety_rules.py` | 6 safety rule types |
| `app/services/safety_boundary_service.py` | Boundary approach monitoring |
| `app/services/approval_service.py` | Tier 2 approval + Tier 3 auto-execute (5 parasite_decisions calls) |
| `app/services/tier_routing_engine.py` | Confidence-based routing (1 parasite_decisions call) |
| `app/services/cov_monitor_service.py` | COV verification + outcome measurement |
| `app/services/decision_event_logger.py` | Structured pipeline event logging |

# AI Recommendation Agent (PARASITE) — Full Specification

> **Version:** 1.0 | **Last Updated:** 2026-02-22 | **Phase:** 109B

## 1. Goals & Success Metrics

**Primary Goal:** Generate, score, approve, and execute equipment control recommendations autonomously at Tier 3, with safety-first bounded autonomy.

| Metric | Target | Current |
|--------|--------|---------|
| Tier 3 auto-execute success rate | > 95% | Simulation only |
| COV verification pass rate | > 98% | N/A (no live writes yet) |
| Quality gate PASS rate (live_control) | > 90% | N/A |
| Recommendation rejection learning rate | Reduce repeated rejections by 50% | N/A |
| Outcome accuracy (predicted vs actual impact) | Within 20% | N/A |
| Auto-rollback rate | < 5% | N/A |

---

## 2. Agent Card

| Field | Value |
|-------|-------|
| **Name** | PARASITE (Proactive Autonomous Recommendation Agent for Site Intelligence Tier3 Execution) |
| **Location** | `backend/app/services/` (distributed across ~15 service files) |
| **Platform** | FastAPI backend, REST API |
| **Runtime** | Python 3, async (uvicorn) |
| **Framework** | Pipeline architecture (scorer -> grouper -> quality gate -> tier router -> approval) |
| **Entry Points** | `recommendation_service.py`, `approval_service.py`, `tier_routing_engine.py` |
| **Key Files** | `quality_gate_policy.py`, `quality_gate_evaluator.py`, `autonomous_decision_engine.py`, `safety_boundary_service.py`, `cov_monitor_service.py`, `health_rating_calculator.py` |
| **Modes** | `simulation` / `shadow_live` / `live_control` |
| **Auth** | FastAPI middleware (JWT + demo mode bypass) |

---

## 3. Pipeline Architecture

### High-Level Flow

```
AI Optimizer
    |
Recommendation Service (create)
    |
Recommendation Scorer (multi-objective)
    |
Recommendation Grouping (cross-system bundling)
    |
Quality Gate Evaluator (Phase 109)
    |
Tier Routing Engine (confidence-based)
    |
Approval Service or Auto-Execute Path
    |
Device Manager (Niagara BMS write)
    |
COV Monitor (verification)
    |
ML Feedback Loop (outcome tracking)
```

### Recommendation Status Lifecycle

```
PENDING -> APPROVED -> EXECUTED -> (outcome measured)
PENDING -> REJECTED
PENDING -> AUTO_EXECUTED -> (COV verified) -> (outcome measured)
PENDING -> AUTO_EXECUTED -> (COV failed) -> ROLLED_BACK
PENDING -> EXPIRED
EXECUTED -> ROLLED_BACK (manual)
AUTO_EXECUTED -> FAILED
```

---

## 4. Core Services

### 4.1 Recommendation Service

**File:** `backend/app/services/recommendation_service.py`

Manages the complete recommendation lifecycle: creation, approval workflow, execution, and outcome tracking.

```python
class RecommendationService:
    async def create_recommendation(rec_data: Dict) -> Recommendation
    async def get_pending_recommendations(site_id: str, limit: int) -> List[Recommendation]
    async def get_history(site_id, status_filter, risk_level_filter, limit) -> List[Recommendation]
    async def approve_recommendation(rec_id, user_id, reason) -> Recommendation
    async def reject_recommendation(rec_id, user_id, reason) -> Recommendation
    async def execute_recommendation(rec_id, rec) -> Dict[str, Any]
```

**Control Tier Decision Logic:**

| Control Tier | Tier 1 (LOW/MEDIUM) | Tier 2 (HIGH/CRITICAL) |
|---|---|---|
| `monitor` | approval (display-only) | approval (display-only) |
| `human_in_loop` | approval | approval |
| `auto_execute` | auto-execute | approval |

### 4.2 Recommendation Scorer

**File:** `backend/app/services/recommendation_scorer.py`

Multi-objective scoring using profile weights.

**Formula:** `score = Sum(normalized_impact * weight)`

**Impact Normalization:**
- `comfort_impact`: -2 to +2 -> 0..1
- `cost_impact`: -100 to +100 -> 0..1
- `health_impact`: -2 to +2 -> 0..1
- `energy_impact`: -50 to +50 -> 0..1
- `maintenance_impact`: -2 to +2 -> 0..1

**Default Profile Weights:**
```python
WEIGHTS = {
    "comfort": 0.2,
    "cost": 0.2,
    "runtime": 0.2,
    "energy": 0.2,
    "maintenance": 0.2
}
```

**Module Performance Multipliers (ML feedback-adjusted):**
```python
module_multipliers = {
    "hvac": 1.0,
    "lighting": 0.95,
    "solar": 1.05,
    "energy": 0.90,
}
```

### 4.3 Recommendation Grouping

**File:** `backend/app/services/recommendation_grouping.py`

Groups related recommendations across systems for coordinated impact.

**Objectives:**
- `LOAD_REDUCTION` — Peak shaving, demand response
- `COMFORT_IMPROVEMENT` — Temperature, humidity, light
- `EFFICIENCY` — Energy optimization
- `FAULT_RECOVERY` — Equipment failure recovery
- `MAINTENANCE` — Scheduled actions

**Execution Order (safest to riskiest):** Lighting -> HVAC -> Power

### 4.4 Quality Gate Evaluator (Phase 109)

**File:** `backend/app/services/quality_gate_evaluator.py`

Evaluates 14 quality metrics against mode-specific thresholds (42 total entries).

**14 Quality Metrics:**

| Metric | Source | Direction |
|---|---|---|
| `freshness_minutes` | MonitoringService | lower_is_better |
| `ingest_error_rate_pct_1h` | MonitoringService | lower_is_better |
| `match_coverage_pct` | MonitoringService | higher_is_better |
| `manual_source_pct` | MonitoringService provenance | lower_is_better |
| `unmatched_points_pct` | MonitoringService | lower_is_better |
| `commissioning_all_gates_passed` | CommissioningService | higher_is_better |
| `truth_check_pass_rate_pct` | CommissioningService | higher_is_better |
| `consecutive_pass_days` | CommissioningService | higher_is_better |
| `mv_accuracy_7d_pct` | MVVerificationService | higher_is_better |
| `comfort_violation_rate_7d_pct` | MVVerificationService | lower_is_better |
| `rollback_rate_7d_pct` | MVVerificationService | lower_is_better |
| `feedback_capture_rate_7d_pct` | MLFeedbackService | higher_is_better |
| `label_lag_p95_hours` | MLFeedbackService | lower_is_better |
| `drift_critical_alerts_24h` | Audit log | lower_is_better |

**Mode Thresholds (examples):**

| Metric | Simulation (pass/warn) | Shadow Live (pass/warn) | Live Control (pass/warn) |
|---|---|---|---|
| `freshness_minutes` | <=1440 / <=4320 | <=120 / <=360 | <=15 / <=60 |
| `ingest_error_rate_pct_1h` | <=15 / <=25 | <=3 / <=5 | <=1 / <=2 |
| `match_coverage_pct` | >=60 / >=40 | >=90 / >=80 | >=98 / >=95 |

**Enforcement Mapping:**

| Mode | Gate Status | Enforcement |
|---|---|---|
| simulation | FAIL | CAP_CONFIDENCE (0.59) |
| shadow_live | FAIL | SUPPRESS_TIER3 |
| live_control | WARN | SUPPRESS_TIER3 |
| live_control | FAIL | BLOCK_WRITES |

### 4.5 Approval Service

**File:** `backend/app/services/approval_service.py`

Executes approved/auto-executed recommendations with safety validation, device control, and outcome tracking.

**Tier 2 Approval Flow:**
1. Fetch recommendation (must be PENDING)
2. Quality gate check (shadow_live -> blocked, FAIL -> blocked, WARN -> allowed)
3. SafetyEngine validation (defense-in-depth)
4. Extract control point & value
5. Read current device value (rollback capability)
6. Device write via device_manager
7. COV feedback verification
8. Update status to EXECUTED
9. Audit log + parasite_decisions entry
10. ML feedback recording

**Tier 3 Auto-Execute Flow (additional steps):**
- Rate limit check (parasite_max_auto_executions_per_hour)
- Auto-rollback on COV failure (if enabled)
- Schedule outcome measurement window (10 minutes)

```python
class ApprovalService:
    async def validate_approval(rec_id, approved_by) -> Tuple[bool, str]
    async def execute_approval(rec_id, approved_by, notes) -> ApprovalResult
    async def reject_approval(rec_id, rejected_by, reason) -> ApprovalResult
    async def rollback_approval(rec_id, reason, initiated_by) -> ApprovalResult
    async def auto_execute_recommendation(rec_id, routing_result) -> ApprovalResult
    async def _auto_rollback(recommendation, original_value, cov_result, decision_id) -> bool
```

### 4.6 Tier Routing Engine

**File:** `backend/app/services/tier_routing_engine.py`

Routes every recommendation to the correct autonomy tier based on confidence and safety gates.

**Routing Logic:**
1. Master switch check (parasite_enabled)
2. Extract confidence (numeric 0.0-1.0 or string mapping)
3. Get thresholds (settings + model_thresholds DB, use stricter)
4. Risk override (critical/high -> Tier 2 max)
5. Tier 3 gate (disabled if not enabled)
6. Rate limit check (auto_executions_per_hour)
7. Route based on confidence:
   - `< 0.70` -> TIER1 "advisory"
   - `0.70 - 0.84` -> TIER2 "require_approval"
   - `>= 0.85` -> TIER3 "auto_execute"

**Confidence Extraction (Fallback Chain):**
1. `confidence_score` (numeric 0.0-1.0)
2. `multi_objective_score` (from AI optimizer)
3. `confidence` string -> map: "high"=0.90, "medium"=0.75, "low"=0.50

### 4.7 Safety Boundary Service

**File:** `backend/app/services/safety_boundary_service.py`

Monitors how close values are to safety boundaries; detects approaches and breaches.

**Escalation Levels:**
- `NONE` — Within safe margin
- `WARNING` — 50%+ toward boundary
- `ALERT` — 75%+ toward boundary
- `CRITICAL` — 85%+ toward boundary
- `EMERGENCY` — 95%+, at boundary, or breached

### 4.8 COV Monitor Service

**File:** `backend/app/services/cov_monitor_service.py`

Verifies device writes via read-back (Change of Value), measures outcomes, triggers auto-rollback on failure.

**Verification Flow:**
1. Write setpoint value to device
2. Read back after configurable delay
3. Compare actual vs expected (numeric tolerance = 0.5)
4. Log verification result
5. If failed AND auto-rollback enabled -> restore original value

### 4.9 Health Rating Calculator (Phase 109B)

**File:** `backend/app/services/health_rating_calculator.py`

5-component weighted health score formula:

| Component | Weight | Source |
|---|---|---|
| Baseline Alignment | 0.35 | baseline_comparisons |
| Service Compliance | 0.20 | service records |
| Runtime / Age | 0.20 | equipment metadata |
| Fault Burden | 0.15 | alerts (30d) |
| Trend Momentum | 0.10 | health snapshots |

**Hard Rules:**
- Status NEVER computed locally (delegated to HealthThresholdService)
- NEVER writes risk probabilities (health only)
- NEVER touches predictions table

### 4.10 Health Feature Provider (Phase 109B)

**File:** `backend/app/services/health_feature_provider.py`

Extracts 7-field health payload for recommendation ranking:

```python
health_score_current: float              # 0-100
health_status_current: str               # "healthy" | "warning" | "critical"
health_trend_7d_slope: Optional[float]   # Points per day
health_trend_30d_slope: Optional[float]
health_volatility_30d: Optional[float]   # Stddev of daily scores
health_confidence: str                   # "high" | "medium" | "low"
baseline_deviation_max_24h: Optional[float]
```

---

## 5. Data Models

### Risk Classification

```python
class ActionRiskLevel(str, Enum):
    LOW = "low"        # Setpoint changes, lighting dimming
    MEDIUM = "medium"  # Equipment staging, VAV overrides
    HIGH = "high"      # Generator start, BESS dispatch, chiller bypass
    CRITICAL = "critical"  # Fire, access control, emergency
```

### Recommendation Status

```python
class RecommendationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_EXECUTED = "auto_executed"
    EXECUTED = "executed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"
    EXPIRED = "expired"
```

### TierRoutingResult

```python
@dataclass
class TierRoutingResult:
    tier: str              # "tier1", "tier2", "tier3"
    action: str            # "advisory", "require_approval", "auto_execute"
    confidence_score: float
    threshold_source: str
    tier2_threshold: float
    tier3_threshold: float
    reason: str
    equipment_type: str
    risk_level: str
    decision_id: str       # UUID for audit
    correlation_id: str
```

---

## 6. Decisions & Risk

| Decision | Criteria | Risk | Mitigation |
|----------|----------|------|------------|
| Risk classification | Equipment type + action type | Underclassified risk | Safety boundaries enforced independently |
| Tier routing | Confidence score vs thresholds | Auto-execute wrong action (Tier 3) | Quality gate + safety validation + COV + rollback |
| Quality gate enforcement | 14 metrics x 3 modes | False PASS (bad data quality) | Fail-closed defaults for uncollected metrics |
| COV verification | Read-back within tolerance | Write succeeded but wrong value | Auto-rollback if read-back mismatches |
| Auto-rollback | COV failure AND rollback enabled | Oscillation (write->rollback->write) | Rate limiting (10/hour max) |
| Module multiplier update | Execution outcome | Positive feedback loop on bad actions | Rejection patterns also tracked |

### Risk Matrix

| Risk Level | Examples | Max Tier | Approval |
|------------|----------|----------|----------|
| LOW | Setpoint +/-5C, lighting dim | Tier 3 | Auto if confidence >= 0.85 |
| MEDIUM | Equipment staging, VAV override | Tier 3 | Auto if confidence >= 0.85 |
| HIGH | Generator start, BESS dispatch | Tier 2 max | Always requires human |
| CRITICAL | Fire, access control, emergency | Tier 2 max | Always requires human |

---

## 7. API Endpoints

### Recommendations API (`backend/app/api/recommendations.py`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/recommendations/{site_id}` | Pending recommendations (Tier 2 approval queue) |
| POST | `/api/recommendations/history/{site_id}` | Historical recommendations with filters |
| POST | `/api/recommendations` | Create new recommendation |

### Approvals API (`backend/app/api/approvals.py`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/approvals/recommendations/{id}/approve` | Approve pending recommendation |
| POST | `/api/approvals/recommendations/{id}/reject` | Reject pending recommendation |
| GET | `/api/approvals/recommendations/{id}/status` | Get approval status |
| POST | `/api/approvals/recommendations/{id}/rollback` | Rollback executed approval |

### Quality Gate API (`backend/app/api/optimization_quality.py`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/optimization/quality-gate/{site_id}` | Evaluate quality gate (14 metrics) |

---

## 8. Data Sources

| Source | Type | Table/Endpoint | Data |
|--------|------|----------------|------|
| Supabase | DB | `recommendations` | Recommendation CRUD |
| Supabase | DB | `parasite_decisions` | Tier 3 audit log |
| Supabase | DB | `equipment` | Equipment metadata |
| Supabase | DB | `health_snapshots` | Health time-series |
| Supabase | DB | `ml_models` + `model_thresholds` | Per-type confidence thresholds |
| Supabase | DB | `audit_log` | System events |
| MonitoringService | Service | `get_snapshot()` | Freshness, error rate, coverage |
| CommissioningService | Service | `get_scorecard()` | Gate pass status, truth checks |
| MVVerificationService | Service | `get_accuracy()` | M&V accuracy, rollback rate |
| MLFeedbackService | Service | `get_capture_rate()` | Feedback rate, label lag |
| HealthRatingCalculator | Service | `compute_rating()` | 5-component health score |
| DeviceManager | Service | `read_value()/set_value()` | BMS device control (Niagara) |
| SafetyEngine | Service | `validate_control_change()` | Safety rules |
| JSON fallback | File | `backend/app/data/*.json` | Demo/offline data |

---

## 9. Mode System

| Mode | Data Source | Quality Gates | Tier 3 | Use Case |
|---|---|---|---|---|
| `simulation` | JSON files | Lenient (CAP on FAIL) | Enabled | Development, demos |
| `shadow_live` | Live BMS | Medium (SUPPRESS on FAIL) | Disabled | Testing without writes |
| `live_control` | Live BMS | Strict (BLOCK on FAIL) | Enabled | Production with real writes |

---

## 10. ML Feedback Loop

### Outcome Recording

```python
def record_module_outcome(
    site_id, module_type, recommendation_id,
    action_type, successful, outcome_status,
    predicted_impact, actual_impact,
    confidence_score, equipment_id, metadata
)
```

### Feedback Paths

- **Successful Execution:** Record successful=True, update module multiplier (positive)
- **Rejected Recommendation:** Record successful=False, track rejection patterns
- **Failed Execution:** Record successful=False, trigger investigation (safety signal)

---

## 11. Configuration

```python
# PARASITE Settings (backend/app/config/settings.py)
parasite_enabled: bool = True
parasite_confidence_tier2_min: float = 0.70
parasite_confidence_tier3_min: float = 0.85
parasite_tier3_enabled: bool = True
parasite_auto_rollback_enabled: bool = True
parasite_max_auto_executions_per_hour: int = 10
parasite_cov_timeout_seconds: int = 10
```

---

## 12. Open Questions / Risks

| # | Question/Risk | Impact | Status |
|---|---------------|--------|--------|
| 1 | No live BMS writes yet — all Tier 3 tested in simulation only | Critical | Graduate to shadow_live first |
| 2 | Quality gate metric collection failures — defaults to FAIL if service down | Medium | Add circuit breaker with cached last-known-good |
| 3 | COV timeout (10s) may be too short for slow BACnet devices | Medium | Make configurable per equipment type |
| 4 | Oscillation risk — Tier 3 write then rollback then write again | High | Add cooldown period per equipment after rollback |
| 5 | Module multiplier drift — positive feedback loop could amplify bad patterns | Medium | Add decay factor and periodic reset |
| 6 | Shadow-to-live transition — no formal graduation criteria defined | High | Define: X days with <Y% rollback rate |
| 7 | Health/recommendation coupling — health decline should boost recommendation urgency | Medium | Wire health feature provider into recommendation generation trigger |

---

## File Locations Summary

| Component | File |
|---|---|
| Recommendation Service | `backend/app/services/recommendation_service.py` |
| Recommendation Scorer | `backend/app/services/recommendation_scorer.py` |
| Recommendation Grouping | `backend/app/services/recommendation_grouping.py` |
| Quality Gate Policy | `backend/app/services/quality_gate_policy.py` |
| Quality Gate Evaluator | `backend/app/services/quality_gate_evaluator.py` |
| Approval Service | `backend/app/services/approval_service.py` |
| Autonomous Decision Engine | `backend/app/services/autonomous_decision_engine.py` |
| Tier Routing Engine | `backend/app/services/tier_routing_engine.py` |
| Safety Boundary Service | `backend/app/services/safety_boundary_service.py` |
| COV Monitor Service | `backend/app/services/cov_monitor_service.py` |
| Health Rating Calculator | `backend/app/services/health_rating_calculator.py` |
| Health Feature Provider | `backend/app/services/health_feature_provider.py` |
| Recommendation Model | `backend/app/models/recommendation.py` |
| Recommendations API | `backend/app/api/recommendations.py` |
| Approvals API | `backend/app/api/approvals.py` |
| Quality Gate API | `backend/app/api/optimization_quality.py` |
| Settings | `backend/app/config/settings.py` |

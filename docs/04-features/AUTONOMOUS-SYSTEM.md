---
title: "Bounded Autonomy System - Complete Documentation"
type: "spec"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# Bounded Autonomy System - Complete Documentation

## Overview

The SENTINEL BMS Bounded Autonomy System (Phase 9) provides limited autonomous control of building equipment within strict safety boundaries, complete with multi-level escalation paths, real-time monitoring, and emergency override capabilities.

**Key Principle:** Autonomy with safety, not autonomy at any cost. Every autonomous action is validated by the safety engine before execution, and boundaries are enforced at 100% with automatic intervention.

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Application                          │
└────────────────────────┬────────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
┌──────────────────┐ ┌──────────────┐ ┌──────────────────┐
│   Autonomous     │ │ Escalation   │ │ Safety Boundary  │
│ Decision Engine  │ │   Engine     │ │    Service       │
└─────────┬────────┘ └──────┬───────┘ └────────┬─────────┘
          │                 │                  │
          └─────────────────┼──────────────────┘
                            ▼
                  ┌──────────────────────┐
                  │ Safety Engine        │
                  │ (Phase 6)            │
                  └──────────┬───────────┘
                             ▼
                  ┌──────────────────────┐
                  │ Device Manager       │
                  │ (Phase 6)            │
                  └──────────┬───────────┘
                             ▼
                  ┌──────────────────────┐
                  │ Audit Logger         │
                  │ (Phase 7)            │
                  └──────────────────────┘
```

### Core Services

#### AutonomousDecisionEngine (`backend/app/services/autonomous_decision_engine.py`)

**Purpose:** Evaluates and executes autonomous decisions within safety boundaries.

**Key Responsibilities:**
- Rule evaluation: Check if rule conditions are met
- Safety validation: Consult SafetyEngine before any action
- Decision execution: Write to devices via DeviceManager
- History persistence: Store all decisions for audit trail
- Performance tracking: Monitor decision execution metrics

**Main Methods:**
```python
async def evaluate_and_execute(
    rule_id: str,
    device_id: str,
    point_name: str,
    target_value: float,
    decision_rationale: str
) -> AutonomousDecision
```

**Decision Lifecycle:**
1. PENDING → Evaluation starts
2. PENDING → BLOCKED (safety check failed)
3. PENDING → FAILED (device communication error)
4. PENDING → SUCCESS (device accepted change)
5. PENDING → CANCELLED (operator override)

#### EscalationEngine (`backend/app/services/escalation_engine.py`)

**Purpose:** Manages multi-level escalation when equipment approaches safety boundaries.

**Escalation Levels:**

| Level | Threshold | Action | Notification | Response |
|-------|-----------|--------|--------------|----------|
| **0** | < 75% | Normal operation | None | Autonomous decisions continue |
| **1** | 75-85% | Warning | System log | Monitor situation |
| **2** | 85-95% | Alert | Email to operators | Operator assessment |
| **3** | 95-100% | Critical | Slack urgent + dashboard | Manual intervention needed |
| **4** | ≥100% | Emergency | SMS + emergency broadcast | Autonomous stop activated |

**Key Methods:**
```python
async def check_and_escalate(boundary_status: BoundaryStatus)
async def send_escalation_notification(
    level: EscalationLevel,
    device_id: str,
    message: str
)
async def acknowledge_escalation(
    escalation_id: str,
    acknowledged_by: str,
    action_taken: str
)
```

#### SafetyBoundaryService (`backend/app/services/safety_boundary_service.py`)

**Purpose:** Monitors equipment against safety boundaries and detects boundary breaches.

**Boundary Types:**

**Temperature Boundaries:**
- HVAC setpoint: 16°C (min) to 28°C (max)
- Chiller supply: 5°C (min) to 12°C (max)
- Approach escalation: 75% → Level 1, 85% → Level 2, 95% → Level 3, 100% → Level 4

**Pressure Boundaries:**
- Equipment pressure: 0 kPa (min) to 1200 kPa (max)
- Relief valve trigger: > 1200 kPa
- Approach escalation: Same as temperature

**Brightness Boundaries:**
- Illuminance: 0% (off) to 90% (max usable)
- Block > 90% to prevent over-illumination
- Approach escalation: Same thresholds

**Runtime Constraints:**
- Equipment minimum runtime: 5 minutes between starts
- Prevents compressor short-cycling
- Checked before any autonomous start command

**Key Methods:**
```python
async def get_boundary_status_summary(device) -> BoundaryStatus
def _calculate_approach_percentage(
    current_value: float,
    min_bound: float,
    max_bound: float
) -> float
async def update_boundary_config(
    device_id: str,
    point_name: str,
    new_boundaries: dict
)
```

## API Endpoints

### Autonomous System Status

```http
GET /api/autonomous/status
```

**Response:**
```json
{
  "enabled": true,
  "decision_count": 42,
  "last_decision_time": "2026-02-13T10:15:30.123456",
  "active_decisions": 3,
  "safety_score": 95.2,
  "escalation_active": false
}
```

### Enable/Disable Autonomous Mode

```http
POST /api/autonomous/enable
POST /api/autonomous/disable
```

**Response:**
```json
{
  "success": true,
  "message": "Autonomous mode enabled"
}
```

### Get Decision History

```http
GET /api/autonomous/decisions?limit=100&offset=0&device_id=hvac_001&status=success
```

**Query Parameters:**
- `limit`: Number of decisions to return (default: 100)
- `offset`: Pagination offset (default: 0)
- `device_id`: Filter by device (optional)
- `status`: Filter by status: pending, success, blocked, failed, cancelled (optional)

**Response:**
```json
{
  "data": [
    {
      "id": "dec-001",
      "device_id": "hvac_001",
      "device_name": "HVAC Unit 1",
      "point_name": "cooling_setpoint",
      "current_value": 22.0,
      "target_value": 23.5,
      "status": "success",
      "decision_rationale": "Temperature optimization for energy savings",
      "timestamp": "2026-02-13T10:15:30.123456",
      "execution_time_ms": 250,
      "safety_score": 98.5
    }
  ],
  "count": 1,
  "total": 42
}
```

### Get Boundary Status

```http
GET /api/autonomous/boundaries
GET /api/autonomous/boundaries?device_id=hvac_001
```

**Response:**
```json
{
  "data": {
    "hvac_001": {
      "device_id": "hvac_001",
      "device_name": "HVAC Unit 1",
      "overall_status": "normal",
      "approach_percentage": 62.5,
      "escalation_level": "LEVEL_0",
      "points": [
        {
          "name": "cooling_setpoint",
          "current_value": 22.0,
          "bounds": {"min": 16.0, "max": 28.0},
          "status": "normal"
        }
      ]
    }
  },
  "count": 1
}
```

### Get System Performance

```http
GET /api/autonomous/performance?days=7
```

**Response:**
```json
{
  "period_days": 7,
  "total_decisions": 284,
  "successful": 275,
  "blocked": 6,
  "failed": 2,
  "cancelled": 1,
  "success_rate": 96.83,
  "avg_execution_time_ms": 187.5,
  "safety_score": 97.4
}
```

## Configuration

### Environment Variables

```bash
# Autonomous system settings
AUTONOMOUS_ENABLED=true                    # Enable autonomous system on startup
AUTONOMOUS_DEMO_MODE=false                 # Load demo data on initialization

# Safety boundaries (temperature in °C, pressure in kPa)
HVAC_TEMP_MIN=16                          # HVAC minimum safe temperature
HVAC_TEMP_MAX=28                          # HVAC maximum safe temperature
CHILLER_TEMP_MIN=5                        # Chiller supply minimum
CHILLER_TEMP_MAX=12                       # Chiller supply maximum
EQUIPMENT_PRESSURE_MAX=1200                # Equipment maximum pressure
BRIGHTNESS_MAX=90                          # Maximum brightness %

# Escalation thresholds (as % of boundary approach)
ESCALATION_LEVEL_1_THRESHOLD=75            # Level 1: warning
ESCALATION_LEVEL_2_THRESHOLD=85            # Level 2: alert
ESCALATION_LEVEL_3_THRESHOLD=95            # Level 3: critical
ESCALATION_LEVEL_4_THRESHOLD=100           # Level 4: emergency
```

### Rule Configuration

Rules are defined in `backend/app/data/autonomous_scenarios.json` and can be customized per site.

**Rule Structure:**
```json
{
  "rule_id": "temp_optimization_001",
  "rule_name": "Temperature Optimization",
  "device_types": ["HVAC"],
  "conditions": {
    "outdoor_temperature": "> 28",
    "occupancy": "> 50%",
    "time_of_day": "08:00-17:00"
  },
  "action": {
    "device_id": "hvac_001",
    "point_name": "cooling_setpoint",
    "target_value": 24.0
  },
  "rationale": "Increase setpoint during high outdoor temperature"
}
```

## Safety Guarantees

### 1. Double-Validation Pattern

Every autonomous action is validated **twice**:
1. **At decision time:** SafetyEngine validates before device write
2. **At enforcement time:** If new anomaly appears during execution, action is blocked

```python
# Step 1: Decision evaluation
is_safe = await safety_engine.validate(decision)
if not is_safe:
    decision.status = DecisionStatus.BLOCKED
    return decision

# Step 2: Device write (only if safe)
result = await device_manager.set_value(device_id, point_name, target_value)
```

### 2. Boundary Enforcement at 100%

Boundaries are **hard limits** - not guidelines:
- Temperature ≤ 28°C: Strictly enforced, no override possible
- Pressure ≤ 1200 kPa: Strictly enforced, relief valve prevents exceeding
- Brightness ≤ 90%: Strictly enforced, prevents eye strain

**Enforcement mechanism:**
```python
if current_value > boundary_max:
    # Emergency stop
    await autonomous_decision_engine.disable_autonomous_mode()
    await escalation_engine.trigger_level_4_emergency()
    return AutonomousDecision(status=DecisionStatus.BLOCKED)
```

### 3. Always-Available Emergency Stop

Operators can stop all autonomous actions instantly:
```http
POST /api/autonomous/emergency-stop
```

**Response time:** < 1 second from request to full stop

### 4. Complete Audit Trail

Every autonomous action is logged with:
- Decision timestamp
- Device and point affected
- Original and target values
- Safety validation result
- Execution result
- Operator who approved/rejected

**Audit log storage:** Supabase `audit_log` table with permanent record

### 5. Graceful Degradation

If autonomous system fails:
- Manual device control still works via supervisor recommendations
- Safety system continues enforcing boundaries
- Equipment reverts to operator-set values
- No loss of safety

## Demo Scenarios

### Scenario 1: Temperature Optimization - Normal Operation

**Timeline:**
1. Outdoor temperature rises to 29°C
2. Autonomous engine detects optimization opportunity
3. SafetyEngine validates increase from 22°C to 23.5°C (safe)
4. Device setpoint updated
5. Cooling reduced, energy savings realized

**Escalation:** Level 0 (normal)
**Energy savings:** 8.5%
**Safety score:** 98.5/100

### Scenario 2: Lighting Optimization - Warning Level

**Timeline:**
1. Occupancy drops to 20%
2. Autonomous engine adjusts brightness from 85% to 75%
3. Approach to max brightness boundary: 83%
4. Level 1 warning triggered (system log)
5. Operator monitoring continues

**Escalation:** Level 1 (warning)
**Energy savings:** 2.1%
**Safety score:** 99.2/100

### Scenario 3: Escalation to Critical - Manual Intervention

**Timeline:**
1. Multiple failures: cooling capacity drops by 40%
2. Temperature rising: 25.2°C (approach: 78% of limit)
3. Level 1 warning (system log)
4. Continue rise: 25.8°C (approach: 85%)
5. Level 2 alert: Email sent to operators
6. Continue rise: 26.4°C (approach: 94%)
7. Level 3 critical: Slack urgent notification
8. **Operator intervention:** Increase chiller capacity
9. Temperature stabilizes
10. Escalation de-escalates back to Level 2

**Resolution time:** 8 minutes
**Prevented:** Boundary breach that would trigger emergency stop

### Scenario 4: Emergency Stop - Boundary Breach

**Timeline:**
1. Faulty pressure sensor reading: 1199 kPa (99.9% of limit)
2. Levels 1-3 escalation triggered in sequence
3. Pressure continues rising (sensor malfunction)
4. Pressure reaches 1200 kPa (100%)
5. **Level 4 emergency:** Autonomous system triggered
6. Compressor disabled immediately
7. Relief valve opens (mechanical fail-safe)
8. Pressure controlled by relief
9. System safe, manual inspection required

**Response time:** < 1 second to autonomous stop
**Outcome:** Equipment protected from damage

## Troubleshooting

### Autonomous decisions not executing

**Symptom:** Decisions show "BLOCKED" status repeatedly

**Diagnosis:**
1. Check SafetyEngine logs for validation failures
2. Verify boundary conditions allow the action
3. Check equipment health (degraded equipment may have stricter boundaries)

**Fix:**
```bash
# Verify safety engine is initialized
curl http://localhost:9095/api/autonomous/status

# Check specific boundary
curl "http://localhost:9095/api/autonomous/boundaries?device_id=hvac_001"

# Check decision rationale for blocked decisions
curl "http://localhost:9095/api/autonomous/decisions?status=blocked"
```

### Escalation not triggering

**Symptom:** Equipment approaching boundary but no escalation alert

**Diagnosis:**
1. Verify escalation engine is running (check startup logs)
2. Check if escalation was already triggered and acknowledged
3. Verify notification service configuration

**Fix:**
```bash
# Trigger manual boundary check
# Edit boundary values to force escalation
curl -X POST http://localhost:9095/api/autonomous/boundaries/update \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "hvac_001",
    "point_name": "cooling_setpoint",
    "new_boundaries": {"min_bound": 22, "max_bound": 25}
  }'
```

### Emergency stop not responding

**Symptom:** POST to /api/autonomous/emergency-stop times out

**Diagnosis:**
1. Check backend service status
2. Check device communication
3. Verify audit logger is not stuck

**Fix:**
```bash
# Force system restart
systemctl restart bms-backend

# Or use manual safety override
curl -X POST http://localhost:9095/api/safety/emergency-override
```

## Performance Targets

- **Decision evaluation:** < 200ms
- **Device write:** < 300ms
- **Escalation trigger:** < 500ms
- **Emergency stop:** < 1 second
- **Dashboard update:** < 5 seconds
- **API response time:** < 2 seconds

## Monitoring & Metrics

Key metrics to monitor via dashboard:
- **Decision success rate:** Target > 95%
- **Safety score:** Target > 90/100
- **Avg decision time:** Target < 250ms
- **Escalation frequency:** Monitor for trends
- **Emergency stop count:** Target = 0 (should rarely trigger)

## Integration with Existing Systems

### SafetyEngine Integration
- Autonomous decisions must pass SafetyEngine validation
- Boundaries inherited from safety rules
- Emergency stop coordinated with safety system

### DeviceManager Integration
- All device writes routed through DeviceManager
- Protocol abstraction handled (BACnet, Modbus, DALI, etc.)
- Error handling and retry logic included

### AuditLogger Integration
- Every decision logged with full context
- Approval/rejection tracked
- Escalation events recorded
- Emergency stops captured

### ChatAI Integration
- AI can reason about autonomous decisions
- Operators ask "Why did the system do X?"
- AI provides decision rationale from audit trail

## Future Enhancements

1. **Machine Learning Optimization:** Learn optimal setpoints from historical data
2. **Predictive Boundaries:** Dynamically adjust boundaries based on weather forecast
3. **Cross-Device Coordination:** Coordinate autonomous actions across HVAC, lighting, power
4. **Cost Optimization:** Autonomous decisions consider TOU tariffs and demand charges
5. **Occupancy Integration:** Autonomous rules adapt to real-time occupancy changes

## References

- Phase 6: Safety Interlocks & Supervised Control
- Phase 7: Audit Logging & PII Protection
- Phase 9: Bounded Autonomy System (this document)
- Autonomous Decisions API: `/docs#/autonomous`
